"""Agent monitor endpoints."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AgentHeartbeat, AgentOutput, EventLog, Message, Task
from ...schemas.agents import (
    AgentHeartbeatCreate,
    AgentOutputCreate,
    AgentOutputResponse,
    AgentSummary,
    AgentTimelineEvent,
)
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/agents", tags=["agents"])

_24H = timedelta(hours=24)


@router.get("", response_model=List[AgentSummary])
async def list_agents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    cutoff = datetime.now(timezone.utc) - _24H

    senders_q = select(Message.sender).distinct().where(
        Message.project_id == project_id, Message.timestamp >= cutoff
    )
    recipients_q = select(Message.recipient).distinct().where(
        Message.project_id == project_id, Message.timestamp >= cutoff
    )
    assignees_q = select(Task.assignee).distinct().where(
        Task.project_id == project_id,
        Task.assignee.isnot(None),
        Task.updated >= cutoff,
    )
    heartbeat_agents_q = select(AgentHeartbeat.agent).distinct().where(
        AgentHeartbeat.project_id == project_id,
        AgentHeartbeat.timestamp >= cutoff,
    )
    output_agents_q = select(AgentOutput.agent).distinct().where(
        AgentOutput.project_id == project_id,
        AgentOutput.timestamp >= cutoff,
    )

    senders_res, recipients_res, assignees_res, hb_agents_res, out_agents_res = await asyncio.gather(
        session.execute(senders_q),
        session.execute(recipients_q),
        session.execute(assignees_q),
        session.execute(heartbeat_agents_q),
        session.execute(output_agents_q),
    )

    agents = set()
    for (name,) in senders_res:
        agents.add(name)
    for (name,) in recipients_res:
        agents.add(name)
    for (name,) in assignees_res:
        if name:
            agents.add(name)
    for (name,) in hb_agents_res:
        agents.add(name)
    for (name,) in out_agents_res:
        agents.add(name)

    summaries = []
    for agent_name in sorted(agents):
        # Latest heartbeat
        hb_q = (
            select(AgentHeartbeat)
            .where(
                AgentHeartbeat.project_id == project_id,
                AgentHeartbeat.agent == agent_name,
            )
            .order_by(AgentHeartbeat.timestamp.desc())
            .limit(1)
        )
        hb_res = await session.execute(hb_q)
        hb = hb_res.scalars().first()

        # Message count (last 24h)
        msg_q = select(Message).where(
            Message.project_id == project_id,
            Message.timestamp >= cutoff,
            (Message.sender == agent_name) | (Message.recipient == agent_name),
        )
        msg_res = await session.execute(msg_q)
        msg_count = len(msg_res.scalars().all())

        # Active task count
        task_q = select(Task).where(
            Task.project_id == project_id,
            Task.assignee == agent_name,
            Task.status.in_(["pending", "assigned", "in_progress"]),
        )
        task_res = await session.execute(task_q)
        task_count = len(task_res.scalars().all())

        summaries.append(
            AgentSummary(
                name=agent_name,
                status=hb.status if hb else "idle",
                latest_status_msg=hb.message if hb else None,
                last_seen=hb.timestamp if hb else None,
                message_count=msg_count,
                active_task_count=task_count,
            )
        )

    return summaries


@router.get("/{name}/timeline", response_model=List[AgentTimelineEvent])
async def agent_timeline(
    name: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project

    msg_q = (
        select(Message)
        .where(
            Message.project_id == project_id,
            (Message.sender == name) | (Message.recipient == name),
        )
        .order_by(Message.timestamp.desc())
        .limit(50)
    )
    log_q = (
        select(EventLog)
        .where(EventLog.project_id == project_id, EventLog.agent == name)
        .order_by(EventLog.timestamp.desc())
        .limit(50)
    )
    hb_q = (
        select(AgentHeartbeat)
        .where(AgentHeartbeat.project_id == project_id, AgentHeartbeat.agent == name)
        .order_by(AgentHeartbeat.timestamp.desc())
        .limit(20)
    )

    msg_res, log_res, hb_res = await asyncio.gather(
        session.execute(msg_q),
        session.execute(log_q),
        session.execute(hb_q),
    )

    events: List[AgentTimelineEvent] = []

    for msg in msg_res.scalars():
        events.append(
            AgentTimelineEvent(
                id=msg.id,
                event_type="message",
                timestamp=msg.timestamp,
                summary=f"{msg.sender} → {msg.recipient}: {(msg.subject or msg.content[:60])}",
                data={"from": msg.sender, "to": msg.recipient, "subject": msg.subject},
            )
        )

    for entry in log_res.scalars():
        events.append(
            AgentTimelineEvent(
                id=entry.id,
                event_type=entry.event_type,
                timestamp=entry.timestamp,
                summary=entry.event_type,
                data=entry.data or {},
            )
        )

    for hb in hb_res.scalars():
        events.append(
            AgentTimelineEvent(
                id=hb.id,
                event_type="heartbeat",
                timestamp=hb.timestamp,
                summary=f"[{hb.status}] {hb.message or ''}",
                data={"status": hb.status, "message": hb.message},
            )
        )

    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events[:50]


@router.post("/{name}/heartbeat", status_code=status.HTTP_201_CREATED)
async def post_heartbeat(
    name: str,
    body: AgentHeartbeatCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    hb = AgentHeartbeat(
        id=f"hb-{short_id()}",
        project_id=project_id,
        agent=name,
        status=body.status,
        message=body.message,
    )
    session.add(hb)
    await session.commit()
    payload = {"agent": name, "status": body.status, "message": body.message}
    await sse_manager.broadcast(project_id, "agent_heartbeat", payload)
    await persist_event(session, project_id, "agent_heartbeat", payload, agent=name)
    return {"id": hb.id, "agent": name, "status": body.status}


@router.post("/{name}/output", status_code=status.HTTP_201_CREATED)
async def post_agent_output(
    name: str,
    body: AgentOutputCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    row = AgentOutput(
        id=f"out-{short_id()}",
        project_id=project_id,
        agent=name,
        session_id=body.session_id,
        content=body.content,
    )
    session.add(row)
    await session.commit()
    await sse_manager.broadcast(
        project_id,
        "agent_output",
        {
            "agent": name,
            "session_id": body.session_id,
            "content": body.content,
            "timestamp": row.timestamp.isoformat(),
        },
    )
    return {"id": row.id}


@router.get("/{name}/output", response_model=List[AgentOutputResponse])
async def get_agent_output(
    name: str,
    limit: int = Query(200, ge=1, le=1000),
    since: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    q = select(AgentOutput).where(
        AgentOutput.project_id == project_id,
        AgentOutput.agent == name,
    )
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            q = q.where(AgentOutput.timestamp > since_dt)
        except ValueError:
            pass
    q = q.order_by(AgentOutput.timestamp.asc()).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()
