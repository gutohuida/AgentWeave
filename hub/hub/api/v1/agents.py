"""Agent monitor endpoints."""

import asyncio
import contextlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, get_args

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import bound_address, project_workspace, spec_documents, spec_lifecycle, worktrees
from ...agent_activity import latest_activity_by_agent
from ...agent_colors import next_color_index
from ...agent_lifecycle import archivable as agent_archivable
from ...agent_lifecycle import archive as archive_agent_row
from ...agent_lifecycle import unarchive as unarchive_agent_row
from ...agent_status import effective_heartbeat_status, heartbeat_is_stale
from ...auth import get_project
from ...checkpoint_policy import CHECKPOINT_MODES, threshold_error
from ...codex_appserver import APP_SERVER_OPT_OUT_FLAG, uses_app_server
from ...context_readings import usable_context_reading as _usable_context_reading
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
    Run,
    Runner,
    Task,
)
from ...inbound_queue import new_entry
from ...launchability import get_agent_config, probe_agent
from ...model_catalog import (
    FULL_ACCESS_PERMISSION_MODE,
    get_provider,
    permission_mode_values,
)
from ...output_recording import record_agent_output, record_context_usage
from ...review_turn import ReviewContext
from ...schemas.agents import (
    AgentHeartbeatCreate,
    AgentOutputCreate,
    AgentOutputResponse,
    AgentSummary,
    AgentTimeline,
    AgentTimelineEvent,
    ContextUsageCreate,
    RunFacts,
)
from ...schemas.common import RequestModel
from ...sse import sse_manager
from ...task_transitions import LIVE_STATUSES
from ...utils import persist_event, short_id

router = APIRouter(prefix="/agents", tags=["agents"])

_24H = timedelta(hours=24)
# One derived set, shared with `checkpoints._LIVE_TASK_STATUSES`, which held the identical
# five statuses in a separate literal until `loop-notices-and-reacts` 3.8. Two copies of one
# answer is the drift shape all three of this product's loop stall bugs came out of.
_ACTIVE_TASK_STATUSES = tuple(sorted(LIVE_STATUSES))
_AGENT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")
_CONTACT_MODES = ("poll", "mcp-push", "watchdog-spawn")


class AgentRequest(RequestModel):
    name: str = Field(min_length=1, max_length=32)
    template: str = Field(min_length=1, max_length=32)
    task: str = Field(min_length=1, max_length=100_000)
    run_id: str = Field(min_length=1, max_length=64)


class OperatorAgentCreate(RequestModel):
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
    hub_address_known = bound_address.known()

    results = {}
    for name in session_agents_meta:
        merged = await get_agent_config(project_id, name, session)
        agent_row = db_agents.get(name)
        runner_row = None
        if agent_row is not None and agent_row.runner_id is not None:
            runner_row = await session.get(Runner, agent_row.runner_id)

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

    # F17: when each agent was last observed doing anything — runs and output, not only the
    # heartbeat rows that a Hub-spawned agent never writes. See `agent_activity` for why the
    # heartbeat-only reading made every managed agent read "No activity yet" forever.
    activity_by_agent = await latest_activity_by_agent(
        session, project_id, agent_names, heartbeats=latest_hbs
    )

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
                last_seen=activity_by_agent.get(agent_name),
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
                # Built by hand, so a grant added to the schema and not added here reads back as
                # its default no matter what the row says — and the operator sees a switch they
                # set turn itself off.
                can_accept_evidence=bool(agent_row.can_accept_evidence) if agent_row else False,
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


@router.get("/{name}/timeline", response_model=AgentTimeline)
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
    events = events[:50]

    # Design D3: the run facts are looked up by the ids the *returned* events name, after the
    # merge and after the truncation — so the map describes exactly the runs the response talks
    # about. A primary-key lookup, deliberately with no ORDER BY and no LIMIT: the id set is the
    # bound. Do not turn this back into a fourth concurrent query ranked by `started_at` and
    # capped (rounds 1 and 2 specified one; round 3 reversed it). A limit governs how many rows
    # return, not which, and `run_reconciliation.reconcile_interrupted_runs` writes an old run's
    # terminal event at Hub-restart time — so an agent's newest events routinely name its oldest
    # runs, which is precisely what a start-time ranking drops.
    #
    # The `project_id` predicate is enforcement, not inference. The ids do come from rows this
    # route already filtered, so the query would be safe without it — but the map is a new
    # cross-project leak surface, `test_bola.py` covers this route because that matters, and
    # `ix_runs_project_agent` makes the predicate free.
    run_ids = set()
    for event in events:
        run_id = (event.data or {}).get("run_id")
        if isinstance(run_id, str) and run_id:
            run_ids.add(run_id)

    runs: Dict[str, RunFacts] = {}
    if run_ids:
        run_res = await session.execute(
            select(Run).where(Run.project_id == project_id, Run.id.in_(run_ids))
        )
        for run in run_res.scalars():
            runs[run.id] = RunFacts(
                # D5: one rename at the boundary; every other value is the row's own.
                status="started" if run.status == "running" else run.status,
                exit_code=run.exit_code,
                started_at=run.started_at,
                ended_at=run.ended_at,
            )

    return AgentTimeline(events=events, runs=runs)


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


