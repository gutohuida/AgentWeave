"""Inbound queue inspection, configuration, and withdrawal endpoints."""

from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import InboundQueueEntry, Project
from ...inbound_queue import DELIVERY_ATTEMPT_LIMIT, release_entry, withdraw_entry
from ...launchability import get_agent_config, probe_agent
from ...sse import sse_manager
from ...usage_accounting import project_budget_state
from ...utils import persist_event

router = APIRouter(prefix="/queue", tags=["inbound-queue"])


class QueueEntryResponse(BaseModel):
    id: str
    agent: str
    origin_type: str
    origin_agent: Optional[str]
    content: str
    arrived_at: datetime
    hop_depth: int
    state: str
    delivered_in_run_id: Optional[str]
    # Which conversation the entry is addressed to. Already stored; exposed so a surface can tell
    # "this conversation has work waiting" from "this agent does" — a checkpoint handed to a
    # successor is the first case, and only that conversation should offer to start it.
    conversation_id: Optional[str] = None
    #: How many deliveries of this entry have failed. Exposed so a queue that is not moving can be
    #: told from one that is merely waiting — before this they looked identical.
    delivery_attempts: int = 0
    #: Set when the Hub stopped trying. Present with `state == "withdrawn"`, which an operator
    #: withdrawal also produces — the reason is what distinguishes the two.
    abandoned_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class QueueSettings(BaseModel):
    hop_budget: int = Field(ge=1)
    turn_delivery_cap: int = Field(ge=1)
    agent_budget: int = Field(default=8, ge=1)
    allow_agent_jobs: bool = False


class QueueStatus(BaseModel):
    agent: str
    waiting_count: int
    running: bool
    waiting_reason: Optional[str]
    #: The worst failure count among the entries still waiting.
    delivery_attempts: int = 0


