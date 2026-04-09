"""Agent monitor endpoints."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    AgentHeartbeat,
    AgentOutput,
    EventLog,
    Message,
    ProjectRolesConfig,
    ProjectSession,
    Task,
)
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


async def _get_session_data(project_id: str, db: AsyncSession) -> Optional[dict]:
    """Return session config for *project_id*.

    Priority:
    1. DB (ProjectSession table) — populated by CLI/watchdog via push_session().
       Works in Docker where the container has no host filesystem access.
    2. Local filesystem fallback — for developers running the Hub directly
       (not in Docker) alongside the CLI in the same working directory.
    """
    result = await db.execute(select(ProjectSession).where(ProjectSession.project_id == project_id))
    row = result.scalars().first()
    if row:
        return row.data

    # Filesystem fallback (local dev without Docker)
    for path in [
        Path(".agentweave") / "session.json",
        Path("..") / ".agentweave" / "session.json",
    ]:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                continue
    return None


@router.get("/configured")
async def get_configured_agents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get the list of configured agents (read-only).

    Agents are managed exclusively via the CLI (agentweave init --agents ...).
    """
    project_id, _ = project
    session_data = await _get_session_data(project_id, session)
    if session_data:
        agents = list(session_data.get("agents", {}).keys())
        return {
            "source": "db",
            "agents": sorted(agents),
            "can_modify": False,
        }
    return {
        "source": "none",
        "agents": [],
        "can_modify": False,
    }


@router.get("", response_model=List[AgentSummary])
async def list_agents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    cutoff = datetime.now(timezone.utc) - _24H

    # Load session config (DB-first, filesystem fallback) for agent metadata
    session_data = await _get_session_data(project_id, session)
    session_agents_meta: dict = session_data.get("agents", {}) if session_data else {}

    # Load roles config for dev_role / dev_role_label
    roles_result = await session.execute(
        select(ProjectRolesConfig).where(ProjectRolesConfig.project_id == project_id)
    )
    roles_row = roles_result.scalars().first()
    roles_data = roles_row.data if roles_row else {}
    agent_assignments: dict = roles_data.get("agent_assignments", {})
    roles_defs: dict = roles_data.get("roles", {})

    # If no session.json, fall back to agents seen in DB activity (last 24h).
    # This covers the Docker case where the hub can't read the host's session.json —
    # the watchdog pushes heartbeats on startup to register agents.
    if not session_agents_meta:
        senders_q = (
            select(Message.sender)
            .distinct()
            .where(Message.project_id == project_id, Message.timestamp >= cutoff)
        )
        recipients_q = (
            select(Message.recipient)
            .distinct()
            .where(Message.project_id == project_id, Message.timestamp >= cutoff)
        )
        hb_q = (
            select(AgentHeartbeat.agent)
            .distinct()
            .where(
                AgentHeartbeat.project_id == project_id,
                AgentHeartbeat.timestamp >= cutoff,
            )
        )
        out_q = (
            select(AgentOutput.agent)
            .distinct()
            .where(
                AgentOutput.project_id == project_id,
                AgentOutput.timestamp >= cutoff,
            )
        )
        s_res, r_res, hb_res, out_res = await asyncio.gather(
            session.execute(senders_q),
            session.execute(recipients_q),
            session.execute(hb_q),
            session.execute(out_q),
        )
        fallback_names: set[str] = set()
        for (name,) in s_res:
            fallback_names.add(name)
        for (name,) in r_res:
            fallback_names.add(name)
        for (name,) in hb_res:
            fallback_names.add(name)
        for (name,) in out_res:
            fallback_names.add(name)
        session_agents_meta = {name: {} for name in fallback_names}

    summaries = []
    for agent_name in sorted(session_agents_meta):
        agent_meta = session_agents_meta.get(agent_name, {})

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

        # Get dev roles - support both new 'agent_roles' (list) and legacy 'agent_assignments' (single)
        dev_role_keys: list[str] = []
        agent_roles_data = roles_data.get("agent_roles", {})
        if agent_name in agent_roles_data:
            # New format: agent_roles is a dict of lists
            roles_entry = agent_roles_data[agent_name]
            if isinstance(roles_entry, list):
                dev_role_keys = roles_entry
            else:
                dev_role_keys = [roles_entry]
        elif agent_name in agent_assignments:
            # Legacy format: agent_assignments is a dict of single role strings
            legacy_role = agent_assignments[agent_name]
            if isinstance(legacy_role, list):
                dev_role_keys = legacy_role
            else:
                dev_role_keys = [legacy_role] if legacy_role else []

        # Get primary role (first one) for single-role display
        dev_role_key = dev_role_keys[0] if dev_role_keys else None
        dev_role_meta = roles_defs.get(dev_role_key, {}) if dev_role_key else {}

        # Build list of role labels for all roles
        dev_role_labels = []
        for role_key in dev_role_keys:
            role_def = roles_defs.get(role_key, {})
            if role_def:
                dev_role_labels.append(role_def.get("label", role_key))
            else:
                dev_role_labels.append(role_key)

        # Latest context_warning event for this agent
        ctx_q = (
            select(EventLog)
            .where(
                EventLog.project_id == project_id,
                EventLog.agent == agent_name,
                EventLog.event_type == "context_warning",
            )
            .order_by(EventLog.timestamp.desc())
            .limit(1)
        )
        ctx_res = await session.execute(ctx_q)
        ctx_row = ctx_res.scalars().first()
        context_usage = ctx_row.data if ctx_row else None

        # Get session started_at from the most recent session with output
        session_started_at = None
        session_q = (
            select(
                AgentOutput.session_id,
                func.min(AgentOutput.timestamp).label("started_at"),
            )
            .where(
                AgentOutput.project_id == project_id,
                AgentOutput.agent == agent_name,
                AgentOutput.session_id.isnot(None),
            )
            .group_by(AgentOutput.session_id)
            .order_by(func.max(AgentOutput.timestamp).desc())
            .limit(1)
        )
        session_res = await session.execute(session_q)
        session_row = session_res.first()
        if session_row and session_row.started_at:
            session_started_at = session_row.started_at

        _runner = agent_meta.get("runner", "native")
        _display_model = {
            "claude": "Claude",
            "claude_proxy": agent_meta.get("model", "Claude Proxy"),
            "kimi": "Kimi",
            "manual": "Manual",
        }.get(_runner, _runner.replace("_", " ").title())

        summaries.append(
            AgentSummary(
                name=agent_name,
                status=hb.status if hb else "idle",
                latest_status_msg=hb.message if hb else None,
                last_seen=hb.timestamp if hb else None,
                message_count=msg_count,
                active_task_count=task_count,
                role=agent_meta.get("role"),
                yolo=bool(agent_meta.get("yolo", False)),
                runner=_runner,
                display_model=_display_model,
                dev_role=dev_role_key,
                dev_role_label=dev_role_meta.get("label"),
                dev_roles=dev_role_keys,
                dev_role_labels=dev_role_labels,
                context_usage=context_usage,
                session_started_at=session_started_at,
            )
        )

    return summaries


