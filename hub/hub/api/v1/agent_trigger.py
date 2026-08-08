"""Agent trigger endpoint — POST /api/v1/agent/trigger

Spawns the target agent's CLI directly and returns a real run identifier immediately.
Claude Code uses a pseudo-terminal (`pty_runner.PtySession`); Codex's non-interactive
``exec --json`` uses a hidden pipe process (`pty_runner.PipeSession`). Output streams live
over the existing SSE channel (`agent_output`, `context_warning`) through the same recording
path a self-reporting agent already uses (`output_recording.py`).

This replaces the message-tag protocol (Decision 2): no synthetic `Message` row, no
`[Session: ...]` / `[NewSession]` text tags, no `execution_confidence` guess about whether
some other process might eventually pick the request up. Session identity is a typed field
on the run record (`Run.session_id`), never text embedded in a message body.

Only claude/claude_proxy/native and codex are wired to an actual spawn path today —
`runner_commands.py`'s scope. Kimi, OpenCode, and Copilot are refused with a stated 501 rather than
silently mishandled. There is no fallback runtime for them. Extending the Hub adapter list to cover
every runner is future work.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import bound_address, instance_identity, project_workspace, worktrees
from ...agent_auth import hash_run_token, mint_run_token
from ...auth import get_project
from ...codex_appserver import (
    TRANSPORT_SENTINELS,
    AppServerError,
    TurnOutcome,
    uses_app_server,
)
from ...codex_appserver import run_turn as codex_run_turn
from ...conversation_titles import maybe_generate_title
from ...conversations import (
    conversation_for_provider_session,
    conversation_id_for_run,
    get_open_conversation,
    name_conversation,
    new_conversation,
)
from ...db.engine import async_session_factory, get_session
from ...db.models import Agent, Conversation, PermissionRequest, Run, Runner
from ...inbound_queue import deliver_entries_with_run, new_entry, return_run_entries
from ...launchability import (
    access_path_notice,
    get_agent_config,
    probe_agent,
    resolve_access_path,
    resolve_agent_env,
)
from ...model_catalog import WORKSPACE_PERMISSION_MODE, validate_overrides
from ...output_recording import record_agent_output, record_context_usage
from ...pty_runner import (
    STRUCTURED_OUTPUT_DIMENSIONS,
    PipeSession,
    PtySession,
    strip_ansi_escapes,
    terminate_process_tree,
)
from ...runner_commands import (
    OPERATOR_POSTURE,
    SUPPORTED_RUNNERS,
    UnsupportedRunnerError,
    build_command,
)
from ...runner_events import AccountingSample
from ...runner_parsing import (
    parse_claude_line,
    parse_codex_line,
    read_codex_rollout_accounting,
)
from ...sse import sse_manager
from ...unasked_question import trailing_question
from ...usage_accounting import record_turn_usage
from ...utils import persist_event, short_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent-trigger"])

# A running background task with no other strong reference can be garbage-collected by
# asyncio mid-execution (a well-documented footgun) — this set keeps each run's task alive
# until it finishes, regardless of the triggering request's own lifecycle.
_background_runs: set = set()

# Live process session per in-progress run_id, so a stop request can reach the actual
# process. `_execute_run` populates/clears this around its own read/wait loop, since that is
# the only place the PTY-or-pipe session instance exists. The legacy internal name remains
# to avoid churning lifecycle code that does not depend on the transport type.
_active_ptys: Dict[str, PipeSession | PtySession] = {}
# run_ids currently executing over the Codex app-server transport (task 2.8). This path has
# no PtySession/PipeSession to register in `_active_ptys` — `codex_appserver.run_turn` owns
# its own subprocess internally — so the stop endpoint and shutdown teardown need a separate
# way to know such a run exists and is interruptible.
_active_app_server_runs: set = set()
# run_ids whose stop was requested via the endpoint below. `_execute_run`'s own completion
# handling reads this once the process exits to tell "stopped deliberately" (final status
# "stopped") apart from "crashed/exited non-zero on its own" (final status "failed") — the
# exit code alone can't distinguish the two once a forced terminate is involved. The
# app-server path also polls this set directly (`run_turn`'s `should_interrupt`), since it has
# no process handle to terminate from the outside.
_stop_requested: set = set()

# How long a Codex approval waits for the operator, and how often it re-reads the decision.
# Codex holds its JSON-RPC request open throughout; unlike Claude's tool call there is no
# provider-side ceiling measured here, so this matches the Claude approver's budget rather than
# inventing a longer one.
CODEX_OPERATOR_DECISION_TIMEOUT = 120
CODEX_OPERATOR_POLL_SECONDS = 2


class TriggerAgentRequest(BaseModel):
    agent: str = Field(..., max_length=64, description="Target agent name (e.g., 'claude')")
    message: str = Field(..., max_length=10000, description="Prompt to send to the agent")
    conversation_id: Optional[str] = Field(default=None, max_length=64)
    session_mode: Optional[str] = Field(
        default=None, max_length=64, description="Deprecated legacy field"
    )
    session_id: Optional[str] = Field(
        default=None, max_length=128, description="Required when session_mode='resume'"
    )
    work_dir: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Project-relative working directory for the agent process (read-only "
        "agents only; refused for a writing agent, which always gets its isolated worktree)",
    )
    overrides: Optional[Dict[str, str]] = Field(
        default=None,
        description="Runtime control overrides (e.g. {'model': 'claude-opus-5', "
        "'effort': 'high'}), validated against the model catalog and persisted onto the "
        "conversation before it is scheduled.",
    )


class TriggerAgentResponse(BaseModel):
    success: bool
    message: str
    agent: str
    run_id: Optional[str] = None
    status: str
    conversation_id: str
    provider_session_id: Optional[str] = None
    session_id: Optional[str] = None
    queue_entry_id: Optional[str] = None
    waiting_reason: Optional[str] = None


class TriggerAgentError(Exception):
    """Raised by `trigger_agent_directly` on any pre-flight rejection.

    Deliberately not `HTTPException` — this function has no FastAPI-request coupling so
    task 3.10's scheduled-job caller (`scheduler.py`) can call it directly. The `/trigger`
    route below catches this and converts it back to an `HTTPException` for HTTP callers.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        workspace_unavailable: bool = False,
        directory_state: Optional[str] = None,
    ) -> None:
        self.status_code = status_code
        self.detail = detail
        self.workspace_unavailable = workspace_unavailable
        self.directory_state = directory_state
        super().__init__(detail)


