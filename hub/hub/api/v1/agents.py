"""Agent monitor endpoints."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    Agent,
    AgentHeartbeat,
    AgentOutput,
    EventLog,
    Message,
    ProjectInstructions,
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

    # Fallback to bundled roles.json (works in Docker without CLI sync)
    if not roles_defs:
        bundled_roles = Path(__file__).parent.parent.parent / "data" / "roles" / "roles.json"
        if bundled_roles.exists():
            try:
                roles_defs = json.loads(bundled_roles.read_text(encoding="utf-8")).get("roles", {})
            except (json.JSONDecodeError, IOError):
                pass

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

    # Also include agents from the Agent table (pilot mode and self-registered agents)
    agent_q = select(Agent).where(Agent.project_id == project_id)
    agent_res = await session.execute(agent_q)
    db_agents: dict[str, Agent] = {}
    for agent_row in agent_res.scalars().all():
        db_agents[agent_row.name] = agent_row
        if agent_row.name not in session_agents_meta:
            session_agents_meta[agent_row.name] = {}

    summaries = []
    for agent_name in sorted(session_agents_meta):
        agent_meta = session_agents_meta.get(agent_name, {})

        # Merge stored config from DB for self-registered agents
        agent_row = db_agents.get(agent_name)
        if agent_row and agent_row.config:
            agent_meta = {**(agent_row.config or {}), **agent_meta}

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

        # Fallback to roles stored in agent config (self-registered agents)
        if not dev_role_keys and agent_meta.get("roles"):
            _meta_roles = agent_meta["roles"]
            if isinstance(_meta_roles, list):
                dev_role_keys = _meta_roles
            else:
                dev_role_keys = [_meta_roles]

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
            "claude": agent_meta.get("model", "Claude"),
            "claude_proxy": agent_meta.get("model", "Claude Proxy"),
            "kimi": agent_meta.get("model", "Kimi"),
            "manual": "Manual",
            "opencode": agent_meta.get("model", "OpenCode"),
            "codex": agent_meta.get("model", "Codex"),
        }.get(_runner, agent_meta.get("model", _runner.replace("_", " ").title()))

        _pilot = agent_row.pilot if agent_row else False
        _registered_session_id = agent_row.registered_session_id if agent_row else None
        _self_registered = agent_row.self_registered if agent_row else False

        # Liveness: online if heartbeat within 2 minutes (only for self-registered agents)
        _liveness = None
        if _self_registered and hb and hb.timestamp:
            now = datetime.now(timezone.utc)
            ts = hb.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = now - ts
            _liveness = "online" if age <= timedelta(minutes=2) else "offline"
        elif _self_registered:
            _liveness = "offline"

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
                pilot=_pilot,
                registered_session_id=_registered_session_id,
                self_registered=_self_registered,
                liveness=_liveness,
                runner_options=agent_meta.get("runner_options"),
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


async def _load_role_content(role: str, project_id: str, db: AsyncSession) -> str:
    """Load role guide markdown content, prepending project instructions if set.

    Tries, in order:
    1. .agentweave/roles/{role}.md (synced by CLI — may be customized)
    2. Bundled templates inside the Hub package (works in Docker)
    3. agentweave.templates package (when CLI is co-installed)
    4. Project-relative fallback for local dev

    If ProjectInstructions row exists for the project, its content is prepended
    with a '---' separator before the role guide.
    """
    role_file = Path(".agentweave/roles") / f"{role}.md"
    if role_file.exists():
        role_content = role_file.read_text(encoding="utf-8")
    else:
        # Bundled templates shipped with the Hub package
        bundled = Path(__file__).parent.parent.parent / "data" / "roles" / f"{role}.md"
        if bundled.exists():
            role_content = bundled.read_text(encoding="utf-8")
        else:
            try:
                from agentweave.templates import get_role_md

                role_content = get_role_md(role)
            except Exception:
                # Fallback for local dev when agentweave isn't installed as a package
                pkg_file = (
                    Path(__file__).parent.parent.parent.parent.parent.parent
                    / "src"
                    / "agentweave"
                    / "templates"
                    / "roles"
                    / f"{role}.md"
                )
                if pkg_file.exists():
                    role_content = pkg_file.read_text(encoding="utf-8")
                else:
                    raise FileNotFoundError(f"Role template not found: {role}")

    # Fetch project instructions from DB
    result = await db.execute(
        select(ProjectInstructions).where(ProjectInstructions.project_id == project_id)
    )
    instr_row = result.scalars().first()
    if instr_row and instr_row.content:
        return instr_row.content + "\n\n---\n\n" + role_content
    return role_content


@router.post("/register")
async def register_agent(
    body: dict,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Register or re-register a self-registered agent."""
    project_id, _ = project
    name = body.get("name")
    contact_mode = body.get("contact_mode")
    role_request = body.get("role_request")
    mcp_endpoint = body.get("mcp_endpoint")
    spawn_cmd = body.get("spawn_cmd")
    config = body.get("config") or {}

    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    CONTACT_MODES = ["poll", "mcp-push", "watchdog-spawn"]

    if contact_mode not in CONTACT_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid contact_mode '{contact_mode}'. Valid: {', '.join(CONTACT_MODES)}",
        )

    # Reject collision with configured agents
    session_data = await _get_session_data(project_id, session)
    if session_data and name in session_data.get("agents", {}):
        raise HTTPException(
            status_code=409, detail=f"Agent name '{name}' is reserved for a configured agent"
        )

    # Sync role_request and config.roles
    if role_request and not config.get("roles"):
        config["roles"] = [role_request]
    elif config.get("roles") and not role_request:
        role_request = config["roles"][0]

    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == name)
    )
    agent_row = result.scalars().first()

    if agent_row:
        agent_row.contact_mode = contact_mode
        agent_row.self_registered = True
        agent_row.mcp_endpoint = mcp_endpoint
        agent_row.spawn_cmd = spawn_cmd
        # Merge config on re-registration so omitted fields don't wipe existing config
        if config:
            agent_row.config = {**(agent_row.config or {}), **config}
        agent_row.updated = datetime.now(timezone.utc)
    else:
        agent_row = Agent(
            id=f"agent-{short_id()}",
            project_id=project_id,
            name=name,
            contact_mode=contact_mode,
            self_registered=True,
            mcp_endpoint=mcp_endpoint,
            spawn_cmd=spawn_cmd,
            config=config,
        )
        session.add(agent_row)

    await session.commit()

    role = role_request or "collaborator"

    try:
        context = await _load_role_content(role, project_id, session)
    except FileNotFoundError:
        context = ""

    return {"role": role, "context": context}


