"""Operator endpoints for checkpoints.

Minimal visibility ships with the record (design.md): a checkpoint the operator cannot see
rebuilds the exact defect this capability removes — a signal that looks like it works because
nothing inspects it. Browsing chains, diffing predecessor against successor and reviewing probe
verdicts are a later change, and cheaper for waiting.
"""

import asyncio
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...checkpoint_cutover import CutoverRefusedError, cut_over, handover_of
from ...checkpoint_generation import generate_checkpoint, render_checkpoint
from ...checkpoint_start import StartRefusedError, start_from_checkpoint, started_from
from ...checkpoints import get_checkpoint_by_id
from ...conversations import get_conversation_by_id
from ...db.engine import get_session
from ...db.models import (
    Checkpoint,
    CheckpointNote,
    InboundQueueEntry,
    Project,
    Run,
    Runner,
    WorkerInvocation,
)
from ...runner_provider import one_shot_model
from ...schemas.common import RequestModel
from ...sse import sse_manager

router = APIRouter(tags=["checkpoints"])
_checkpoint_claims: set[tuple[str, str]] = set()
_checkpoint_claims_lock = asyncio.Lock()


class CheckpointSummary(BaseModel):
    id: str
    conversation_id: str
    agent: str
    trigger: str
    status: str
    probe_status: Optional[str] = None
    probe_findings: Optional[list] = None
    previous_checkpoint_id: Optional[str] = None
    lineage_id: str
    files_changed: Optional[list] = None
    open_questions: Optional[list] = None
    runtime_overrides: Optional[dict] = None
    citations: Optional[list] = None
    body: Optional[str] = None
    generation_error: Optional[str] = None
    cut_over_to_conversation_id: Optional[str] = None
    created_at: Optional[str] = None
    # What tells one checkpoint from another (`every-checkpoint-findable-and-readable`). NULL only
    # on a checkpoint the one-time fill has not reached yet.
    title: Optional[str] = None
    summary: Optional[str] = None
    title_made_by: Optional[str] = None
    title_reason: Optional[str] = None
    # Only when the caller asks (`include_raw`); whether there is any is `has_unreadable_answer`.
    has_unreadable_answer: bool = False
    unreadable_answer: Optional[str] = None
    # The runs the checkpoint accounts for, oldest first. Empty when it recorded none.
    covered_runs: List[dict] = []
    # The checkpoint this one's conversation was carried over from, and the conversation this
    # checkpoint was carried into -- both ways (FR-10).
    carried_from: Optional[dict] = None
    carried_into: Optional[dict] = None
    # The conversations the operator started from this checkpoint, oldest first, each with its
    # agent and when -- not the one it was carried into, which is `carried_into` (FR-7).
    started_conversations: List[dict] = []

    @classmethod
    def of(
        cls,
        row: Checkpoint,
        *,
        generation_error: Optional[str] = None,
        include_raw: bool = False,
        covered_runs: Optional[List[dict]] = None,
        carried_from: Optional[dict] = None,
        started_conversations: Optional[List[dict]] = None,
    ) -> "CheckpointSummary":
        return cls(
            started_conversations=started_conversations or [],
            title=row.title,
            summary=row.summary,
            title_made_by=row.title_made_by,
            title_reason=row.title_reason,
            has_unreadable_answer=bool(row.unreadable_answer),
            unreadable_answer=row.unreadable_answer if include_raw else None,
            covered_runs=covered_runs or [],
            carried_from=carried_from,
            carried_into=(
                {"conversation_id": row.cut_over_to_conversation_id}
                if row.cut_over_to_conversation_id
                else None
            ),
            id=row.id,
            conversation_id=row.conversation_id,
            agent=row.agent,
            trigger=row.trigger,
            status=row.status,
            probe_status=row.probe_status,
            probe_findings=row.probe_findings,
            previous_checkpoint_id=row.previous_checkpoint_id,
            lineage_id=row.lineage_id,
            files_changed=row.files_changed,
            open_questions=row.open_questions,
            runtime_overrides=row.runtime_overrides,
            citations=row.citations,
            body=row.body,
            generation_error=generation_error,
            cut_over_to_conversation_id=row.cut_over_to_conversation_id,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )


async def _conversation_or_404(session: AsyncSession, project_id: str, conversation_id: str):
    conversation = await get_conversation_by_id(session, conversation_id)
    if conversation is None or conversation.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")
    return conversation


async def _covered_runs(session: AsyncSession, rows: List[Checkpoint]) -> dict:
    """`{checkpoint id: [run, ...]}`: the runs each checkpoint accounts for, oldest first.

    A checkpoint records the first and last run it covers; the runs between them in its
    conversation are the ones it covers. One query for all the conversations, not one per row.
    A checkpoint with no recorded first run covers none.
    """
    conversation_ids = {row.conversation_id for row in rows if row.covers_from_run_id}
    runs_by_conversation: dict = {}
    if conversation_ids:
        runs = (
            (
                await session.execute(
                    select(Run)
                    .where(Run.conversation_id.in_(conversation_ids))
                    .order_by(Run.started_at, Run.id)
                )
            )
            .scalars()
            .all()
        )
        for run in runs:
            runs_by_conversation.setdefault(run.conversation_id, []).append(run)

    covered: dict = {}
    for row in rows:
        picked: List[dict] = []
        if row.covers_from_run_id:
            through = row.covers_through_run_id or row.covers_from_run_id
            inside = False
            for run in runs_by_conversation.get(row.conversation_id, []):
                if run.id == row.covers_from_run_id:
                    inside = True
                if inside:
                    picked.append(
                        {
                            "run_id": run.id,
                            "agent": run.agent,
                            "status": run.status,
                            "started_at": run.started_at.isoformat() if run.started_at else None,
                            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
                        }
                    )
                if run.id == through:
                    break
        covered[row.id] = picked
    return covered


