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
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ... import (
    bound_address,
    instance_identity,
    project_workspace,
    requirement_evidence,
    worktrees,
)
from ...agent_auth import hash_run_token, mint_run_token
from ...auth import get_project
from ...codex_appserver import (
    TRANSPORT_SENTINELS,
    AppServerError,
    TurnOutcome,
    readable_exit_code,
    uses_app_server,
)
from ...codex_appserver import approval_label as codex_approval_label
from ...codex_appserver import run_turn as codex_run_turn
from ...conversation_titles import maybe_generate_title
from ...conversations import (
    conversation_for_provider_session,
    conversation_id_for_run,
    get_conversation_by_id,
    get_open_conversation,
    name_conversation,
    new_conversation,
)
from ...db.engine import async_session_factory, get_session
from ...db.models import Agent, Conversation, PermissionRequest, Project, Run, Runner
from ...inbound_queue import (
    abandoned_for_run,
    deliver_entries_with_run,
    new_entry,
    return_run_entries,
)
from ...launchability import (
    access_path_notice,
    get_agent_config,
    probe_agent,
    resolve_access_path,
    resolve_agent_env,
    spec_turn_notice,
)
from ...model_catalog import (
    PERMISSION_MODE_CONTROL,
    WORKSPACE_PERMISSION_MODE,
    validate_overrides,
)
from ...output_recording import record_agent_output, record_context_usage
from ...permission_requests import expire_pending_for_run
from ...pty_runner import (
    STRUCTURED_OUTPUT_DIMENSIONS,
    PipeSession,
    PtySession,
    strip_ansi_escapes,
    terminate_process_tree,
)
from ...run_divergence import evaluate_run_end, record_response_run
from ...run_task_binding import (
    bind_run_to_task,
    rebind_conversation,
    resolve_bound_task,
    resolve_task_for_project,
    spec_document_for_task,
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
from ...scheduler import finalize_job_run_for_conversation
from ...spec_manifest import SpecPathError, validate_spec_path
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
    spec_document: Optional[str] = Field(
        default=None,
        max_length=512,
        description="The specification document the operator has open, when the message comes "
        "from the specification workspace. Carried into the canonical turn context, never into "
        "the stored message.",
    )
    task_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="The task this run is being started for. Binds the run and moves the task to "
        "in_progress when that move is legal. Operator-supplied: an agent cannot bind its own run, "
        "because a run that never binds is never checked at its boundary.",
    )

    @field_validator("spec_document")
    @classmethod
    def _validate_spec_document(cls, v: Optional[str]) -> Optional[str]:
        # Same validator the sync endpoint uses, so one definition of a legal specification path
        # serves both the write and the read. An empty string is "no document open", not a path.
        if v is None or v == "":
            return None
        try:
            return validate_spec_path(v)
        except SpecPathError as exc:
            raise ValueError(str(exc)) from exc


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


