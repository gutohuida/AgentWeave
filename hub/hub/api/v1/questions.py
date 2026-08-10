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
from ...run_task_binding import release_block_for_answer
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
    return await ask_question_for_actor(
        body,
        project_id=project_id,
        from_agent=body.from_agent,
        created_by_run_id=None,
        session=session,
    )


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
    return result.scalars().all()


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
    return question


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
    q_text = question.question

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
    released = await release_block_for_answer(session, question)

    # `ask_user` only holds the tool call open while the run lives. A blocking question that
    # outlived its run — it timed out, or the run crashed — has nobody awake to receive the answer,
    # so the "already awake" shortcut below would silently drop it and the operator's answer would
    # reach no one. That is precisely the question that parked a task, so it is precisely the one
    # that must not vanish.
    asker_still_waiting = question.blocking and not await _asking_run_has_ended(session, question)

    entry = None
    conversation = None
    if not asker_still_waiting:
        conversation = await latest_open_conversation(
            session, project_id=project_id, agent=from_agent
        )
        if conversation is None:
            # The operator answering is what opens this thread.
            conversation = new_conversation(
                project_id=project_id, agent=from_agent, origin="operator"
            )
            session.add(conversation)

        entry = new_entry(
            project_id=project_id,
            agent=from_agent,
            origin_type="operator",
            origin_agent=None,
            content=f"Question: {q_text}\n\nAnswer: {body.answer}",
            hop_depth=0,
            conversation_id=conversation.id,
        )
        # Named from the question rather than the entry's text: the entry restates the answer
        # too, and "Question: … Answer: …" is not what the thread is about.
        name_conversation(conversation, q_text)
        session.add(entry)
    await session.commit()
    await session.refresh(question)

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
    return question
