"""Agent monitor endpoints."""

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, get_args

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import bound_address, project_workspace, worktrees
from ...agent_colors import next_color_index
from ...agent_lifecycle import archivable as agent_archivable
from ...agent_lifecycle import archive as archive_agent_row
from ...agent_lifecycle import unarchive as unarchive_agent_row
from ...agent_status import effective_heartbeat_status, heartbeat_is_stale
from ...auth import get_project
from ...checkpoint_policy import CHECKPOINT_MODES, threshold_error
from ...codex_appserver import APP_SERVER_OPT_OUT_FLAG, uses_app_server
from ...conversations import new_conversation
from ...db.engine import get_session
from ...db.models import (
    Agent,
    AgentHeartbeat,
    AgentOutput,
    Charter,
    EventLog,
    InboundQueueEntry,
    Message,
    Project,
    ProjectInstructions,
    ProjectSession,
    ProjectSpec,
    Run,
    Runner,
    Task,
)
from ...inbound_queue import new_entry
from ...launchability import get_agent_config, probe_agent
from ...model_catalog import get_provider, permission_mode_values
from ...output_recording import record_agent_output, record_context_usage
from ...schemas.agents import (
    AgentHeartbeatCreate,
    AgentOutputCreate,
    AgentOutputResponse,
    AgentSummary,
    AgentTimelineEvent,
    ContextUsageCreate,
)
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/agents", tags=["agents"])

_24H = timedelta(hours=24)
_ACTIVE_TASK_STATUSES = ("pending", "assigned", "in_progress", "under_review", "revision_needed")
_AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
_CONTACT_MODES = ("poll", "mcp-push", "watchdog-spawn")


class AgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    template: str = Field(min_length=1, max_length=32)
    task: str = Field(min_length=1, max_length=100_000)
    run_id: str = Field(min_length=1, max_length=64)


class OperatorAgentCreate(BaseModel):
    """Either `runner_id` (an existing runner) or both `provider` and `model` (find-or-create
    one) must be given, not both and not neither — provider+model is the primary path the
    Hub UI's Add-agent dialog uses (2026-08-04-hub-model-control-and-provisioning); runner_id
    remains valid for a caller that already has a runner in hand, and is what
    Runners-section-driven binding still uses.
    """

    name: str = Field(min_length=1, max_length=32, pattern=r"^[a-zA-Z0-9_-]{1,32}$")
    runner_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=16)
    model: Optional[str] = Field(default=None, max_length=256)
    charter_id: Optional[str] = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _exactly_one_capability_source(self) -> "OperatorAgentCreate":
        has_runner = self.runner_id is not None
        has_provider_model = self.provider is not None and self.model is not None
        if self.provider is not None and self.model is None:
            raise ValueError("model is required when provider is given")
        if self.model is not None and self.provider is None:
            raise ValueError("provider is required when model is given")
        if has_runner == has_provider_model:
            raise ValueError(
                "Provide either runner_id or both provider and model, not both or neither"
            )
        return self


class OperatorAgentResponse(BaseModel):
    id: str
    name: str
    runner_id: str
    charter_id: Optional[str]
    color_index: int
    contact_mode: str
    self_registered: bool


async def _get_session_data(project_id: str, db: AsyncSession) -> Optional[dict]:
    """Return session config for *project_id* from the `ProjectSession` table.

    Populated by the CLI/watchdog via `push_session()` on every session save. There is
    no filesystem fallback: a global `.agentweave/session.json` read relative to the Hub
    process's own working directory could only ever represent one project, and would
    leak that project's configured agents across every other project's boundary (task 3.4).
    """
    result = await db.execute(select(ProjectSession).where(ProjectSession.project_id == project_id))
    row = result.scalars().first()
    return row.data if row else None


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


