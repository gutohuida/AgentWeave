"""Loop endpoints — a `Loop` row's own surface, independent of its parent job.

Deliberately minimal today: a single-loop detail route and its archive action (design D16-D18,
change `2026-08-18-a-loop-writes-its-own-queue`, tasks B2.2/B2.3/B2.6). A project-wide index and
a richer drill-down (queue, current item, firing history, live-ness) are `B4.3`/`B5`/`B6` — this
file is the landing spot those add to, not a re-implementation of them ahead of time.
"""

from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import JobRun, Loop
from ...schemas.jobs import LoopDetail
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
    )


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
    await persist_event(session, project_id, "loop_archived", {"id": loop_id})

    return await _get_loop_detail(session, project_id, loop_id)
