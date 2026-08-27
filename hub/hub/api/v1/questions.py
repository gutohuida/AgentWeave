"""Question endpoints — POST/GET/GET{id}/PATCH."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace
from ...auth import get_project
from ...conversations import (
    conversation_id_for_run,
    latest_open_conversation,
    name_conversation,
    new_conversation,
)
from ...db.engine import get_session
from ...db.models import Question, Run
from ...inbound_queue import new_entry
from ...run_task_binding import release_block_for_question
from ...schemas.questions import QuestionAnswer, QuestionCreate, QuestionResponse
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/questions", tags=["questions"])


async def _asking_run_has_ended(session: AsyncSession, question: Question) -> bool:
    """Has the run that asked this question ended, leaving nobody awake to receive the answer?

    Deliberately answers False unless it *knows* the run ended. A blocking question is presumed to
    have someone waiting on it — that is what `blocking` means, and it is the behaviour measured
    live — so this only overrides that presumption on positive evidence: a recorded asking run that
    is no longer running.

    An unrecorded asker (a row predating `created_by_run_id`, or a question posted through the
    operator route rather than by a run) is left to the presumption. Guessing it had ended would
    queue an answer the waiting agent already received as its tool result, which is the duplicate
    turn this shortcut exists to avoid.
    """
    if not question.created_by_run_id:
        return False
    run = await session.get(Run, question.created_by_run_id)
    return run is not None and run.status != "running"


async def _completed_batch(session: AsyncSession, question: Question) -> Optional[List[Question]]:
    """The batch *question* belongs to, in ask order, once every one of them is resolved.

    `None` while any question in the batch is still outstanding — the operator is mid-decision, and
    delivering what they have said so far is the defect this exists to prevent
    (`2026-08-13-answers-arrive-together`, D1/D2).

    A question with no `batch_id` is a batch of one and is returned immediately. That is not a
    special case for convenience: `POST /questions` and the agent's single-question route both leave
    `batch_id` NULL, so a null id is what "asked on its own" looks like in the database, and it must
    keep behaving exactly as it did before batching existed (D7).

    Resolved means answered **or declined**. A decline is the operator handing the decision back
    (`2026-08-11-declining-a-question`, D2), not an absence — so a batch whose remainder is declined
    is finished, and the answers already given are released rather than stranded.
    """
    if not question.batch_id:
        return [question]

    # The caller has mutated `question` but not committed. Flush so this query sees the answer or
    # decline that prompted it; otherwise the batch is never complete and nothing is ever delivered.
    await session.flush()

    result = await session.execute(
        select(Question)
        .where(Question.project_id == question.project_id)
        .where(Question.batch_id == question.batch_id)
        .order_by(Question.batch_index)
    )
    rows = list(result.scalars().all())
    if any(not (row.answered or row.declined) for row in rows):
        return None
    return rows


async def _deliver_batch_if_complete(
    session: AsyncSession, question: Question, project_id: str
) -> Optional[Tuple[object, object]]:
    """Queue the batch's answers if this resolution finished it. Returns `(entry, conversation)`.

    **Called after the answer or decline is committed, deliberately.** Two operators resolving the
    last two questions at once would otherwise each look at the batch from inside their own
    uncommitted transaction, each see the other's question still outstanding, and each decline to
    deliver — leaving a complete batch that reaches nobody. Checking against committed state makes
    the concurrent failure a *duplicate* delivery rather than a lost one, and losing what the
    operator decided is much the worse of the two.

    That duplicate is the residual risk and it is not closed here: collapsing it needs a delivery
    marker the schema has nowhere to put, and the panel answers strictly one question at a time, so
    two simultaneous resolutions of the same batch are not a thing the product can currently
    produce.
    """
    batch = await _completed_batch(session, question)
    content = _batch_delivery_text(batch) if batch is not None else None
    if content is None:
        return None

    from_agent = question.from_agent
    conversation = await latest_open_conversation(session, project_id=project_id, agent=from_agent)
    if conversation is None:
        # The operator answering is what opens this thread.
        conversation = new_conversation(project_id=project_id, agent=from_agent, origin="operator")
        session.add(conversation)

    entry = new_entry(
        project_id=project_id,
        agent=from_agent,
        origin_type="operator",
        origin_agent=None,
        content=content,
        hop_depth=0,
        conversation_id=conversation.id,
    )
    # Named from the question rather than the entry's text: the entry restates the answer too, and
    # "Question: … Answer: …" is not what the thread is about. For a batch it is the *first*
    # question, not whichever one happened to complete it — the thread is about what the agent set
    # out to ask, and completion order is the operator's rather than the topic.
    name_conversation(conversation, batch[0].question)
    session.add(entry)
    await session.commit()
    return entry, conversation


def _batch_delivery_text(rows: List[Question]) -> Optional[str]:
    """What the agent reads when a batch reaches it as new input.

    `None` when the batch carries no answers at all: a decline has no content to act on beyond the
    fact itself, and that is already true of a single declined question, which queues nothing
    (D6). A turn spent saying "you asked three things and all of them were declined" tells an agent
    that nothing was decided, at the price of a whole turn.

    A batch of one keeps the exact wording it has always had, so the overwhelmingly common case does
    not change shape to accommodate the rare one.
    """
    if not any(row.answered for row in rows):
        return None
    if len(rows) == 1:
        return f"Question: {rows[0].question}\n\nAnswer: {rows[0].answer}"

    parts = [f"You asked {len(rows)} questions. The operator has now resolved all of them.", ""]
    for position, row in enumerate(rows, start=1):
        parts.append(f"{position}. {row.question}")
        if row.answered:
            parts.append(f"   Answer: {row.answer}")
        else:
            # Named rather than omitted: an agent cannot otherwise tell "the operator saw this and
            # passed" from "this was never asked", and those call for opposite behaviour (D4).
            parts.append("   Declined — the operator saw this and chose not to answer it.")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


async def ask_question_for_actor(
    body: QuestionCreate,
    *,
    project_id: str,
    from_agent: str,
    created_by_run_id: Optional[str],
    session: AsyncSession,
    batch_id: Optional[str] = None,
    batch_index: int = 0,
    batch_size: int = 1,
) -> Question:
    """Create one question row. A question asked on its own is a batch of one.

    Batched questions come through here too, one call each, so a question that arrives as part of a
    set is created by exactly the same path — same id scheme, same event, same broadcast — as one
    asked alone.
    """
    q_id = f"q-{short_id()}"
    question = Question(
        id=q_id,
        project_id=project_id,
        from_agent=from_agent,
        question=body.question,
        blocking=body.blocking,
        options=[option.model_dump() for option in (body.options or [])],
        header=body.header,
        multi_select=body.multi_select,
        created_by_run_id=created_by_run_id,
        conversation_id=await conversation_id_for_run(session, created_by_run_id),
        batch_id=batch_id,
        batch_index=batch_index,
        batch_size=batch_size,
    )
    session.add(question)
    await session.commit()
    await session.refresh(question)
    await sse_manager.broadcast(
        project_id,
        "question_asked",
        {"id": q_id, "from_agent": from_agent, "blocking": body.blocking},
    )
    await persist_event(
        session,
        project_id,
        "question_asked",
        {"id": q_id, "from_agent": from_agent, "blocking": body.blocking},
        agent=from_agent,
    )
    return question


@router.post("", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def ask_question(
    body: QuestionCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    # Converted here rather than inside the helper: `ask_question_for_actor` is shared with the
    # agent-facing path, which reads `conversation_id` off the row it returns and would break on a
    # response model that does not carry it. The route is what owes the caller `asker_waiting`.
    question = await ask_question_for_actor(
        body,
        project_id=project_id,
        from_agent=body.from_agent,
        created_by_run_id=None,
        session=session,
    )
    return await _with_asker_state_one(session, question)


@router.get("", response_model=List[QuestionResponse])
async def list_questions(
    answered: Optional[bool] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    q = select(Question).where(Question.project_id == project_id)
    if answered is not None:
        q = q.where(Question.answered == answered)
    q = q.order_by(Question.created_at).offset(offset).limit(limit)
    result = await session.execute(q)
    rows = list(result.scalars().all())
    return await _with_asker_state(session, rows)


async def _with_asker_state(session: AsyncSession, rows: List[Question]) -> List[QuestionResponse]:
    """Attach `asker_waiting` to each question, in one query rather than one per row.

    The panel re-reads this list on every SSE tick, so a per-row lookup for the asking run would be
    a query per outstanding question on every render.
    """
    run_ids = {row.created_by_run_id for row in rows if row.created_by_run_id}
    ended: set = set()
    if run_ids:
        result = await session.execute(
            select(Run.id).where(Run.id.in_(run_ids)).where(Run.status != "running")
        )
        ended = set(result.scalars().all())

    responses = []
    for row in rows:
        response = QuestionResponse.model_validate(row, from_attributes=True)
        # Unknown asker → presumed waiting (design D5). Only a run positively known to have ended
        # marks the question inert.
        response.asker_waiting = row.created_by_run_id not in ended
        responses.append(response)
    return responses


async def _with_asker_state_one(session: AsyncSession, question: Question) -> QuestionResponse:
    """The same field for a single row, for every route that returns one (F80).

    Four routes returned the ORM row directly, so Pydantic filled `asker_waiting` from its schema
    default — and that default is `True`, the answer meaning *someone is still waiting*. The field
    was not stale on those routes, it was a constant, and it was the constant that sends an operator
    to answer a question nobody is listening for.

    Built on `_asking_run_has_ended` rather than on a second copy of the rule. That leaves two
    computations of one fact in this module — this one and `_with_asker_state`'s bulk query, which
    exists because the panel re-reads a whole page on every SSE tick — and
    `test_the_list_and_the_detail_route_agree` is what stops them drifting apart.
    """
    response = QuestionResponse.model_validate(question, from_attributes=True)
    response.asker_waiting = not await _asking_run_has_ended(session, question)
    return response


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    question = await session.get(Question, question_id)
    if question is None or question.project_id != project_id:
        raise HTTPException(status_code=404, detail="Question not found")
    return await _with_asker_state_one(session, question)


@router.patch("/{question_id}", response_model=QuestionResponse)
async def answer_question(
    question_id: str,
    body: QuestionAnswer,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    question = await session.get(Question, question_id)
    if question is None or question.project_id != project_id:
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        project_workspace.raise_workspace_http_error(exc)

    from_agent = question.from_agent

    question.answer = body.answer
    question.answer_labels = list(body.labels or [])
    question.answered = True
    question.answered_at = datetime.now(timezone.utc)

    # Operator answers are typed depth-zero queue entries, not magic "user"
    # messages or inbox-poll triggers. They resume autonomous chains in the same
    # governed path as every other operator input.
    #
    # Skipped for a blocking question *whose asker is still running*: `ask_user` waits and returns
    # the answer as its own tool result, so the asking agent already has it. Queuing as well told it
    # twice and cost a whole extra turn — measured live, the agent answered, then woke again and
    # restated the same directive. A non-blocking question still needs this, and so does a blocking
    # one whose run has since ended: nothing is waiting to receive it.
    # The answer is what releases a parked task (design D3). Done before the queue decision below,
    # because whether the asker is still waiting is the same fact both need.
    released = await release_block_for_question(session, question)

    # `ask_user` only holds the tool call open while the run lives. A blocking question that
    # outlived its run — it timed out, or the run crashed — has nobody awake to receive the answer,
    # so the "already awake" shortcut below would silently drop it and the operator's answer would
    # reach no one. That is precisely the question that parked a task, so it is precisely the one
    # that must not vanish.
    asker_still_waiting = question.blocking and not await _asking_run_has_ended(session, question)

    await session.commit()
    await session.refresh(question)

    # One delivery per *batch*, not per answer. Answering the first of three used to wake the agent
    # immediately, so it began work on one decision while the operator was still making the other
    # two — the interruption that asking together exists to prevent.
    #
    # After the commit above, so a concurrent resolution cannot leave a complete batch undelivered
    # (see `_deliver_batch_if_complete`).
    entry = None
    conversation = None
    if not asker_still_waiting:
        delivered = await _deliver_batch_if_complete(session, question, project_id)
        if delivered is not None:
            entry, conversation = delivered

    await sse_manager.broadcast(
        project_id, "question_answered", {"id": question_id, "answer": body.answer}
    )
    if released is not None:
        unblocked = {
            "task_id": released.id,
            "task_title": released.title,
            "question_id": question_id,
        }
        await persist_event(session, project_id, "task_unblocked", unblocked, agent=from_agent)
        await sse_manager.broadcast(project_id, "task_unblocked", unblocked)
    # Only a queued answer has a queue event to report, or an agent to wake for it. A blocking
    # asker is already awake and holding the tool call open.
    if entry is not None:
        queue_payload = {
            "entry_id": entry.id,
            "agent": from_agent,
            "origin_type": "operator",
            "hop_depth": 0,
            "question_id": question_id,
            "conversation_id": conversation.id,
        }
        await persist_event(
            session, project_id, "queue_entry_queued", queue_payload, agent=from_agent
        )
        await sse_manager.broadcast(project_id, "queue_entry_queued", queue_payload)
    await persist_event(
        session,
        project_id,
        "question_answered",
        {"id": question_id, "answer": body.answer},
    )
    if entry is not None:
        from ...turn_scheduler import schedule_agent

        await schedule_agent(project_id, from_agent)
    return await _with_asker_state_one(session, question)


@router.post("/{question_id}/decline", response_model=QuestionResponse)
async def decline_question(
    question_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Close a question without answering it.

    The operator's escape from a question they do not intend to answer — most often one whose agent
    has already given up and asked again, which otherwise sits at the head of the queue in front of
    the question someone is actually waiting on.

    The row is kept, not deleted: that the operator was asked and chose not to answer is exactly the
    kind of thing the record exists to hold.

    A blocking asker that is still waiting learns this on its next poll and stops waiting, rather
    than spending its whole question timeout on an answer that has been decided against
    (`2026-08-11-declining-a-question`, D2). Nothing is queued *for the decline itself* — unlike an
    answer, a decline carries no content for the agent to act on beyond the fact itself.

    A decline can still **complete a batch**, and then the answers already given are delivered
    (`2026-08-13-answers-arrive-together`, D2). That is how the operator sends what they have
    decided without answering the rest, and it is what stops a part-answered batch stranding real
    answers. A batch resolved entirely by declines still delivers nothing, because there is nothing
    in it to deliver.
    """
    project_id, _ = project
    question = await session.get(Question, question_id)
    if question is None or question.project_id != project_id:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.answered:
        raise HTTPException(
            status_code=409,
            detail=(
                "This question has already been answered. Declining it would discard a decision "
                "that was already made."
            ),
        )

    # Idempotent: declining twice is the state the caller asked for, not a conflict.
    if not question.declined:
        question.declined = True
        question.declined_at = datetime.now(timezone.utc)

    # Same function the answer path uses (design D3): the operator has said no answer is coming, so
    # a task held waiting on this question is no longer waiting on anyone.
    released = await release_block_for_question(session, question)

    from_agent = question.from_agent
    asker_still_waiting = question.blocking and not await _asking_run_has_ended(session, question)

    await session.commit()
    await session.refresh(question)

    # A decline can complete a batch, and then the answers already given are delivered — how the
    # operator sends what they have decided without answering the rest. The decline itself is still
    # not content: a batch resolved entirely by declines delivers nothing.
    entry = None
    conversation = None
    if not asker_still_waiting:
        delivered = await _deliver_batch_if_complete(session, question, project_id)
        if delivered is not None:
            entry, conversation = delivered

    payload = {"id": question_id, "agent": question.from_agent}
    await persist_event(
        session, project_id, "question_declined", payload, agent=question.from_agent
    )
    await sse_manager.broadcast(project_id, "question_declined", payload)

    if released is not None:
        unblocked = {
            "task_id": released.id,
            "task_title": released.title,
            "question_id": question_id,
        }
        await persist_event(
            session, project_id, "task_unblocked", unblocked, agent=question.from_agent
        )
        await sse_manager.broadcast(project_id, "task_unblocked", unblocked)

    # A decline that completed a batch delivers the answers already given. The decline itself is
    # still not the content — what reaches the agent is the batch — so this only fires when there
    # was something to send, which `_batch_delivery_text` decided.
    if entry is not None:
        queue_payload = {
            "entry_id": entry.id,
            "agent": from_agent,
            "origin_type": "operator",
            "hop_depth": 0,
            "question_id": question_id,
            "conversation_id": conversation.id,
        }
        await persist_event(
            session, project_id, "queue_entry_queued", queue_payload, agent=from_agent
        )
        await sse_manager.broadcast(project_id, "queue_entry_queued", queue_payload)

        from ...turn_scheduler import schedule_agent

        await schedule_agent(project_id, from_agent)

    return await _with_asker_state_one(session, question)
