"""Loop endpoints — a `Loop` row's own surface, independent of its parent job.

A single-loop detail route, a project-wide list, and the archive action (design D16-D18, D20,
change `2026-08-18-a-loop-writes-its-own-queue`, tasks B2.2/B2.3/B2.6/B4.3). Both list and detail
require no conversation id — D20 is the reason this surface exists at all: a loop firing always
starts a fresh conversation (D4), so a conversation-scoped view would be empty in every
conversation the operator actually sits in. The richer drill-down UI is `B5`/`B6`.

`events` (task A4.1/A4.2) is this loop's own slice of `event_logs` — control changes, staged and
applied edits, how it stopped — filtered by the indexed `EventLog.loop_id` column added for this,
never another loop's rows.

**Known gap, not fixed here**: neither route reports whether a firing is currently in progress.
D13's live-ness helper (`JobRun.status` gaining a "running" value, plus the one shared helper both
this surface and the loop-edit path are meant to use) is not built yet — that is tasks A4.3-A4.5,
still open. Adding a proxy for it here (e.g. joining `JobRun.conversation_id` to `Run.status`)
is exactly the shape D19 already rejected once, by name. `history` below still reports each past
firing's recorded status (`fired`/`failed`) faithfully; it just cannot yet say "running".
"""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import EventLog, JobRun, Loop
from ...schemas.jobs import LoopControlUpdate, LoopDetail, LoopSummary
from ...sse import sse_manager
from ...utils import persist_event
from .jobs import _batch_loop_summaries

router = APIRouter(prefix="/loops", tags=["loops"])


def _require_operator(agent: Optional[str], run_id: Optional[str]) -> None:
    """Archiving a loop is operator-only (D18), mirroring `spec_lifecycle.py`'s own rule for
    documents (`only the operator can archive a document`, `archive_is_the_operators`).

    Belt and suspenders: `get_project` already requires an operator (`aw_live_`) credential, which
    no run token can satisfy, and no `agent_actions.py` wrapper calls this function with headers
    populated — so this branch is unreachable today. It stays explicit anyway, the same reason
    `spec_lifecycle.py` checks `actor.kind` at the function itself rather than trusting only its
    callers: a rule enforced in one place is a rule that survives exactly as long as nobody adds a
    second caller.
    """
    if agent is not None or run_id is not None:
        raise HTTPException(status_code=403, detail="only the operator can archive a loop")


async def _get_loop_detail(session: AsyncSession, project_id: str, loop_id: str) -> LoopDetail:
    loop = await session.get(Loop, loop_id)
    if loop is None or loop.project_id != project_id:
        raise HTTPException(status_code=404, detail="Loop not found")

    summaries = await _batch_loop_summaries(session, [loop.job_id])
    summary = summaries.get(loop.job_id)
    # A batch built for exactly this loop's own job always contains it — `loop` was just loaded
    # from the same table the batch queries.
    assert summary is not None

    history_result = await session.execute(
        select(JobRun)
        .where(JobRun.job_id == loop.job_id)
        .order_by(JobRun.fired_at.desc())
        .limit(10)
    )
    runs = history_result.scalars().all()

    events_result = await session.execute(
        select(EventLog)
        .where(EventLog.loop_id == loop.id)
        .order_by(EventLog.timestamp.desc())
        .limit(10)
    )
    events = events_result.scalars().all()

    return LoopDetail(
        **summary.model_dump(),
        job_id=loop.job_id,
        history=[
            {
                "id": run.id,
                "job_id": run.job_id,
                "fired_at": run.fired_at,
                "status": run.status,
                "trigger": run.trigger,
                "session_id": run.session_id,
            }
            for run in runs
        ],
        events=[
            {
                "id": event.id,
                "event_type": event.event_type,
                "agent": event.agent,
                "data": event.data,
                "timestamp": event.timestamp,
            }
            for event in events
        ],
    )