async def _spec_phase_for(session, project_id: str, spec_document: Optional[str]) -> Optional[str]:
    """The open document's phase, or None when there is no document or no row for it.

    Failure is silent by design: a turn must not be refused because the phase could not be read.
    The canonical context carries the same statement, so losing the prompt notice degrades to the
    behaviour that existed before it.
    """
    if not spec_document:
        return None
    try:
        from ... import spec_lifecycle

        row = await spec_lifecycle.get_document(session, project_id, spec_document)
        return row.phase if row is not None else None
    except Exception:  # noqa: BLE001 - a missing phase must never cost the turn
        return None


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
    spec_document: Optional[str] = None,
    task_id: Optional[str] = None,
    divergence_source_run_id: Optional[str] = None,
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
    if agent_row.lifecycle == "archived":
        # `agent-configuration`'s spec states "nothing runs an archived agent" as the reason a
        # blocked send need not open a new conversation as a workaround — that sentence is only
        # true if this is enforced here, the one choke point both a manual trigger and a queued
        # delivery (`turn_scheduler.py`) go through. Without it, an archived agent that was
        # queued or triggered directly before archiving (or by a caller that names it explicitly)
        # would still spawn a real run and inherit whatever authority its name carries — the
        # D15 gap `2026-08-19-a-loop-writes-its-own-queue`'s A5.3 documented as surviving the
        # literal name-reuse scenario a unique index already blocks.
        raise TriggerAgentError(
            status.HTTP_409_CONFLICT,
            f"{agent} is archived and cannot be triggered. Unarchive it first.",
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
    # The agent's default posture sits between the conversation's own choice and the built-in
    # fallback. It has to be applied here rather than only in the composer, because a run
    # triggered by a peer message or a scheduled job has no composer to state one — and those are
    # exactly the runs where "what may this agent do unattended" is the question being asked.
    if agent_row.default_permission_mode and PERMISSION_MODE_CONTROL not in control_overrides:
        control_overrides[PERMISSION_MODE_CONTROL] = agent_row.default_permission_mode
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
    #
    # Only where there *is* isolation to override. A project directory that is not a git
    # repository has none, so refusing there would be a guard with no subject.
    project_is_repo = worktrees.is_git_repo(repo_root)
    if work_dir and worktrees.is_writing_agent(config) and project_is_repo:
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

    # Which task this turn is about, answered before the context is rendered rather than after.
    #
    # A builder triggered on a task could not find the document it was implementing: the read tool
    # documents its argument as "the path, as given in your turn context", and a task-triggered
    # context gave no path and no document id. Observed twice in one run, in two conversations —
    # the second time it blocked recording evidence entirely, and the agents worked around it by
    # messaging each other for the path.
    #
    # Reads only. The staging that acts on this stays where it is, below, before delivery.
    binding = await resolve_bound_task(
        session,
        project_id=project_id,
        conversation=conversation,
        queue_entry_ids=queue_entry_ids,
        task_id=task_id,
    )
    task_document = await spec_document_for_task(session, binding.task)

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
        # A writing agent working in the project directory is doing so because there is no
        # repository to cut a worktree from — the only remaining path through
        # `resolve_agent_workspace`. Told apart from a read-only agent sharing by choice,
        # because an agent that does not know there is no repository proposes branches,
        # offers to commit, and reads a failed `git status` as a broken environment.
        isolation_unavailable=worktrees.is_writing_agent(config) and not project_is_repo,
        # Which specification document the operator has open, when the message came from the
        # specification workspace. Deliberately here and not prepended to `message`: the message
        # is the durable record of what the operator said, and re-reading the conversation later
        # must not show them saying something they did not.
        spec_document=spec_document,
        # The document the bound task implements, which is a different claim from the one above:
        # that one is where the operator happens to be looking, this one is what the work is
        # against. Rendered as its own block for exactly that reason.
        task_spec_document=task_document,
        task_id=binding.task.id if binding.task is not None else None,
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
    notices = [access_path_notice(access_path)]
    # A specification turn says so beside the operator's message, not only in the system context.
    # Three live runs had the phase block, the precedence statement and the tool list all correctly
    # delivered, and reached for a different workflow anyway: what an agent weighs against the
    # request is what arrives with the request. Prepended rather than merged into `message`, which
    # stays the durable record of what the operator actually said — the same division
    # `access_path_notice` has always used.
    spec_notice = spec_turn_notice(await _spec_phase_for(session, project_id, spec_document))
    if spec_notice:
        notices.append(spec_notice)
    prompt = "\n\n".join([*notices, message])
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
            # F4 (`openspec/changes/2026-08-17-authoring-rigor-and-scope`, design D6): a turn
            # triggered with a specification document open loses file-write tools, mechanically,
            # regardless of phase, rigor or permission posture — a role boundary, not a rigor gate.
            restrict_spec_writes=bool(spec_document),
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
        divergence_source_run_id=divergence_source_run_id,
    )

    # The binding, and the automatic move it causes, are staged here — before delivery, which is
    # what commits — so a bound run whose task never moved cannot exist as a partial write.
    #
    # *Which* task it is was resolved further up, before the context was rendered, because the
    # context has to be able to name the specification the work implements. That resolution reads
    # only, and nothing below feeds back into it.
    bound_task, task_was_named, delegated_source_run_id = binding
    if delegated_source_run_id is not None:
        # Carried from the queue entry rather than passed in: the Hub queued this response in an
        # earlier call, and the retry bound cannot see its own source unless the entry brings it.
        run.divergence_source_run_id = delegated_source_run_id
        # The divergence record could not name its response when it was written — the answer was
        # queued, and only becomes a run here, whenever the agent was next free.
        await record_response_run(session, delegated_source_run_id, run.id)

    if task_was_named and bound_task is not None:
        # This turn named a task, so the thread follows it. The more specific statement wins, and
        # the operator does not have to release an old binding before starting something else here.
        rebind_conversation(conversation, bound_task)

    if bound_task is not None:
        await bind_run_to_task(session, run, bound_task)

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

    # Mirrors the same guard in `trigger_agent_directly` — see its comment for why this is the
    # one invariant that makes "nothing runs an archived agent" true rather than aspirational.
    archived_check = await session.execute(
        select(Agent.lifecycle).where(Agent.project_id == project_id, Agent.name == body.agent)
    )
    if archived_check.scalars().first() == "archived":
        raise HTTPException(
            status_code=409,
            detail=f"{body.agent} is archived and cannot be triggered. Unarchive it first.",
        )

    try:
        workspace_root = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        project_workspace.raise_workspace_http_error(exc)

    config = await get_agent_config(project_id, body.agent, session)
    # Mirrors the same guard in `trigger_agent_directly`, including its repository condition:
    # there is no isolation to override in a project that is not a git repository.
    if (
        body.work_dir
        and worktrees.is_writing_agent(config)
        and worktrees.is_git_repo(workspace_root.root)
    ):
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
        # No inheritance here, deliberately. `agent-conversation-workspace` requires that a
        # conversation the *operator* starts begins clean — they are looking at the composer and
        # can choose. What this change fixes is the conversation a peer or a job opens, where
        # nobody was asked.
        conversation = new_conversation(project_id=project_id, agent=body.agent, origin="operator")
        session.add(conversation)

    if body.task_id:
        # Refused now, while the operator is looking at the response, rather than at spawn — a
        # request that names a task the project does not have is a mistake, not a reason to start
        # an unbound run whose boundary is then never checked.
        await resolve_task_for_project(session, body.task_id, project_id)

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
        spec_document=body.spec_document,
        # Carried on the entry rather than held for the spawn, so an operator starting work from a
        # board card binds through the same path a delegation does. The scheduler may start this
        # agent's turn from a later call than this one, and anything held only here would be gone.
        task_id=body.task_id,
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


