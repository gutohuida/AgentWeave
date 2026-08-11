"""Closing permission requests that nobody is waiting on any more.

A run and the Hub each hold a view of one pending decision, and only the Hub's was ever written
down. When the run stopped waiting — timeout, kill, or crash — the row stayed "pending", so the
operator kept being offered a card whose answer could no longer reach anyone, and whose approval
the Hub recorded anyway.

The run reports (`mcp_server._report_wait_ended`) and the run's end sweeps. Both, because
reporting is best-effort by design and a killed run never gets to report; see the change's
design.md, D1.
"""

from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import PermissionRequest


async def expire_pending_for_run(db: AsyncSession, run_id: Optional[str]) -> int:
    """Close every request this run left pending. Returns how many were closed.

    Caller commits — this is meant to join the transaction that sets `run.status` and
    `run.ended_at`, so a run cannot be recorded as over while its requests still read as live.

    `decided_at` is deliberately left NULL, as on the reported path: the model states that it is
    what distinguishes an answer from a timeout, so only a human answering may set it.
    """
    if not run_id:
        return 0
    result = await db.execute(
        update(PermissionRequest)
        .where(PermissionRequest.run_id == run_id, PermissionRequest.status == "pending")
        .values(status="expired")
    )
    return result.rowcount or 0