@router.get("", response_model=List[LoopSummary])
async def list_loops(
    include_archived: bool = Query(False),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> List[LoopSummary]:
    """Project-scoped list of loops (B4.3/B5.1) — label, purpose, ending state, queue counts,
    open questions, no conversation id required (D20). Archived loops are excluded by default
    (B5.4), mirroring `list_jobs`'s own `include_archived`; nothing is deleted (D16), so a caller
    that wants them can always ask."""
    project_id, _ = project
    q = select(Loop).where(Loop.project_id == project_id)
    if not include_archived:
        q = q.where(Loop.archived_at.is_(None))
    q = q.order_by(Loop.created_at)
    result = await session.execute(q)
    loops = result.scalars().all()
    if not loops:
        return []
    summaries = await _batch_loop_summaries(session, [loop.job_id for loop in loops])
    # Every row here came from `Loop` itself, so `_batch_loop_summaries` — keyed by job_id, one
    # entry per job that actually has a loop — is guaranteed to hold each one.
    return [summaries[loop.job_id] for loop in loops]


@router.get("/{loop_id}", response_model=LoopDetail)
async def get_loop(
    loop_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> LoopDetail:
    """A loop's own record: purpose, stop condition, ending state, queue counts, the claimed
    item, open questions, and firing history — regardless of whether it is archived (design D16's
    guarantee, B2.6). Not filtered by `archived_at`: fetching one specific loop by id is not a
    listing."""
    project_id, _ = project
    return await _get_loop_detail(session, project_id, loop_id)


@router.post("/{loop_id}/archive", response_model=LoopDetail)
async def archive_loop(
    loop_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
) -> LoopDetail:
    """Archive a loop (design D16-D18). Hides it from default listings; deletes nothing.

    Operator-only (B2.2) and refused while the loop is still running (B2.3) — archiving one would
    hide unattended work that is still firing, the exact governance failure loops exist to make
    impossible (D17).
    """
    _require_operator(agent_identity, run_identity)
    project_id, _ = project
    loop = await session.get(Loop, loop_id)
    if loop is None or loop.project_id != project_id:
        raise HTTPException(status_code=404, detail="Loop not found")
    if loop.ending_state is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="this loop is still running; it must stop or complete before it can be archived",
        )
    if loop.archived_at is not None:
        raise HTTPException(status_code=400, detail="loop is already archived")

    loop.archived_at = datetime.now(timezone.utc)
    await session.commit()

    await sse_manager.broadcast(project_id, "loop_archived", {"id": loop_id})
    await persist_event(session, project_id, "loop_archived", {"id": loop_id}, loop_id=loop_id)

    return await _get_loop_detail(session, project_id, loop_id)


@router.post("/{loop_id}/control", response_model=LoopDetail)
async def set_loop_control(
    loop_id: str,
    body: LoopControlUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
) -> LoopDetail:
    """Delegate this loop's control to its creator agent, or take it back to the operator
    (design D10, task A1.2/A1.3). Operator-only (A1.2's own text: "the operator can leave the
    control to the agent" — the decision to delegate is never the creator agent's to make for
    itself), mirroring `archive_loop`'s `_require_operator` above.

    `body.control == "creator"` is stored as-is (delegated). `body.control == "operator"`
    stores NULL, not the literal string — the same "never a stored copy of the default" rule
    `Loop.control`'s own comment states, so a delegation that is later taken back reads
    identically to a loop nobody ever delegated.
    """
    _require_operator(agent_identity, run_identity)
    project_id, _ = project
    loop = await session.get(Loop, loop_id)
    if loop is None or loop.project_id != project_id:
        raise HTTPException(status_code=404, detail="Loop not found")

    previous = loop.control or "operator"
    loop.control = "creator" if body.control == "creator" else None
    await session.commit()

    new_value = loop.control or "operator"
    await sse_manager.broadcast(
        project_id, "loop_control_changed", {"id": loop_id, "from": previous, "to": new_value}
    )
    await persist_event(
        session,
        project_id,
        "loop_control_changed",
        {"id": loop_id, "from": previous, "to": new_value},
        loop_id=loop_id,
    )

    return await _get_loop_detail(session, project_id, loop_id)