async def trigger_agent_directly(
    *,
    project_id: str,
    agent: str,
    message: str,
    conversation_id: str,
    work_dir: Optional[str] = None,
    session: AsyncSession,
    queue_entry_ids: Optional[List[str]] = None,
    turn_depth: Optional[int] = None,
    initiator: str = "operator",
) -> TriggerAgentResponse:
    """Validate and spawn *agent* directly, returning its run identifier.

    The core of what `POST /agent/trigger` does (see that route below), factored out so a
    scheduled job (`scheduler.py`, task 3.10) goes through the exact same direct-execution
    path a manual trigger does — no synthetic `Message` for the watchdog to later detect and
    re-trigger, which is the same class of indirection Decision 2 already removed from the
    manual-trigger path in task 3.5. Raises `TriggerAgentError` on any rejection.
    """
    from sqlalchemy import select

    try:
        worktrees.validate_agent_name(agent)
    except ValueError as exc:
        raise TriggerAgentError(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    conversation = await get_open_conversation(
        session,
        project_id=project_id,
        agent=agent,
        conversation_id=conversation_id,
    )
    if conversation is None:
        raise TriggerAgentError(status.HTTP_409_CONFLICT, "Conversation is unavailable")

    agent_row_result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = agent_row_result.scalars().first()
    if agent_row is None or agent_row.runner_id is None:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"{agent} has no runner bound. Bind one via PATCH "
            f"/api/v1/projects/{project_id}/agents/{agent} "
            "(runner_id) or the Hub UI before triggering.",
        )
    runner_row = await session.get(Runner, agent_row.runner_id)
    if runner_row is None:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT, f"{agent}'s bound runner no longer exists."
        )

    config = await get_agent_config(project_id, agent, session)
    # The bound Runner record is now the sole source of which CLI/model to launch —
    # legacy config-dict runner/model keys (from session-synced or self-registered
    # config) are superseded, not merged. See
    # openspec/changes/runner-agent-charter-separation/specs/runner-registry/spec.md.
    config["runner"] = runner_row.cli
    config["model"] = runner_row.model
    probe = probe_agent(agent, config)
    runner = probe["runner"]

    # Checked before launchability: whether we know how to spawn this runner at all is a
    # more fundamental, permanent gate than whether its CLI happens to be on PATH right
    # now, and keeps the response deterministic regardless of what's installed on the Hub
    # host (an unimplemented runner is still unimplemented even if its CLI is present).
    if runner not in SUPPORTED_RUNNERS:
        raise TriggerAgentError(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"Direct spawn for runner {runner!r} is not implemented yet "
            f"(supported: {', '.join(SUPPORTED_RUNNERS)}). "
            "This runner has no Hub-owned execution adapter.",
        )

    if not probe["runnable"]:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT, probe["reason"] or f"{agent} is not currently launchable."
        )

    existing = await session.execute(
        select(Run.id)
        .where(Run.project_id == project_id, Run.agent == agent, Run.status == "running")
        .limit(1)
    )
    if existing.scalar() is not None:
        raise TriggerAgentError(status.HTTP_409_CONFLICT, f"{agent} already has a run in progress.")

    # Resolution order (design.md): conversation.runtime_overrides -> runner.model / runner
    # defaults -> catalog control defaults. Overrides were already validated against the
    # catalog when the operator set them (`trigger_agent`'s /trigger handler), so they are
    # trusted here rather than re-validated per turn.
    conversation_overrides = dict(conversation.runtime_overrides or {})
    model = conversation_overrides.get("model") or config.get("model")
    control_overrides = {k: v for k, v in conversation_overrides.items() if k != "model"}
    try:
        workspace_root = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"Project workspace is unavailable: {exc}",
            workspace_unavailable=True,
            directory_state=exc.directory_state,
        ) from exc
    repo_root = workspace_root.root
    yolo = bool(config.get("yolo"))
    resume_session_id = conversation.provider_session_id
    session_mode = "resume" if resume_session_id else "new"
    env = resolve_agent_env(runner, config)

    # Task 5.1/5.2: a writing agent gets its own git worktree, isolated from every other
    # agent's (Decision 7). A custom work_dir cannot override that isolation. Read-only
    # agents may retain the existing project-relative work_dir behavior.
    if work_dir and worktrees.is_writing_agent(config):
        raise TriggerAgentError(
            status.HTTP_400_BAD_REQUEST,
            "work_dir cannot override workspace isolation for a writing agent",
        )
    if work_dir:
        # Task 3.3: work_dir is resolved as a project-relative path, never an absolute
        # or escaping one — resolve_relative rejects traversal, absolute paths, control
        # characters, and symlink escapes in one place.
        try:
            effective_work_dir = str(workspace_root.resolve_relative(work_dir))
        except project_workspace.ProjectPathError as exc:
            raise TriggerAgentError(
                status.HTTP_400_BAD_REQUEST, f"Invalid work_dir: {exc}"
            ) from exc
        isolated_workspace: Optional[Path] = None
    else:
        try:
            workspace = worktrees.resolve_agent_workspace(repo_root, agent, config)
        except (worktrees.GitCommandError, worktrees.IsolationUnavailableError) as exc:
            raise TriggerAgentError(
                status.HTTP_409_CONFLICT,
                f"Could not prepare isolated worktree for {agent}: {exc}",
            ) from exc
        effective_work_dir = str(workspace)
        isolated_workspace = workspace if workspace != repo_root else None

    # Build context from current Hub-owned state for every turn. Runners consume a file,
    # so materialize the canonical response inside the effective workspace immediately
    # before command construction; an edited charter is therefore visible on the next run.
    from .agents import _get_session_data, _render_hub_agent_context

    session_data = await _get_session_data(project_id, session)
    rendered_context = await _render_hub_agent_context(
        agent=agent,
        project_id=project_id,
        db=session,
        session_data=session_data,
        agent_row=agent_row,
        # The directory the run will actually execute in. Passed rather than recomputed so the
        # text an agent reads cannot disagree with the process's own cwd — agents were resolving
        # paths against the project root while running in a worktree, and every such read and
        # write was refused.
        work_dir=effective_work_dir,
        isolated=isolated_workspace is not None,
    )
    context_file = Path(effective_work_dir) / ".agentweave" / "context" / f"{agent}.md"
    try:
        context_file.parent.mkdir(parents=True, exist_ok=True)
        context_file.write_text(rendered_context["context"], encoding="utf-8")
    except OSError as exc:
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"Could not materialize canonical context for {agent}: {exc}",
        ) from exc

    # Task 4.5: tell the agent, at turn start, which access path is in use — never offer
    # one that isn't actually available in this environment.
    access_path = resolve_access_path(runner, probe["cli"] or agent, config.get("hub_client"))
    prompt = f"{access_path_notice(access_path)}\n\n{message}"
    mcp_command = None
    if access_path == "mcp":
        canonical_server = Path(__file__).resolve().parents[2] / "mcp_server.py"
        mcp_command = [sys.executable, str(canonical_server)]

    # Codex uses the app-server transport unless the runner explicitly opts out; see
    # `uses_app_server`. Both transport sentinels are stripped before `flags` reaches
    # `build_command` — neither is a real `codex exec` argument, and either would otherwise
    # leak into that argv unchanged.
    runner_flags = list(runner_row.flags or [])
    use_codex_app_server = uses_app_server(runner, runner_flags)
    runner_flags = [f for f in runner_flags if f not in TRANSPORT_SENTINELS]

    try:
        cmd = build_command(
            runner=runner,
            cli=probe["cli"],
            prompt=prompt,
            model=model,
            context_file=context_file,
            session_id=resume_session_id,
            yolo=yolo,
            mcp_command=mcp_command,
            extra_flags=runner_flags,
            control_overrides=control_overrides,
        )
    except UnsupportedRunnerError as exc:
        raise TriggerAgentError(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc

    run_id = f"run-{short_id()}"
    run_token = mint_run_token()

    # Task 4.1: identity is established here, once, by the Hub — never asserted by the
    # agent itself. Every tool call this run makes reads AW_AGENT_IDENTITY from its own
    # process environment; no tool accepts a caller-supplied identity. `env=None` meant
    # "inherit the Hub's own environment unchanged" (resolve_agent_env's contract) — that
    # base must be preserved, not replaced, when adding these two keys.
    env = dict(env) if env is not None else dict(os.environ)
    env["AW_AGENT_IDENTITY"] = agent
    env["AW_RUN_ID"] = run_id
    env["AW_RUN_TOKEN"] = run_token
    # The boundary the "Workspace only" posture enforces. Deliberately the same
    # `effective_work_dir` passed to the context renderer above as "Your workspace": the boundary
    # the agent is *told* about and the one that is *enforced* must come from one value, or an
    # agent can be refused at a line it was never shown.
    env["AW_WORKSPACE_DIR"] = effective_work_dir
    # Which approver posture this run is under. The approval tool serves both, and only this
    # tells it whether to decide against the workspace itself or put the call to the operator.
    if (control_overrides or {}).get("permission_mode") == "manual":
        env["AW_PERMISSION_POSTURE"] = OPERATOR_POSTURE
    # How long this agent waits on the operator. Set only when configured — an absent variable is
    # what tells the tool to use its own default, so writing one unconditionally would turn every
    # agent into a configured one and freeze today's numbers.
    if agent_row.permission_timeout_seconds is not None:
        env["AW_DECISION_TIMEOUT"] = str(agent_row.permission_timeout_seconds)
    if agent_row.question_timeout_seconds is not None:
        env["AW_QUESTION_TIMEOUT"] = str(agent_row.question_timeout_seconds)
    if turn_depth is not None:
        env["AW_TURN_DEPTH"] = str(turn_depth)
    explicit_hub_url = os.environ.get("HUB_URL")
    if explicit_hub_url:
        env["HUB_URL"] = explicit_hub_url
    else:
        observed = bound_address.get()
        if observed is None:
            raise TriggerAgentError(
                status.HTTP_409_CONFLICT,
                "Cannot determine the Hub's own address for this run: no HUB_URL is set "
                "in the Hub's environment and no bound address has been observed from an "
                "incoming connection yet. Set HUB_URL explicitly, or retry once the Hub "
                "has served at least one request.",
            )
        # The agent is always spawned as a local subprocess of the Hub (native mode);
        # only the observed *port* corrects the defect (settings.aw_port can silently
        # diverge from where uvicorn actually bound). The host is always loopback.
        _, observed_port = observed
        env["HUB_URL"] = f"http://127.0.0.1:{observed_port}"
    # A parent service environment may contain operator credentials. Never pass them
    # through to a spawned run: AW_RUN_TOKEN is the run's complete authority.
    env.pop("HUB_API_KEY", None)
    env.pop("HUB_PROJECT_ID", None)

    run = Run(
        id=run_id,
        project_id=project_id,
        agent=agent,
        session_id=resume_session_id,
        conversation_id=conversation.id,
        status="running",
        turn_depth=turn_depth,
        initiator=initiator,
        capability_token_hash=hash_run_token(run_token),
        instance_id=instance_identity.get(),
    )
    delivered = []
    if queue_entry_ids:
        delivered = await deliver_entries_with_run(
            session,
            project_id=project_id,
            agent=agent,
            entry_ids=queue_entry_ids,
            run=run,
        )
    else:
        session.add(run)
        await session.commit()

    # Register execution immediately after the atomic Run + delivery commit. Event rows are
    # observability; a transient failure while writing one must never strand a running Run
    # whose queue entries are already marked delivered but which has no process task.
    task = asyncio.create_task(
        _execute_run(
            project_id=project_id,
            agent=agent,
            run_id=run_id,
            conversation_id=conversation.id,
            runner=runner,
            cmd=cmd,
            model=model,
            work_dir=effective_work_dir,
            known_session_id=resume_session_id,
            env=env,
            worktree=isolated_workspace,
            use_codex_app_server=use_codex_app_server,
            cli=probe["cli"],
            prompt=prompt,
            yolo=yolo,
            mcp_command=mcp_command,
            permission_mode=(control_overrides or {}).get("permission_mode"),
        )
    )
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)

    try:
        await persist_event(
            session,
            project_id,
            "run_triggered",
            {
                "agent": agent,
                "run_id": run_id,
                "conversation_id": conversation.id,
                "session_mode": session_mode,
                "initiator": initiator,
            },
            agent=agent,
        )
        for entry in delivered:
            payload = {
                "entry_id": entry.id,
                "agent": agent,
                "run_id": run_id,
                "conversation_id": conversation.id,
                "hop_depth": entry.hop_depth,
            }
            await persist_event(session, project_id, "queue_entry_delivered", payload, agent=agent)
            await sse_manager.broadcast(project_id, "queue_entry_delivered", payload)
    except Exception:
        logger.exception(
            "Run %s started but its trigger/delivery events could not be persisted", run_id
        )

    return TriggerAgentResponse(
        success=True,
        message=f"{agent} started (run {run_id}).",
        agent=agent,
        run_id=run_id,
        status="running",
        conversation_id=conversation.id,
        provider_session_id=resume_session_id,
        session_id=resume_session_id,
    )


