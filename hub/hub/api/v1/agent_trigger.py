"""Agent trigger endpoint — POST /api/v1/agent/trigger

Spawns the target agent's CLI directly (Claude Code, Codex) attached to a pseudo-terminal
(`pty_runner.PtySession`) and returns a real run identifier immediately; output streams
live over the existing SSE channel (`agent_output`, `context_warning`) as the process
produces it, through the same recording path a self-reporting agent already uses
(`output_recording.py`).

This replaces the message-tag protocol (Decision 2): no synthetic `Message` row, no
`[Session: ...]` / `[NewSession]` text tags, no `execution_confidence` guess about whether
some other process might eventually pick the request up. Session identity is a typed field
on the run record (`Run.session_id`), never text embedded in a message body.

Only claude/claude_proxy/native and codex are wired to an actual spawn path today —
`runner_commands.py`'s scope. Kimi, OpenCode, and Copilot are refused with a stated 501
rather than silently mishandled; they still work via the watchdog's own trigger path
(unaffected — `agentweave` watchdog's message-tag construction, `[Session:]`/`[NewSession]`
tags included, is untouched by this file's rewrite. That entire path is removed only once
every runner has a direct-spawn equivalent, which is future work, not this task).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import async_session_factory, get_session
from ...db.models import Run
from ...launchability import get_agent_config, probe_agent
from ...output_recording import record_agent_output, record_context_usage
from ...pty_runner import PtySession, strip_ansi_escapes, terminate_process_tree
from ...runner_commands import SUPPORTED_RUNNERS, UnsupportedRunnerError, build_command
from ...runner_parsing import parse_claude_line, parse_codex_line
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/agent", tags=["agent-trigger"])

# A running background task with no other strong reference can be garbage-collected by
# asyncio mid-execution (a well-documented footgun) — this set keeps each run's task alive
# until it finishes, regardless of the triggering request's own lifecycle.
_background_runs: set = set()

# Live PtySession per in-progress run_id, so a stop request (task 3.7) can reach the actual
# process — `_execute_run` populates/clears this around its own read/wait loop, since that's
# the only place the PtySession instance exists.
_active_ptys: Dict[str, PtySession] = {}
# run_ids whose stop was requested via the endpoint below. `_execute_run`'s own completion
# handling reads this once the process exits to tell "stopped deliberately" (final status
# "stopped") apart from "crashed/exited non-zero on its own" (final status "failed") — the
# exit code alone can't distinguish the two once a forced terminate is involved.
_stop_requested: set = set()


class TriggerAgentRequest(BaseModel):
    agent: str = Field(..., max_length=64, description="Target agent name (e.g., 'claude')")
    message: str = Field(..., max_length=10000, description="Prompt to send to the agent")
    session_mode: str = Field(default="new", max_length=64, description="'new' or 'resume'")
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
    run_id: str
    status: str
    session_id: Optional[str] = None


@router.post("/trigger", response_model=TriggerAgentResponse)
async def trigger_agent(
    body: TriggerAgentRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Spawn an agent directly and return its run identifier.

    Examples:
    - New session: `{"agent": "claude", "message": "Hello", "session_mode": "new"}`
    - Resume: `{"agent": "claude", "message": "Continue", "session_mode": "resume", "session_id": "..."}`
    """
    from sqlalchemy import select

    project_id, _ = project

    if body.session_mode not in ("new", "resume"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_mode must be 'new' or 'resume'",
        )
    if body.session_mode == "resume" and not body.session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id is required when session_mode='resume'",
        )
    if body.work_dir and (
        ".." in body.work_dir or "~" in body.work_dir or any(ord(c) < 32 for c in body.work_dir)
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid work_dir")

    config = await get_agent_config(project_id, body.agent, session)
    probe = probe_agent(body.agent, config)
    runner = probe["runner"]

    # "manual" is a permanent, deliberate no-CLI declaration, not an unimplemented runner —
    # give it probe_agent's specific reason rather than the generic "not implemented yet"
    # 501 below, which would misleadingly suggest support is just missing today.
    if runner == "manual":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=probe["reason"])

    # Checked before launchability: whether we know how to spawn this runner at all is a
    # more fundamental, permanent gate than whether its CLI happens to be on PATH right
    # now, and keeps the response deterministic regardless of what's installed on the Hub
    # host (an unimplemented runner is still unimplemented even if its CLI is present).
    if runner not in SUPPORTED_RUNNERS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                f"Direct spawn for runner {runner!r} is not implemented yet "
                f"(supported: {', '.join(SUPPORTED_RUNNERS)}). "
                "This agent can still be triggered via the watchdog's own message-based path."
            ),
        )

    if not probe["runnable"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=probe["reason"] or f"{body.agent} is not currently launchable.",
        )

    existing = await session.execute(
        select(Run.id)
        .where(Run.project_id == project_id, Run.agent == body.agent, Run.status == "running")
        .limit(1)
    )
    if existing.scalar() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{body.agent} already has a run in progress.",
        )

    model = config.get("model")
    context_file = Path.cwd() / ".agentweave" / "context" / f"{body.agent}.md"
    yolo = bool(config.get("yolo"))
    resume_session_id = body.session_id if body.session_mode == "resume" else None

    try:
        cmd = build_command(
            runner=runner,
            cli=probe["cli"],
            prompt=body.message,
            model=model,
            context_file=context_file,
            session_id=resume_session_id,
            yolo=yolo,
        )
    except UnsupportedRunnerError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc

    run_id = f"run-{short_id()}"
    run = Run(
        id=run_id,
        project_id=project_id,
        agent=body.agent,
        session_id=resume_session_id,
        status="running",
    )
    session.add(run)
    await session.commit()

    await persist_event(
        session,
        project_id,
        "run_triggered",
        {"agent": body.agent, "run_id": run_id, "session_mode": body.session_mode},
        agent=body.agent,
    )

    task = asyncio.create_task(
        _execute_run(
            project_id=project_id,
            agent=body.agent,
            run_id=run_id,
            runner=runner,
            cmd=cmd,
            model=model,
            work_dir=body.work_dir,
            known_session_id=resume_session_id,
        )
    )
    _background_runs.add(task)
    task.add_done_callback(_background_runs.discard)

    return TriggerAgentResponse(
        success=True,
        message=f"{body.agent} started (run {run_id}).",
        agent=body.agent,
        run_id=run_id,
        status="running",
        session_id=resume_session_id,
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
    runner: str,
    cmd: list,
    model: Optional[str],
    work_dir: Optional[str],
    known_session_id: Optional[str],
) -> None:
    """Background task: spawn, capture output, persist Run/AgentOutput, broadcast SSE."""
    loop = asyncio.get_running_loop()

    try:
        pty = await loop.run_in_executor(None, lambda: PtySession.spawn(cmd, cwd=work_dir))
    except FileNotFoundError as exc:
        async with async_session_factory() as db:
            run = await db.get(Run, run_id)
            if run:
                run.status = "failed"
                run.error = str(exc)
                run.ended_at = datetime.now(timezone.utc)
                await db.commit()
            await _broadcast_run_lifecycle(
                db, project_id, "run_failed", agent=agent, run_id=run_id, error=str(exc)
            )
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
        sequence = 0
        buffer = ""

        async def _flush_line(raw_line: str) -> None:
            nonlocal session_id, sequence
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
            if parsed.session_id and not session_id:
                session_id = parsed.session_id
                async with async_session_factory() as db:
                    run = await db.get(Run, run_id)
                    if run:
                        run.session_id = session_id
                        await db.commit()
            for event in parsed.events:
                sequence += 1
                async with async_session_factory() as db:
                    await record_agent_output(
                        db,
                        project_id,
                        agent,
                        content=event.content,
                        session_id=session_id,
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

        # A deliberate stop (task 3.7) also exits the read loop and reaches this same
        # point — force-terminating a process rarely yields exit code 0, so without this
        # check a stop would be misreported as "failed". Checked before the exit-code
        # branch below so a stop always wins regardless of what the process happened to
        # exit with.
        if run_id in _stop_requested:
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
                run.ended_at = datetime.now(timezone.utc)
                await db.commit()
            await _broadcast_run_lifecycle(
                db,
                project_id,
                lifecycle_event,
                agent=agent,
                run_id=run_id,
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
                    "session_id": session_id,
                    "content": f"Run {final_status} (exit {exit_code}).",
                    "kind": "status",
                    "payload": {"phase": "completed", "exit_code": exit_code},
                    "run_id": run_id,
                    "sequence": sequence + 1,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
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