# Tools the server serves that `_tool_surface_lines` deliberately does not describe, each with the
# reason. An entry here is a decision someone recorded; anything served and absent from both is a
# line nobody wrote, and `test_tool_surface_matches_server.py` refuses it.
UNDESCRIBED_TOOLS = {
    "approve_tool_call": (
        "A runtime endpoint the harness invokes on the agent's behalf, not a capability the agent "
        "has. Calling it accomplishes nothing and grants nothing, and listing it would misrepresent "
        "what the agent is for."
    ),
    "submit_checkpoint_notes": (
        "Named in the checkpoint prompt itself, at the moment it applies. Describing it on every "
        "turn would invite it on turns that are not checkpoints."
    ),
}


def _tool_surface_lines(*, has_peers: bool = True) -> List[str]:
    """Describe every tool an agent can call, with the values its constrained parameters take.

    `has_peers` is False in a project with one agent. The closing sentence otherwise points at
    "the roster above", and in that case there is no roster above to point at — the Team section is
    omitted entirely (task 13.9). The tools themselves stay described either way, because they stay
    callable: `request_agent` is in fact how a single-agent project stops being one.

    Naming a tool without its accepted values is what produced the Codex failure: the turn
    preamble listed four tool names and nothing else, so agents guessed `message_type="text"` and
    were rejected. Four job tools were never mentioned at all. Constrained values are taken from
    `mcp_server`'s own `Literal` aliases, so this cannot drift from the schema clients receive.

    `mcp_server.approve_tool_call` is deliberately absent and must stay absent. It is registered
    on the same server for convenience but is a runtime endpoint the harness invokes, not a
    capability the agent has: calling it accomplishes nothing and grants nothing. This section
    exists to tell an agent what it can deliberately use.

    Every other served tool must appear here or in `UNDESCRIBED_TOOLS` below, and
    `test_tool_surface_matches_server.py` fails the build otherwise. That test exists because this
    list has now fallen behind the server twice. The second time cost a completed interview: an
    agent was instructed by the phase block to call `submit_spec_document`, found no such tool in
    this section, concluded *"the required `submit_spec_document` capability was not exposed in this
    session"*, and stopped without writing the document it had just spent three rounds designing.
    A silently incomplete inventory is worse than none, because the agent believes it.
    """
    from ...mcp_server import (
        JobSessionMode,
        MessageType,
        SpecKind,
        TaskPriority,
        TaskStatus,
    )

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
        "- `ask_user(questions)` — put a **decision** to the operator and **wait** for it. This is "
        "for a genuine fork: real alternatives, and you cannot sensibly continue until you know "
        "which. It blocks your turn, and every question needs options, so it is a decision tool "
        "rather than the way you ask things generally — an open question, or one whose answer you "
        "cannot enumerate, belongs in your reply, where the operator can tell you something you "
        "did not think to ask about. Do not ask what the repository or the task already answers.",
        "  `questions` is a list of 1 to 4. Ask everything you need in one call: the operator "
        "steps through them in a single sitting, which interrupts them once instead of once per "
        "question. Each entry needs `question`, `header`, `options` and `multi_select`, all "
        "required. `header` is two or three words naming the decision. `options` "
        'is 2 to 8 entries of `{"label", "description"}` — the label comes back to you, and '
        "the description is what lets the operator choose without already knowing the trade-off, "
        "so write what picking it actually means rather than restating the label. There is no "
        "way to ask without options — which is the signal that a question with no real alternatives "
        "is not one for this tool. Manufacturing plausible-looking options for an open question is "
        "how an interview turns into a quiz; ask it in your reply instead. `multi_select` is true "
        "when several can be chosen together, and that answer "
        "then arrives as a list. The operator can always reply in their own words instead, so "
        "handle an answer that is none of yours.",
        "- `get_answer(question_id)` — only needed for a question you asked with "
        "`blocking=False`; a normal `ask_user` has already returned the answer.",
        "- `create_spec_document(title=None)` — start a specification document yourself; you do "
        "not need the operator to start it. Returns a placeholder `path` (meaningless — a colour "
        "and a mythic animal) and `phase`. Always a `change-spec`, always `exploring`; there is no "
        "`kind` or `path` argument to set either. Call `rename_spec_document` once you know the "
        "subject, then `submit_spec_document` with the renamed path.",
        f"- `submit_spec_document(path, title, kind, summary, problem, design, lifecycle, scope, "
        f"requirements, acceptance_criteria, tasks, algorithms, evidence, open_questions)` — write "
        f"the specification document the operator has open. `kind` is one of {values(SpecKind)}. "
        "Only `path`, `title` and `kind` are required; the rest fill in as the document takes "
        "shape. You pass the structure as these arguments — there is no single payload argument, "
        "and no argument takes prerendered markup. The Hub validates what you send, mints "
        "requirement identifiers and renders the file, so never write specification HTML "
        "yourself. Submitting an incomplete document is expected while exploring: what is missing "
        "comes back to you as `blocking`, and is a list of what to ask about next rather than an "
        "error. There is no argument that sets a phase or approves — those are the operator's.",
        "- `rename_spec_document(path, subject)` — a document is created before anyone knows what "
        "it is about, so it starts with a meaningless placeholder name. `subject` is plain words "
        "describing what it turned out to cover; the Hub derives the path. Returns the new path, "
        "which is the one to use for the rest of the turn.",
        "- `read_spec_document(path)` — read a specification document. **Use this before writing "
        "code against one.** The document lives in the project directory, not in your working "
        "copy, so you probably cannot open it as a file; working from someone's summary of it is "
        "how an implementation stops matching what was approved. Each requirement comes back with "
        "the `FR-n` identifier the Hub minted, its statement, and its own acceptance criteria — "
        "quote those identifiers, because tasks, evidence and completion gates all refer to them. "
        "Readable at any phase, and `phase` tells you how settled it is.",
        "- `record_evidence(identifier, summary)` — record what demonstrates that a requirement "
        "is satisfied, as `FR-1`. **This is what lets approved work merge**: approving a task "
        "integrates nothing until evidence for its requirements has been accepted, and the "
        "operator is simply told there is nothing to merge. It enters `awaiting` — what you record "
        "is a claim until somebody else decides on it.",
        "- `list_evidence(identifier, review_state)` — the evidence this project holds, with who "
        "produced each row and which branch and commit it was taken from. `review_state=awaiting` "
        "is what is waiting on somebody.",
        "- `decide_evidence(evidence_id, decision, reason)` — accept or reject somebody else's "
        "evidence; `decision` is `accepted` or `rejected`. Only if the operator has granted you "
        "this, and never on evidence you produced yourself.",
        "- `list_checkpoints(agent=None)` — the conversation summaries you may open: your own, "
        "and any peer's the operator has granted you. Each row carries the id the next tool takes.",
        "- `read_checkpoint(checkpoint_id)` — one of those in full, as an agent continuing that "
        "conversation would receive it. Read a peer's before you review or continue their work "
        "rather than re-deriving what they already decided.",
        "- `recall(observation_id)` — read back one observation by its identifier. Only if the "
        "operator has granted you this; without it, an observation another agent recorded returns "
        "not-found whether or not it exists. Your own are always yours to read.",
        "- `request_agent(name, template, task)` — governed; subject to the project agent budget.",
        f"- `create_job(name, agent, message, cron, session_mode=new)` — session_mode is one of "
        f"{values(JobSessionMode)}. Requires the operator's scheduled-work allowance.",
        "- `toggle_job(job_id, enabled)`, `run_job(job_id)` — same allowance.",
        "- `archive_job(job_id)` — same allowance for the capability, but always puts this exact "
        "call to the operator and waits for an explicit answer, whatever this run's permission "
        "posture is. The allowance alone is not enough — it is what makes the call reachable, not "
        "a standing yes. Refused if the job has a loop: a loop is archived by the operator only.",
        '- `create_loop(name, agent, message, cron, purpose="", stop_at=None, '
        "stop_when_queue_empties=False, work_needs_evidence=None, spec_document_id=None, "
        "initial_tasks=None)` — a job that "
        "also queues its own work, each firing claiming the queue's current task. Refused with no "
        "HTTP call made unless at least one of `stop_at` or `stop_when_queue_empties` is given: a "
        "loop that cannot stop is not created, and refused if `spec_document_id` is given: a loop "
        "that declares a document is a flow. `work_needs_evidence` says whether approving one of "
        "this loop's tasks may write its work to the project's main branch without a reviewer "
        "having accepted evidence for it; left unset, a loop with no document merges the task's "
        "own branch. It is fixed at creation and cannot be changed afterwards. `initial_tasks` "
        "seeds the queue at creation, each "
        "entry the same shape `create_task` takes. Same allowance as `create_job`.",
        '- `create_flow(name, agent, message, spec_document_id, cron, purpose="", stop_at=None, '
        "stop_when_queue_empties=False, work_needs_evidence=None, initial_tasks=None)` — a loop "
        "that decomposes an approved "
        "specification document. Same row and same allowance as `create_loop`; what differs is the "
        "queue behaviour. Each firing starts every task whose prerequisites are met and for which "
        "an agent is free, so independent work runs in parallel, and a task somebody finished "
        "becomes claimable by anybody except its author — which is how work is reviewed without "
        "the author being asked to hand it over. `agent` is the default, not the mandate. Refused "
        "if `work_needs_evidence` is given: a flow's requirements are its evidence chain, so "
        "accepted evidence always decides what approving one of its tasks merges.",
        "",
        (
            "Address a peer by its exact name from the roster above. There is no inbox tool: "
            "everything addressed to you already appears in this turn."
            if has_peers
            else "You are the only agent in this project. There is no inbox tool: everything "
            "addressed to you already appears in this turn."
        ),
        "",
    ]


