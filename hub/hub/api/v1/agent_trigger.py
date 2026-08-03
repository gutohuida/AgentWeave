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
`runner_commands.py`'s scope. Kimi, OpenCode, and Copilot are refused with a stated 501
rather than silently mishandled. There is no fallback path left for them over HTTP
transport: task 3.10 removed the watchdog's message-scanning auto-trigger (the thing
that used to pick these runners up indirectly, for job-triggered runs only — a manual
`POST /agent/trigger` for one of these runners has 501'd since task 3.5, before this
file ever created a message for any runner). Extending this list to cover every runner
is future work, not this task; local/git transport is unaffected (the watchdog's own
`_check_jobs`/`_fire_job` "timer duties" still spawn these runners directly, no Hub
involved).
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

from ... import worktrees
from ...auth import get_project
from ...config import settings
from ...conversations import (
    conversation_for_provider_session,
    get_open_conversation,
    new_conversation,
)
from ...db.engine import async_session_factory, get_session
from ...db.models import ApiKey, Conversation, Run
from ...inbound_queue import deliver_entries_with_run, new_entry, return_run_entries
from ...launchability import (
    access_path_notice,
    get_agent_config,
    probe_agent,
    resolve_access_path,
    resolve_agent_env,
)
from ...output_recording import record_agent_output, record_context_usage
from ...pty_runner import (
    STRUCTURED_OUTPUT_DIMENSIONS,
    PipeSession,
    PtySession,
    strip_ansi_escapes,
    terminate_process_tree,
)
from ...runner_commands import SUPPORTED_RUNNERS, UnsupportedRunnerError, build_command
from ...runner_events import AccountingSample
from ...runner_parsing import (
    parse_claude_line,
    parse_codex_line,
    read_codex_rollout_accounting,
)
from ...sse import sse_manager
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
# run_ids whose stop was requested via the endpoint below. `_execute_run`'s own completion
# handling reads this once the process exits to tell "stopped deliberately" (final status
# "stopped") apart from "crashed/exited non-zero on its own" (final status "failed") — the
# exit code alone can't distinguish the two once a forced terminate is involved.
_stop_requested: set = set()


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
        default=None, max_length=4096, description="Working directory for the agent process"
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

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
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
    if work_dir and (".." in work_dir or "~" in work_dir or any(ord(c) < 32 for c in work_dir)):
        raise TriggerAgentError(status.HTTP_400_BAD_REQUEST, "Invalid work_dir")

    config = await get_agent_config(project_id, agent, session)
    probe = probe_agent(agent, config)
    runner = probe["runner"]

    # "manual" is a permanent, deliberate no-CLI declaration, not an unimplemented runner —
    # give it probe_agent's specific reason rather than the generic "not implemented yet"
    # 501 below, which would misleadingly suggest support is just missing today.
    if runner == "manual":
        raise TriggerAgentError(status.HTTP_409_CONFLICT, probe["reason"])

    # Checked before launchability: whether we know how to spawn this runner at all is a
    # more fundamental, permanent gate than whether its CLI happens to be on PATH right
    # now, and keeps the response deterministic regardless of what's installed on the Hub
    # host (an unimplemented runner is still unimplemented even if its CLI is present).
    if runner not in SUPPORTED_RUNNERS:
        raise TriggerAgentError(
            status.HTTP_501_NOT_IMPLEMENTED,
            f"Direct spawn for runner {runner!r} is not implemented yet "
            f"(supported: {', '.join(SUPPORTED_RUNNERS)}). "
            "This runner has no Hub-triggered execution path over HTTP transport — "
            "use local/git transport, where the watchdog's own timer duties still spawn it.",
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

    model = config.get("model")
    repo_root = Path.cwd()
    context_file = repo_root / ".agentweave" / "context" / f"{agent}.md"
    yolo = bool(config.get("yolo"))
    resume_session_id = conversation.provider_session_id
    session_mode = "resume" if resume_session_id else "new"
    env = resolve_agent_env(runner, config)

    # Task 5.1/5.2: a writing agent gets its own git worktree, isolated from every other
    # agent's (Decision 7). A custom cwd cannot override that isolation. Read-only
    # agents may retain the existing explicit-cwd behavior.
    if work_dir and worktrees.is_writing_agent(config):
        raise TriggerAgentError(
            status.HTTP_400_BAD_REQUEST,
            "work_dir cannot override workspace isolation for a writing agent",
        )
    if work_dir:
        effective_work_dir = work_dir
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

    # Task 4.5: tell the agent, at turn start, which access path is in use — never offer
    # one that isn't actually available in this environment.
    access_path = resolve_access_path(runner, probe["cli"] or agent, config.get("hub_client"))
    prompt = f"{access_path_notice(access_path)}\n\n{message}"
    mcp_command = None
    if access_path == "mcp":
        canonical_server = Path(__file__).resolve().parents[2] / "mcp_server.py"
        mcp_command = [sys.executable, str(canonical_server)]

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
        )
    except UnsupportedRunnerError as exc:
        raise TriggerAgentError(status.HTTP_501_NOT_IMPLEMENTED, str(exc)) from exc

    run_id = f"run-{short_id()}"

    # Task 4.1: identity is established here, once, by the Hub — never asserted by the
    # agent itself. Every tool call this run makes reads AW_AGENT_IDENTITY from its own
    # process environment; no tool accepts a caller-supplied identity. `env=None` meant
    # "inherit the Hub's own environment unchanged" (resolve_agent_env's contract) — that
    # base must be preserved, not replaced, when adding these two keys.
    env = dict(env) if env is not None else dict(os.environ)
    env["AW_AGENT_IDENTITY"] = agent
    env["AW_RUN_ID"] = run_id
    if turn_depth is not None:
        env["AW_TURN_DEPTH"] = str(turn_depth)
    if access_path == "mcp":
        key_result = await session.execute(
            select(ApiKey.id)
            .where(ApiKey.project_id == project_id, ApiKey.revoked == False)  # noqa: E712
            .limit(1)
        )
        api_key = key_result.scalar_one_or_none()
        if not api_key:
            raise TriggerAgentError(
                status.HTTP_409_CONFLICT,
                "No active project credential is available for the injected tool surface",
            )
        host = "127.0.0.1" if settings.aw_host in ("0.0.0.0", "::") else settings.aw_host
        env["HUB_URL"] = os.environ.get("HUB_URL", f"http://{host}:{settings.aw_port}")
        env["HUB_API_KEY"] = api_key
        env["HUB_PROJECT_ID"] = project_id

    run = Run(
        id=run_id,
        project_id=project_id,
        agent=agent,
        session_id=resume_session_id,
        conversation_id=conversation.id,
        status="running",
        turn_depth=turn_depth,
        initiator=initiator,
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
    if body.work_dir and (
        ".." in body.work_dir
        or "~" in body.work_dir
        or any(ord(char) < 32 for char in body.work_dir)
    ):
        raise HTTPException(status_code=400, detail="Invalid work_dir")

    config = await get_agent_config(project_id, body.agent, session)
    if body.work_dir and worktrees.is_writing_agent(config):
        raise HTTPException(
            status_code=400,
            detail="work_dir cannot override workspace isolation for a writing agent",
        )

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
            conversation = new_conversation(project_id=project_id, agent=body.agent)
            conversation.provider_session_id = body.session_id
            session.add(conversation)
    else:
        conversation = new_conversation(project_id=project_id, agent=body.agent)
        session.add(conversation)

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
    if scheduled.response is not None:
        response = scheduled.response
        response.queue_entry_id = entry.id
        return response
    return TriggerAgentResponse(
        success=True,
        message=f"Input queued for {body.agent}.",
        agent=body.agent,
        status="queued",
        conversation_id=conversation.id,
        provider_session_id=conversation.provider_session_id,
        session_id=conversation.provider_session_id,
        queue_entry_id=entry.id,
        waiting_reason=scheduled.waiting_reason,
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
    if pty is None:
        # Spawned but not yet registered, or already past its read/wait loop — either way
        # there's nothing left to terminate; the run's own completion handling will settle
        # its final status shortly.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{agent}'s run is not in a stoppable state right now.",
        )

    _stop_requested.add(run.id)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: pty.terminate(force=True))

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

    Returns the number of runs terminated.
    """
    loop = asyncio.get_running_loop()
    ptys = list(_active_ptys.values())
    for pty in ptys:
        await loop.run_in_executor(None, lambda p=pty: terminate_process_tree(p.pid, force=True))
    return len(ptys)


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
) -> None:
    """Background task: spawn, capture output, persist Run/AgentOutput, broadcast SSE.

    *worktree*, when given, is this run's isolated git worktree (task 5.1) — its
    working directory *is* `work_dir` here, but `_execute_run` needs the fact that it's
    an isolated worktree specifically (not just "some cwd") to know whether to snapshot
    it once the run ends (task 5.3's conflict detection needs real commits to compare).
    """
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

        # A turn ending with queued entries starts the next turn without waiting for
        # operator input. The scheduler itself applies the hop budget and drain cap.
        from ...turn_scheduler import schedule_agent

        await schedule_agent(project_id, agent)
    finally:
        _active_ptys.pop(run_id, None)
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
