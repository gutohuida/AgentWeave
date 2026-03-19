"""Agent monitor endpoints."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
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

# In-memory store for manually added agents (per project)
# In production, this should be in the database
_manually_added_agents: dict[str, set[str]] = {}


def _get_session_agents(project_id: str) -> Optional[set[str]]:
    """Try to read configured agents from .agentweave/session.json.
    
    Returns None if session file doesn't exist.
    """
    # Try common locations for session.json
    possible_paths = [
        Path(".agentweave") / "session.json",
        Path("..") / ".agentweave" / "session.json",
        Path.home() / ".agentweave" / "session.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                agents = data.get("agents", {})
                if agents:
                    return set(agents.keys())
            except (json.JSONDecodeError, IOError):
                continue
    
    return None


class AddAgentRequest(BaseModel):
    agent_name: str


@router.post("/configure", status_code=status.HTTP_201_CREATED)
async def add_configured_agent(
    body: AddAgentRequest,
    project: Tuple[str, str] = Depends(get_project),
):
    """Manually add an agent to the configured list for this project."""
    project_id, _ = project
    agent_name = body.agent_name.strip().lower()
    
    if not agent_name or len(agent_name) > 32:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid agent name"
        )
    
    if project_id not in _manually_added_agents:
        _manually_added_agents[project_id] = set()
    
    _manually_added_agents[project_id].add(agent_name)
    
    await sse_manager.broadcast(
        project_id,
        "agent_configured",
        {"agent": agent_name, "action": "added"}
    )
    
    return {"success": True, "agent": agent_name}


@router.delete("/configure/{agent_name}", status_code=status.HTTP_200_OK)
async def remove_configured_agent(
    agent_name: str,
    project: Tuple[str, str] = Depends(get_project),
):
    """Remove a manually added agent from the configured list."""
    project_id, _ = project
    agent_name = agent_name.strip().lower()
    
    if project_id in _manually_added_agents:
        _manually_added_agents[project_id].discard(agent_name)
    
    await sse_manager.broadcast(
        project_id,
        "agent_configured",
        {"agent": agent_name, "action": "removed"}
    )
    
    return {"success": True, "agent": agent_name}


@router.get("/configured")
async def get_configured_agents(
    project: Tuple[str, str] = Depends(get_project),
):
    """Get the list of configured agents for this project.
    
    Returns agents from session.json if it exists, otherwise manually added agents.
    """
    project_id, _ = project
    
    # Try to get from session file first
    session_agents = _get_session_agents(project_id)
    if session_agents is not None:
        return {
            "source": "session.json",
            "agents": sorted(session_agents),
            "can_modify": False
        }
    
    # Fall back to manually added agents
    manual_agents = _manually_added_agents.get(project_id, set())
    return {
        "source": "manual",
        "agents": sorted(manual_agents),
        "can_modify": True
    }


@router.get("", response_model=List[AgentSummary])
async def list_agents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    cutoff = datetime.now(timezone.utc) - _24H

    # Active agents (last 24h) - for status/heartbeat info
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

    # ALL agents ever seen (no time cutoff) - to show configured agents
    all_senders_q = select(Message.sender).distinct().where(
        Message.project_id == project_id
    )
    all_recipients_q = select(Message.recipient).distinct().where(
        Message.project_id == project_id
    )
    all_assignees_q = select(Task.assignee).distinct().where(
        Task.project_id == project_id,
        Task.assignee.isnot(None),
    )

    senders_res, recipients_res, assignees_res, hb_agents_res, out_agents_res, \
        all_senders_res, all_recipients_res, all_assignees_res = await asyncio.gather(
        session.execute(senders_q),
        session.execute(recipients_q),
        session.execute(assignees_q),
        session.execute(heartbeat_agents_q),
        session.execute(output_agents_q),
        # All-time queries
        session.execute(all_senders_q),
        session.execute(all_recipients_q),
        session.execute(all_assignees_q),
    )

    # Active agents (for status detection)
    active_agents = set()
    for (name,) in senders_res:
        active_agents.add(name)
    for (name,) in recipients_res:
        active_agents.add(name)
    for (name,) in assignees_res:
        if name:
            active_agents.add(name)
    for (name,) in hb_agents_res:
        active_agents.add(name)
    for (name,) in out_agents_res:
        active_agents.add(name)

    # Get configured agents from session.json or manual configuration
    configured_agents = _get_session_agents(project_id)
    if configured_agents is not None:
        # Use agents from session.json
        agents = configured_agents
    else:
        # Use manually added agents, or fall back to active agents only
        agents = _manually_added_agents.get(project_id, set())
        if not agents:
            # No configuration yet - only show agents that have been active
            agents = active_agents.copy()
    
    # Always ensure active agents are included even if not in config
    agents.update(active_agents)

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