@router.get("/launchability")
async def get_agents_launchability(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Probe every configured agent's launchability: CLI present, authorized, runnable —
    and, for an agent the Hub can actually trigger directly, whether it is
    collaboration-ready (task 6).

    Read-only and side-effect-free — this checks PATH, environment variables, and DB
    rows visible to the Hub process; it never spawns anything (task 6.2). Feeds
    launchability indicators in the agent/runner selector.

    For an agent bound to a Hub Runner (`Agent.runner_id` set), the Runner's own
    `cli`/`model` are the source of truth for the probe — mirroring
    `trigger_agent_directly`'s own override of the legacy session-config-derived
    `runner`/`model` keys (see that function's comment). Without this override, an agent
    whose session-synced config disagreed with its actually-bound Runner would report
    launchability for a CLI/model combination `trigger_agent_directly` would never
    actually use. An agent with no bound Runner (self-registered or CLI-launched,
    outside the Hub's own spawn path) keeps the legacy config-derived probe unchanged —
    that path is real for those agents, not stale.
    """
    project_id, _ = project

    session_data = await _get_session_data(project_id, session)
    session_agents_meta: dict = dict(session_data.get("agents", {})) if session_data else {}

    agent_q = select(Agent).where(Agent.project_id == project_id)
    agent_res = await session.execute(agent_q)
    db_agents: dict[str, Agent] = {row.name: row for row in agent_res.scalars().all()}
    for name in db_agents:
        session_agents_meta.setdefault(name, {})

    # Task 6.1's "callback-address agreement": the same condition
    # `trigger_agent_directly` itself requires before it will start any run at all (see
    # its own HUB_URL / bound_address.get() check) — a Hub-instance-wide fact, checked
    # once rather than per agent.
    hub_address_known = bool(os.environ.get("HUB_URL")) or bound_address.get() is not None

    results = {}
    for name in session_agents_meta:
        merged = await get_agent_config(project_id, name, session)
        agent_row = db_agents.get(name)
        runner_row = None
        if agent_row is not None and agent_row.runner_id is not None:
            runner_row = await session.get(Runner, agent_row.runner_id)
        if runner_row is not None:
            merged["runner"] = runner_row.cli
            merged["model"] = runner_row.model

        probe = probe_agent(name, merged)

        # Collaboration readiness only applies to an agent the Hub can trigger directly
        # (a bound Runner) and only once basic launchability already holds — an agent
        # that cannot even start has nothing more specific to say here.
        collaboration_ready: Optional[bool] = None
        collaboration_reason: Optional[str] = None
        if runner_row is not None and probe["runnable"]:
            if not hub_address_known:
                collaboration_ready = False
                collaboration_reason = (
                    "The Hub cannot determine its own callback address yet, so a "
                    "triggered run could not reach it — trigger any run once first, or "
                    "set HUB_URL explicitly."
                )
            elif runner_row.cli == "codex":
                # Derived from the same helper the trigger path uses to pick the transport, so
                # what the operator is told and what actually runs cannot drift apart.
                yolo = bool(merged.get("yolo"))
                if uses_app_server(runner_row.cli, runner_row.flags) or yolo:
                    collaboration_ready = True
                else:
                    collaboration_ready = False
                    collaboration_reason = (
                        "This Codex agent's runner opted out of the app-server transport "
                        f'(flags: ["{APP_SERVER_OPT_OUT_FLAG}"]) and does not have yolo '
                        "enabled, so it falls back to classic exec — AgentWeave tool calls "
                        "(send_message, etc.) will be silently denied with no operator "
                        "present to approve them. Remove the opt-out, or enable yolo."
                    )
            else:
                collaboration_ready = True

        results[name] = {
            **probe,
            "collaboration_ready": collaboration_ready,
            "collaboration_reason": collaboration_reason,
        }

    return {"agents": results}


def _usable_context_reading(rows: List[Any]) -> Any:
    """Pick the reading to report from an agent's `context_warning` rows, newest first.

    Taking the newest row alone is what made Claude agents report nothing for 329 samples: the
    end-of-turn message reports a context window with no token count, so the last row to arrive
    routinely carried no usable percentage and hid the complete one behind it.

    The newest row still wins whenever it carries a percentage. Otherwise the newest row **from
    the same provider session** that does is used — scoped to the session because a compaction or
    a fresh session resets usage, and reporting a pre-reset percentage as current would be worse
    than reporting none. An unscoped fallback would do exactly that.
    """
    if not rows:
        return None
    newest = rows[0]
    if not isinstance(newest, dict) or newest.get("percent") is not None:
        return newest
    session_id = newest.get("session_id")
    if session_id is None:
        return newest
    for row in rows[1:]:
        if (
            isinstance(row, dict)
            and row.get("percent") is not None
            and row.get("session_id") == session_id
        ):
            return row
    return newest


@router.get("", response_model=List[AgentSummary])
async def list_agents(
    lifecycle: Literal["open", "archived", "all"] = Query("open"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The project's agent roster.

    Archived agents are excluded by default, and this one filter is what removes them from every
    surface that offers an agent — the rail, task assignment, the job form, peer recipients, the
    new-conversation surface — because all of them read this endpoint. Adding the filter at each
    call site instead would mean one missed site leaves an archived agent selectable.

    `?lifecycle=all` is what the agent's own configuration page asks for: an archived agent must
    still resolve there, or there would be nowhere to unarchive it from.
    """
    project_id, _ = project
    cutoff = datetime.now(timezone.utc) - _24H

    # Load session config (DB-first, filesystem fallback) for agent metadata
    session_data = await _get_session_data(project_id, session)
    session_agents_meta: dict = session_data.get("agents", {}) if session_data else {}

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
        task_assignees_q = (
            select(Task.assignee)
            .distinct()
            .where(
                Task.project_id == project_id,
                Task.assignee.isnot(None),
                Task.status.in_(_ACTIVE_TASK_STATUSES),
            )
        )
        s_res, r_res, hb_res, out_res, task_assignees_res = await asyncio.gather(
            session.execute(senders_q),
            session.execute(recipients_q),
            session.execute(hb_q),
            session.execute(out_q),
            session.execute(task_assignees_q),
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
        for (name,) in task_assignees_res:
            if name:
                fallback_names.add(name)
        session_agents_meta = {name: {} for name in fallback_names}

    # Task assignees are meaningful even when a synced session config exists:
    # users can create tasks for an agent before it has heartbeats/messages.
    task_assignees_q = (
        select(Task.assignee)
        .distinct()
        .where(
            Task.project_id == project_id,
            Task.assignee.isnot(None),
            Task.status.in_(_ACTIVE_TASK_STATUSES),
        )
    )
    task_assignees_res = await session.execute(task_assignees_q)
    for (name,) in task_assignees_res:
        if name and name not in session_agents_meta:
            session_agents_meta[name] = {}

    # Also include agents from the Agent table (self-registered agents)
    agent_q = select(Agent).where(Agent.project_id == project_id)
    agent_res = await session.execute(agent_q)
    db_agents: dict[str, Agent] = {}
    for agent_row in agent_res.scalars().all():
        db_agents[agent_row.name] = agent_row
        if agent_row.name not in session_agents_meta:
            session_agents_meta[agent_row.name] = {}

    # Applied after every source has contributed, not to the Agent query alone: a name also
    # arrives here from session config, from 24h of activity, and from being a task's assignee.
    # Filtering only the query would let an archived agent back in through any of those.
    if lifecycle != "all":
        wanted = lifecycle
        session_agents_meta = {
            name: meta
            for name, meta in session_agents_meta.items()
            # An agent with no row cannot have been archived, so it counts as open.
            if (db_agents[name].lifecycle if name in db_agents else "open") == wanted
        }

    # The bound Runner is the truth about what a Hub-spawned agent actually runs. Without it
    # `_runner`/`_display_model` below fall through to their "native"/"Native" defaults, because
    # neither the (now unwritten) session config nor `Agent.config` carries the binding — see
    # `get_agents_launchability`, which applies the same override for the same reason.
    runners_q = select(Runner).where(Runner.project_id == project_id)
    runners_res = await session.execute(runners_q)
    runners_by_id: dict[str, Runner] = {r.id: r for r in runners_res.scalars().all()}

    if not session_agents_meta:
        return []

    agent_names = list(session_agents_meta.keys())

    # Bulk fetch latest heartbeat per agent (ordered by agent, then timestamp desc)
    hb_q = (
        select(AgentHeartbeat)
        .where(
            AgentHeartbeat.project_id == project_id,
            AgentHeartbeat.agent.in_(agent_names),
        )
        .order_by(AgentHeartbeat.agent, AgentHeartbeat.timestamp.desc())
    )
    hb_res = await session.execute(hb_q)
    latest_hbs: dict[str, AgentHeartbeat] = {}
    for hb in hb_res.scalars().all():
        latest_hbs.setdefault(hb.agent, hb)

    # Bulk fetch agents with a direct-spawn run in progress. A Hub-triggered
    # run (agent_trigger.py) never posts a heartbeat, so without this the
    # heartbeat-only effective_status below would show "idle" for the whole
    # duration of a live direct spawn.
    running_run_q = select(Run.agent).where(
        Run.project_id == project_id,
        Run.agent.in_(agent_names),
        Run.status == "running",
    )
    running_run_res = await session.execute(running_run_q)
    agents_with_active_run = {name for (name,) in running_run_res}

    # Bulk fetch message counts (last 24h) per agent
    sender_counts_q = (
        select(Message.sender, func.count())
        .where(Message.project_id == project_id, Message.timestamp >= cutoff)
        .group_by(Message.sender)
    )
    recipient_counts_q = (
        select(Message.recipient, func.count())
        .where(Message.project_id == project_id, Message.timestamp >= cutoff)
        .group_by(Message.recipient)
    )
    sender_counts_res, recipient_counts_res = await asyncio.gather(
        session.execute(sender_counts_q),
        session.execute(recipient_counts_q),
    )
    msg_counts: dict[str, int] = {}
    for name, cnt in sender_counts_res:
        msg_counts[name] = msg_counts.get(name, 0) + cnt
    for name, cnt in recipient_counts_res:
        msg_counts[name] = msg_counts.get(name, 0) + cnt

    # Bulk fetch active task counts per agent
    active_task_counts_q = (
        select(Task.assignee, func.count())
        .where(
            Task.project_id == project_id,
            Task.assignee.in_(agent_names),
            Task.status.in_(_ACTIVE_TASK_STATUSES),
        )
        .group_by(Task.assignee)
    )
    active_task_counts_res = await session.execute(active_task_counts_q)
    # Not `dict(...)`: a SQLAlchemy Result exposes .keys(), so dict() takes the
    # mapping path and tries to subscript it rather than iterating (name, count)
    # rows, raising TypeError. The comprehension forces row iteration.
    active_task_counts = {name: cnt for name, cnt in active_task_counts_res}  # noqa: C416

    # Bulk fetch context_warning event data per agent, newest first.
    ctx_q = (
        select(EventLog)
        .where(
            EventLog.project_id == project_id,
            EventLog.event_type == "context_warning",
            EventLog.agent.in_(agent_names),
        )
        .order_by(EventLog.agent, EventLog.timestamp.desc())
    )
    ctx_res = await session.execute(ctx_q)
    ctx_rows_by_agent: dict[str, List[Any]] = {}
    for row in ctx_res.scalars().all():
        ctx_rows_by_agent.setdefault(row.agent, []).append(row.data)
    context_usage_map: dict[str, Any] = {
        agent_name: _usable_context_reading(rows) for agent_name, rows in ctx_rows_by_agent.items()
    }

    # Bulk fetch session started_at: first output timestamp of the most recent
    # session (by last output timestamp) per agent.
    session_q = (
        select(
            AgentOutput.agent,
            AgentOutput.session_id,
            func.min(AgentOutput.timestamp).label("started_at"),
            func.max(AgentOutput.timestamp).label("last_active"),
        )
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent.in_(agent_names),
            AgentOutput.session_id.isnot(None),
        )
        .group_by(AgentOutput.agent, AgentOutput.session_id)
    )
    session_res = await session.execute(session_q)
    session_started_map: dict[str, datetime] = {}
    best_last_active: dict[str, datetime] = {}
    for row in session_res.all():
        agent, sess_id, started_at, last_active = row
        if sess_id and (agent not in best_last_active or last_active > best_last_active[agent]):
            best_last_active[agent] = last_active
            session_started_map[agent] = started_at

    summaries = []
    for agent_name in sorted(session_agents_meta):
        agent_meta = session_agents_meta.get(agent_name, {})

        # Merge stored config from DB for self-registered agents
        agent_row = db_agents.get(agent_name)
        if agent_row and agent_row.config:
            agent_meta = {**(agent_row.config or {}), **agent_meta}

        hb = latest_hbs.get(agent_name)
        effective_status, effective_status_message = effective_heartbeat_status(hb)
        if agent_name in agents_with_active_run:
            effective_status, effective_status_message = "running", None
        msg_count = msg_counts.get(agent_name, 0)
        task_count = active_task_counts.get(agent_name, 0)
        context_usage = context_usage_map.get(agent_name)
        session_started_at = session_started_map.get(agent_name)

        # A Runner-bound agent reports its runner's cli/model; an agent with no binding
        # (self-registered, launched outside the Hub's spawn path) keeps deriving from its own
        # stored config, because for those agents that path is still the real one.
        bound_runner = runners_by_id.get(agent_row.runner_id) if agent_row else None
        if bound_runner is not None:
            agent_meta = {
                **agent_meta,
                "runner": bound_runner.cli,
                **({"model": bound_runner.model} if bound_runner.model else {}),
            }

        _runner = agent_meta.get("runner", "native")
        _display_model = {
            "claude": agent_meta.get("model", "Claude"),
            "claude_proxy": agent_meta.get("model", "Claude Proxy"),
            "kimi": agent_meta.get("model", "Kimi"),
            "manual": "Manual",
            "opencode": agent_meta.get("model", "OpenCode"),
            "codex": agent_meta.get("model", "Codex"),
            "codex_mcp": agent_meta.get("model", "Codex MCP"),
        }.get(_runner, agent_meta.get("model", _runner.replace("_", " ").title()))

        _self_registered = agent_row.self_registered if agent_row else False

        # Liveness: online if heartbeat within 2 minutes (only for self-registered agents)
        _liveness = None
        if _self_registered and hb and hb.timestamp:
            now = datetime.now(timezone.utc)
            ts = hb.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            _liveness = "offline" if heartbeat_is_stale(hb, now=now) else "online"
        elif _self_registered:
            _liveness = "offline"

        summaries.append(
            AgentSummary(
                name=agent_name,
                description=(agent_row.description if agent_row else None),
                status=effective_status,
                latest_status_msg=effective_status_message,
                last_seen=hb.timestamp if hb else None,
                message_count=msg_count,
                active_task_count=task_count,
                lifecycle=(agent_row.lifecycle if agent_row else "open"),
                runner=_runner,
                display_model=_display_model,
                context_usage=context_usage,
                session_started_at=session_started_at,
                self_registered=_self_registered,
                liveness=_liveness,
                runner_options=agent_meta.get("runner_options"),
                color_index=agent_row.color_index if agent_row else None,
                runner_id=agent_row.runner_id if agent_row else None,
                charter_id=agent_row.charter_id if agent_row else None,
                permission_timeout_seconds=(
                    agent_row.permission_timeout_seconds if agent_row else None
                ),
                question_timeout_seconds=(
                    agent_row.question_timeout_seconds if agent_row else None
                ),
                default_permission_mode=(agent_row.default_permission_mode if agent_row else None),
                checkpoint_mode=agent_row.checkpoint_mode if agent_row else None,
                checkpoint_threshold_mode=(
                    agent_row.checkpoint_threshold_mode if agent_row else None
                ),
                checkpoint_threshold_value=(
                    agent_row.checkpoint_threshold_value if agent_row else None
                ),
                checkpoint_notes_value=(agent_row.checkpoint_notes_value if agent_row else None),
                can_read_checkpoints=bool(agent_row.can_read_checkpoints) if agent_row else False,
                can_recall=bool(agent_row.can_recall) if agent_row else False,
            )
        )

    return summaries


@router.post("", response_model=OperatorAgentResponse, status_code=status.HTTP_201_CREATED)
async def create_operator_agent(
    body: OperatorAgentCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Create a Hub-owned agent identity from existing project resources."""
    project_id, _ = project
    try:
        await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        project_workspace.raise_workspace_http_error(exc)

    existing = await session.execute(
        select(Agent.id).where(Agent.project_id == project_id, Agent.name == body.name)
    )
    session_data = await _get_session_data(project_id, session)
    configured_names = (session_data or {}).get("agents", {})
    if existing.scalar() is not None or body.name in configured_names:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent name '{body.name}' already exists in this project",
        )

    if body.runner_id is not None:
        runner = await session.get(Runner, body.runner_id)
        if runner is None or runner.project_id != project_id:
            raise HTTPException(status_code=404, detail=f"Runner '{body.runner_id}' not found")
    else:
        # provider + model: atomic find-or-create (design.md). Reuses a matching runner
        # already in this project rather than creating a duplicate; a runner created here
        # is added to the session but not committed until the same commit as the agent
        # below, so a failure anywhere before that commit leaves neither record behind.
        provider_entry = get_provider(body.provider)
        model_entry = provider_entry.model(body.model) if provider_entry is not None else None
        if provider_entry is None or model_entry is None:
            raise HTTPException(
                status_code=400,
                detail=f"{body.model!r} is not a model {body.provider!r} declares",
            )
        existing_runner = await session.execute(
            select(Runner).where(
                Runner.project_id == project_id,
                Runner.cli == body.provider,
                Runner.model == body.model,
            )
        )
        runner = existing_runner.scalars().first()
        if runner is None:
            runner = Runner(
                id=f"runner-{short_id()}",
                project_id=project_id,
                name=f"{provider_entry.label} — {model_entry.label}",
                cli=body.provider,
                model=body.model,
            )
            session.add(runner)

    if body.charter_id is not None:
        charter = await session.get(Charter, body.charter_id)
        if charter is None or charter.project_id != project_id:
            raise HTTPException(status_code=404, detail=f"Charter '{body.charter_id}' not found")

    probe = probe_agent(body.name, {"runner": runner.cli, "model": runner.model})
    if not probe["runnable"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=probe.get("reason") or "Runner is not currently launchable",
        )

    agent = Agent(
        id=f"agent-{short_id()}",
        project_id=project_id,
        name=body.name,
        contact_mode="watchdog-spawn",
        self_registered=False,
        config={},
        color_index=await next_color_index(session, project_id),
        runner_id=runner.id,
        charter_id=body.charter_id,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)

    payload = {
        "agent": agent.name,
        "agent_id": agent.id,
        "runner_id": agent.runner_id,
        "charter_id": agent.charter_id,
        "color_index": agent.color_index,
    }
    await persist_event(session, project_id, "agent_created", payload, agent=agent.name)
    await sse_manager.broadcast(project_id, "agent_created", payload)
    return OperatorAgentResponse(
        id=agent.id,
        name=agent.name,
        runner_id=agent.runner_id,
        charter_id=agent.charter_id,
        color_index=agent.color_index,
        contact_mode=agent.contact_mode,
        self_registered=agent.self_registered,
    )


def _run_lifecycle_summary(event_type: str, data: Optional[dict]) -> Optional[str]:
    """Human-readable summary for a run-lifecycle EventLog row.

    Falls back to the bare event_type (existing behavior for every other
    EventLog-derived timeline entry) when the type isn't one of these or
    the expected fields are missing.
    """
    data = data or {}
    if event_type == "run_started":
        runner = data.get("runner")
        model = data.get("model")
        detail = " (" + ", ".join(x for x in (runner, model) if x) + ")" if runner or model else ""
        return f"Run started{detail}"
    if event_type == "run_completed":
        return f"Run completed (exit {data.get('exit_code', 0)})"
    if event_type == "run_failed":
        error = data.get("error")
        exit_code = data.get("exit_code")
        if error:
            return f"Run failed: {error}"
        return f"Run failed (exit {exit_code})" if exit_code is not None else "Run failed"
    if event_type == "run_stopped":
        exit_code = data.get("exit_code")
        return f"Run stopped (exit {exit_code})" if exit_code is not None else "Run stopped"
    if event_type == "run_interrupted":
        return "Run interrupted (Hub restarted)"
    return None


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
                summary=_run_lifecycle_summary(entry.event_type, entry.data) or entry.event_type,
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


def _runner_summary(agent_meta: dict) -> str:
    parts = [f"runner={agent_meta.get('runner') or 'native'}"]
    if agent_meta.get("model"):
        parts.append(f"model={agent_meta['model']}")
    flags = []
    if agent_meta.get("yolo"):
        flags.append("yolo")
    if flags:
        parts.append("flags=" + ",".join(flags))
    env_vars = agent_meta.get("env_vars") or {}
    env_names = []
    if isinstance(env_vars, dict):
        for key, value in env_vars.items():
            if str(key).endswith("_VAR") and value:
                env_names.append(str(value))
            elif str(key).isupper():
                env_names.append(str(key))
    if env_names:
        parts.append("env=" + ",".join(sorted(set(env_names))))
    return "; ".join(parts)


def _tool_surface_lines() -> List[str]:
    """Describe every tool an agent can call, with the values its constrained parameters take.

    Naming a tool without its accepted values is what produced the Codex failure: the turn
    preamble listed four tool names and nothing else, so agents guessed `message_type="text"` and
    were rejected. Four job tools were never mentioned at all. Constrained values are taken from
    `mcp_server`'s own `Literal` aliases, so this cannot drift from the schema clients receive.

    `mcp_server.approve_tool_call` is deliberately absent and must stay absent. It is registered
    on the same server for convenience but is a runtime endpoint the harness invokes, not a
    capability the agent has: calling it accomplishes nothing and grants nothing. This section
    exists to tell an agent what it can deliberately use.
    """
    from ...mcp_server import JobSessionMode, MessageType, TaskPriority, TaskStatus

    def values(alias: Any) -> str:
        return ", ".join(f"`{value}`" for value in get_args(alias))

    return [
        "## Your tools",
        "",
        "Names below are as injected; with an MCP surface they are prefixed `mcp__agentweave__`.",
        "",
        f"- `send_message(to_agent, subject, content, message_type=message, task_id=None)` — "
        f"message_type is one of {values(MessageType)}.",
        "- `create_task(title, description, assignee, priority=medium, requirements, "
        f"acceptance_criteria)` — priority is one of {values(TaskPriority)}.",
        "- `list_tasks(agent=None)` — read the shared task ledger.",
        "- `get_task(task_id)` — read one ledger entry.",
        f"- `update_task(task_id, status)` — status is required, one of {values(TaskStatus)}.",
        "- `ask_user(questions)` — ask the operator and **wait** for the answers, which are "
        "returned to you. Ask whenever a choice is genuinely the operator's to make and guessing "
        "wrong would waste real work; do not ask what the repository or the task already answers.",
        "  `questions` is a list of 1 to 4. Ask everything you need in one call: the operator "
        "steps through them in a single sitting, which interrupts them once instead of once per "
        "question. Each entry needs `question`, `header`, `options` and `multi_select`, all "
        "required. `header` is two or three words naming the decision. `options` "
        'is 2 to 8 entries of `{"label", "description"}` — the label comes back to you, and '
        "the description is what lets the operator choose without already knowing the trade-off, "
        "so write what picking it actually means rather than restating the label. There is no "
        "way to ask without options: if the decision feels open, offer the answers you consider "
        "most likely. `multi_select` is true when several can be chosen together, and that answer "
        "then arrives as a list. The operator can always reply in their own words instead, so "
        "handle an answer that is none of yours.",
        "- `get_answer(question_id)` — only needed for a question you asked with "
        "`blocking=False`; a normal `ask_user` has already returned the answer.",
        "- `request_agent(name, template, task)` — governed; subject to the project agent budget.",
        f"- `create_job(name, agent, message, cron, session_mode=new)` — session_mode is one of "
        f"{values(JobSessionMode)}. Requires the operator's scheduled-work allowance.",
        "- `delete_job(job_id)`, `toggle_job(job_id, enabled)`, `run_job(job_id)` — same allowance.",
        "",
        "Address a peer by its exact name from the roster above. There is no inbox tool: "
        "everything addressed to you already appears in this turn.",
        "",
    ]


async def _render_hub_agent_context(
    *,
    agent: str,
    project_id: str,
    db: AsyncSession,
    session_data: Optional[dict],
    agent_row: Optional[Agent],
    work_dir: Optional[str] = None,
    isolated: bool = False,
    spec_document: Optional[str] = None,
) -> Dict[str, Any]:
    """Render the canonical model-facing context for one agent.

    The Hub's own records decide what an agent is told. Whether the Hub knows an agent is
    `agent_row is not None` — nothing else. This used to key off `declared`, meaning "present in
    the synced session config", but `project_sessions` lost both of its writers (the CLI's
    `Session.save()` push and the watchdog) in `2026-08-03-single-runtime`. Every Hub-native agent
    was therefore permanently undeclared and received a stand-down block telling it not to modify
    files, not to claim tasks, and to report to a `principal` that does not exist in a Hub-owned
    project — so agents ignored the operator's instructions and 404'd addressing a phantom peer.
    See `2026-08-06-hub-collaboration-and-conversation-fixes`.

    `session_data` is still consulted for quality gates, which have no Hub-native home yet and are
    surfaced read-only by the UI's own quality panel. It no longer decides anything about identity
    or the roster.

    `work_dir`/`isolated` describe the directory the run will execute in. They are supplied by
    `trigger_agent_directly`, which already computes them, so the text cannot disagree with the
    process. Without them an agent had no idea it was in a worktree and addressed the project root
    instead, and every such read and write was refused
    (`2026-08-06-agent-permissions-tool-schemas-and-base-knowledge`). They are optional because the
    same renderer serves `GET /agents/agent-context`, which is asked outside any run and so has no
    workspace to describe.

    `spec_document` is the specification document the operator has open in the specification
    workspace, when they have one. It is rendered only when the Hub can confirm the document
    exists for this project — the operator can only be looking at a document the inventory
    listed, so a path that resolves to no row is a stale client value, and naming it would be a
    guess. Absent, it renders nothing at all rather than a placeholder.
    """
    registered = agent_row is not None
    missing: List[str] = []

    instructions_result = await db.execute(
        select(ProjectInstructions).where(ProjectInstructions.project_id == project_id)
    )
    instructions_row = instructions_result.scalars().first()
    project_instructions = instructions_row.content if instructions_row else ""

    charter = None
    if agent_row and agent_row.charter_id:
        candidate = await db.get(Charter, agent_row.charter_id)
        if candidate is not None and candidate.project_id == project_id:
            charter = candidate

    project_row = await db.get(Project, project_id)

    # The roster is the part that makes collaboration possible at all: an agent cannot message a
    # peer whose name it was never told. Read it from the Hub's own tables, binding each agent to
    # its runner so the entry can state what that peer actually runs.
    #
    # Archived peers are left out. Naming one here would be worse than unhelpful: sending to an
    # archived agent is refused, so the roster would be inviting a turn that can only fail.
    roster_result = await db.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.lifecycle == "open")
    )
    roster = sorted(roster_result.scalars().all(), key=lambda row: row.name)
    runners_result = await db.execute(select(Runner).where(Runner.project_id == project_id))
    roster_runners = {row.id: row for row in runners_result.scalars().all()}

    lines = []
    if registered:
        lines.append(f"# {agent} - AgentWeave Runtime Context")
    else:
        lines.append(f"# {agent} - AgentWeave Onboarding Context")
    lines.append("")
    lines.append("## Project Operating Profile")
    lines.append("")
    project_name = (project_row.name if project_row else None) or project_id
    lines.append(f"- Project: {project_name}")
    # Deliberately no pointer to `.agentweave/context/<agent>.md`. Its contents *are* this text,
    # already delivered as the system prompt, and following that pointer is what produced the
    # first permission denial of the operator's 2026-08-06 test.
    lines.append("")

    if work_dir:
        lines.append("### Your workspace")
        lines.append(f"- Working directory: `{work_dir}`")
        if isolated:
            lines.append(
                f"- This is an isolated git worktree on branch `{worktrees.branch_name(agent)}`."
            )
            lines.append(
                "- Other agents work in separate worktrees on their own branches. You cannot see "
                "their changes, and they cannot see yours until branches are merged."
            )
        else:
            lines.append("- This is the project's shared checkout, not an isolated worktree.")
        lines.append(
            "- Resolve every path against this directory. Files outside it are normally refused."
        )
        lines.append("")

    # Where the operator is looking, when they are looking at a specification document. Stated as
    # context for what they ask, never as an instruction: the operator sending "why does this say
    # that?" from the specification workspace means the open document, and without this line the
    # agent has no way to know which one.
    if spec_document:
        open_spec = (
            (
                await db.execute(
                    select(ProjectSpec).where(
                        ProjectSpec.project_id == project_id,
                        ProjectSpec.path == spec_document,
                    )
                )
            )
            .scalars()
            .first()
        )
        if open_spec is not None:
            lines.append("### Open specification document")
            lines.append(f"- The operator is viewing `{open_spec.path}` in the Hub's Spec view.")
            lines.append(
                "- This is where they are looking right now. Treat it as context for what they "
                "ask, not as an instruction to act on it."
            )
            lines.append("")

    lines.append("### Team")
    if roster:
        for row in roster:
            meta = dict(row.config or {})
            bound = roster_runners.get(row.runner_id)
            if bound is not None:
                meta["runner"] = bound.cli
                if bound.model:
                    meta["model"] = bound.model
            marker = " <- you" if row.name == agent else ""
            lines.append(f"- `{row.name}`: {_runner_summary(meta)}{marker}")
        lines.append("")
        lines.append(
            "Address a peer by the exact name above when sending a message or assigning a task."
        )
    else:
        lines.append("- No other agents are registered in this project yet.")
    lines.append("")

    quality = (session_data or {}).get("quality") or {}
    if quality:
        docs_path = quality.get("docs_path") or ".agentweave/code-docs"
        lines.append("### Quality Gates")
        lines.append(f"- docs_threshold: `{quality.get('docs_threshold', 'never')}`")
        lines.append(f"- docs_path: `{docs_path}/<task-id>.md`")
        lines.append(f"- review_required: `{str(bool(quality.get('review_required'))).lower()}`")
        lines.append(f"- echo_chamber_guard: `{quality.get('echo_chamber_guard', 'off')}`")
        lines.append(f"- attribution_tag: `{str(bool(quality.get('attribution_tag'))).lower()}`")
        lines.append(f"- dependency_check: `{str(bool(quality.get('dependency_check'))).lower()}`")
        lines.append("")

    if project_instructions:
        lines.append("## Project Instructions")
        lines.append("")
        lines.append(project_instructions)
        lines.append("")

    if registered:
        lines.append("## Communication Mode")
        lines.append("")
        lines.append(
            "Use the outbound path named in the turn prompt: injected AgentWeave tools or "
            "their ordinary command equivalents. Inbound state is already supplied."
        )
        lines.append("")
        lines.extend(_tool_surface_lines())
    else:
        lines.append("## Registration")
        lines.append("")
        lines.append("You are not registered with AgentWeave yet.")
        lines.append("Ask the operator to register or configure this agent before taking work.")
        lines.append("")
        missing.append("agent registration")

    if charter:
        lines.append(f"## Charter: {charter.name}")
        lines.append("")
        lines.append(charter.content)
        lines.append("")
    else:
        lines.append("## Charter")
        lines.append("")
        lines.append("No charter is assigned to this agent.")
        lines.append("")
        missing.append("charter")

    context = "\n".join(lines).rstrip() + "\n"
    # `declared`/`provisional` are kept for existing clients, but Hub registration is now the only
    # thing that decides them — there is no separate "declared in agentweave.yml" state to report.
    return {
        "agent": agent,
        "known": registered,
        "declared": registered,
        "registered": registered,
        "provisional": not registered,
        "charter_id": charter.id if charter else None,
        "charter_name": charter.name if charter else None,
        "missing": sorted(set(missing)),
        "metadata": {
            "context_path": f".agentweave/context/{agent}.md" if registered else None,
            "source": "hub",
        },
        "context": context,
    }


@router.post("/request", status_code=status.HTTP_201_CREATED)
async def request_agent(
    body: AgentRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Create a budgeted agent from a configured template and queue its first turn.

    The source identity is derived from the bound running Run. Neither the MCP tool nor
    the command endpoint accepts a caller-supplied requester identity.
    """
    project_id, _ = project
    try:
        worktrees.validate_agent_name(body.name)
        worktrees.validate_agent_name(body.template)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    source_run = await session.get(Run, body.run_id)
    if (
        source_run is None
        or source_run.project_id != project_id
        or source_run.status != "running"
        or source_run.turn_depth is None
    ):
        raise HTTPException(
            status_code=409, detail="Agent request run identity is invalid or stale"
        )

    session_data = await _get_session_data(project_id, session) or {}
    templates = session_data.get("agents", {}) or {}
    template_config = templates.get(body.template)
    if not isinstance(template_config, dict):
        raise HTTPException(
            status_code=400,
            detail=f"Agent template '{body.template}' is not pre-approved for this project",
        )

    existing_rows = (
        (await session.execute(select(Agent).where(Agent.project_id == project_id))).scalars().all()
    )
    existing_names = set(templates) | {row.name for row in existing_rows}
    if body.name in existing_names:
        raise HTTPException(status_code=409, detail=f"Agent '{body.name}' already exists")

    project_row = await session.get(Project, project_id)
    if project_row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if len(existing_names) >= project_row.agent_budget:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Project agent budget exhausted ({len(existing_names)}/"
                f"{project_row.agent_budget})"
            ),
        )

    copied_config = dict(template_config)
    copied_config.pop("principal", None)
    agent_row = Agent(
        id=f"agent-{short_id()}",
        project_id=project_id,
        name=body.name,
        contact_mode="watchdog-spawn",
        self_registered=False,
        config=copied_config,
        color_index=await next_color_index(session, project_id),
        created_by_run_id=source_run.id,
    )
    hop_depth = source_run.turn_depth + 1
    # A peer asked for this agent to exist; the thread it opens with is that peer's, not the
    # operator's, even though no message has been sent through the messaging path yet.
    conversation = new_conversation(project_id=project_id, agent=body.name, origin="peer")
    message = Message(
        id=f"msg-{short_id()}",
        project_id=project_id,
        sender=source_run.agent,
        recipient=body.name,
        subject=f"Agent request from {source_run.agent}",
        content=body.task,
        type="delegation",
        task_id=None,
        # Recorded association, not inferred (task 8.3) — same as messages.py's
        # create_message.
        session_id=source_run.session_id,
        conversation_id=source_run.conversation_id,
        created_by_run_id=source_run.id,
    )
    entry: InboundQueueEntry = new_entry(
        project_id=project_id,
        agent=body.name,
        origin_type="agent",
        origin_agent=source_run.agent,
        content=body.task,
        hop_depth=hop_depth,
        message_id=message.id,
        conversation_id=conversation.id,
    )
    session.add_all([agent_row, conversation, message, entry])
    await session.commit()

    payload = {
        "agent": body.name,
        "template": body.template,
        "requester": source_run.agent,
        "run_id": source_run.id,
        "queue_entry_id": entry.id,
        "hop_depth": hop_depth,
        "conversation_id": conversation.id,
    }
    await persist_event(session, project_id, "agent_requested", payload, agent=source_run.agent)
    await sse_manager.broadcast(project_id, "agent_requested", payload)
    await persist_event(session, project_id, "queue_entry_queued", payload, agent=body.name)
    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)

    from ...turn_scheduler import schedule_agent

    await schedule_agent(project_id, body.name)
    return {**payload, "status": "queued"}


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
    mcp_endpoint = body.get("mcp_endpoint")
    spawn_cmd = body.get("spawn_cmd")
    config = body.get("config") or {}

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        worktrees.validate_agent_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if contact_mode not in _CONTACT_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid contact_mode '{contact_mode}'. Valid: {', '.join(_CONTACT_MODES)}",
        )

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
            color_index=await next_color_index(session, project_id),
        )
        session.add(agent_row)

    await session.commit()

    rendered = await _render_hub_agent_context(
        agent=name,
        project_id=project_id,
        db=session,
        session_data=session_data,
        agent_row=agent_row,
    )
    return {"charter_id": agent_row.charter_id, "context": rendered["context"]}