@router.post("/trigger", response_model=TriggerAgentResponse)
async def trigger_agent(
    body: TriggerAgentRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Append input to an AgentWeave conversation and schedule it when possible."""
    from sqlalchemy import select

    project_id, _ = project
    try:
        worktrees.validate_agent_name(body.agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if body.session_mode is not None and body.session_mode not in ("new", "resume"):
        raise HTTPException(status_code=400, detail="session_mode must be 'new' or 'resume'")
    if body.session_mode == "resume" and not body.session_id:
        raise HTTPException(
            status_code=400, detail="session_id is required when session_mode='resume'"
        )

    try:
        workspace_root = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        project_workspace.raise_workspace_http_error(exc)

    config = await get_agent_config(project_id, body.agent, session)
    if body.work_dir and worktrees.is_writing_agent(config):
        raise HTTPException(
            status_code=400,
            detail="work_dir cannot override workspace isolation for a writing agent",
        )
    if body.work_dir:
        try:
            workspace_root.resolve_relative(body.work_dir)
        except project_workspace.ProjectPathError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid work_dir: {exc}") from exc

    conversation: Optional[Conversation] = None
    if body.conversation_id is not None:
        conversation = await get_open_conversation(
            session,
            project_id=project_id,
            agent=body.agent,
            conversation_id=body.conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=409, detail="Conversation is unavailable")
    elif body.session_mode == "resume" and body.session_id:
        conversation = await conversation_for_provider_session(
            session,
            project_id=project_id,
            agent=body.agent,
            provider_session_id=body.session_id,
        )
        if conversation is None:
            conversation = new_conversation(
                project_id=project_id, agent=body.agent, origin="operator"
            )
            conversation.provider_session_id = body.session_id
            session.add(conversation)
    else:
        # This route queues its entry as `origin_type="operator"` below; the conversation it
        # opens is the same act.
        conversation = new_conversation(project_id=project_id, agent=body.agent, origin="operator")
        session.add(conversation)

    if body.overrides:
        agent_row_result = await session.execute(
            select(Agent).where(Agent.project_id == project_id, Agent.name == body.agent)
        )
        agent_row = agent_row_result.scalars().first()
        if agent_row is None or agent_row.runner_id is None:
            raise HTTPException(
                status_code=409, detail=f"{body.agent} has no runner bound; cannot set overrides."
            )
        runner_row = await session.get(Runner, agent_row.runner_id)
        if runner_row is None:
            raise HTTPException(
                status_code=409, detail=f"{body.agent}'s bound runner no longer exists."
            )
        accepted, rejection = validate_overrides(runner_row.cli, body.overrides)
        if rejection is not None:
            raise HTTPException(status_code=400, detail=rejection.reason)
        # Overrides are stored per conversation, not per agent — the runner binding
        # this validated against is unchanged (design.md: "Rejected: overrides on the
        # agent").
        conversation.runtime_overrides = accepted

    entry = new_entry(
        project_id=project_id,
        agent=body.agent,
        origin_type="operator",
        content=body.message,
        hop_depth=0,
        session_mode=body.session_mode,
        session_id=body.session_id,
        conversation_id=conversation.id,
        work_dir=body.work_dir,
    )
    session.add(entry)
    conversation.updated_at = entry.arrived_at
    name_conversation(conversation, body.message)
    await session.commit()
    payload = {
        "entry_id": entry.id,
        "agent": body.agent,
        "conversation_id": conversation.id,
        "origin_type": "operator",
        "hop_depth": 0,
    }
    await persist_event(session, project_id, "queue_entry_queued", payload, agent=body.agent)
    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)

    from ...turn_scheduler import schedule_agent

    scheduled = await schedule_agent(project_id, body.agent)
    # The scheduler picks the conversation of the *oldest* eligible entry across this
    # agent's whole queue, which is not necessarily the conversation this request just
    # appended to (spec `agent-conversation-workspace`: "Different conversations never
    # share one provider turn"). When it picked a different one, this caller's input is
    # still queued: report that, and this request's own conversation, rather than another
    # conversation's run — the response must always describe the input it accepted (same
    # spec: "the response contains the new conversation_id whether its status is running
    # or queued").
    if scheduled.response is not None and scheduled.response.conversation_id == conversation.id:
        response = scheduled.response
        response.queue_entry_id = entry.id
        return response
    waiting_reason = scheduled.waiting_reason
    if scheduled.response is not None:
        waiting_reason = (
            "an older conversation's queued input is being delivered first "
            f"(run {scheduled.response.run_id})"
        )
    return TriggerAgentResponse(
        success=True,
        message=f"Input queued for {body.agent}.",
        agent=body.agent,
        status="queued",
        conversation_id=conversation.id,
        provider_session_id=conversation.provider_session_id,
        session_id=conversation.provider_session_id,
        queue_entry_id=entry.id,
        waiting_reason=waiting_reason,
    )


class StopAgentResponse(BaseModel):
    success: bool
    message: str
    agent: str
    run_id: str
    status: str


@router.post("/{agent}/stop", response_model=StopAgentResponse)
async def stop_agent_run(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Interrupt the agent's in-progress direct-spawn run, if any.

    Force-terminates the owned PTY process. `_execute_run`'s own read/wait loop observes
    the exit and does the actual status/broadcast bookkeeping (see `_stop_requested` above)
    — this endpoint only signals intent and terminates the process, it does not itself mark
    the Run row, since that must happen only after the process has actually exited.
    """
    from sqlalchemy import select

    project_id, _ = project

    result = await session.execute(
        select(Run)
        .where(Run.project_id == project_id, Run.agent == agent, Run.status == "running")
        .order_by(Run.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{agent} has no run in progress.",
        )

    pty = _active_ptys.get(run.id)
    if pty is not None:
        _stop_requested.add(run.id)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: pty.terminate(force=True))
    elif run.id in _active_app_server_runs:
        # No process handle to terminate directly (codex_appserver.run_turn owns the
        # subprocess internally) — `_stop_requested` is itself the signal: `run_turn`'s
        # `should_interrupt` polls this same set and sends `turn/interrupt` within one poll
        # interval (task 2.7).
        _stop_requested.add(run.id)
    else:
        # Spawned but not yet registered, or already past its read/wait loop — either way
        # there's nothing left to terminate; the run's own completion handling will settle
        # its final status shortly.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{agent}'s run is not in a stoppable state right now.",
        )

    return StopAgentResponse(
        success=True,
        message=f"Stop signal sent to {agent} (run {run.id}).",
        agent=agent,
        run_id=run.id,
        status="stopping",
    )