async def _restamp_evidence_footprints(
    db: AsyncSession,
    *,
    project_id: str,
    run_id: str,
    worktree: Optional[Path],
    snapshot_sha: Optional[str],
) -> None:
    """Point this run's evidence at the commit that contains its work.

    Evidence is recorded mid-turn, while the work is still uncommitted, so it can only name the
    commit the turn started from. `snapshot_worktree` has just made the commit that actually holds
    the work, and this is the first moment the right answer is knowable.

    Best-effort, and for the same reason the snapshot above it is: a git failure here must not turn
    a finished run into a failed one. A run that never reaches this point keeps the stale footprint,
    which is the pre-existing behaviour rather than a new one.
    """
    if worktree is None:
        return
    try:
        project = await db.get(Project, project_id)
        await requirement_evidence.restamp_run_footprints(
            db,
            project_id=project_id,
            run_id=run_id,
            root=worktree,
            commit_sha=snapshot_sha,
            main_branch=project.main_branch if project else None,
        )
    except Exception:  # noqa: BLE001 - never worsen a run's outcome over a footprint
        logger.warning("Could not re-stamp evidence footprints for run %s", run_id, exc_info=True)


async def _report_abandoned_entries(
    db: AsyncSession, project_id: str, agent: str, run_id: str
) -> None:
    """Tell the operator about input the Hub has stopped trying to deliver.

    Retrying without limit is indistinguishable from being stuck, so the Hub eventually gives up —
    but a message dropped silently is worse than one dropped loudly. Emitted at `warn`, because
    something the operator or another agent said is not going to be acted on.
    """
    abandoned = await abandoned_for_run(db, run_id)
    for entry in abandoned:
        payload = {
            "entry_id": entry.id,
            "agent": agent,
            "run_id": run_id,
            "attempts": entry.delivery_attempts,
            "reason": entry.abandoned_reason,
            "conversation_id": entry.conversation_id,
        }
        await persist_event(
            db, project_id, "queue_entry_abandoned", payload, agent=agent, severity="warn"
        )
        await sse_manager.broadcast(project_id, "queue_entry_abandoned", payload)