# What the agent owes the operator in each phase. Five lines, code-owned, and deliberately not in
# the charter: §1.8 of the spec-Hub exploration makes the charter optional, so anything load-bearing
# placed there would be load-bearing only when someone remembered to bind it. The charter carries
# the *skill* at interviewing; this carries the *obligation* to do it.
SPEC_PHASE_DUTIES = {
    "exploring": (
        "- Interview before writing. Ask about the problem, who it affects, what is out of scope, "
        "and the cases nobody has raised. Ground what you claim in the codebase rather than "
        "guessing. Do not implement anything.\n"
        "- **Interview in your reply, not through a tool.** Write your questions out, lay the "
        "plausible directions side by side with what each makes easier and harder, and say what "
        "reading the code established. Then end your turn and let the operator answer in the "
        "composer. That is where they volunteer the constraint nobody asked about, which is most "
        "of what an exploration is for — a list of questions with fixed answers can only collect "
        "what you already thought to ask.\n"
        "- Use `ask_user` only for a genuine fork: real alternatives, and you cannot sensibly "
        "continue until you know. It blocks your turn, so spend it on a decision rather than on "
        "a question you could have asked in a sentence.\n"
        "- Sketch when it makes something easier to see than a paragraph — a workflow, a boundary, "
        "a before and after. A few lines of plain text beat a wall of prose."
    ),
    "proposed": (
        "- This document is proposed and awaiting the operator's decision. Do not implement it, "
        "and do not treat it as approved."
    ),
    "approved": (
        "- This document is approved. Implement against it; a material change to what was approved "
        "needs the operator to reopen it, not a rewrite."
    ),
}


