"""GET /api/v1/events — SSE stream and history."""

from datetime import datetime, timezone
from typing import AsyncGenerator, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ...auth import _make_ticket, get_project, get_project_for_sse
from ...db.engine import get_session
from ...db.models import EventLog
from ...sse import make_connected_event, sse_manager

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/history")
async def event_history(
    limit: int = Query(100, ge=1, le=500),
    severity: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Return recent persisted events from the EventLog table (oldest-first)."""
    project_id, _ = project
    q = select(EventLog).where(EventLog.project_id == project_id)
    if severity and severity != "all":
        q = q.where(EventLog.severity == severity)
    q = q.order_by(EventLog.timestamp.desc()).limit(limit)
    result = await session.execute(q)
    rows = result.scalars().all()
    return [
        {
            "type": r.event_type,
            "data": r.data or {},
            "timestamp": r.timestamp.isoformat(),
            "agent": r.agent,
            "severity": r.severity,
        }
        for r in reversed(rows)  # oldest first
    ]


@router.get("/ticket")
async def get_event_ticket(project: Tuple[str, str] = Depends(get_project)):
    """Issue a short-lived signed ticket for the SSE stream.

    Clients using EventSource (which cannot send custom headers) should call this
    first with their API key, then connect to /api/v1/events?token=<ticket>.
    """
    project_id, _ = project
    token, expires = _make_ticket(project_id)
    return {
        "token": token,
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
    }


@router.get("")
async def event_stream(
    request: Request,
    project: Tuple[str, str] = Depends(get_project_for_sse),
):
    """Server-Sent Events stream.

    Yields `sse_starlette.ServerSentEvent` (and subclass) objects straight
    from the SSEManager queue. EventSourceResponse serializes them to the
    standard SSE wire format (`event: <name>\\r\\ndata: <json>\\r\\n\\r\\n`).

    Keepalives are produced by `EventSourceResponse(ping=15)` (a `: ping ...`
    comment every 15s), not by a hand-rolled `yield ": keepalive\\n\\n"`.
    Hand-rolling the keepalive would force us to yield a raw string, which
    sse_starlette would re-wrap as `data: : keepalive\\n\\n` and break the
    comment semantics.
    """
    project_id, _ = project
    queue = sse_manager.subscribe(project_id)

    async def generator() -> AsyncGenerator:
        try:
            yield make_connected_event()
            while True:
                if await request.is_disconnected():
                    break
                # Block forever (no timeout) — EventSourceResponse handles
                # keepalives on its own via the `ping` parameter, so a stalled
                # stream can never silently time out the connection.
                message = await queue.get()
                yield message
        finally:
            sse_manager.unsubscribe(project_id, queue)

    return EventSourceResponse(generator(), ping=15)