@router.get("/settings", response_model=QueueSettings)
async def get_queue_settings(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> QueueSettings:
    project_id, _ = project
    row = await session.get(Project, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return QueueSettings(
        hop_budget=row.hop_budget,
        turn_delivery_cap=row.turn_delivery_cap,
        agent_budget=row.agent_budget,
        allow_agent_jobs=row.allow_agent_jobs,
    )


@router.patch("/settings", response_model=QueueSettings)
async def update_queue_settings(
    body: QueueSettings,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> QueueSettings:
    project_id, _ = project
    row = await session.get(Project, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    row.hop_budget = body.hop_budget
    row.turn_delivery_cap = body.turn_delivery_cap
    row.agent_budget = body.agent_budget
    row.allow_agent_jobs = body.allow_agent_jobs
    await session.commit()
    queued_agents = await session.execute(
        select(InboundQueueEntry.agent)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.state == "queued",
        )
        .distinct()
    )
    from ...turn_scheduler import schedule_agent

    for agent in queued_agents.scalars().all():
        await schedule_agent(project_id, agent)
    return body


@router.get("/{agent}/status", response_model=QueueStatus)
async def get_queue_status(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> QueueStatus:
    from ...db.models import Run

    project_id, _ = project
    entries_result = await session.execute(
        select(InboundQueueEntry).where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.state == "queued",
        )
    )
    entries = list(entries_result.scalars().all())
    running = (
        await session.execute(
            select(func.count(Run.id)).where(
                Run.project_id == project_id, Run.agent == agent, Run.status == "running"
            )
        )
    ).scalar_one() > 0
    reason = None
    if entries and running:
        reason = "agent is already running"
    elif entries:
        project_row = await session.get(Project, project_id)
        if project_row and all(entry.hop_depth > project_row.hop_budget for entry in entries):
            reason = "hop budget exhausted"
        elif (
            all(entry.origin_type != "operator" for entry in entries)
            and (await project_budget_state(session, project_id))["exhausted"]
        ):
            reason = "token budget exhausted"
        else:
            config = await get_agent_config(project_id, agent, session)
            # The bound Runner record is the sole source of which CLI to launch, exactly as
            # in `agent_trigger` and the agent roster. Probing without it fell through to
            # `RUNNER_CLI["native"] is None`, whose fallback is the **agent's own name** —
            # so an agent called `codex-spec` bound to the `codex` runner was reported as
            # "Runner CLI 'codex-spec' was not found in PATH". The agent was launchable; the
            # status said otherwise, and the message masked the real reason a turn had not
            # started.
            probe = probe_agent(agent, config)
            if not probe["runnable"]:
                reason = probe["reason"] or "agent is not launchable"
            else:
                # Launchable is not the same as startable: a turn can be refused inside the
                # trigger, where the reason was raised and then discarded, leaving the operator
                # with "1 waiting" and no explanation to reason from. Anything checked here is
                # read-only; provisioning stays the trigger's to do.
                #
                # A project that is not a git repository used to be reported here. It no longer
                # blocks anything — a writing agent runs in the project directory instead — so
                # naming it would describe a state that stops nothing.
                from ... import project_workspace

                try:
                    await project_workspace.resolve_project_workspace(session, project_id)
                except project_workspace.ProjectWorkspaceError as exc:
                    reason = f"project workspace is unavailable: {exc}"
    attempts = max((entry.delivery_attempts or 0 for entry in entries), default=0)
    if reason is None and attempts:
        # Last, deliberately. Every reason above explains the wait better than a retry count does —
        # a missing CLI is the answer, and "delivery failed twice" would merely describe the
        # symptom. This fires only when nothing else did, which is exactly the case that used to
        # show "1 waiting" and no explanation at all.
        left = max(DELIVERY_ATTEMPT_LIMIT - attempts, 0)
        reason = (
            f"delivery failed {attempts} time{'s' if attempts != 1 else ''}; "
            f"{left} attempt{'s' if left != 1 else ''} left"
        )
    return QueueStatus(
        agent=agent,
        waiting_count=len(entries),
        running=running,
        waiting_reason=reason,
        delivery_attempts=attempts,
    )


@router.get("/{agent}", response_model=List[QueueEntryResponse])
async def list_queue_entries(
    agent: str,
    state_filter: Optional[str] = Query(default=None, alias="state"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> List[InboundQueueEntry]:
    project_id, _ = project
    query = select(InboundQueueEntry).where(
        InboundQueueEntry.project_id == project_id, InboundQueueEntry.agent == agent
    )
    if state_filter is not None:
        if state_filter not in ("queued", "delivered", "withdrawn"):
            raise HTTPException(status_code=400, detail="Invalid queue entry state")
        query = query.where(InboundQueueEntry.state == state_filter)
    result = await session.execute(query.order_by(InboundQueueEntry.sequence))
    return list(result.scalars().all())


@router.post("/entries/{entry_id}/release", response_model=QueueEntryResponse)
async def release_queue_entry(
    entry_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> InboundQueueEntry:
    """Continue a chain the hop budget is holding: re-base the entry to depth 0 and deliver it.

    A bound with no exit is a wedge (design D3). Filtering delivery by depth without this would be
    worse than the leak it replaces: the held entry would sit queued forever while the agent, told
    something by the operator, starts a fresh chain around it — so a real message from another
    agent is silently never read, and there are now two conversations about it.
    """
    project_id, _ = project
    outcome = await release_entry(session, project_id, entry_id)
    if outcome.entry is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=outcome.refusal)
    entry = outcome.entry
    payload = {
        "entry_id": entry.id,
        "agent": entry.agent,
        # The depth it was released *from* is the whole content of the record: after the re-base
        # the row itself says 0, and nothing else would show that a chain was restarted here.
        "released_from_depth": outcome.released_from_depth,
    }
    await persist_event(session, project_id, "queue_entry_released", payload, agent=entry.agent)
    await sse_manager.broadcast(project_id, "queue_entry_released", payload)

    from ...turn_scheduler import schedule_agent

    await schedule_agent(project_id, entry.agent)
    await session.refresh(entry)
    return entry


@router.delete("/entries/{entry_id}", response_model=QueueEntryResponse)
async def withdraw_queue_entry(
    entry_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> InboundQueueEntry:
    project_id, _ = project
    entry = await withdraw_entry(session, project_id, entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Queue entry is absent or has already been delivered/withdrawn",
        )
    payload = {"entry_id": entry.id, "agent": entry.agent}
    await persist_event(session, project_id, "queue_entry_withdrawn", payload, agent=entry.agent)
    await sse_manager.broadcast(project_id, "queue_entry_withdrawn", payload)
    return entry
