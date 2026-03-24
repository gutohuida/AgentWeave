"""Agent monitor endpoints."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AgentConfig, AgentHeartbeat, AgentOutput, EventLog, Message, Project, Task
from ...schemas.agents import (
    AgentHeartbeatCreate,
    AgentOutputCreate,
    AgentOutputResponse,
    AgentSummary,
    AgentTimelineEvent,
)
from ...sse import sse_manager
from ...utils import persist_event, short_id, get_context_file_for_agent

router = APIRouter(prefix="/agents", tags=["agents"])

_24H = timedelta(hours=24)


# =============================================================================
# Session.json Helpers (Read-Only)
# =============================================================================

def _find_session_json() -> Optional[Path]:
    """Find session.json in common locations."""
    possible_paths = [
        Path(".agentweave") / "session.json",
        Path("..") / ".agentweave" / "session.json",
        Path.home() / ".agentweave" / "session.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            return path
    
    return None


def _get_session_agents_with_roles(project_id: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """Try to read configured agents with their roles from .agentweave/session.json.
    
    Returns None if session file doesn't exist.
    Returns dict of {agent_name: {role, principal, ...}} if it exists.
    """
    path = _find_session_json()
    if not path:
        return None
    
    try:
        data = json.loads(path.read_text())
        agents = data.get("agents", {})
        principal = data.get("principal")
        
        # Enhance agent data with role info
        result = {}
        for agent_name, agent_data in agents.items():
            if isinstance(agent_data, dict):
                result[agent_name] = agent_data.copy()
            else:
                result[agent_name] = {}
            
            # Add role based on principal field
            if agent_name == principal:
                result[agent_name]["role"] = "principal"
            else:
                result[agent_name]["role"] = result[agent_name].get("role", "delegate")
        
        return result
    except (json.JSONDecodeError, IOError):
        return None


def _get_session_agents(project_id: str) -> Optional[set[str]]:
    """Try to read configured agents from .agentweave/session.json.
    
    Returns None if session file doesn't exist.
    """
    agents_data = _get_session_agents_with_roles(project_id)
    if agents_data is None:
        return None
    return set(agents_data.keys())


# =============================================================================
# Agent List and Status (Read-Only from Hub DB + session.json)
# =============================================================================

@router.get("", response_model=List[AgentSummary])
async def list_agents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List all agents for this project.
    
    Combines agents from:
    - Hub database (persisted configs)
    - session.json (local CLI config)
    - Recent activity (heartbeats, messages, tasks)
    """
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

    # Get configured agents from session.json
    session_agents_data = _get_session_agents_with_roles(project_id) or {}
    session_agents = set(session_agents_data.keys())
    
    # Get agents from Hub database
    result = await session.execute(
        select(AgentConfig.agent_name).where(AgentConfig.project_id == project_id)
    )
    hub_agents = {row[0] for row in result.all()}
    
    # Combine all agent names
    agents = session_agents | hub_agents
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


# =============================================================================
# Agent Configuration Endpoints (Read-Only for Hub UI)
# CLI is the source of truth - these endpoints only display synced data
# =============================================================================

class AgentConfigResponse(BaseModel):
    """Agent configuration response."""
    agent: str
    role: str
    yolo_enabled: bool
    context_file: str
    settings: Optional[dict]
    source: str  # "hub" or "session.json"
    updated_at: Optional[datetime]