# How long an agent may be told to wait on the operator. The floor stops a wait so short the card
# has barely rendered; the ceiling is well past anything measured. What *was* measured is narrower:
# the permission-prompt tool tolerated at least 150s and an ordinary MCP tool call at least 240s,
# and both were the spike's own limits rather than a proven ceiling. Values above those are allowed
# and untested, which the settings row says out loud.
MIN_WAITING_SECONDS = 10
MAX_WAITING_SECONDS = 600
WAITING_SETTING_FIELDS = ("permission_timeout_seconds", "question_timeout_seconds")

# Access grants, separate from the policy overrides: one governs *when* a checkpoint is taken,
# the other *who may read* one. Both closed by default.
CHECKPOINT_GRANT_FIELDS = ("can_read_checkpoints", "can_recall")

CHECKPOINT_OVERRIDE_FIELDS = (
    "checkpoint_mode",
    "checkpoint_threshold_mode",
    "checkpoint_threshold_value",
    "checkpoint_notes_value",
)


def _apply_checkpoint_override(agent_row: Agent, body: Dict[str, Any]) -> None:
    """Apply an agent's checkpoint override, as a whole threshold or not at all.

    An override replaces mode and value **together**. Accepting one without the other lets an
    agent inherit `percent` from its project and supply `150`, producing a threshold of 150% that
    can never fire — and the agent would look configured while behaving as though it were not.
    Clearing is symmetrical: both go back to NULL, and the project's threshold applies again.
    """
    touches_threshold = any(
        field in body for field in ("checkpoint_threshold_mode", "checkpoint_threshold_value")
    )
    if touches_threshold:
        mode = body.get("checkpoint_threshold_mode")
        value = body.get("checkpoint_threshold_value")
        if mode is None and value is None:
            agent_row.checkpoint_threshold_mode = None
            agent_row.checkpoint_threshold_value = None
            agent_row.checkpoint_notes_value = None
        else:
            if mode is None or value is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "checkpoint_threshold_mode and checkpoint_threshold_value must be set "
                        "together; half a threshold is not a partial setting"
                    ),
                )
            error = threshold_error(mode, value)
            if error:
                raise HTTPException(status_code=400, detail=error)
            agent_row.checkpoint_threshold_mode = mode
            agent_row.checkpoint_threshold_value = value

    if "checkpoint_notes_value" in body:
        notes = body["checkpoint_notes_value"]
        if notes is not None:
            threshold = agent_row.checkpoint_threshold_value
            if threshold is None:
                raise HTTPException(
                    status_code=400, detail="a notes point needs a threshold to sit below"
                )
            if not isinstance(notes, int) or isinstance(notes, bool) or notes >= threshold:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "the notes point must be a positive whole number below the checkpoint "
                        "threshold, or notes are written from the context the checkpoint exists "
                        "to escape"
                    ),
                )
        agent_row.checkpoint_notes_value = notes

    if "checkpoint_mode" in body:
        mode = body["checkpoint_mode"]
        # NULL is "inherit the project's", which is a real and common choice, so it is accepted
        # rather than coerced to "off".
        if mode is not None and mode not in CHECKPOINT_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"checkpoint_mode must be null or one of {list(CHECKPOINT_MODES)}",
            )
        agent_row.checkpoint_mode = mode