@router.put("/roles/config", status_code=200)
async def put_roles_config(
    body: dict,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Upsert the roles.json config pushed from the CLI at init time."""
    project_id, _ = project
    result = await session.execute(
        select(ProjectRolesConfig).where(ProjectRolesConfig.project_id == project_id)
    )
    row = result.scalars().first()
    if row:
        row.data = body
        from datetime import datetime, timezone

        row.synced_at = datetime.now(timezone.utc)
    else:
        row = ProjectRolesConfig(project_id=project_id, data=body)
        session.add(row)
    await session.commit()
    return {"status": "ok"}


@router.get("/roles/config")
async def get_roles_config(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Return the stored roles.json config for this project."""
    project_id, _ = project
    result = await session.execute(
        select(ProjectRolesConfig).where(ProjectRolesConfig.project_id == project_id)
    )
    row = result.scalars().first()
    if not row:
        return {}
    return row.data


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

    # Detect if this is the first output for this session_id (new session)
    is_new_session = False
    if body.session_id:
        count_result = await session.execute(
            select(func.count(AgentOutput.id)).where(
                AgentOutput.project_id == project_id,
                AgentOutput.agent == name,
                AgentOutput.session_id == body.session_id,
            )
        )
        is_new_session = (count_result.scalar() or 0) == 0

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
            "id": row.id,
            "agent": name,
            "session_id": body.session_id,
            "content": body.content,
            "timestamp": row.timestamp.isoformat(),
        },
    )
    if is_new_session:
        await sse_manager.broadcast(
            project_id,
            "agent_session_changed",
            {"agent": name, "session_id": body.session_id},
        )
    return {"id": row.id}


@router.post("/{name}/context-usage", status_code=status.HTTP_201_CREATED)
async def post_context_usage(
    name: str,
    body: dict,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Receive a context usage report from the watchdog and broadcast to Hub UI via SSE.

    Expected body: {agent, model, tokens_used, tokens_limit, percent, warning,
                    critical, threshold_warning, threshold_critical, updated_at}
    """
    project_id, _ = project
    payload = {**body, "agent": name}
    severity = "warning" if body.get("warning") else "info"
    await persist_event(
        session, project_id, "context_warning", payload, agent=name, severity=severity
    )
    await sse_manager.broadcast(project_id, "context_warning", payload)
    return {"status": "ok", "agent": name}


@router.post("/{name}/compact", status_code=status.HTTP_201_CREATED)
async def post_compact_request(
    name: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Send a compact request to the agent's inbox."""
    project_id, _ = project
    msg = Message(
        id=f"msg-{short_id()}",
        project_id=project_id,
        sender="hub",
        recipient=name,
        subject="compact_request",
        content=(
            "**Context management: Compact requested**\n\n"
            "1. Run `/aw-checkpoint` to save your session state.\n"
            "2. Run `/compact` in your session.\n"
            "3. After compacting, re-read your checkpoint and resume from Next Steps."
        ),
        type="message",
    )
    session.add(msg)
    await session.commit()
    payload = {"agent": name, "action": "compact", "message_id": msg.id}
    await sse_manager.broadcast(project_id, "message_created", {"id": msg.id, "recipient": name})
    await persist_event(session, project_id, "compact_request", payload, agent=name)
    return {"status": "ok", "message_id": msg.id}


@router.post("/{name}/new-session", status_code=status.HTTP_201_CREATED)
async def post_new_session_request(
    name: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Send a new-session request to the agent's inbox."""
    project_id, _ = project
    msg = Message(
        id=f"msg-{short_id()}",
        project_id=project_id,
        sender="hub",
        recipient=name,
        subject="new_session_request",
        content=(
            "**Context management: New session requested**\n\n"
            "1. Run `/aw-checkpoint` to save your session state.\n"
            "2. Your principal will start a fresh session for you.\n"
            "3. The new session will read your checkpoint as its first action."
        ),
        type="message",
    )
    session.add(msg)
    await session.commit()
    payload = {"agent": name, "action": "new_session", "message_id": msg.id}
    await sse_manager.broadcast(project_id, "message_created", {"id": msg.id, "recipient": name})
    await persist_event(session, project_id, "new_session_request", payload, agent=name)
    return {"status": "ok", "message_id": msg.id}


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
