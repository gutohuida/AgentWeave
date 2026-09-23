"""Project-scoped persistent event log endpoints."""

from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, EventLog
from ...schemas.logs import EventLogResponse, LogEventCreate
from ...sse import sse_manager
from ...utils import KNOWN_SEVERITIES, persist_event

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/agents", response_model=List[str])
async def list_log_agents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Return actual agent names known to logs or project configuration."""
    project_id, _ = project
    agent_rows = await session.execute(
        select(Agent.name).where(Agent.project_id == project_id).distinct()
    )
    log_rows = await session.execute(
        select(EventLog.agent)
        .where(EventLog.project_id == project_id, EventLog.agent.isnot(None))
        .distinct()
    )
    names = {row[0] for row in agent_rows if row[0]}
    names.update(row[0] for row in log_rows if row[0])
    names.add("system")
    return sorted(names)


def require_known_severity(severity: str) -> str:
    """*severity*, or a 400 naming the ones that exist (F257).

    The write path normalises an unknown severity to `warn`, so no row can carry one; filtering by
    one answered an empty list, which reads as "nothing of that kind happened".
    """
    if severity not in KNOWN_SEVERITIES:
        known = ", ".join(sorted(KNOWN_SEVERITIES | {"all"}))
        raise HTTPException(
            status_code=400, detail=f"Unknown severity {severity!r}; expected one of {known}"
        )
    return severity


@router.get("", response_model=List[EventLogResponse])
async def list_logs(
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    agent: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """A page of the project's log, **newest first** (F252); `offset` counts back from the newest.

    It answered oldest first, so `limit=500` with no offset was the first five hundred events the
    project ever recorded, and every later one was unreachable from the Logs screen, which
    refetched that same window on every live event. `/events/history` already reads this table
    newest first; the two routes now agree on which end an operator wants. The screen shows a page
    in time order and asks for the next page back to reach older entries.
    """
    project_id, _ = project
    q = select(EventLog).where(EventLog.project_id == project_id)
    if agent:
        q = q.where(EventLog.agent == agent)
    if event_type:
        q = q.where(EventLog.event_type == event_type)
    if severity and severity != "all":
        q = q.where(EventLog.severity == require_known_severity(severity))
    if since:
        # F255: a malformed `since` used to be dropped, and the answer read as the whole window —
        # to a poller, "everything is new".
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"since {since!r} is not an ISO 8601 timestamp; send one like "
                    "2026-09-23T10:00:00Z (a + must be sent as %2B)"
                ),
            ) from exc
        q = q.where(EventLog.timestamp > since_dt)
    q = q.order_by(EventLog.timestamp.desc(), EventLog.id.desc()).offset(offset).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("", status_code=status.HTTP_201_CREATED)
async def push_log(
    body: LogEventCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Accept a log event from the CLI and persist it to EventLog + broadcast via SSE."""
    project_id, _ = project
    normalised_severity = await persist_event(
        session,
        project_id,
        body.event_type,
        data=body.data if isinstance(body.data, dict) else {"value": body.data},
        agent=body.agent,
        severity=body.severity,
    )
    await sse_manager.broadcast(
        project_id,
        "log_event",
        {
            "event_type": body.event_type,
            "agent": body.agent,
            "data": body.data,
            "severity": normalised_severity,
        },
    )
    return {"ok": True}