@router.patch("/{name}")
async def patch_agent(
    name: str,
    body: dict,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Partially update a self-registered agent's fields.

    Only fields present in the body are modified. Config is merged
    (existing keys preserved unless overridden).
    """
    project_id, _ = project

    # Reject collision with configured agents
    session_data = await _get_session_data(project_id, session)
    if session_data and name in session_data.get("agents", {}):
        raise HTTPException(
            status_code=409, detail=f"Agent name '{name}' is reserved for a configured agent"
        )

    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == name)
    )
    agent_row = result.scalars().first()
    if not agent_row:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    # Update top-level fields if provided
    if "contact_mode" in body:
        contact_mode = body["contact_mode"]
        CONTACT_MODES = ["poll", "mcp-push", "watchdog-spawn"]
        if contact_mode not in CONTACT_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid contact_mode '{contact_mode}'. Valid: {', '.join(CONTACT_MODES)}",
            )
        agent_row.contact_mode = contact_mode

    if "mcp_endpoint" in body:
        agent_row.mcp_endpoint = body["mcp_endpoint"]
    if "spawn_cmd" in body:
        agent_row.spawn_cmd = body["spawn_cmd"]

    # Merge config if provided
    if "config" in body:
        new_config = body["config"] or {}
        agent_row.config = {**(agent_row.config or {}), **new_config}

    agent_row.updated = datetime.now(timezone.utc)
    await session.commit()

    return {
        "id": agent_row.id,
        "name": agent_row.name,
        "contact_mode": agent_row.contact_mode,
        "self_registered": agent_row.self_registered,
        "mcp_endpoint": agent_row.mcp_endpoint,
        "spawn_cmd": agent_row.spawn_cmd,
        "config": agent_row.config,
    }


@router.get("/context")
async def get_agent_context(
    role: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get role guide content for an agent."""
    project_id, _ = project
    try:
        content = await _load_role_content(role, project_id, session)
        return {"content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Role template not found: {role}")


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
    await sse_manager.broadcast(project_id, "new_session_request", payload)
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


@router.post("/{name}/register-session")
async def register_session(
    name: str,
    body: dict,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Register a session ID for a pilot agent.

    Creates or updates the agent record with pilot=true and the registered session ID.
    """
    project_id, _ = project
    session_id = body.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    # Check if agent exists
    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == name)
    )
    agent_row = result.scalars().first()

    if agent_row:
        # Update existing agent
        agent_row.registered_session_id = session_id
        agent_row.pilot = True
        agent_row.updated = datetime.now(timezone.utc)
    else:
        # Create new agent with pilot=true
        agent_row = Agent(
            id=f"agent-{short_id()}",
            project_id=project_id,
            name=name,
            pilot=True,
            registered_session_id=session_id,
        )
        session.add(agent_row)

    await session.commit()

    return {
        "success": True,
        "agent": name,
        "session_id": session_id,
        "pilot": True,
    }


@router.post("/{name}/pilot")
async def set_agent_pilot(
    name: str,
    body: dict,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Enable or disable pilot mode for an agent.

    Creates the agent record if it doesn't exist.
    """
    project_id, _ = project
    enabled = body.get("enabled", True)

    # Check if agent exists
    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == name)
    )
    agent_row = result.scalars().first()

    if agent_row:
        agent_row.pilot = enabled
        agent_row.updated = datetime.now(timezone.utc)
    else:
        agent_row = Agent(
            id=f"agent-{short_id()}",
            project_id=project_id,
            name=name,
            pilot=enabled,
            registered_session_id=None,
        )
        session.add(agent_row)

    await session.commit()

    return {
        "success": True,
        "agent": name,
        "pilot": enabled,
    }