@router.get("/configs", response_model=List[AgentConfigResponse])
async def list_agent_configs(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List all agent configurations for this project.
    
    READ-ONLY: Hub displays merged config from:
    - Hub database (synced from CLI)
    - session.json (local CLI config, if accessible)
    
    To modify agents, use the CLI: agentweave agent add/set-role/set-yolo
    """
    project_id, _ = project
    
    # Get all agents from Hub database
    q = select(AgentConfig).where(AgentConfig.project_id == project_id)
    result = await session.execute(q)
    hub_configs = {c.agent_name: c for c in result.scalars().all()}
    
    # Get agents from session.json
    session_agents = _get_session_agents_with_roles(project_id) or {}
    
    # Combine all agent names
    all_agents = set(hub_configs.keys()) | set(session_agents.keys())
    
    configs = []
    for agent_name in sorted(all_agents):
        hub_config = hub_configs.get(agent_name)
        session_data = session_agents.get(agent_name, {})
        
        # Determine context file
        context_file = hub_config.context_file if hub_config else get_context_file_for_agent(agent_name)
        
        # Determine role (Hub config takes precedence, then session.json)
        role = hub_config.role if hub_config else session_data.get("role", "delegate")
        
        # Determine YOLO (Hub has it, session.json doesn't)
        yolo_enabled = hub_config.yolo_enabled if hub_config else False
        
        configs.append(AgentConfigResponse(
            agent=agent_name,
            role=role,
            yolo_enabled=yolo_enabled,
            context_file=context_file,
            settings=hub_config.settings if hub_config else None,
            source="hub" if hub_config else "session.json",
            updated_at=hub_config.updated_at if hub_config else None,
        ))
    
    return configs


@router.get("/{name}/config", response_model=AgentConfigResponse)
async def get_agent_config(
    name: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get configuration for a specific agent.
    
    READ-ONLY: Use CLI to modify: agentweave agent set-role/set-yolo
    """
    project_id, _ = project
    agent_name = name.lower()
    
    # Get from Hub database
    q = select(AgentConfig).where(
        AgentConfig.project_id == project_id,
        AgentConfig.agent_name == agent_name,
    )
    result = await session.execute(q)
    hub_config = result.scalars().first()
    
    # Check if in session.json
    session_agents = _get_session_agents_with_roles(project_id) or {}
    session_data = session_agents.get(agent_name, {})
    in_session = agent_name in session_agents
    
    # Determine context file
    context_file = hub_config.context_file if hub_config else get_context_file_for_agent(agent_name)
    
    # Determine role
    role = hub_config.role if hub_config else session_data.get("role", "delegate")
    
    # Determine YOLO
    yolo_enabled = hub_config.yolo_enabled if hub_config else False
    
    if hub_config:
        return AgentConfigResponse(
            agent=agent_name,
            role=role,
            yolo_enabled=yolo_enabled,
            context_file=context_file,
            settings=hub_config.settings,
            source="hub",
            updated_at=hub_config.updated_at,
        )
    else:
        # Return default config
        return AgentConfigResponse(
            agent=agent_name,
            role=role,
            yolo_enabled=yolo_enabled,
            context_file=context_file,
            settings=None,
            source="session.json" if in_session else "default",
            updated_at=None,
        )


# =============================================================================
# CLI-to-Hub Sync Endpoints (CLI Only)
# These are called by the CLI to sync local changes to the Hub
# =============================================================================

class SyncAgentConfigRequest(BaseModel):
    """Request from CLI to sync agent config to Hub."""
    role: str
    yolo_enabled: bool = False


@router.post("/{name}/sync", response_model=AgentConfigResponse)
async def sync_agent_config(
    name: str,
    body: SyncAgentConfigRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Sync agent config from CLI to Hub.
    
    This is called by the CLI (agentweave agent add/set-role/set-yolo)
    to sync local session.json changes to the Hub.
    """
    from ...utils import short_id
    
    project_id, _ = project
    agent_name = name.lower()
    
    # Validate role
    valid_roles = {"principal", "delegate", "reviewer"}
    if body.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )
    
    # Get existing config or create new
    q = select(AgentConfig).where(
        AgentConfig.project_id == project_id,
        AgentConfig.agent_name == agent_name,
    )
    result = await session.execute(q)
    config = result.scalars().first()
    
    if config:
        # Update existing
        config.role = body.role
        config.yolo_enabled = body.yolo_enabled
    else:
        # Create new
        config = AgentConfig(
            id=f"acfg-{short_id()}",
            project_id=project_id,
            agent_name=agent_name,
            role=body.role,
            yolo_enabled=body.yolo_enabled,
            context_file=get_context_file_for_agent(agent_name),
        )
        session.add(config)
    
    await session.commit()
    await session.refresh(config)
    
    # Broadcast update
    await sse_manager.broadcast(
        project_id,
        "agent_config_updated",
        {"agent": agent_name, "role": config.role, "yolo_enabled": config.yolo_enabled}
    )
    
    # Log event for YOLO toggle
    event_type = "yolo_enabled" if body.yolo_enabled else "yolo_disabled"
    await persist_event(
        session,
        project_id,
        event_type,
        {"agent": agent_name, "yolo_enabled": config.yolo_enabled},
        agent=agent_name,
    )
    await sse_manager.broadcast(
        project_id,
        "log_event",
        {
            "event_type": event_type,
            "agent": agent_name,
            "data": {"agent": agent_name, "yolo_enabled": config.yolo_enabled},
            "severity": "info",
        },
    )
    
    return AgentConfigResponse(
        agent=agent_name,
        role=config.role,
        yolo_enabled=config.yolo_enabled,
        context_file=config.context_file,
        settings=config.settings,
        source="hub",
        updated_at=config.updated_at,
    )


@router.delete("/{name}/sync", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_config(
    name: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Delete agent config from Hub (called by CLI when agent is removed)."""
    project_id, _ = project
    agent_name = name.lower()
    
    # Delete from Hub database
    q = select(AgentConfig).where(
        AgentConfig.project_id == project_id,
        AgentConfig.agent_name == agent_name,
    )
    result = await session.execute(q)
    config = result.scalars().first()
    
    if config:
        await session.delete(config)
        await session.commit()
        
        # Broadcast removal
        await sse_manager.broadcast(
            project_id,
            "agent_removed",
            {"agent": agent_name}
        )
    
    return None