# Matches the column. Long enough for a line that says what the agent is for, short enough that it
# stays a label rather than becoming a second charter written where nothing reads it.
MAX_DESCRIPTION_CHARS = 256


def _validated_description(value: object) -> Optional[str]:
    """Coerce a description, or refuse it.

    Blank collapses to NULL rather than being stored as "": the two are the same state to every
    reader, and keeping both would mean every consumer has to test for both.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="description must be text")
    trimmed = value.strip()
    if not trimmed:
        return None
    if len(trimmed) > MAX_DESCRIPTION_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"description must be at most {MAX_DESCRIPTION_CHARS} characters",
        )
    return trimmed


# The posture that means "no restraint" — the one value that has to stay reconciled with the
# legacy `config["yolo"]` flag, because that flag is what `runner_commands` and `codex_appserver`
# already read and what the collaboration-readiness check already tests.
FULL_ACCESS_PERMISSION_MODE = "bypassPermissions"


def _validated_permission_mode(value: object) -> Optional[str]:
    """Coerce a default posture, or refuse it. `None` means the built-in default.

    Validated against the catalog's declared postures rather than against the agent's bound
    runner: an agent may have no runner bound, and rebinding one must not silently invalidate a
    default the operator already chose.
    """
    if value is None:
        return None
    permitted = {item.id for item in permission_mode_values()}
    if not isinstance(value, str) or value not in permitted:
        raise HTTPException(
            status_code=400,
            detail=("default_permission_mode must be one of: " + ", ".join(sorted(permitted))),
        )
    return value


def _apply_default_permission_mode(agent_row: Agent, value: object) -> None:
    """Set the agent's default posture, and keep `config["yolo"]` saying the same thing.

    `yolo` is not a second setting to maintain — it is the older, two-valued spelling of this
    one, and it is what `runner_commands._build_claude_command`, `codex_appserver._thread_policy`
    and the collaboration-readiness check at `get_agents_launchability` actually read. Leaving
    the two free to disagree produces the specific incoherence of an agent running under "Ask me"
    while `yolo` suppresses the `--allowedTools` allowlist its own MCP tools need.

    Clearing the posture therefore clears `yolo` as well: "no default" means the built-in
    default, which is what the settings row says, and an agent that silently stayed at full
    access after the operator cleared full access would be the worst reading of that.
    """
    posture = _validated_permission_mode(value)
    agent_row.default_permission_mode = posture
    agent_row.config = {
        **(agent_row.config or {}),
        "yolo": posture == FULL_ACCESS_PERMISSION_MODE,
    }


def _validated_waiting_seconds(field: str, value: object) -> Optional[int]:
    """Coerce one waiting setting, or refuse it.

    Validated here rather than only in the UI: this endpoint takes a raw dict, so without this a
    bad value reaches the column and surfaces later as a run that waits a nonsense length of time.
    `None` clears the setting back to the built-in default.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(status_code=400, detail=f"{field} must be a whole number of seconds")
    if not MIN_WAITING_SECONDS <= value <= MAX_WAITING_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field} must be between {MIN_WAITING_SECONDS} and {MAX_WAITING_SECONDS} seconds"
            ),
        )
    return value


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

    # Reject collision with configured agents — except for the fields the CLI's legacy
    # session-sync config never owned. runner_id/charter_id are runner-agent-charter-separation
    # fields; the waiting settings are newer still. A configured agent needs all of them settable
    # exactly like a self-registered one — an agent does not wait differently for the operator
    # because of how it was declared.
    _unrestricted_fields = {
        "runner_id",
        *CHECKPOINT_GRANT_FIELDS,
        "charter_id",
        "description",
        "default_permission_mode",
        *CHECKPOINT_OVERRIDE_FIELDS,
        *WAITING_SETTING_FIELDS,
    }
    session_data = await _get_session_data(project_id, session)
    if (
        session_data
        and name in session_data.get("agents", {})
        and not set(body.keys()) <= _unrestricted_fields
    ):
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
        if contact_mode not in _CONTACT_MODES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid contact_mode '{contact_mode}'. Valid: {', '.join(_CONTACT_MODES)}",
            )
        agent_row.contact_mode = contact_mode

    if "description" in body:
        agent_row.description = _validated_description(body["description"])

    if "mcp_endpoint" in body:
        agent_row.mcp_endpoint = body["mcp_endpoint"]
    if "spawn_cmd" in body:
        agent_row.spawn_cmd = body["spawn_cmd"]

    if "runner_id" in body:
        runner_id = body["runner_id"]
        if runner_id is not None:
            runner_row = await session.get(Runner, runner_id)
            if runner_row is None or runner_row.project_id != project_id:
                raise HTTPException(status_code=404, detail=f"Runner '{runner_id}' not found")
        agent_row.runner_id = runner_id

    if "charter_id" in body:
        charter_id = body["charter_id"]
        if charter_id is not None:
            charter_row = await session.get(Charter, charter_id)
            if charter_row is None or charter_row.project_id != project_id:
                raise HTTPException(status_code=404, detail=f"Charter '{charter_id}' not found")
        agent_row.charter_id = charter_id

    for field in WAITING_SETTING_FIELDS:
        if field in body:
            setattr(agent_row, field, _validated_waiting_seconds(field, body[field]))

    # Merge config if provided
    if "config" in body:
        new_config = body["config"] or {}
        agent_row.config = {**(agent_row.config or {}), **new_config}

    # After the config merge, deliberately: a body carrying both must end with the two agreeing,
    # and the posture is the newer spelling of the same choice, so it is the one that wins.
    if "default_permission_mode" in body:
        _apply_default_permission_mode(agent_row, body["default_permission_mode"])

    _apply_checkpoint_override(agent_row, body)

    for grant in CHECKPOINT_GRANT_FIELDS:
        if grant in body:
            value = body[grant]
            if not isinstance(value, bool):
                raise HTTPException(status_code=400, detail=f"{grant} must be true or false")
            setattr(agent_row, grant, value)

    agent_row.updated = datetime.now(timezone.utc)
    await session.commit()

    return {
        "id": agent_row.id,
        "name": agent_row.name,
        "description": agent_row.description,
        "contact_mode": agent_row.contact_mode,
        "self_registered": agent_row.self_registered,
        "mcp_endpoint": agent_row.mcp_endpoint,
        "spawn_cmd": agent_row.spawn_cmd,
        "config": agent_row.config,
        "runner_id": agent_row.runner_id,
        "charter_id": agent_row.charter_id,
        "permission_timeout_seconds": agent_row.permission_timeout_seconds,
        "question_timeout_seconds": agent_row.question_timeout_seconds,
        "default_permission_mode": agent_row.default_permission_mode,
        **{field: getattr(agent_row, field) for field in CHECKPOINT_OVERRIDE_FIELDS},
        **{field: getattr(agent_row, field) for field in CHECKPOINT_GRANT_FIELDS},
    }


