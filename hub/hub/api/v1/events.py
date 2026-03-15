"""GET /api/v1/events — SSE stream and history."""

import asyncio
from typing import AsyncGenerator, List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import EventLog
from ...sse import sse_manager

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


@router.get("")
async def event_stream(
    request: Request,
    project: Tuple[str, str] = Depends(get_project),
):
    project_id, _ = project
    queue = sse_manager.subscribe(project_id)

    async def generator() -> AsyncGenerator[str, None]:
        try:
            yield "data: connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield message
                except asyncio.TimeoutError:
                    # Send keepalive comment
                    yield ": keepalive\n\n"
        finally:
            sse_manager.unsubscribe(project_id, queue)

    return EventSourceResponse(generator())