def _transport_failure_fields(exc: BaseException, conversation_id: Optional[str]) -> dict:
    """What a run that never got going can say about why.

    The normal-completion broadcast carries `exit_code`/`conversation_id`; this path carried only
    a string, so the two shapes disagreed exactly where diagnosis is hardest. `getattr` because
    this `except` also catches `FileNotFoundError`/`OSError`/`TimeoutError`, which carry none of
    these — an absent fact is reported as absent rather than invented.
    """
    return {
        "error": str(exc),
        # Rendered, not raw — this dict is broadcast for display. See `_runtime_failure_fields`.
        "exit_code": readable_exit_code(getattr(exc, "exit_code", None)),
        "method": getattr(exc, "method", None),
        # Absent until 2026-08-14, so the tail could only surface by having been composed into
        # `str(exc)`. Of the three facts this dict was written to report — exit code, method,
        # stderr tail — only the first two were ever in it.
        "stderr_tail": getattr(exc, "stderr_tail", None) or None,
        "conversation_id": conversation_id,
    }


def _runtime_failure_fields(outcome, lifecycle_event: str) -> dict:
    """What the app-server itself did, for a turn that failed without raising.

    The pre-spawn path reports this through `_transport_failure_fields`, off an `AppServerError`.
    A turn that fails once it is under way has no exception at all — `run_turn` returns a failed
    `TurnOutcome` — so these facts have to be lifted off the outcome instead. Until they were, a
    killed app-server produced a `run_failed` carrying only the synthetic exit code.

    Only on a failure, and only for facts that exist: a completed run has nothing to explain, and
    a key that is present but null invites a reader to render "exit: null".

    The status is **rendered**, not raw. Measured 2026-08-15 against a live Hub: this payload went
    out as `runtime_exit_code: 4294967295` while `run.error` for the same run said `exit -1`, so one
    death was described by three numbers. D3 put normalisation "where the value is composed for a
    human" and kept recorded values raw — a broadcast payload is the former, not the latter, and
    reading it as the latter is what produced the defect. `TurnOutcome.exit_code` and
    `AppServerError.exit_code` still hold what the platform reported; every surface a person reads
    now renders it.
    """
    if lifecycle_event != "run_failed":
        return {}
    fields = {}
    if getattr(outcome, "exit_code", None) is not None:
        fields["runtime_exit_code"] = readable_exit_code(outcome.exit_code)
    if getattr(outcome, "stderr_tail", None):
        fields["stderr_tail"] = outcome.stderr_tail
    return fields


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
        logger.warning("Could not check run %s for an unasked question", run_id, exc_info=True)


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
                # Nothing spawned, so nothing can have asked — swept anyway, because the rule is
                # "a terminal run leaves nothing pending", not "the paths where we expect some".
                await expire_pending_for_run(db, run_id)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner=runner,
                    sample=None,
                )
            # Design D13, task A4.3 — same as `_execute_run`'s success-path finalize below;
            # a spawn that never started still ends the firing that queued it.
            await finalize_job_run_for_conversation(db, conversation_id, "failed")
            returned = await return_run_entries(db, run_id)
            await db.commit()
            await _report_abandoned_entries(db, project_id, agent, run_id)
            await _broadcast_run_lifecycle(
                db,
                project_id,
                "run_failed",
                agent=agent,
                run_id=run_id,
                **_transport_failure_fields(exc, conversation_id),
            )
            for entry_id in returned:
                payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
        # This branch `return`s before the `schedule_agent` the normal path runs at its end, so
        # without this an entry handed back here waits for something else to drain it. Nothing
        # does on a timer: `redrain_queued_agents` is reachable only from project open, settings
        # save and relocate. Measured — an entry sat `queued` at one attempt until an unrelated
        # settings save drove the second, which is a limit protecting nobody.
        if returned:
            from ...turn_scheduler import schedule_agent

            await schedule_agent(project_id, agent)
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
                    conversation = await get_conversation_by_id(db, conversation_id)
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

        snapshot_sha: Optional[str] = None
        if worktree is not None:
            # Task 5.3 needs real commits to compare branches with `git merge-tree` —
            # an agent's turn just ends with dirty files in its worktree otherwise, which
            # a conflict check has nothing to diff against. Best-effort: a git failure here
            # must not turn a completed/failed run into something worse than it already is.
            try:
                snapshot_sha = await loop.run_in_executor(
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
            if run is None:
                # Loud on purpose. This was a bare `if run:` with no `else`, so a finalize that
                # could not see its own row did nothing and said nothing: no exception, no log and
                # no `error` field, while the row stays `running` for good.
                # `turn_scheduler.schedule_agent` then refuses every later turn for the agent
                # (`turn_scheduler.py:37-43`) and `trigger_agent` answers 200/`queued` to each, so
                # the agent goes quietly deaf while every surface still reads "running". That is
                # the same unbounded outage the `except` handler below was widened to prevent,
                # reached by a second route — and a run that ends but cannot record that it ended
                # is a defect wherever it comes from, so it is reported rather than swallowed.
                logger.error(
                    "Run %s for %r finished (%s, exit %r) but its row was not visible to the "
                    "finalizing session, so the terminal status could not be recorded. The row "
                    "stays 'running' and the agent will queue every later turn.",
                    run_id,
                    agent,
                    final_status,
                    exit_code,
                )
            if run:
                run.status = final_status
                run.exit_code = exit_code
                if binding_conflict is not None:
                    run.error = binding_conflict
                run.ended_at = datetime.now(timezone.utc)
                # NULL when the turn changed nothing — `snapshot_worktree` commits only a dirty
                # tree. A checkpoint reads these to say what its conversation changed.
                run.snapshot_commit_sha = snapshot_sha
                # Evidence this run recorded named the commit the turn *started* from, because the
                # work was still uncommitted then. The commit above is the one that holds it.
                await _restamp_evidence_footprints(
                    db,
                    project_id=project_id,
                    run_id=run_id,
                    worktree=worktree,
                    snapshot_sha=snapshot_sha,
                )
                # A run that is over has stopped waiting on anything, so nothing it opened may
                # still read as answerable. In the same transaction as `ended_at`: the two facts
                # must not be separable by a reader.
                await expire_pending_for_run(db, run_id)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner=runner,
                    sample=accounting_sample,
                )
            # Outside the `if run` guard, and before the commit that closes this block. A run that
            # ended abnormally is carrying input nobody else will hand back, and the spawn-failure
            # branch above already reads this way — a run row that has vanished still has entries.
            # Until this existed, `return_run_entries` was reachable only from the two *pre-spawn*
            # `except` blocks, so a runtime that died once the turn was under way came back as a
            # failed status here and its entries stayed `delivered` at zero attempts: never
            # retried, never abandoned, never reported. A deliberate stop is `stopped`, not
            # `failed`, so it keeps its input.
            #
            # A binding conflict is excluded, and it is the one failure that has to be. It is
            # raised *after* the turn ran — the agent did the work and streamed its output — so the
            # input was processed rather than lost, and re-delivering it makes the agent redo a
            # completed turn. Worse, the retry would defeat the check it comes from: at
            # `RESUME_RETRY_LIMIT` the conversation gives up its provider session, so the third
            # attempt binds the very session id the conflict refused, and a misbehaving CLI
            # overwrites the binding this check exists to protect.
            #
            # Design D13, task A4.3: if this run's conversation belongs to a job's loop firing,
            # that firing is no longer "in progress" once the agent's own turn has ended, one
            # way or the other. A no-op for the common case of a run that was never a firing.
            await finalize_job_run_for_conversation(db, conversation_id, final_status)
            returned = (
                await return_run_entries(db, run_id)
                if final_status == "failed" and binding_conflict is None
                else []
            )
            await db.commit()
            # The run boundary. After the commit, so the check reads the run's final state, and
            # outside the `if run` block for the same reason — a missing run row is not a
            # divergence, and `evaluate_run_end` says so itself.
            #
            # Skipped when this run's input went back to the queue, exactly as
            # `run_reconciliation.py:59` skips it: the work is about to be handed to a new run that
            # will bind to the same task, so nothing has been dropped. The condition is on the
            # returned set rather than on `final_status` — a failed run whose entries were all
            # abandoned on this attempt has genuinely dropped its work and must still be evaluated.
            if not returned:
                await evaluate_run_end(run_id)
            await _report_abandoned_entries(db, project_id, agent, run_id)
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
            for entry_id in returned:
                payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
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
    except (Exception, asyncio.CancelledError) as exc:
        # Every step above this point is inside the same `try` and none of it is wrapped
        # individually — so an exception anywhere between the spawn succeeding and this turn's
        # own bookkeeping (title generation, the next-turn scheduler, ...) used to leave the
        # `Run` row exactly where the spawn-success commit put it: `status="running"`, forever.
        # `turn_scheduler.schedule_agent` refuses a new turn while one is `running`
        # (`turn_scheduler.py:37-43`), so the agent silently queued every future trigger instead
        # of running it — an unbounded outage with no error anywhere a human would see. Measured
        # live in CI (`test_a_conversation_whose_model_changed_attributes_usage_per_turn`,
        # 2026-08-17): `_active_ptys` and `_background_runs` both empty — the task had genuinely
        # finished — while the `Run` row still read `running` with `error=None`, which ruled out
        # every regular `Exception` (an `except Exception` guard here, tried first, changed
        # nothing — same symptom, same `error=None` on the next CI run). `CancelledError` is a
        # `BaseException` in Python 3.8+, not an `Exception`, and nothing in this codebase calls
        # `.cancel()` on this task (`_stop_requested` is a cooperative flag the read loop checks
        # itself, not a cancellation) — but that only means no *known* caller does; a test
        # transport or event-loop teardown cancelling an orphaned background task is exactly the
        # kind of thing that would vanish from view rather than log anything, since asyncio's own
        # default handler does not warn on an unretrieved `CancelledError` the way it does for
        # everything else. Re-raised below, once the row is marked, to preserve real cancellation
        # semantics for anything that legitimately depends on it propagating.
        logger.exception("Unhandled error in run %s for %r", run_id, agent)
        already_terminal = False
        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run is None or run.status != "running":
                # The turn itself already reached a terminal status (or the row is gone) before
                # this exception happened, so whatever failed is downstream of a turn that
                # already succeeded or failed cleanly. Overwriting that here would let unrelated
                # bookkeeping failures relabel a completed run as failed.
                already_terminal = True
            else:
                run.status = "failed"
                run.error = str(exc)
                run.ended_at = datetime.now(timezone.utc)
                await expire_pending_for_run(db, run_id)
                # Design D13, task A4.3 — same as `_execute_run`'s other finalize sites.
                await finalize_job_run_for_conversation(db, conversation_id, "failed")
                returned = await return_run_entries(db, run_id)
                await db.commit()
                await _report_abandoned_entries(db, project_id, agent, run_id)
                await _broadcast_run_lifecycle(
                    db,
                    project_id,
                    "run_failed",
                    agent=agent,
                    run_id=run_id,
                    **_transport_failure_fields(exc, conversation_id),
                )
                for entry_id in returned:
                    payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                    await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
        if not already_terminal and returned:
            from ...turn_scheduler import schedule_agent

            await schedule_agent(project_id, agent)
        if isinstance(exc, asyncio.CancelledError):
            raise
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
        {
            "id": request_id,
            "agent": agent,
            "tool_name": _CODEX_APPROVAL_LABELS.get(method, method),
            "run_id": run_id,
        },
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
                db,
                project_id,
                "run_started",
                agent=agent,
                run_id=run_id,
                runner="codex",
                model=model,
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
                conversation = await get_conversation_by_id(db, conversation_id)
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

        async def _on_refusal(method: str, subject: Dict[str, Any]) -> None:
            """Record a refusal this runtime decided by itself.

            Claude's refusals reach the event log through `approve_tool_call`, which is a
            `--permission-prompt-tool` flag and therefore Claude-only. A Codex agent declined by
            its own sandbox produced nothing at all: not an event, not an SSE frame, not a line in
            the timeline. Found live -- a reviewing agent was refused permission to write its own
            review file and said so in prose, while the Hub's durable record showed a clean run.
            """
            reason = subject.get("reason") or ""
            detail = subject.get("command") or subject.get("grantRoot") or ""
            async with async_session_factory() as db:
                await persist_event(
                    db,
                    project_id=project_id,
                    event_type="permission_denied",
                    agent=agent,
                    data={
                        "tool_name": codex_approval_label(method),
                        "reason": reason or (f"outside {agent}'s workspace" if detail else ""),
                        "detail": detail if isinstance(detail, str) else " ".join(map(str, detail)),
                        "run_id": run_id,
                        "decided_by": "runtime",
                    },
                    severity="warn",
                )
            await sse_manager.broadcast(
                project_id,
                "permission_denied",
                {"agent": agent, "tool_name": codex_approval_label(method), "run_id": run_id},
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
                on_refusal=_on_refusal,
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
                    # See `_execute_run`'s spawn-failure branch.
                    await expire_pending_for_run(db, run_id)
                    await record_turn_usage(
                        db,
                        run_id=run_id,
                        project_id=project_id,
                        agent=agent,
                        runner="codex",
                        sample=None,
                    )
                # Design D13, task A4.3 — see `_execute_run`'s spawn-failure branch.
                await finalize_job_run_for_conversation(db, conversation_id, "failed")
                returned = await return_run_entries(db, run_id)
                await db.commit()
                await _report_abandoned_entries(db, project_id, agent, run_id)
                await _broadcast_run_lifecycle(
                    db,
                    project_id,
                    "run_failed",
                    agent=agent,
                    run_id=run_id,
                    **_transport_failure_fields(exc, conversation_id),
                )
                for entry_id in returned:
                    payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                    await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                    await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
            # See `_execute_run`'s spawn-failure branch: this one `return`s too, so the entries it
            # hands back need the same push.
            if returned:
                from ...turn_scheduler import schedule_agent

                await schedule_agent(project_id, agent)
            return

        snapshot_sha: Optional[str] = None
        if worktree is not None:
            # Same best-effort snapshot as `_execute_run` — a git failure here must not turn
            # a completed/failed run into something worse than it already is.
            try:
                loop = asyncio.get_running_loop()
                snapshot_sha = await loop.run_in_executor(
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
                # NULL when the turn changed nothing — see `_execute_run`.
                run.snapshot_commit_sha = snapshot_sha
                # See `_execute_run`.
                await _restamp_evidence_footprints(
                    db,
                    project_id=project_id,
                    run_id=run_id,
                    worktree=worktree,
                    snapshot_sha=snapshot_sha,
                )
                # See `_execute_run`. A no-op on the Codex path's own approvals, which expire
                # themselves at their `asyncio.TimeoutError` — the guard is `status == "pending"`,
                # so arriving second changes nothing rather than double-writing.
                await expire_pending_for_run(db, run_id)
                await record_turn_usage(
                    db,
                    run_id=run_id,
                    project_id=project_id,
                    agent=agent,
                    runner="codex",
                    sample=accounting_sample,
                )
            # See `_execute_run`. This is the path a killed app-server actually takes: `run_turn`
            # returns a failed `TurnOutcome` rather than raising, so the pre-spawn `except` above
            # never sees it. A stop arrives as `outcome.status == "interrupted"` → `stopped`, and
            # keeps its input. A binding conflict is excluded for the reason given there.
            #
            # See `_execute_run`'s identical call — design D13, task A4.3.
            await finalize_job_run_for_conversation(db, conversation_id, final_status)
            returned = (
                await return_run_entries(db, run_id)
                if final_status == "failed" and binding_conflict is None
                else []
            )
            await db.commit()
            # The run boundary, as in `_execute_run`. Both runners reach it, because the check sits
            # at a boundary AgentWeave owns rather than inside either agent. Skipped when the input
            # went back to the queue, for the reason given there.
            if not returned:
                await evaluate_run_end(run_id)
            await _report_abandoned_entries(db, project_id, agent, run_id)
            # `exit_code` above is the synthetic 0/1 this transport has to invent, because there is
            # no per-turn process status; `AgentOutputPanel.tsx` reads it to detect a handoff and
            # the status line derives from it, so its meaning is fixed. The runtime's own status
            # travels beside it under its own name — one death used to report two numbers with
            # nothing to say which was which. Omitted, not nulled, where there is nothing to say.
            await _broadcast_run_lifecycle(
                db,
                project_id,
                lifecycle_event,
                agent=agent,
                run_id=run_id,
                conversation_id=conversation_id,
                session_id=session_id,
                exit_code=exit_code,
                **_runtime_failure_fields(outcome, lifecycle_event),
            )
            for entry_id in returned:
                payload = {"entry_id": entry_id, "agent": agent, "run_id": run_id}
                await persist_event(db, project_id, "queue_entry_queued", payload, agent=agent)
                await sse_manager.broadcast(project_id, "queue_entry_queued", payload)
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