async def terminate_all_active_runs() -> int:
    """Terminate every currently-tracked run's process tree (task 3.9: a clean Hub
    shutdown must not leave an agent process, or anything it spawned, orphaned).

    Called from `main.py`'s `lifespan()` teardown. Deliberately does not touch any `Run`
    row's DB status — a shutdown-then-restart is picked up by `run_reconciliation.py`'s
    `reconcile_interrupted_runs()` on the next boot (task 3.8), which is the single place
    that owns transitioning a run's persisted status; duplicating that here risks the two
    disagreeing about *when* a run's status actually changes.

    An app-server run has no process handle here to kill directly — the same
    `_stop_requested` signal `stop_agent_run` uses is the only lever available, so this is
    best-effort within `run_turn`'s poll interval, not an immediate kill like the PTY/pipe
    case. `run_turn`'s own `finally` still closes its subprocess once its loop notices.

    Returns the number of runs terminated or signalled to stop.
    """
    loop = asyncio.get_running_loop()
    ptys = list(_active_ptys.values())
    for pty in ptys:
        await loop.run_in_executor(None, lambda p=pty: terminate_process_tree(p.pid, force=True))
    app_server_run_ids = list(_active_app_server_runs)
    _stop_requested.update(app_server_run_ids)
    return len(ptys) + len(app_server_run_ids)


