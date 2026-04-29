"""GET /api/v1/logs — persistent event log endpoint.
POST /api/v1/logs — CLI→Hub log bridge."""

from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Agent, EventLog
from ...schemas.logs import EventLogResponse, LogEventCreate
from ...sse import sse_manager
from ...utils import persist_event

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
    project_id, _ = project
    q = select(EventLog).where(EventLog.project_id == project_id)
    if agent:
        q = q.where(EventLog.agent == agent)
    if event_type:
        q = q.where(EventLog.event_type == event_type)
    if severity and severity != "all":
        q = q.where(EventLog.severity == severity)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            q = q.where(EventLog.timestamp > since_dt)
        except ValueError:
            pass
    q = q.order_by(EventLog.timestamp.asc()).offset(offset).limit(limit)
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
    await persist_event(
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
            "severity": body.severity,
        },
    )
    return {"ok": True}
