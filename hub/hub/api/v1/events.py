"""Project-scoped SSE stream, ticket, and history endpoints."""

from datetime import datetime, timezone
from typing import AsyncGenerator, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ...auth import (
    _make_operator_ticket,
    _make_ticket,
    get_operator,
    get_operator_for_sse,
    get_project,
    get_project_for_sse,
)
from ...db.engine import get_session
from ...db.models import EventLog, OperatorCredential
from ...sse import make_connected_event, sse_manager

router = APIRouter(prefix="/events", tags=["events"])

# One instance-level operator stream, mounted directly on the API root rather
# than under /projects/{project_id} — see "instance_events_router" in
# api/v1/__init__.py. Kept in this module (not a new file) since it shares
# make_connected_event()/EventSourceResponse wiring with the project stream.
instance_router = APIRouter(prefix="/events", tags=["events"])


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
    first with their operator credential, then connect to the explicit project event URL.
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


@instance_router.get("/ticket")
async def get_operator_event_ticket(operator: OperatorCredential = Depends(get_operator)):
    """Issue a short-lived signed ticket for the one instance-level operator stream.

    Unlike `/projects/{project_id}/events/ticket`, this ticket is scoped to the
    operator, not to any single project — it unlocks `/api/v1/events`, which
    carries every project's events with a server-stamped `project_id`.
    """
    del operator
    token, expires = _make_operator_ticket()
    return {
        "token": token,
        "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
    }


@instance_router.get("")
async def operator_event_stream(
    request: Request,
    operator: OperatorCredential = Depends(get_operator_for_sse),
):
    """The one instance-level operator Server-Sent Events stream.

    Carries every project's broadcasts, each envelope stamped with that
    project's `project_id` by `SSEManager.broadcast` — so the operator sees
    events for projects it has no other open connection to (an inactive
    project changing in the rail, a project being created), not only the
    project currently open in a project-scoped stream.
    """
    del operator
    queue = sse_manager.subscribe_operator()

    async def generator() -> AsyncGenerator:
        try:
            yield make_connected_event()
            while True:
                if await request.is_disconnected():
                    break
                message = await queue.get()
                yield message
        finally:
            sse_manager.unsubscribe_operator(queue)

    return EventSourceResponse(generator(), ping=15)