async def _carried_from(session: AsyncSession, conversation_ids: set) -> dict:
    """`{conversation id: the checkpoint it was carried over from}` for those that were."""
    if not conversation_ids:
        return {}
    sources = (
        (
            await session.execute(
                select(Checkpoint).where(
                    Checkpoint.cut_over_to_conversation_id.in_(conversation_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    return {
        source.cut_over_to_conversation_id: {
            "checkpoint_id": source.id,
            "conversation_id": source.conversation_id,
            "title": source.title,
        }
        for source in sources
    }


async def _started_from_checkpoint(session: AsyncSession, conversation) -> Optional[dict]:
    checkpoint_id = conversation.started_from_checkpoint_id
    if not checkpoint_id:
        return None
    source = await get_checkpoint_by_id(session, checkpoint_id)
    return {
        "checkpoint_id": checkpoint_id,
        "conversation_id": source.conversation_id if source else None,
        "agent": source.agent if source else None,
        "title": source.title if source else None,
    }


async def _summaries(
    session: AsyncSession, rows: List[Checkpoint], *, include_raw: bool = False
) -> List[CheckpointSummary]:
    invocation_ids = [row.worker_invocation_id for row in rows if row.worker_invocation_id]
    errors = {}
    if invocation_ids:
        invocations = (
            (
                await session.execute(
                    select(WorkerInvocation).where(WorkerInvocation.id.in_(invocation_ids))
                )
            )
            .scalars()
            .all()
        )
        errors = {invocation.id: invocation.error for invocation in invocations}
    covered = await _covered_runs(session, rows)
    carried = await _carried_from(session, {row.conversation_id for row in rows})
    started = await started_from(session, [row.id for row in rows])
    return [
        CheckpointSummary.of(
            row,
            generation_error=errors.get(row.worker_invocation_id),
            include_raw=include_raw,
            covered_runs=covered.get(row.id),
            carried_from=carried.get(row.conversation_id),
            started_conversations=started.get(row.id),
        )
        for row in rows
    ]


@router.get("/checkpoints")
async def list_project_checkpoints(
    agent: Optional[str] = None,
    trigger: Optional[str] = None,
    conversation_id: Optional[str] = None,
    include_raw: bool = False,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Every checkpoint the project holds, newest first, across agents and conversations --
    archived and carried-over conversations included. `agent`, `trigger` and `conversation_id`
    narrow it and combine. `include_raw` adds the text of an answer that could not be read.

    Naming a conversation also answers where that conversation came from and went
    (`lineage`), which its own checkpoints cannot: a conversation carried over holds none yet.
    """
    project_id, _ = project
    query = select(Checkpoint).where(Checkpoint.project_id == project_id)
    lineage = None
    if conversation_id is not None:
        named = await _conversation_or_404(session, project_id, conversation_id)
        query = query.where(Checkpoint.conversation_id == conversation_id)
        carried_from = (await _carried_from(session, {conversation_id})).get(conversation_id)
        carried_into = await handover_of(session, conversation_id)
        lineage = {
            "conversation_id": conversation_id,
            "started_from": carried_from,
            # The checkpoint the operator started this conversation from, if they did (FR-7).
            "started_from_checkpoint": await _started_from_checkpoint(session, named),
            "carried_into": (
                {"checkpoint_id": carried_into[0], "conversation_id": carried_into[1]}
                if carried_into
                else None
            ),
        }
    if agent is not None:
        query = query.where(Checkpoint.agent == agent)
    if trigger is not None:
        query = query.where(Checkpoint.trigger == trigger)
    rows = (await session.execute(query.order_by(Checkpoint.sequence.desc()))).scalars().all()
    return {
        "checkpoints": await _summaries(session, list(rows), include_raw=include_raw),
        "lineage": lineage,
    }


@router.get("/conversations/{conversation_id}/checkpoints", response_model=List[CheckpointSummary])
async def list_checkpoints(
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Every checkpoint for a conversation, newest first."""
    project_id, _ = project
    await _conversation_or_404(session, project_id, conversation_id)
    rows = (
        (
            await session.execute(
                select(Checkpoint)
                .where(Checkpoint.conversation_id == conversation_id)
                .order_by(Checkpoint.sequence.desc())
            )
        )
        .scalars()
        .all()
    )
    return await _summaries(session, list(rows))


@router.get("/conversations/{conversation_id}/checkpoint-notes")
async def list_checkpoint_notes(
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """What agents asked the next checkpoint to carry, oldest first, and which checkpoint did
    (slice remaining-hidden-data: notes had a write route and no read route)."""
    project_id, _ = project
    await _conversation_or_404(session, project_id, conversation_id)
    rows = (
        (
            await session.execute(
                select(CheckpointNote)
                .where(
                    CheckpointNote.conversation_id == conversation_id,
                    CheckpointNote.project_id == project_id,
                )
                .order_by(CheckpointNote.created_at, CheckpointNote.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "notes": [
            {
                "id": row.id,
                "agent": row.agent,
                "run_id": row.run_id,
                "intent": row.intent,
                "suspicions": row.suspicions or [],
                "warnings": row.warnings or [],
                "consumed_by_checkpoint_id": row.consumed_by_checkpoint_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.get("/checkpoints/{checkpoint_id}/rendered")
async def get_rendered_checkpoint(
    checkpoint_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The artifact exactly as a successor receives it — envelope, body and citations."""
    project_id, _ = project
    row = await get_checkpoint_by_id(session, checkpoint_id)
    if row is None or row.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Checkpoint '{checkpoint_id}' not found")
    return {"id": row.id, "status": row.status, "rendered": render_checkpoint(row)}


@router.post(
    "/conversations/{conversation_id}/checkpoint",
    response_model=CheckpointSummary,
    status_code=status.HTTP_201_CREATED,
)
async def take_checkpoint(
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Generate a checkpoint now, on the operator's say-so.

    Blocking: generation is a real model call and the operator pressed a button expecting a
    result. Refused when no checkpoint runner is configured rather than falling back to some
    other agent's runner, which would be a bill nobody agreed to.
    """
    project_id, _ = project
    conversation = await _conversation_or_404(session, project_id, conversation_id)

    # F716: a checkpoint here could never be handed over -- `cut_over` refuses a conversation
    # already handed over (design D6) -- so it is refused before the paid model call, as the
    # automatic trigger already declines it.
    prior = await handover_of(session, conversation_id)
    if prior is not None:
        handed_by, successor = prior
        raise HTTPException(
            status_code=409,
            detail=(
                f"Conversation {conversation_id} was already handed over to {successor} "
                f"(checkpoint {handed_by}), so a checkpoint here could not be handed over again. "
                "Continue in that conversation, and take its checkpoint when it needs one."
            ),
        )

    project_row = await session.get(Project, project_id)
    runner = (
        await session.get(Runner, project_row.checkpoint_runner_id)
        if project_row and project_row.checkpoint_runner_id
        else None
    )
    if runner is None or runner.project_id != project_id:
        raise HTTPException(
            status_code=409,
            detail=(
                "No checkpoint runner is configured for this project. Choose one in project "
                "settings — the Hub will not spend another agent's runner on your behalf."
            ),
        )

    claim = (project_id, conversation_id)
    async with _checkpoint_claims_lock:
        if claim in _checkpoint_claims:
            raise HTTPException(
                status_code=409,
                detail="A checkpoint is already being written for this conversation.",
            )
        _checkpoint_claims.add(claim)
    try:
        checkpoint = await generate_checkpoint(
            session,
            conversation,
            trigger="operator",
            cli=runner.cli,
            model=one_shot_model(runner, project_row.checkpoint_model),
            runner_id=runner.id,
        )
    finally:
        async with _checkpoint_claims_lock:
            _checkpoint_claims.discard(claim)
    # The warning has been answered by doing the thing it asked about. Leaving it `due` would
    # keep offering a decision the operator has already made — and leaving it `final` would keep
    # showing a warning that cannot be dismissed, about a checkpoint that now exists. `dismissed`
    # too (F234): it means "declined this checkpoint", and there is now a checkpoint, so the next
    # crossing must be offered again rather than read as already declined. Only a checkpoint that
    # exists answers it (F817): an `unwritten` press answered nothing, and clearing the warning
    # left no trace on screen of either the offer or the failure after a reload.
    if checkpoint.status == "ready" and conversation.checkpoint_warning in (
        "due",
        "final",
        "dismissed",
    ):
        conversation.checkpoint_warning = None
        await session.commit()
    await sse_manager.broadcast(
        project_id,
        "checkpoint_ready",
        {
            "checkpoint_id": checkpoint.id,
            "conversation_id": conversation_id,
            "agent": checkpoint.agent,
            "status": checkpoint.status,
            "probe_status": checkpoint.probe_status,
        },
    )
    invocation = (
        await session.get(WorkerInvocation, checkpoint.worker_invocation_id)
        if checkpoint.worker_invocation_id
        else None
    )
    return CheckpointSummary.of(
        checkpoint,
        generation_error=invocation.error if invocation else None,
    )


@router.post("/conversations/{conversation_id}/dismiss-checkpoint-warning")
async def dismiss_checkpoint_warning(
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Wave away the warning for this conversation, for as long as there is room to keep working.

    Deliberately not re-asked at every subsequent reading: telling an operator who has already
    said "not yet" that it is still not yet is the same as not letting them say it. A successor is
    created with no warning state, so the next conversation in the line warns on its own
    threshold.

    The one exception is the final warning near the window, which this endpoint refuses to
    dismiss. That state is only reachable *because* a dismissal was already spent, so accepting a
    second one would mean the first bought silence all the way through the provider's own
    compaction — the outcome the operator was avoiding when they dismissed.
    """
    project_id, _ = project
    conversation = await _conversation_or_404(session, project_id, conversation_id)
    if conversation.checkpoint_warning == "final":
        raise HTTPException(
            status_code=409,
            detail=(
                "This conversation is close enough to the end of its context window that the "
                "provider will compact it shortly. Take the checkpoint, or keep going knowing "
                "the summary will be one nobody wrote."
            ),
        )
    if conversation.checkpoint_warning == "dismissed":
        # Already waved away: saying so again changes nothing, and is not an error.
        return {"conversation_id": conversation_id, "checkpoint_warning": "dismissed"}
    if conversation.checkpoint_warning != "due":
        # F398/F233: `dismissed` is read as "already offered and declined", so writing it over a
        # conversation that was never warned silenced its first warning for good — and nothing
        # anywhere shows that a conversation is in that state.
        raise HTTPException(
            status_code=409,
            detail=(
                "This conversation has no checkpoint warning to dismiss: it has not reached its "
                "threshold. A dismissal answers a warning that is showing; it cannot be given in "
                "advance."
            ),
        )
    conversation.checkpoint_warning = "dismissed"
    await session.commit()
    await sse_manager.broadcast(
        project_id,
        "checkpoint_warning_dismissed",
        {"conversation_id": conversation_id, "agent": conversation.agent},
    )
    return {"conversation_id": conversation_id, "checkpoint_warning": "dismissed"}


async def _given_up_reason(session: AsyncSession, entry_ids: List[str]) -> str:
    """What to say about a conversation whose queued input the pass took out of the queue.

    Read fresh: the scheduler wrote those rows in its own session, so this session's copies are
    the ones from before the pass. The refusal that gave the input up is quoted, since it is the
    reason the operator needs — it used to be only in the timeline, one row above an answer that
    said nothing had been queued.
    """
    entries = (
        (
            await session.execute(
                select(InboundQueueEntry)
                .where(InboundQueueEntry.id.in_(entry_ids))
                .order_by(InboundQueueEntry.sequence)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    reasons = [entry.abandoned_reason for entry in entries if entry.abandoned_reason]
    if reasons:
        # The screen appends its own full stop (`AgentOutputPanel`), so the quote ends without one.
        return f"this conversation's input was given up: {reasons[-1].rstrip().rstrip('.')}"
    return "this conversation's input was taken out of the queue before it could start"


@router.post("/conversations/{conversation_id}/continue")
async def continue_conversation(
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Start a turn from what is already queued, without inventing a message to carry it.

    A successor is handed its checkpoint as a queue entry, so it has everything it needs and
    nothing to say. Requiring the operator to type something to get it moving made the handover a
    dead end — this is the same act, named for what it does.

    **`started` is about the conversation this request names, not about the agent** (F131). The
    turn is the agent's: `schedule_agent` builds it from the oldest eligible entry across the
    agent's whole queue, so the conversation that starts is frequently not the one addressed here.
    `started` used to be `result.waiting_reason is None`, which answers "did a turn begin for this
    agent" — indistinguishable from success to a caller watching one conversation, where no run,
    no output and no error will ever appear. It is now the comparison `POST /agent/trigger`
    already makes (`agent_trigger.py:1353`) for the refusal direction of the same rule.

    The conversation that did start is reported separately as `started_conversation_id`, so a
    caller answered as waiting can act on it rather than only retry.
    """
    project_id, _ = project
    conversation = await _conversation_or_404(session, project_id, conversation_id)

    from ...inbound_queue import queued_entries
    from ...turn_scheduler import schedule_agent

    # Asked before the pass as well as after it (F333): the pass can give this conversation's
    # input up — withdrawn at its attempt limit — and then start another conversation. Read only
    # afterwards, that input looked like it had never been there.
    queued_before = [
        entry.id
        for entry in await queued_entries(session, project_id, conversation.agent, conversation_id)
    ]
    # The release is written down before the pass (`a-held-successor-waits-for-continue`, D3): a
    # press that meets a running agent is then delivered by that run's end, not lost.
    if queued_before:
        await session.execute(
            update(InboundQueueEntry)
            .where(
                InboundQueueEntry.id.in_(queued_before),
                InboundQueueEntry.awaits_continue.is_(True),
            )
            .values(awaits_continue=False)
            .execution_options(synchronize_session=False)
        )
        await session.commit()
    result = await schedule_agent(project_id, conversation.agent)
    started_conversation_id = (
        result.response.conversation_id if result.response is not None else None
    )
    started = started_conversation_id == conversation_id
    waiting_reason = result.waiting_reason
    if started_conversation_id is not None and not started:
        # A turn began, in another conversation, so the scheduler has no `waiting_reason` to
        # offer — it did not wait. Which reason is right depends on whether this conversation
        # submitted anything: telling a caller with nothing queued that their input is "waiting
        # behind other input" reports a queue position that does not exist, and directs them to
        # wait for a delivery that will never arrive. Both are worded to be distinguishable from
        # the scheduler's own "queue is empty", which is about the *agent*.
        #
        # Neither names the conversation that ran: `started_conversation_id` carries that, and
        # saying it twice would leave the interface choosing which copy to render. This is the
        # first caller to pass `queued_entries`' `conversation_id` parameter — the scheduler
        # deliberately does not, because scoping *selection* to the addressed conversation would
        # let a later-arriving entry overtake an earlier one. Asking here is a question about the
        # answer, not about which turn runs.
        waiting = await queued_entries(session, project_id, conversation.agent, conversation_id)
        if waiting:
            waiting_reason = "this conversation's input is waiting behind other input"
        elif queued_before:
            waiting_reason = await _given_up_reason(session, queued_before)
        else:
            waiting_reason = "this conversation had nothing queued"
    return {
        "agent": conversation.agent,
        "conversation_id": conversation_id,
        "started": started,
        "started_conversation_id": started_conversation_id,
        "waiting_reason": waiting_reason,
    }


@router.post("/checkpoints/{checkpoint_id}/cutover")
async def cutover_to_successor(
    checkpoint_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Open the successor, hand it this checkpoint, and archive the predecessor."""
    project_id, _ = project
    checkpoint = await get_checkpoint_by_id(session, checkpoint_id)
    if checkpoint is None or checkpoint.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Checkpoint '{checkpoint_id}' not found")

    conversation = await _conversation_or_404(session, project_id, checkpoint.conversation_id)
    project_row = await session.get(Project, project_id)
    try:
        successor, entry_id = await cut_over(
            session,
            conversation,
            checkpoint,
            auto_continue=bool(project_row and project_row.checkpoint_auto_continue),
        )
    except CutoverRefusedError as exc:
        # 409, not 400: the request is well-formed and the refusal is about state the operator
        # can change — finish the run, or let the queue drain.
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    payload = {
        "checkpoint_id": checkpoint.id,
        "conversation_id": conversation.id,
        "successor_conversation_id": successor.id,
        "queue_entry_id": entry_id,
        "agent": successor.agent,
    }
    await sse_manager.broadcast(project_id, "conversation_cut_over", payload)
    return payload


class StartFromCheckpointRequest(RequestModel):
    agent: str
    message: Optional[str] = None


@router.post("/checkpoints/{checkpoint_id}/start", status_code=status.HTTP_201_CREATED)
async def start_conversation_from_checkpoint(
    checkpoint_id: str,
    body: StartFromCheckpointRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Start a new conversation of `agent` whose first input is this checkpoint, and its turn.

    Any written checkpoint, any number of times, for any open agent of the project; the
    conversation the checkpoint came from, and its carry-over, are left as they were
    (`start-a-conversation-from-any-checkpoint-with-any-agent`). The turn is scheduled now,
    whatever `checkpoint_auto_continue` says: the operator's confirm is the Continue (FR-5).

    `started` says whether the turn began in the new conversation; when the agent is busy the
    input stays queued and `waiting_reason` says why, as `continue` answers.
    """
    project_id, _ = project
    checkpoint = await get_checkpoint_by_id(session, checkpoint_id)
    if checkpoint is None or checkpoint.project_id != project_id:
        raise HTTPException(
            status_code=404, detail=f"Checkpoint '{checkpoint_id}' not found in this project"
        )
    try:
        conversation, entry_id = await start_from_checkpoint(
            session, checkpoint, agent=body.agent, message=body.message
        )
    except StartRefusedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    conversation_id, agent = conversation.id, conversation.agent
    await sse_manager.broadcast(
        project_id,
        "conversation_updated",
        {
            "project_id": project_id,
            "agent": agent,
            "conversation_id": conversation_id,
            "lifecycle": conversation.lifecycle,
            "title": conversation.title,
        },
    )

    from ...turn_scheduler import schedule_agent

    result = await schedule_agent(project_id, agent)
    started_conversation_id = (
        result.response.conversation_id if result.response is not None else None
    )
    started = started_conversation_id == conversation_id
    waiting_reason = result.waiting_reason
    if started_conversation_id is not None and not started:
        waiting_reason = "this conversation's input is waiting behind other input"
    payload = {
        "checkpoint_id": checkpoint_id,
        "conversation_id": conversation_id,
        "agent": agent,
        "title": conversation.title,
        "queue_entry_id": entry_id,
        "started": started,
        "waiting_reason": waiting_reason,
    }
    await sse_manager.broadcast(project_id, "conversation_started_from_checkpoint", payload)
    return payload