_RUN_LIFECYCLE_EVENTS = ("run_started", "run_completed", "run_failed", "run_stopped")


async def _broadcast_run_lifecycle(
    db: AsyncSession,
    project_id: str,
    event_type: str,
    *,
    agent: str,
    run_id: str,
    **fields,
) -> None:
    """Persist + SSE-broadcast one of the typed run-lifecycle events.

    A distinct, named event per phase (rather than folding everything into the
    generic `agent_output` stream) is what lets the UI render "run started" /
    "run failed" as first-class states instead of grepping status text out of
    output lines — see design.md's Typed activity stream section.
    """
    assert event_type in _RUN_LIFECYCLE_EVENTS
    payload = {"agent": agent, "run_id": run_id, **fields}
    await persist_event(
        db,
        project_id,
        event_type,
        payload,
        agent=agent,
        severity="warn" if event_type == "run_failed" else "info",
    )
    await sse_manager.broadcast(project_id, event_type, payload)


async def _flag_unasked_question(
    *,
    project_id: str,
    agent: str,
    run_id: str,
    conversation_id: Optional[str],
    final_status: str,
) -> None:
    """Record a turn that ended on a question the agent never routed through `ask_user`.

    Measured failure this exists for: told to ask which package manager to use, Codex wrote the
    question into its final message and ended the turn. No question row was created, so the one
    person who could answer was never told a question existed, and the agent sat waiting for an
    answer that could not arrive. A tool call cannot be required by either provider's protocol, so
    the Hub reads what the run actually said instead.

    Everything here is best-effort: the run has already been recorded as finished, and a backstop
    that could turn a completed run into a failed one would be worse than the gap it closes.
    """
    try:
        # A failed or stopped run has a louder story to tell, and its trailing text is often cut
        # off mid-sentence — a fragment ending in "?" there is truncation, not a question.
        if final_status != "completed":
            return

        from sqlalchemy import select

        from ...db.models import AgentOutput, Question, UnaskedQuestion
        from ...inbound_queue import queued_entries

        async with async_session_factory() as db:
            asked = (
                await db.execute(
                    select(Question.id).where(Question.created_by_run_id == run_id).limit(1)
                )
            ).scalar_one_or_none()
            if asked is not None:
                return

            # `schedule_agent` runs moments after this and starts the next turn if anything is
            # queued, so the question is about to be answered by the next turn's input rather
            # than stranded. Uses the scheduler's own helper so the two cannot disagree.
            if await queued_entries(db, project_id, agent):
                return

            final_text = (
                await db.execute(
                    select(AgentOutput.content)
                    .where(
                        AgentOutput.project_id == project_id,
                        AgentOutput.run_id == run_id,
                        AgentOutput.kind == "text",
                    )
                    .order_by(AgentOutput.sequence.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            question = trailing_question(final_text or "")
            if not question:
                return

            record_id = f"unasked-{short_id()}"
            db.add(
                UnaskedQuestion(
                    id=record_id,
                    project_id=project_id,
                    agent=agent,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    question=question,
                    status="pending",
                )
            )
            await persist_event(
                db,
                project_id,
                "question_not_asked",
                {
                    "id": record_id,
                    "agent": agent,
                    "run_id": run_id,
                    "conversation_id": conversation_id,
                    "question": question,
                },
                agent=agent,
                severity="warn",
            )
            await db.commit()

        await sse_manager.broadcast(
            project_id,
            "question_not_asked",
            {"id": record_id, "agent": agent, "run_id": run_id, "question": question},
        )
    except Exception:  # noqa: BLE001 — a backstop must never worsen the run it observes
        logger.warning(
            "Could not check run %s for an unasked question", run_id, exc_info=True
        )


async def _execute_run(
    *,
    project_id: str,
    agent: str,
    run_id: str,
    conversation_id: str,
    runner: str,
    cmd: list,
    model: Optional[str],
    work_dir: Optional[str],
    known_session_id: Optional[str],
    env: Optional[Dict[str, str]] = None,
    worktree: Optional[Path] = None,
    use_codex_app_server: bool = False,
    cli: Optional[str] = None,
    prompt: Optional[str] = None,
    yolo: bool = False,
    mcp_command: Optional[List[str]] = None,
    permission_mode: Optional[str] = None,
) -> None:
    """Background task: spawn, capture output, persist Run/AgentOutput, broadcast SSE.

    *worktree*, when given, is this run's isolated git worktree (task 5.1) — its
    working directory *is* `work_dir` here, but `_execute_run` needs the fact that it's
    an isolated worktree specifically (not just "some cwd") to know whether to snapshot
    it once the run ends (task 5.3's conflict detection needs real commits to compare).

    *use_codex_app_server* (task 2.8) selects a completely separate execution path —
    `_execute_codex_appserver_run` below — since the app-server transport has no PTY/pipe
    subprocess for this function's own read/wait loop to drive; `cli`/`prompt`/`yolo`/
    `mcp_command` are only meaningful for that path (`cmd` was still built for it by the
    caller, but is unused here — app-server has no argv, it speaks JSON-RPC).
    """
    if use_codex_app_server:
        await _execute_codex_appserver_run(
            project_id=project_id,
            agent=agent,
            run_id=run_id,
            conversation_id=conversation_id,
            cli=cli,
            prompt=prompt,
            model=model,
            work_dir=work_dir,
            known_session_id=known_session_id,
            yolo=yolo,
            mcp_command=mcp_command,
            env=env,
            worktree=worktree,
            permission_mode=permission_mode,
        )
        return

    loop = asyncio.get_running_loop()

    try:
        if runner == "codex":
            pty = await loop.run_in_executor(
                None,
                lambda: PipeSession.spawn(cmd, cwd=work_dir, env=env),
            )
        else:
            pty = await loop.run_in_executor(
                None,
                lambda: PtySession.spawn(
                    cmd,
                    cwd=work_dir,
                    env=env,
                    dimensions=STRUCTURED_OUTPUT_DIMENSIONS,
                ),
            )
    except FileNotFoundError as exc:
        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.status = "failed"
                run.error = str(exc)
                run.ended_at = datetime.now(timezone.utc)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner=runner,
                    sample=None,
                )
            returned = await return_run_entries(db, run_id)
            await db.commit()
            await _broadcast_run_lifecycle(
                db, project_id, "run_failed", agent=agent, run_id=run_id, error=str(exc)
            )
            for entry_id in returned:
                payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
        return

    _active_ptys[run_id] = pty
    try:
        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.pid = pty.pid
                await db.commit()
            await _broadcast_run_lifecycle(
                db,
                project_id,
                "run_started",
                agent=agent,
                run_id=run_id,
                runner=runner,
                model=model,
            )

        parse_line = parse_claude_line if runner in ("claude", "claude_proxy", "native") else None

        session_id = known_session_id
        binding_conflict: Optional[str] = None
        accounting_sample: Optional[AccountingSample] = None
        sequence = 0
        buffer = ""

        async def _flush_line(raw_line: str) -> None:
            nonlocal accounting_sample, binding_conflict, session_id, sequence
            # ConPTY output is control-sequence-laden, not plain text (live-verified — see
            # pty_runner.strip_ansi_escapes's docstring) — every line needs stripping before
            # a JSON-parse attempt, not just the first (e.g. a trailing cursor-restore
            # sequence ConPTY appends after the child exits arrives as its own line).
            line = strip_ansi_escapes(raw_line.rstrip("\r"))
            if not line.strip():
                return
            parsed = (
                parse_line(line) if parse_line is not None else parse_codex_line(line, model=model)
            )
            # Resolve session_id from *this* line before writing its own events, so the row
            # that establishes the session carries it too, not just subsequent rows.
            if parsed.session_id:
                async with async_session_factory() as db:
                    run = await db.get(Run, run_id)
                    conversation = await db.get(Conversation, conversation_id)
                    if conversation is None:
                        binding_conflict = "Conversation disappeared during provider binding"
                    elif conversation.provider_session_id is None:
                        conversation.provider_session_id = parsed.session_id
                        conversation.updated_at = datetime.now(timezone.utc)
                        session_id = parsed.session_id
                    elif conversation.provider_session_id == parsed.session_id:
                        session_id = parsed.session_id
                    else:
                        binding_conflict = (
                            "Provider session binding conflict: "
                            f"expected {conversation.provider_session_id!r}, "
                            f"received {parsed.session_id!r}"
                        )
                    if run and binding_conflict is None:
                        run.session_id = session_id
                    await db.commit()
                    if binding_conflict is not None:
                        await persist_event(
                            db,
                            project_id,
                            "conversation_binding_conflict",
                            {
                                "agent": agent,
                                "run_id": run_id,
                                "conversation_id": conversation_id,
                                "error": binding_conflict,
                            },
                            agent=agent,
                            severity="warn",
                        )
                        return
            for event in parsed.events:
                sequence += 1
                async with async_session_factory() as db:
                    await record_agent_output(
                        db,
                        project_id,
                        agent,
                        content=event.content,
                        session_id=session_id,
                        conversation_id=conversation_id,
                        kind=event.kind,
                        payload=event.payload,
                        run_id=run_id,
                        sequence=sequence,
                    )
            if parsed.usage is not None:
                async with async_session_factory() as db:
                    await record_context_usage(
                        db, project_id, agent, parsed.usage.to_payload(agent)
                    )
            if parsed.accounting is not None:
                accounting_sample = (
                    parsed.accounting
                    if accounting_sample is None
                    else accounting_sample.merged(parsed.accounting)
                )

        while True:
            chunk = await loop.run_in_executor(None, pty.read)
            if not chunk:
                break
            buffer += chunk
            while "\n" in buffer:
                raw_line, buffer = buffer.split("\n", 1)
                await _flush_line(raw_line)
        if buffer.strip():
            await _flush_line(buffer)

        exit_code = await loop.run_in_executor(None, pty.wait)

        if runner == "codex" and session_id:
            codex_home = Path(env["CODEX_HOME"]) if env and env.get("CODEX_HOME") else None
            rollout_accounting = await loop.run_in_executor(
                None,
                lambda: read_codex_rollout_accounting(
                    session_id, codex_home=codex_home, model=model
                ),
            )
            if rollout_accounting is not None:
                accounting_sample = (
                    rollout_accounting
                    if accounting_sample is None
                    else accounting_sample.merged(rollout_accounting)
                )

        if worktree is not None:
            # Task 5.3 needs real commits to compare branches with `git merge-tree` —
            # an agent's turn just ends with dirty files in its worktree otherwise, which
            # a conflict check has nothing to diff against. Best-effort: a git failure here
            # must not turn a completed/failed run into something worse than it already is.
            try:
                await loop.run_in_executor(
                    None, lambda: worktrees.snapshot_worktree(worktree, agent)
                )
            except worktrees.GitCommandError:
                logger.warning(
                    "Could not snapshot %r's worktree after run %s", agent, run_id, exc_info=True
                )

        # A deliberate stop (task 3.7) also exits the read loop and reaches this same
        # point — force-terminating a process rarely yields exit code 0, so without this
        # check a stop would be misreported as "failed". Checked before the exit-code
        # branch below so a stop always wins regardless of what the process happened to
        # exit with.
        if binding_conflict is not None:
            final_status, lifecycle_event = "failed", "run_failed"
        elif run_id in _stop_requested:
            final_status, lifecycle_event = "stopped", "run_stopped"
        elif exit_code == 0:
            final_status, lifecycle_event = "completed", "run_completed"
        else:
            final_status, lifecycle_event = "failed", "run_failed"

        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.status = final_status
                run.exit_code = exit_code
                if binding_conflict is not None:
                    run.error = binding_conflict
                run.ended_at = datetime.now(timezone.utc)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner=runner,
                    sample=accounting_sample,
                )
                await db.commit()
            await _broadcast_run_lifecycle(
                db,
                project_id,
                lifecycle_event,
                agent=agent,
                run_id=run_id,
                conversation_id=conversation_id,
                session_id=session_id,
                exit_code=exit_code,
            )
            # Kept alongside the typed lifecycle event above rather than replaced by it:
            # the "Handoff" flow in AgentOutputPanel.tsx detects run completion by scanning
            # for this exact kind="status"/phase="completed" line in the output stream
            # (useAgentOutput's `lines`), not via a separate SSE listener. Removing this
            # would silently break that feature. `phase` stays "completed" even for a
            # stopped/failed run — it means "the run has ended", not "it succeeded".
            await sse_manager.broadcast(
                project_id,
                "agent_output",
                {
                    "id": f"status-{run_id}",
                    "agent": agent,
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "content": f"Run {final_status} (exit {exit_code}).",
                    "kind": "status",
                    "payload": {"phase": "completed", "exit_code": exit_code},
                    "run_id": run_id,
                    "sequence": sequence + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        # Before the scheduler, because one of the suppressions is "the queue is not empty" —
        # asking after the next turn had already started would read a queue this run's
        # successor was draining.
        await _flag_unasked_question(
            project_id=project_id,
            agent=agent,
            run_id=run_id,
            conversation_id=conversation_id,
            final_status=final_status,
        )

        # After the response has landed, so the titler sees the exchange rather than the
        # opening line alone, and so nothing the operator is waiting on is delayed by it.
        await maybe_generate_title(project_id=project_id, conversation_id=conversation_id)

        # A turn ending with queued entries starts the next turn without waiting for
        # operator input. The scheduler itself applies the hop budget and drain cap.
        from ...turn_scheduler import schedule_agent

        await schedule_agent(project_id, agent)
    finally:
        _active_ptys.pop(run_id, None)
        _stop_requested.discard(run_id)


# How Codex's approval methods read on the operator's card. The raw method names
# ("item/commandExecution/requestApproval") are protocol, not something to put in front of a
# person deciding in seconds.
_CODEX_APPROVAL_LABELS = {
    "item/commandExecution/requestApproval": "a command",
    "item/fileChange/requestApproval": "a file change",
}


def _codex_posture(permission_mode: Optional[str]) -> Optional[str]:
    """Map the operator's chosen posture onto what `decide_approval` understands.

    "manual" is the operator-answered posture for both providers; the value differs only
    because Claude's spelling is its CLI's own.
    """
    if permission_mode == "manual":
        return OPERATOR_POSTURE
    if permission_mode == WORKSPACE_PERMISSION_MODE:
        return WORKSPACE_PERMISSION_MODE
    return None


def _codex_decision_timeout(env: Optional[Dict[str, str]]) -> int:
    """This run's permission wait, from the same environment variable the Claude path uses.

    Read from `env` rather than threaded as another parameter because the trigger already put it
    there for the MCP process, and one carrier for one setting means the two transports cannot
    drift apart. Anything unparseable or out of range falls back, matching `mcp_server`'s rule.
    """
    # Imported here, not at module scope: `.agents` imports this module back.
    from .agents import MAX_WAITING_SECONDS, MIN_WAITING_SECONDS

    raw = (env or {}).get("AW_DECISION_TIMEOUT")
    if not raw:
        return CODEX_OPERATOR_DECISION_TIMEOUT
    try:
        value = int(raw)
    except ValueError:
        return CODEX_OPERATOR_DECISION_TIMEOUT
    if MIN_WAITING_SECONDS <= value <= MAX_WAITING_SECONDS:
        return value
    return CODEX_OPERATOR_DECISION_TIMEOUT


async def _await_operator_permission(
    *,
    project_id: str,
    agent: str,
    run_id: str,
    method: str,
    subject: Dict[str, object],
    timeout_seconds: Optional[int] = None,
) -> bool:
    """Open a permission request for a Codex approval and wait for the operator.

    The Codex counterpart of `mcp_server._ask_operator`, and it holds the same line: a turn is
    suspended, not failed, while this waits, so the wait is bounded and running out denies.
    Codex is waiting on a JSON-RPC response the whole time.
    """
    request_id = f"perm-{short_id()}"
    async with async_session_factory() as db:
        db.add(
            PermissionRequest(
                id=request_id,
                project_id=project_id,
                agent=agent,
                run_id=run_id,
                conversation_id=await conversation_id_for_run(db, run_id),
                tool_name=_CODEX_APPROVAL_LABELS.get(method, method),
                tool_use_id="",
                tool_input=dict(subject),
                status="pending",
            )
        )
        await db.commit()
    await sse_manager.broadcast(
        project_id,
        "permission_requested",
        {"id": request_id, "agent": agent, "tool_name": _CODEX_APPROVAL_LABELS.get(method, method),
         "run_id": run_id},
    )

    deadline = asyncio.get_event_loop().time() + (
        timeout_seconds if timeout_seconds is not None else CODEX_OPERATOR_DECISION_TIMEOUT
    )
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(CODEX_OPERATOR_POLL_SECONDS)
        async with async_session_factory() as db:
            row = await db.get(PermissionRequest, request_id)
            status_now = row.status if row is not None else "denied"
        if status_now == "allowed":
            return True
        if status_now in ("denied", "expired"):
            return False

    async with async_session_factory() as db:
        row = await db.get(PermissionRequest, request_id)
        if row is not None and row.status == "pending":
            row.status = "expired"
            await db.commit()
    return False


async def _execute_codex_appserver_run(
    *,
    project_id: str,
    agent: str,
    run_id: str,
    conversation_id: str,
    cli: str,
    prompt: str,
    model: Optional[str],
    work_dir: Optional[str],
    known_session_id: Optional[str],
    yolo: bool,
    mcp_command: Optional[List[str]],
    env: Optional[Dict[str, str]],
    worktree: Optional[Path],
    permission_mode: Optional[str] = None,
) -> None:
    """Codex `app-server` (task 2.8) counterpart to `_execute_run`'s PTY/pipe read loop above.

    `codex_appserver.run_turn` owns the actual subprocess and JSON-RPC exchange internally
    (see its own docstring); this function's job is only to wire that transport's callbacks
    to the same recording/broadcast/scheduling calls `_execute_run` makes for `exec`, so the
    two transports are indistinguishable to everything downstream of a `Run` row (task 2.5's
    stated goal) — a `Run`, its `AgentOutput` rows, its usage accounting, and its lifecycle
    broadcasts all look the same regardless of which transport produced them.
    """
    _active_app_server_runs.add(run_id)
    try:
        async with async_session_factory() as db:
            await _broadcast_run_lifecycle(
                db, project_id, "run_started", agent=agent, run_id=run_id, runner="codex", model=model
            )

        session_id = known_session_id
        binding_conflict: Optional[str] = None
        accounting_sample: Optional[AccountingSample] = None
        sequence = 0

        async def _bind_session_id(thread_id: str) -> None:
            # Mirrors `_execute_run._flush_line`'s conversation-binding logic (same
            # conflict/first-writer rules), fired once per turn instead of once per line —
            # app-server hands the Hub its session identity up front, `exec` reveals it
            # mid-stream.
            nonlocal binding_conflict, session_id
            async with async_session_factory() as db:
                run = await db.get(Run, run_id)
                conversation = await db.get(Conversation, conversation_id)
                if conversation is None:
                    binding_conflict = "Conversation disappeared during provider binding"
                elif conversation.provider_session_id is None:
                    conversation.provider_session_id = thread_id
                    conversation.updated_at = datetime.now(timezone.utc)
                    session_id = thread_id
                elif conversation.provider_session_id == thread_id:
                    session_id = thread_id
                else:
                    binding_conflict = (
                        "Provider session binding conflict: "
                        f"expected {conversation.provider_session_id!r}, received {thread_id!r}"
                    )
                if run and binding_conflict is None:
                    run.session_id = session_id
                await db.commit()
                if binding_conflict is not None:
                    await persist_event(
                        db,
                        project_id,
                        "conversation_binding_conflict",
                        {
                            "agent": agent,
                            "run_id": run_id,
                            "conversation_id": conversation_id,
                            "error": binding_conflict,
                        },
                        agent=agent,
                        severity="warn",
                    )

        async def _on_event(event) -> None:
            nonlocal sequence
            sequence += 1
            async with async_session_factory() as db:
                await record_agent_output(
                    db,
                    project_id,
                    agent,
                    content=event.content,
                    session_id=session_id,
                    conversation_id=conversation_id,
                    kind=event.kind,
                    payload=event.payload,
                    run_id=run_id,
                    sequence=sequence,
                )

        async def _on_usage(usage) -> None:
            async with async_session_factory() as db:
                await record_context_usage(db, project_id, agent, usage.to_payload(agent))

        async def _on_accounting(accounting) -> None:
            nonlocal accounting_sample
            accounting_sample = (
                accounting if accounting_sample is None else accounting_sample.merged(accounting)
            )

        try:
            outcome: TurnOutcome = await codex_run_turn(
                cli=cli,
                posture=_codex_posture(permission_mode),
                workspace=work_dir,
                request_approval=lambda method, subject: _await_operator_permission(
                    project_id=project_id,
                    agent=agent,
                    run_id=run_id,
                    method=method,
                    subject=subject,
                    timeout_seconds=_codex_decision_timeout(env),
                ),
                cwd=work_dir,
                env=env,
                prompt=prompt,
                model=model,
                resume_thread_id=known_session_id,
                yolo=yolo,
                mcp_command=mcp_command,
                on_event=_on_event,
                on_usage=_on_usage,
                on_accounting=_on_accounting,
                on_thread_started=_bind_session_id,
                should_interrupt=lambda: run_id in _stop_requested,
            )
        except (FileNotFoundError, AppServerError, asyncio.TimeoutError, OSError) as exc:
            # Mirrors `_execute_run`'s own early-spawn-failure handling: nothing was ever
            # delivered to the agent, so returned queue entries go back to "queued" rather
            # than being recorded against a run that never really started.
            async with async_session_factory() as db:
                run = await db.get(Run, run_id)
                if run:
                    run.status = "failed"
                    run.error = str(exc)
                    run.ended_at = datetime.now(timezone.utc)
                    await record_turn_usage(
                        db,
                        run_id=run_id,
                        project_id=project_id,
                        agent=agent,
                        runner="codex",
                        sample=None,
                    )
                returned = await return_run_entries(db, run_id)
                await db.commit()
                await _broadcast_run_lifecycle(
                    db, project_id, "run_failed", agent=agent, run_id=run_id, error=str(exc)
                )
                for entry_id in returned:
                    payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                    await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
            return

        if worktree is not None:
            # Same best-effort snapshot as `_execute_run` — a git failure here must not turn
            # a completed/failed run into something worse than it already is.
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, lambda: worktrees.snapshot_worktree(worktree, agent)
                )
            except worktrees.GitCommandError:
                logger.warning(
                    "Could not snapshot %r's worktree after run %s", agent, run_id, exc_info=True
                )

        # A deliberate stop reaches here as `TurnOutcome.status == "interrupted"` (run_turn's
        # own `should_interrupt` handling), the app-server equivalent of exec's
        # `run_id in _stop_requested` check — that same set is what `should_interrupt` above
        # polled to decide to send `turn/interrupt` in the first place.
        if binding_conflict is not None:
            final_status, lifecycle_event = "failed", "run_failed"
        elif outcome.status == "interrupted":
            final_status, lifecycle_event = "stopped", "run_stopped"
        elif outcome.status == "completed":
            final_status, lifecycle_event = "completed", "run_completed"
        else:
            final_status, lifecycle_event = "failed", "run_failed"
        # No process exit code exists for this transport; 0/1 keeps `Run.exit_code` and the
        # "Run {status} (exit {code})" status line meaningful to the same UI code that reads
        # them for the exec path (AgentOutputPanel's handoff-detection, see below).
        exit_code = 0 if final_status == "completed" else 1

        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.status = final_status
                run.exit_code = exit_code
                if binding_conflict is not None:
                    run.error = binding_conflict
                elif outcome.error:
                    run.error = outcome.error
                run.ended_at = datetime.now(timezone.utc)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner="codex",
                    sample=accounting_sample,
                )
                await db.commit()
            await _broadcast_run_lifecycle(
                db,
                project_id,
                lifecycle_event,
                agent=agent,
                run_id=run_id,
                conversation_id=conversation_id,
                session_id=session_id,
                exit_code=exit_code,
            )
            # Kept for the same reason as `_execute_run`'s identical broadcast: the
            # "Handoff" flow in AgentOutputPanel.tsx detects run completion by scanning for
            # this exact kind="status"/phase="completed" line, not via a separate listener.
            await sse_manager.broadcast(
                project_id,
                "agent_output",
                {
                    "id": f"status-{run_id}",
                    "agent": agent,
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "content": f"Run {final_status} (exit {exit_code}).",
                    "kind": "status",
                    "payload": {"phase": "completed", "exit_code": exit_code},
                    "run_id": run_id,
                    "sequence": sequence + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        # Same backstop, same reason, same position relative to the scheduler as the exec path
        # above. Codex is the transport this was measured failing on.
        await _flag_unasked_question(
            project_id=project_id,
            agent=agent,
            run_id=run_id,
            conversation_id=conversation_id,
            final_status=final_status,
        )
        await maybe_generate_title(project_id=project_id, conversation_id=conversation_id)

        from ...turn_scheduler import schedule_agent

        await schedule_agent(project_id, agent)
    finally:
        _active_app_server_runs.discard(run_id)
        _stop_requested.discard(run_id)


@router.get("/sessions/{agent}")
async def get_agent_sessions(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get unique session IDs for an agent from AgentOutput table.

    Returns sessions that the agent has generated output for, ordered by recency.
    Each session includes last_active (most recent output) and started_at (first output).
    """
    from sqlalchemy import func, select

    from ...db.models import AgentOutput

    project_id, _ = project

    # Group by session_id to get first and last output timestamps per session
    q = (
        select(
            AgentOutput.session_id,
            func.max(AgentOutput.timestamp).label("last_active"),
            func.min(AgentOutput.timestamp).label("started_at"),
        )
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
            AgentOutput.session_id.isnot(None),
        )
        .group_by(AgentOutput.session_id)
        .order_by(func.max(AgentOutput.timestamp).desc())
    )
    result = await session.execute(q)
    rows = result.all()

    sessions = [
        {
            "id": row.session_id,
            "type": "agent",
            "path": f".agentweave/agents/{agent}-session.json",
            "last_active": row.last_active.isoformat() if row.last_active else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
        }
        for row in rows
        if row.session_id
    ]

    return {"sessions": sessions}