async def _render_hub_agent_context(
    *,
    agent: str,
    project_id: str,
    db: AsyncSession,
    session_data: Optional[dict],
    agent_row: Optional[Agent],
    work_dir: Optional[str] = None,
    isolated: bool = False,
    workspace_branch: Optional[str] = None,
    isolation_unavailable: bool = False,
    spec_document: Optional[str] = None,
    task_spec_document: Optional[str] = None,
    task_id: Optional[str] = None,
    review: Optional[ReviewContext] = None,
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

    `workspace_branch` is the third of that set and arrives for the same reason (task 6.5): the
    branch the run will actually be on. Since per-task isolation that is not derivable from the
    agent's name — a task-bound turn stands on `agentweave/task/<id>` — and this renderer stating
    it independently is how it came to tell agents something untrue about their own checkout.

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
        if review is not None:
            # The other half of design D4. The boundary already put this agent somewhere it cannot
            # damage the author's checkout; what it cannot do is stop the agent deciding it is here
            # to build. Said first, before anything about branches, because everything below reads
            # differently once you know you are reviewing.
            lines.append(
                "- **This is a review turn. You are reviewing someone else's work, not doing your "
                "own.**"
            )
            lines.append(
                f"- Under review: task `{review.task_id}` — {review.task_title}, at commit "
                f"`{review.commit_sha}`"
                + (f" from branch `{review.branch}`." if review.branch else ".")
            )
            lines.append(
                "- This directory is a detached checkout of that commit. `git status` will say "
                "`HEAD detached` — that is correct and expected, not a problem to fix."
            )
            lines.append(
                "- Read it, search it, and **run its test suite**. Verifying the evidence yourself "
                "is the reason you were given a checkout rather than a diff."
            )
            lines.append(
                "- Do not fix what you find. Report it. The author makes the change, through "
                "`revision_needed` — a reviewer that edits the work has reviewed its own work."
            )
            # Finding F45. The turn above already says what to do about work that is wrong and
            # said nothing at all about work that is right, so a reviewer finding no fault had no
            # stated way to end -- and measured across this Hub, none of them ever did: not one
            # flow-dispatched review had recorded a transition. Both edges are named here, and
            # both are legal, because the firing enters the task at `under_review` rather than
            # leaving it in `completed`, from which neither was reachable.
            lines.append(
                "- **End the review with a verdict, using `update_task`.** The task is "
                "`under_review`: set it to `approved` if the work is right, or `revision_needed` "
                "if it is not. Leaving it where it is ends your turn without a review having "
                "happened, and the work waits for a person."
            )
            lines.append(
                "- Your own working checkout is outside this turn's boundary. You are not in it "
                "and cannot reach it from here."
            )
            if review.work_moved:
                # Design D5: told, not silently handed the newest. An agent that knows the work
                # moved can ask why; one that does not cannot.
                moved = ", ".join(
                    f"`{c.commit_sha}` ({c.evidence_id})" for c in review.earlier_commits
                )
                lines.append(
                    f"- Earlier evidence for this task named a different commit: {moved}. You have "
                    "the most recent one. If that difference matters to your verdict, ask."
                )
        elif isolated:
            # Task 6.5. `workspace_branch` is supplied by the caller from the same dispatch that
            # chose the directory, for the reason `work_dir` is: this used to hardcode
            # `branch_name(agent)`, and from phase 4B onwards it told every task-bound turn it was
            # on `agentweave/<agent>` while the process stood on `agentweave/task/<id>`. Falls back
            # to the agent branch only for callers with no run to describe — `GET
            # /agents/agent-context`, which is asked outside any turn.
            branch = workspace_branch or worktrees.branch_name(agent)
            lines.append(f"- This is an isolated git worktree on branch `{branch}`.")
            if branch.startswith(worktrees.TASK_BRANCH_PREFIX):
                # Said because the agent will otherwise reason about this directory as its own and
                # be wrong in both directions: it will not find its earlier unbound work here, and
                # it will assume nobody else will ever stand where it is standing.
                lines.append(
                    "- **This checkout belongs to the task, not to you.** Whoever works this task "
                    "next continues in this same directory on this same branch, and it is "
                    "released once the task is approved or rejected."
                )
            lines.append(
                "- Other work is in separate checkouts on separate branches — other agents, other "
                "tasks, and your own turns that are not this one. You cannot see those changes, "
                "and they cannot see yours until branches are merged."
            )
        elif isolation_unavailable:
            # Said rather than left to be discovered. The sentence above is true for a read-only
            # agent too, and stopping there leaves an agent to find out there is no repository by
            # running git and reading the failure as a broken machine.
            lines.append(
                "- This directory is not a git repository, so there is no isolated worktree and "
                "no branch of your own. Do not expect git to work here, and do not offer to "
                "commit or branch."
            )
            lines.append(
                "- Any other agent in this project works in this same directory. Your edits and "
                "theirs can overwrite each other with no conflict to resolve, so prefer small, "
                "complete changes over long-running edits across many files."
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
    # What the bound task implements. A **different claim** from the block below, and rendered
    # separately for that reason: that one says where the operator happens to be looking and tells
    # the agent not to act on it, which is exactly backwards here — this document *is* the
    # instruction.
    #
    # Suppressed when the operator has the same document open, so the stronger framing wins rather
    # than being restated beside the weaker one.
    if task_spec_document and task_spec_document != spec_document:
        task_phase = None
        with contextlib.suppress(Exception):
            row = await spec_lifecycle.get_document(db, project_id, task_spec_document)
            task_phase = row.phase if row is not None else None

        lines.append("### The specification this task implements")
        if task_id:
            lines.append(
                f"- This turn is bound to `{task_id}`, which implements `{task_spec_document}`."
            )
        else:
            lines.append(f"- The task you are working on implements `{task_spec_document}`.")
        lines.append(
            f"- Read it with `read_spec_document('{task_spec_document}')`. It is not in your "
            "working copy, so this is how you see what it actually says — working from a summary, "
            "or from another agent's description, is how an implementation stops matching what "
            "was approved."
        )
        if task_phase:
            lines.append(f"- Phase: **{task_phase}**.")
            duty = SPEC_PHASE_DUTIES.get(task_phase, "")
            if duty:
                lines.append(duty)
        lines.append("")

    if spec_document:
        # The document is the file on disk, so its existence is a filesystem question. A project
        # whose directory is unavailable simply contributes no line here — an unavailable workspace
        # is reported where the run is triggered, and failing context assembly over it would turn a
        # missing document into a failed turn.
        open_spec_path: Optional[str] = None
        try:
            workspace = await project_workspace.resolve_project_workspace(db, project_id)
            if spec_documents.document_exists(workspace, spec_document):
                open_spec_path = spec_document
        except (project_workspace.ProjectWorkspaceError, OSError):
            open_spec_path = None

        if open_spec_path is not None:
            phase = None
            is_unwritten = False
            with contextlib.suppress(Exception):
                row = await spec_lifecycle.get_document(db, project_id, open_spec_path)
                phase = row.phase if row is not None else None
                is_unwritten = row is not None and not row.requirement_digests

            lines.append("### Open specification document")
            lines.append(f"- The operator is viewing `{open_spec_path}` in the Hub's Spec view.")
            if phase == "exploring" and is_unwritten:
                # F51: an empty exploring document, freshly created by "start exploration", IS the
                # instruction — it exists, per the button's own purpose, so that pressing it creates
                # the document to be written into. The general "treat it as context, not an
                # instruction" framing below is correct for an unrelated document happening to be
                # open, and wrong here: it was followed correctly and produced a second, orphaned
                # document every time (measured live, `spdoc-9c8691592be1` stayed `requirements: []`
                # forever while a same-run `create_spec_document` call built the real one).
                lines.append(
                    "- **This document is empty and is what you are interviewing for.** When you "
                    f"call `submit_spec_document`, pass `path='{open_spec_path}'` — do not call "
                    "`create_spec_document`, one already exists for this turn."
                )
            else:
                lines.append(
                    "- This is where they are looking right now. Treat it as context for what they "
                    "ask, not as an instruction to act on it."
                )
            # Named here as well as in the tool list, because this is the moment it applies. A tool
            # that is served and undiscovered at the point of use is the same failure as one that
            # was never served: an agent concluded it had no way to read the document and worked
            # from a paraphrase instead.
            lines.append(
                f"- Read it with `read_spec_document('{open_spec_path}')`. It is not in your "
                "working copy, so this is how you see what it actually says."
            )
            # The procedure floor. Code-owned and unconditional, because a project may have no
            # charter bound and the obligation to interview is an exit condition, not advice —
            # a charter makes the work better and must never be what makes it valid.
            if phase:
                lines.append(f"- Phase: **{phase}**.")
                lines.append(SPEC_PHASE_DUTIES.get(phase, ""))
                lines.append(
                    "- Write the document with `submit_spec_document`. Never write specification "
                    "HTML yourself; the Hub renders it and assigns requirement identifiers."
                )
                lines.append(
                    "- You cannot propose or approve. Those are the operator's, and there is no "
                    "argument that does either."
                )
                # The exit condition, stated as one (F38). Measured 2026-08-25: the author
                # diagnosed the bug correctly and unprompted, then asked four well-judged questions
                # as chat text in a turn that completed — no question row, nothing blocking, and
                # the specification never written. Its charter already named `ask_user` six times,
                # so the instruction existed and the tool worked; what was missing was anything
                # saying that ending the turn was not one of the ways to finish.
                lines.append(
                    "- **Ending this turn without either submitting the document or calling "
                    "`ask_user` is not a way to finish.** Questions written as ordinary reply text "
                    "reach nobody: the turn ends, nothing is recorded, and the operator is not "
                    "waiting for you. If you need an answer before you can write, ask for it with "
                    "the tool."
                )
                # Precedence, not just procedure. Saying *how* to author a document does not settle
                # *which authority governs it*, and until this was stated an agent read the block,
                # understood it, and still opened with "I'm going to use the OpenSpec proposal
                # workflow" — because a skill whose description matched the operator's own opening
                # sentence had already answered the question by the time this paragraph was weighed.
                #
                # Deliberately names no product (D5): a blocklist dates the moment a different tool
                # is installed and implies the unnamed ones are fine. And deliberately says what to
                # *do* with the thing it found (D2) — an agent told only "don't" is holding a fact
                # with nowhere to put it, and the tool belongs to the operator anyway.
                lines.append(
                    "- This procedure is the one that governs this document. No other "
                    "specification workflow, skill, command or tool applies to it — including one "
                    "installed on this machine and one you have used before."
                )
                lines.append(
                    "- If you find another specification workflow here, say so to the operator and "
                    "let them decide about it. Do not follow it, and do not adopt its format or "
                    "its file layout for this document."
                )
                lines.append(
                    "- Reading such a workflow's files as context about the project is fine. What "
                    "is not is authoring this document through anything but `submit_spec_document`."
                )
            lines.append("")

    # A project with nobody else in it gets no Team section at all — not a Team section saying the
    # team is empty. `roster` includes the agent being addressed (that is what the `<- you` marker
    # is for), so "is anyone else here" is a question about peers, not about the roster's length.
    #
    # The old `else` branch printed "No other agents are registered in this project yet." on every
    # single-agent turn. Naming the absence is worse than saying nothing: it puts collaboration in
    # the agent's head, invites it to wonder who it should be waiting for, and costs context on
    # every turn of the journey a first-time user actually takes.
    peers = [row for row in roster if row.name != agent]
    if peers:
        lines.append("### Team")
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

    # A capability an agent does not know it holds is one it does not use, and one it guesses at is
    # a 403 in the middle of a turn it has already spent. This is the `submit_spec_document`
    # failure mode exactly: served, correct, and invisible.
    if agent_row is not None and getattr(agent_row, "can_accept_evidence", False):
        lines.append("### You can decide evidence")
        lines.append(
            "- The operator has granted you authority to accept or reject requirement evidence. "
            "Accepted evidence is what allows approving a task to merge the work, so this is a "
            "judgement about what ships, not a formality."
        )
        lines.append(
            "- `list_evidence(review_state='awaiting')` is what is waiting on somebody; "
            "`decide_evidence(evidence_id, decision, reason)` answers it. You cannot decide "
            "evidence you produced yourself."
        )
        lines.append("")
    else:
        # The other half of the comment above, and the half that was missing (F32). Measured
        # 2026-08-25: a reviewer spent a full 97-row turn — a genuine review, running the suite
        # twice and writing a reproducer — and only then discovered it could not record the
        # verdict. `list_evidence` had succeeded moments earlier, so it could read the queue it was
        # not permitted to answer, and nothing said so.
        #
        # Saying where the verdict goes instead is not politeness. Unable to record it, that
        # reviewer wrote the review to a file inside its own worktree, which is isolated by design
        # — so its actual conclusion, "ship it", landed on a branch nobody reads.
        lines.append("### You cannot decide evidence")
        lines.append(
            "- Accepting or rejecting requirement evidence is the operator's here. "
            "`decide_evidence` will refuse you, so do not spend a turn planning around it."
        )
        lines.append(
            "- `list_evidence` still works, and showing you the queue is not an invitation to "
            "answer it — you can see what is waiting on somebody without being that somebody."
        )
        lines.append(
            "- If you reviewed something, put the verdict where it will be read: send it as a "
            "message, or record it on the task. A review written only into your worktree is on a "
            "branch nobody reads."
        )
        lines.append("")

    # F39: the same reasoning again, for the pair the F32 audit found announced in neither
    # direction. `can_read_checkpoints` and `can_recall` are separate grants (`checkpoint_access`:
    # "summary access is not transcript access"), but an agent only ever meets them as one
    # question — how much of a peer's history can I see — so they are stated together and named
    # individually.
    #
    # Stated even when both are withheld, and that is the half worth defending. The failure this
    # closes is not an agent missing a capability; it is an agent reading a checkpoint that cites
    # observation ids, calling `recall` on one, getting not-found, and concluding the record is
    # missing rather than that it is not permitted to see it. Not-found is deliberately
    # indistinguishable from absent — it must be, or the refusal would itself confirm the record
    # exists — which is exactly why the boundary has to be stated up front instead of discovered.
    if agent_row is not None:
        may_read = bool(getattr(agent_row, "can_read_checkpoints", False))
        may_recall = bool(getattr(agent_row, "can_recall", False))
        lines.append("### Other agents' history")
        if may_read:
            lines.append(
                "- You may read your peers' checkpoints — the summaries an agent leaves when its "
                "conversation is cut over — where those are shared with the project. "
                "`list_checkpoints()` is how you find them and `read_checkpoint(id)` opens one."
            )
        else:
            lines.append(
                "- You may read your own checkpoints and no one else's: `list_checkpoints()` "
                "returns yours alone. A peer's is not withheld from you by accident, so do not "
                "go looking for a way around it."
            )
        if may_recall:
            lines.append(
                "- `recall(observation_id)` returns a cited observation verbatim, for the "
                "checkpoints you may read. Use it rather than guessing at what a summary "
                "compressed away."
            )
        else:
            lines.append(
                "- `recall` will not return another agent's observations to you. It answers "
                "not-found rather than refusing, so treat a not-found on an id a checkpoint "
                "cited as this boundary and not as a missing record — asking the agent that "
                "recorded it is the way through."
            )
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
        lines.extend(_tool_surface_lines(has_peers=bool(peers)))
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

# Every boolean capability the operator confers, which is what the PATCH loop and the response are
# built from. `can_accept_evidence` is deliberately **not** folded into the checkpoint pair: those
# two widen what an agent may read, and this one decides whether work is allowed to merge. Grouping
# them would tell the operator that authority over what ships is a kind of reading.
#
# The column and its migration have existed since `0068`. Nothing could set it — no schema, no
# route, no control — so `requirement_evidence.may_accept` refused every agent in every project,
# and a capability enforced everywhere and grantable nowhere is a refusal of everyone.
GRANT_FIELDS = (*CHECKPOINT_GRANT_FIELDS, "can_accept_evidence")

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
        *GRANT_FIELDS,
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

    runner_newly_bound = False
    if "runner_id" in body:
        runner_id = body["runner_id"]
        if runner_id is not None:
            runner_row = await session.get(Runner, runner_id)
            if runner_row is None or runner_row.project_id != project_id:
                raise HTTPException(status_code=404, detail=f"Runner '{runner_id}' not found")
        runner_newly_bound = runner_id is not None and runner_id != agent_row.runner_id
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

    for grant in GRANT_FIELDS:
        if grant in body:
            value = body[grant]
            if not isinstance(value, bool):
                raise HTTPException(status_code=400, detail=f"{grant} must be true or false")
            setattr(agent_row, grant, value)

    agent_row.updated = datetime.now(timezone.utc)
    await session.commit()

    if runner_newly_bound:
        # Binding a runner is the repair the refusal names, so it has to be a redrain site — the
        # same shape `POST /relocate` already has for "project workspace is unavailable". Without
        # it, an operator who does exactly what the product told them to do ("No runner is bound
        # to this agent. Bind one in the Hub UI before it can run.") is left with the message
        # still queued, and a status that no longer even mentions the runner because the retry
        # counter has taken the reason's place. Measured live 2026-08-28 (F96): the entry sat
        # untouched across a rebind and every subsequent poll, and was then delivered by an
        # unrelated `PUT /settings` — proving it had been deliverable the whole time.
        #
        # `schedule_agent` rather than `redrain_queued_agents`: this repair is agent-scoped, and
        # it is a no-op ("queue is empty") for the overwhelmingly common case of binding a runner
        # to an agent nobody has written to yet.
        from ...turn_scheduler import schedule_agent

        await schedule_agent(project_id, name)

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
        **{field: getattr(agent_row, field) for field in GRANT_FIELDS},
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
        queued_ids = list(
            (
                await session.execute(
                    select(InboundQueueEntry.id).where(
                        InboundQueueEntry.project_id == project_id,
                        InboundQueueEntry.agent == name,
                        InboundQueueEntry.state == "queued",
                    )
                )
            ).scalars()
        )
        if queued_ids:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f"{name} has {len(queued_ids)} queued message"
                        f"{'s' if len(queued_ids) != 1 else ''}. Discard them to archive the agent."
                    ),
                    "blocking_queue_entry_count": len(queued_ids),
                    "blocking_queue_entry_ids": queued_ids,
                },
            )
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
    if result == "unchanged":
        return {"status": "ignored", "agent": name, "reason": "unchanged"}
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
