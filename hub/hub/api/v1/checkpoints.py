"""Operator endpoints for checkpoints.

Minimal visibility ships with the record (design.md): a checkpoint the operator cannot see
rebuilds the exact defect this capability removes — a signal that looks like it works because
nothing inspects it. Browsing chains, diffing predecessor against successor and reviewing probe
verdicts are a later change, and cheaper for waiting.
"""

from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...checkpoint_cutover import CutoverRefusedError, cut_over
from ...checkpoint_generation import generate_checkpoint, render_checkpoint
from ...db.engine import get_session
from ...db.models import Checkpoint, Conversation, Project, Runner
from ...sse import sse_manager

router = APIRouter(tags=["checkpoints"])


class CheckpointSummary(BaseModel):
    id: str
    conversation_id: str
    agent: str
    trigger: str
    status: str
    visibility: str
    probe_status: Optional[str] = None
    probe_findings: Optional[list] = None
    previous_checkpoint_id: Optional[str] = None
    lineage_id: str
    files_changed: Optional[list] = None
    open_questions: Optional[list] = None
    runtime_overrides: Optional[dict] = None
    citations: Optional[list] = None
    body: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def of(cls, row: Checkpoint) -> "CheckpointSummary":
        return cls(
            id=row.id,
            conversation_id=row.conversation_id,
            agent=row.agent,
            trigger=row.trigger,
            status=row.status,
            visibility=row.visibility,
            probe_status=row.probe_status,
            probe_findings=row.probe_findings,
            previous_checkpoint_id=row.previous_checkpoint_id,
            lineage_id=row.lineage_id,
            files_changed=row.files_changed,
            open_questions=row.open_questions,
            runtime_overrides=row.runtime_overrides,
            citations=row.citations,
            body=row.body,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )


async def _conversation_or_404(session: AsyncSession, project_id: str, conversation_id: str):
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found")
    return conversation


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
                .order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [CheckpointSummary.of(row) for row in rows]


@router.get("/checkpoints/{checkpoint_id}/rendered")
async def get_rendered_checkpoint(
    checkpoint_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The artifact exactly as a successor receives it — envelope, body and citations."""
    project_id, _ = project
    row = await session.get(Checkpoint, checkpoint_id)
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

    checkpoint = await generate_checkpoint(
        session,
        conversation,
        trigger="operator",
        cli=runner.cli,
        model=project_row.checkpoint_model or runner.model,
        runner_id=runner.id,
    )
    # The warning has been answered by doing the thing it asked about. Leaving it `due` would
    # keep offering a decision the operator has already made — and leaving it `final` would keep
    # showing a warning that cannot be dismissed, about a checkpoint that now exists.
    if conversation.checkpoint_warning in ("due", "final"):
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
    return CheckpointSummary.of(checkpoint)


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
    conversation.checkpoint_warning = "dismissed"
    await session.commit()
    await sse_manager.broadcast(
        project_id,
        "checkpoint_warning_dismissed",
        {"conversation_id": conversation_id, "agent": conversation.agent},
    )
    return {"conversation_id": conversation_id, "checkpoint_warning": "dismissed"}


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
    """
    project_id, _ = project
    conversation = await _conversation_or_404(session, project_id, conversation_id)

    from ...turn_scheduler import schedule_agent

    result = await schedule_agent(project_id, conversation.agent)
    return {
        "agent": conversation.agent,
        "conversation_id": conversation_id,
        "started": result.waiting_reason is None,
        "waiting_reason": result.waiting_reason,
    }


@router.post("/checkpoints/{checkpoint_id}/cutover")
async def cutover_to_successor(
    checkpoint_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Open the successor, hand it this checkpoint, and archive the predecessor."""
    project_id, _ = project
    checkpoint = await session.get(Checkpoint, checkpoint_id)
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