@router.get("/context")
async def get_charter_context(
    charter: str = Query(..., min_length=1, max_length=64),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get one charter's authored content by stable identifier."""
    project_id, _ = project
    charter_row = await session.get(Charter, charter)
    if charter_row is None or charter_row.project_id != project_id:
        raise HTTPException(status_code=404, detail=f"Charter '{charter}' not found")
    instructions_result = await session.execute(
        select(ProjectInstructions).where(ProjectInstructions.project_id == project_id)
    )
    instructions_row = instructions_result.scalars().first()
    content = charter_row.content
    if instructions_row and instructions_row.content:
        content = instructions_row.content + "\n\n---\n\n" + content
    return {
        "content": content,
        "hint": "Use get_agent_context(agent) for full project and onboarding context.",
    }


@router.get("/agent-context")
async def get_agent_runtime_context(
    agent: str = Query(..., min_length=1, max_length=32),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get full runtime or onboarding context for an agent name."""
    if not _AGENT_NAME_RE.match(agent):
        raise HTTPException(status_code=400, detail="Invalid agent name")

    project_id, _ = project
    session_data = await _get_session_data(project_id, session)
    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = result.scalars().first()
    return await _render_hub_agent_context(
        agent=agent,
        project_id=project_id,
        db=session,
        session_data=session_data,
        agent_row=agent_row,
    )


async def _owned_agent(session: AsyncSession, project_id: str, name: str) -> Agent:
    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == name)
    )
    agent_row = result.scalars().first()
    if agent_row is None:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")
    return agent_row


@router.post("/{name}/archive")
async def archive_agent(
    name: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Archive an agent, or refuse with the reason it cannot be archived yet.

    There is deliberately no counterpart that deletes one. See `agent_lifecycle`.
    """
    project_id, _ = project
    agent_row = await _owned_agent(session, project_id, name)

    obstruction = await agent_archivable(session, agent_row)
    if obstruction is not None:
        raise HTTPException(status_code=409, detail=obstruction)

    archive_agent_row(agent_row)
    await session.commit()
    await session.refresh(agent_row)
    return {"name": agent_row.name, "lifecycle": agent_row.lifecycle}


@router.post("/{name}/unarchive")
async def unarchive_agent(
    name: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Reopen an archived agent. Never refused — reopening obstructs nothing."""
    project_id, _ = project
    agent_row = await _owned_agent(session, project_id, name)

    unarchive_agent_row(agent_row)
    await session.commit()
    await session.refresh(agent_row)
    return {"name": agent_row.name, "lifecycle": agent_row.lifecycle}


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
    row = await record_agent_output(
        session,
        project_id,
        name,
        content=body.content,
        session_id=body.session_id,
        kind=body.kind,
        payload=body.payload,
        run_id=body.run_id,
        sequence=body.sequence,
    )
    return {"id": row.id}


@router.post("/{name}/context-usage", status_code=status.HTTP_201_CREATED)
async def post_context_usage(
    name: str,
    body: ContextUsageCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Store and project the latest canonical context snapshot for an agent."""
    project_id, _ = project
    payload = body.model_dump(exclude_none=True)
    result = await record_context_usage(session, project_id, name, payload)
    if result == "ignored":
        return {"status": "ignored", "agent": name, "reason": "stale"}
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
            # Was: "Run `/aw-checkpoint` to save your session state" — a skill AgentWeave has
            # never installed, followed by "re-read your checkpoint", a file nothing wrote.
            # The Hub now generates checkpoints itself, so the only thing worth asking the agent
            # for is what its record cannot hold.
            "**Context management: Compact requested**\n\n"
            "1. Call `submit_checkpoint_notes` with what this conversation's record cannot "
            "show: what you are mid-way through, what you suspect but have not verified, and "
            "what a successor should not repeat. Skip the files, tasks and open questions — "
            "the Hub already has those.\n"
            "2. Run `/compact` in your session.\n"
            "3. Carry on. The Hub keeps the checkpoint; you do not need to re-read anything."
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
            # Same dead reference as the compact request above, and the same correction: the
            # successor is handed a Hub-generated checkpoint as a queued entry, so nothing here
            # depends on the agent writing or finding a file.
            "**Context management: New session requested**\n\n"
            "1. Call `submit_checkpoint_notes` with what this conversation's record cannot "
            "show: work in flight, unverified suspicions, and warnings for whoever continues.\n"
            "2. The operator will start a fresh session for you.\n"
            "3. It will be given a checkpoint the Hub generates from this conversation's "
            "record — you do not need to write or save one."
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
    cursor_requested = False
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            q = q.where(AgentOutput.timestamp > since_dt)
            cursor_requested = True
        except ValueError:
            pass
    if cursor_requested:
        q = q.order_by(
            AgentOutput.timestamp.asc(),
            func.coalesce(AgentOutput.sequence, -1).asc(),
            AgentOutput.id.asc(),
        ).limit(limit)
        result = await session.execute(q)
        return result.scalars().all()

    q = q.order_by(
        AgentOutput.timestamp.desc(),
        func.coalesce(AgentOutput.sequence, -1).desc(),
        AgentOutput.id.desc(),
    ).limit(limit)
    result = await session.execute(q)
    return list(reversed(result.scalars().all()))
