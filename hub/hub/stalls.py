"""Stalls, and the mender who unblocks them (`a-stalled-project-wakes-a-doctor-that-unblocks-it`).

A stall is one time a project's work stopped moving, keyed by its cause and subject
(`integration_skipped:task-x`). It is recorded where the Hub already decides it -- a loop firing
that finds nothing it can start, a merge skipped or failed after approval, a review or a turn
nobody may take -- and by `sweep`, which notices dead runs, stuck tasks and a loop with open work
that has made no progress for `NO_PROGRESS_MINUTES`. The same stall seen again is the same row,
counted; it wakes the mender once.

**The mender is the first manager entry that is an agent.** `manager.py` says the manager is a Hub
function, not an agent, because its jobs are one-shot spawns; mending needs tools, git and
`ask_user`, so the mender is an `Agent` row the Hub creates (marked `config.hub_role == "mender"`)
and briefs through the ordinary queue, which gives it the budget holds, traces and permission
posture every agent turn has. It unblocks without review, through the routes in
`api/v1/mender.py`; anything hardcore it asks the operator first (its brief says which).

Reports are fire-and-forget: a stall must never fail the work that noticed it. `report` runs at
once; `report_after_commit` waits for the caller's transaction, as `sse.defer_broadcast` does, so
the mender's brief reads the rows that transaction wrote.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import blocking
from .db.models import (
    STALL_CAUSES,
    Agent,
    AIJob,
    InboundQueueEntry,
    Loop,
    Project,
    Run,
    Runner,
    Stall,
    Task,
    TaskDependency,
    TaskIntegration,
    TaskTransition,
)
from .model_catalog import default_model
from .runner_provider import has_provider
from .subprocess_windows import no_console_kwargs
from .utils import persist_event, short_id

logger = logging.getLogger(__name__)

MENDER = "mender"
#: `Agent.config["hub_role"]` on the row the Hub made; a project's own agent named `mender` is
#: never taken over.
HUB_ROLE = "mender"
#: Operator, 2026-10-23: a loop with open work and no run started and no task moved for this long
#: has stalled, whatever the reason.
NO_PROGRESS_MINUTES = 30
#: Operator, 2026-10-23: the most mender turns one stall gets.
MENDER_TURN_CAP = 40
SWEEP_SECONDS = 300
#: How long a new run may be recorded `running` before this Hub registers it as executing: the
#: row is written before the process starts (worktree, briefing, spawn).
DEAD_RUN_GRACE = timedelta(minutes=5)
STALL_RECORDED = "stall_recorded"
STALL_ENDED = "stall_ended"

_PENDING_KEY = "aw_pending_stalls"
_tasks: Set["asyncio.Task[Any]"] = set()


# --- reporting -----------------------------------------------------------------------------------


def report(project_id: str, *, cause: str, subject: str, text: str, **fields: Any) -> None:
    """Record a stall in the background, now. Never raises."""
    if cause not in STALL_CAUSES:
        logger.warning("unknown stall cause %r", cause)
        return
    _spawn(_record_and_wake(project_id, cause=cause, subject=subject, text=text, **fields))


def report_after_commit(
    session: AsyncSession, project_id: str, *, cause: str, subject: str, text: str, **fields: Any
) -> None:
    """`report`, once *session*'s root transaction commits, and never if it does not."""
    sync = session.sync_session
    if not sync.in_transaction():
        sync.begin()
    sync.info.setdefault(_PENDING_KEY, []).append(
        (report, project_id, dict(cause=cause, subject=subject, text=text, **fields))
    )


def resolve_task_after_commit(session: AsyncSession, project_id: str, task_id: str, *, by: str):
    """`resolve_task`, in the background, once *session*'s root transaction commits."""
    sync = session.sync_session
    if not sync.in_transaction():
        sync.begin()
    sync.info.setdefault(_PENDING_KEY, []).append(
        (_spawn_resolve, project_id, {"task_id": task_id, "by": by})
    )


def _spawn(coroutine: Any) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        coroutine.close()
        return
    task = loop.create_task(coroutine)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _spawn_resolve(project_id: str, *, task_id: str, by: str) -> None:
    async def _resolve() -> None:
        from .db.engine import async_session_factory

        try:
            async with async_session_factory() as db:
                await resolve_task(db, project_id, task_id, by=by)
        except Exception:  # noqa: BLE001 -- a background resolution must not raise
            logger.warning("could not resolve %s's stalls", task_id, exc_info=True)

    _spawn(_resolve())


@event.listens_for(Session, "after_commit")
def _report_deferred(session: Session) -> None:
    if session.in_nested_transaction():
        return
    for call, project_id, fields in session.info.pop(_PENDING_KEY, []):
        call(project_id, **fields)


@event.listens_for(Session, "after_rollback")
def _drop_deferred(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)


async def drain() -> None:
    """Wait for every report in flight (tests, and the sweep's own end)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def stall_key(cause: str, subject: str) -> str:
    return f"{cause}:{subject}"


def classify_unstaffed(reason: str) -> str:
    """A `decide_firing` unstaffed sentence is a refused delivery or a review nobody may take."""
    refused = (
        "No firing will retry it",
        "stopped retrying",
        "delivery was refused",
        "delivering it was refused",
        "waits behind refused input",
    )
    return "delivery_refused" if any(words in reason for words in refused) else "review_unstaffed"


async def _record_and_wake(project_id: str, **fields: Any) -> None:
    from .db.engine import async_session_factory

    try:
        async with async_session_factory() as db:
            stall, created = await record(db, project_id, **fields)
            if created:
                await wake(db, stall)
    except Exception:  # noqa: BLE001 -- a background report must not raise
        logger.warning("could not record a %s stall", fields.get("cause"), exc_info=True)


async def open_stall(db: AsyncSession, project_id: str, key: str) -> Optional[Stall]:
    return (
        await db.execute(
            select(Stall).where(
                Stall.project_id == project_id, Stall.key == key, Stall.ended_at.is_(None)
            )
        )
    ).scalar_one_or_none()


async def record(
    db: AsyncSession,
    project_id: str,
    *,
    cause: str,
    subject: str,
    text: str,
    task_id: Optional[str] = None,
    loop_id: Optional[str] = None,
) -> "tuple[Stall, bool]":
    """The open stall for this cause and subject, counted again, or a new one. Commits.

    A stall the mender gave up on is the operator's while its reason holds, so the same reason is
    counted on it rather than opening a new stall that wakes the mender to give up again (F1048:
    30 turns and 27 copies of one question in a night). A changed reason is a new situation.
    """
    key = stall_key(cause, subject)
    now = datetime.now(timezone.utc)
    stall = await open_stall(db, project_id, key)
    if stall is None:
        latest = (
            await db.execute(
                select(Stall)
                .where(Stall.project_id == project_id, Stall.key == key)
                .order_by(Stall.first_seen_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest is not None and latest.outcome == "gave_up" and latest.reason == text[:4000]:
            stall = latest
    if stall is not None:
        stall.last_seen_at = now
        stall.seen_count += 1
        await db.commit()
        return stall, False
    stall = Stall(
        id=f"stall-{short_id()}",
        project_id=project_id,
        key=key,
        cause=cause,
        reason=text[:4000],
        task_id=task_id,
        loop_id=loop_id,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(stall)
    await db.commit()
    await persist_event(db, project_id, STALL_RECORDED, view(stall))
    await _broadcast(project_id, STALL_RECORDED, view(stall))
    return stall, True


async def end(
    db: AsyncSession, stall: Stall, outcome: str, detail: str = "", *, commit: bool = True
) -> Stall:
    """End an open stall `fixed`, `gave_up` or `resolved`. Ending an ended one changes nothing."""
    if stall.ended_at is not None:
        return stall
    stall.outcome = outcome
    stall.outcome_detail = detail[:4000]
    stall.ended_at = datetime.now(timezone.utc)
    await _withdraw_unread_brief(db, stall)
    await _release_abandoned_mend(db, stall)
    if commit:
        await db.commit()
        await persist_event(db, stall.project_id, STALL_ENDED, view(stall))
        await _broadcast(stall.project_id, STALL_ENDED, view(stall))
    return stall


async def release_mend_checkout(db: AsyncSession, project_id: str, task_id: str) -> bool:
    """Remove the scratch checkout the mender built *task_id*'s mend in, if there is one.

    Never raises: it runs after the work it follows has been recorded, and a checkout that could
    not be removed is logged and left (the next mend of the task resumes it).
    """
    from . import project_workspace, worktrees

    try:
        root = (await project_workspace.resolve_project_workspace(db, project_id)).root
        path = worktrees.mend_checkout_path(root, MENDER, task_id)
        if not path.exists():
            return False
        return await blocking.run_serialized(worktrees.release_mend_checkout, root, MENDER, task_id)
    except Exception:  # noqa: BLE001 -- see above
        logger.warning("could not remove the mend checkout of %s", task_id, exc_info=True)
        return False


async def _release_abandoned_mend(db: AsyncSession, stall: Stall) -> None:
    """A stall that ends takes the mend checkout of its task with it, unless another open stall is
    still being mended on the same task (the mender works one thread across them)."""
    if not stall.task_id:
        return
    another = (
        await db.execute(
            select(func.count())
            .select_from(Stall)
            .where(
                Stall.project_id == stall.project_id,
                Stall.task_id == stall.task_id,
                Stall.ended_at.is_(None),
                Stall.id != stall.id,
            )
        )
    ).scalar_one()
    if not another:
        await release_mend_checkout(db, stall.project_id, stall.task_id)


async def _withdraw_unread_brief(db: AsyncSession, stall: Stall) -> None:
    """A brief still queued for an ended stall's thread is about nothing now: withdraw it, unless
    another open stall shares the thread (found 2026-10-23 by the acceptance drive: a conflict seen
    while the mender was mending left a second brief queued after both stalls had ended)."""
    if stall.conversation_id is None:
        return
    sharing = (
        await db.execute(
            select(func.count())
            .select_from(Stall)
            .where(
                Stall.conversation_id == stall.conversation_id,
                Stall.ended_at.is_(None),
                Stall.id != stall.id,
            )
        )
    ).scalar_one()
    if sharing:
        return
    entries = (
        (
            await db.execute(
                select(InboundQueueEntry).where(
                    InboundQueueEntry.conversation_id == stall.conversation_id,
                    InboundQueueEntry.agent == MENDER,
                    InboundQueueEntry.state == "queued",
                    # Only the brief. The operator's answer to a note the mender left is queued into
                    # this same thread, and the brief tells the mender to end the stall `gave_up`
                    # right after leaving the note: that answer is not about the stall's end and is
                    # delivered when the mender's run ends.
                    InboundQueueEntry.origin_type == "mender",
                )
            )
        )
        .scalars()
        .all()
    )
    for entry in entries:
        entry.state = "withdrawn"
        entry.withdrawn_at = stall.ended_at
        entry.abandoned_reason = f"The stall it briefed the mender on ended {stall.outcome}."


async def mending_thread(db: AsyncSession, stall: Stall) -> Optional[str]:
    """The thread of an open stall on the same task (or loop) the mender already holds, if any."""
    subject = []
    if stall.task_id:
        subject.append(Stall.task_id == stall.task_id)
    elif stall.loop_id:
        subject.append(Stall.loop_id == stall.loop_id)
    else:
        return None
    return (
        (
            await db.execute(
                select(Stall.conversation_id)
                .where(
                    Stall.project_id == stall.project_id,
                    Stall.id != stall.id,
                    Stall.ended_at.is_(None),
                    Stall.conversation_id.is_not(None),
                    *subject,
                )
                .order_by(Stall.first_seen_at)
            )
        )
        .scalars()
        .first()
    )


async def resolve_task(db: AsyncSession, project_id: str, task_id: str, *, by: str) -> None:
    """The task's work merged: its open integration stalls end, `fixed` when the mender landed it."""
    rows = (
        (
            await db.execute(
                select(Stall).where(
                    Stall.project_id == project_id,
                    Stall.task_id == task_id,
                    Stall.ended_at.is_(None),
                    Stall.cause.in_(("integration_skipped", "integration_failed")),
                )
            )
        )
        .scalars()
        .all()
    )
    for stall in rows:
        if by == MENDER:
            await end(db, stall, "fixed", "The mender landed the work.")
        else:
            await end(db, stall, "resolved", f"The work merged ({by or 'the Hub'}).")


def view(stall: Stall) -> Dict[str, Any]:
    def at(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value is not None else None

    return {
        "id": stall.id,
        "key": stall.key,
        "cause": stall.cause,
        "reason": stall.reason,
        "task_id": stall.task_id,
        "loop_id": stall.loop_id,
        "first_seen_at": at(stall.first_seen_at),
        "last_seen_at": at(stall.last_seen_at),
        "seen_count": stall.seen_count,
        "conversation_id": stall.conversation_id,
        "mender_turns": stall.mender_turns,
        "outcome": stall.outcome,
        "outcome_detail": stall.outcome_detail,
        "ended_at": at(stall.ended_at),
    }


async def list_stalls(
    db: AsyncSession, project_id: str, *, open_only: bool = False, limit: int = 50
) -> List[Dict[str, Any]]:
    query = select(Stall).where(Stall.project_id == project_id)
    if open_only:
        query = query.where(Stall.ended_at.is_(None))
    rows = (
        (await db.execute(query.order_by(Stall.last_seen_at.desc()).limit(limit))).scalars().all()
    )
    return [view(row) for row in rows]


async def _broadcast(project_id: str, event_type: str, data: Dict[str, Any]) -> None:
    from .sse import sse_manager

    try:
        await sse_manager.broadcast(project_id, event_type, data)
    except Exception:  # noqa: BLE001
        logger.debug("stall broadcast failed", exc_info=True)


# --- the mender ----------------------------------------------------------------------------------


def is_mender(agent: Optional[Agent]) -> bool:
    return agent is not None and (agent.config or {}).get("hub_role") == HUB_ROLE


async def mender_enabled(db: AsyncSession, project_id: str) -> bool:
    from . import manager

    row = await manager.get_job_row(db, project_id, manager.MENDER)
    return bool(row is not None and row.enabled and row.runner_id)


async def ensure_mender(db: AsyncSession, project_id: str) -> "tuple[Optional[Agent], str]":
    """The project's mender agent, made or brought up to date from its Manager choice.

    `(agent, "")`, or `(None, why)` when the Manager entry has no runner or the project already has
    an agent named `mender` the Hub did not make. Does not commit.
    """
    from . import manager

    row = await manager.get_job_row(db, project_id, manager.MENDER)
    if row is None or not row.runner_id:
        return None, "The mender has no runner: choose one on the Manager page."
    chosen = await db.get(Runner, row.runner_id)
    if chosen is None or chosen.project_id != project_id:
        return None, f"The mender's runner '{row.runner_id}' no longer exists in this project."
    runner = chosen
    # **No model chosen means the catalog's default for the runner's CLI, not the runner's own**
    # (`the-mender-wakes-only-for-real-stalls` D5). On :8000 the operator picked a runner, never a
    # model, and 42 mender turns in one night ran on that runner's Opus. Mending is reading state
    # and calling a few routes; the everyday model does it, and a model the operator chose on the
    # Manager page is kept. Resolved here, on every wake, so no migration moves an existing mender.
    #
    # A runner with its own model provider keeps its own model: the catalog's default names a
    # subscription model that provider may not serve.
    wanted = (
        row.model
        or (None if has_provider(chosen.provider_config) else default_model(chosen.cli))
        or chosen.model
    )
    if wanted and wanted != chosen.model:
        # The runner the mender is moved to carries the chosen runner's provider and flags: they
        # are how that runner runs, and only its model differs.
        candidates = (
            (
                await db.execute(
                    select(Runner)
                    .where(
                        Runner.project_id == project_id,
                        Runner.cli == chosen.cli,
                        Runner.model == wanted,
                    )
                    .order_by(Runner.created_at)
                )
            )
            .scalars()
            .all()
        )
        runner = next(
            (
                candidate
                for candidate in candidates
                if (candidate.flags or None) == (chosen.flags or None)
                and (candidate.provider_config or None) == (chosen.provider_config or None)
            ),
            None,
        ) or Runner(
            id=f"runner-{short_id()}",
            project_id=project_id,
            name=f"{chosen.cli} — {wanted} (mender)",
            cli=chosen.cli,
            model=wanted,
            flags=deepcopy(chosen.flags),
            provider_config=deepcopy(chosen.provider_config),
        )
        db.add(runner)
    agent = (
        await db.execute(select(Agent).where(Agent.project_id == project_id, Agent.name == MENDER))
    ).scalar_one_or_none()
    if agent is not None and not is_mender(agent):
        return None, (
            "This project already has its own agent named 'mender'. Rename or archive it to let "
            "the Hub's mender in; the Hub will not take an agent over."
        )
    if agent is None:
        from .agent_colors import next_color_index

        agent = Agent(
            id=f"agent-{short_id()}",
            project_id=project_id,
            name=MENDER,
            description="The Hub's mender: unblocks stalled work.",
            config={"hub_role": HUB_ROLE},
            color_index=await next_color_index(db, project_id),
            runner_id=runner.id,
        )
        db.add(agent)
        await db.flush()
    else:
        agent.runner_id = runner.id
        if agent.lifecycle != "open":
            agent.lifecycle = "open"
            agent.archived_at = None
    return agent, ""


async def wake(db: AsyncSession, stall: Stall) -> bool:
    """Brief the mender on *stall*, once, if the project has it on. Commits; True if briefed."""
    if stall.conversation_id is not None or stall.ended_at is not None:
        return False
    if stall.mender_turns >= MENDER_TURN_CAP:
        return False
    if not await mender_enabled(db, stall.project_id):
        return False
    shared = await mending_thread(db, stall)
    if shared is not None:
        # The mender is already on this task: the new cause is part of the same mending, and its
        # tools' answers tell it so. A second brief would start a turn after the first had fixed it.
        stall.conversation_id = shared
        await db.commit()
        return False
    agent, refusal = await ensure_mender(db, stall.project_id)
    if agent is None:
        stall.outcome_detail = refusal
        await db.commit()
        return False
    from .conversations import inherit_runtime_overrides, name_conversation, new_conversation
    from .inbound_queue import new_entry

    conversation = new_conversation(project_id=stall.project_id, agent=MENDER, origin="mender")
    name_conversation(conversation, f"Mending: {stall.reason[:80]}")
    db.add(conversation)
    await inherit_runtime_overrides(db, conversation)
    await db.flush()
    db.add(
        new_entry(
            project_id=stall.project_id,
            agent=MENDER,
            origin_type="mender",
            content=await brief(db, stall),
            hop_depth=0,
            conversation_id=conversation.id,
        )
    )
    stall.conversation_id = conversation.id
    stall.mender_turns += 1
    await db.commit()
    from .turn_scheduler import schedule_accepted

    await schedule_accepted(stall.project_id, MENDER)
    return True


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=30,
            **no_console_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"(git failed: {exc})"
    return (result.stdout or result.stderr).strip()


async def _mend_checkout_note(root: Path, task_id: str, commit: Optional[str]) -> str:
    """Make the scratch checkout of a mend and say where it is, or "" when it cannot be made.

    The mender builds a mend in a checkout of its own that the Hub removes afterwards
    (`worktrees.ensure_mend_checkout`), so its own workspace never leaves its branch.
    """
    from . import worktrees

    if not commit or not await blocking.run(worktrees.is_git_repo, root):
        return ""
    try:
        path = await blocking.run_serialized(
            worktrees.ensure_mend_checkout, root, MENDER, task_id, commit
        )
    except (worktrees.IsolationUnavailableError, worktrees.GitCommandError, OSError) as exc:
        logger.warning("no mend checkout for %s: %s", task_id, exc)
        return ""
    return (
        f"it is ready at {path}, on branch {worktrees.mend_branch_name(task_id)} cut from "
        f"{commit[:12]}. Work there (`git -C {path} ...`, or edit files under it)."
    )


async def brief(db: AsyncSession, stall: Stall) -> str:
    """The facts the mender starts from, and what it may do with them."""
    from . import project_workspace, worktrees

    lines = [
        "You are the mender, the Hub's agent for stalled work. Your one job is to get this "
        "project's agents moving again. You do no feature work.",
        "",
        f"## The stall ({stall.id})",
        f"Cause: {stall.cause}",
        stall.reason,
    ]
    project = await db.get(Project, stall.project_id)
    root: Optional[Path] = None
    try:
        root = (await project_workspace.resolve_project_workspace(db, stall.project_id)).root
    except Exception:  # noqa: BLE001 -- a brief without the repository still helps
        root = None
    mend_note = ""
    if stall.task_id:
        task = await db.get(Task, stall.task_id)
        if task is not None:
            lines += [
                "",
                f"## The task {task.id}",
                f"Title: {task.title}",
                f"Status: {task.status}; assignee: {task.assignee or 'nobody'}",
                f"Branch: {worktrees.task_branch_name(task.id)}",
            ]
            deps = (
                (await db.execute(select(TaskDependency).where(TaskDependency.task_id == task.id)))
                .scalars()
                .all()
            )
            for dep in deps:
                other = await db.get(Task, dep.depends_on_task_id)
                if other is not None:
                    lines.append(f"Depends on {other.id} ({other.title!r}): {other.status}")
            integrations = (
                (
                    await db.execute(
                        select(TaskIntegration)
                        .where(TaskIntegration.task_id == task.id)
                        .order_by(TaskIntegration.created_at.desc())
                        .limit(3)
                    )
                )
                .scalars()
                .all()
            )
            for row in integrations:
                lines.append(
                    f"Merge {row.created_at:%Y-%m-%d %H:%M} of commit {row.commit_sha or '-'} "
                    f"(branch {row.source_branch or '-'}) by {row.actor or row.actor_kind}: "
                    f"{row.outcome} {(row.reason or '')[:300]}"
                )
            if task.status == "approved" and integrations and root is not None:
                mend_note = await _mend_checkout_note(root, task.id, integrations[0].commit_sha)
    if stall.loop_id:
        loop = await db.get(Loop, stall.loop_id)
        if loop is not None:
            job = await db.get(AIJob, loop.job_id)
            lines += ["", f"## The loop {loop.id}", f"Job: {job.name if job else loop.job_id}"]
    refused = (
        (
            await db.execute(
                select(InboundQueueEntry)
                .where(
                    InboundQueueEntry.project_id == stall.project_id,
                    InboundQueueEntry.state == "queued",
                    InboundQueueEntry.agent != MENDER,
                )
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    if refused:
        lines += ["", "## Input waiting in agents' queues"]
        for entry in refused:
            lines.append(f"{entry.id} for {entry.agent} (task {entry.task_id or '-'})")
    if root is not None:
        main = (project.main_branch if project else None) or "the main branch"
        lines += [
            "",
            "## The project's checkout",
            f"Path: {root}; main branch: {main}",
            "git status --short:",
            await blocking.run(_git, root, "status", "--short") or "(clean)",
        ]
    lines += [
        "",
        "## What you may do on your own, without review",
        "- Resolve a merge conflict on an approved task's work, in the scratch checkout the Hub "
        "makes for the mend (never in your own workspace, which must stay on its own branch): "
        + (
            mend_note
            or "none could be made for this task (no merge to cut it from above). Ask the operator."
        )
        + " Merge the main branch into it, resolve the conflict keeping the task's intent, "
        "commit, then call `mend_task_branch(task_id, <your commit>)`. The Hub runs the "
        "project's checks on it, merges it, and removes the scratch checkout. No reviewer is "
        "involved.",
        "- Retry a merge whose obstacle is gone: `mend_task_branch(task_id)` with no commit.",
        "- Withdraw input whose delivery was refused, so the next firing briefs the agent again: "
        "`mend_withdraw_input(entry_id)`.",
        "- Hand a stuck task back to the queue or to another agent: "
        "`mend_reset_task(task_id, status, assignee)` (status `assigned` or `pending`).",
        "- Hand finished (`completed`) work nobody is moving to a reviewer who did not write it: "
        '`mend_reset_task(task_id, "under_review", reviewer)` queues that reviewer\'s review turn.',
        "- Read anything: files, git log, the task, the spec.",
        "",
        "## What you must leave the operator a note about, and not do (ask_user)",
        "- Touching uncommitted changes you did not make, anywhere (the project's checkout above "
        "included). Never stash, reset, checkout over, commit or delete someone else's work.",
        "- Rewriting or reverting the main branch, force-pushing, deleting a branch or any work.",
        "- Rejecting or deleting a task; changing a specification or its requirements.",
        "- Changing agents, permissions, budgets or project settings.",
        "- Changing product logic beyond the conflicting lines.",
        "- A fix whose checks fail.",
        "The operator is usually away when you are woken, so nothing waits for them. For each of "
        "these, leave your question as a note with `ask_user`: it returns at once, and the "
        "answer reaches you later as a message in this conversation. Do not take the action. "
        "Offer concrete options in the note, and say which you recommend. Then end the stall "
        'with `mend_end_stall(stall_id, "gave_up", summary)` and a summary that names the note.',
        "",
        "## How to end",
        "Call `mend_end_stall(stall_id, outcome, summary)` with outcome `fixed` once the agents "
        "can move again, or `gave_up` with what the operator needs to know (and the note you "
        "left, if you left one). A summary is two or "
        f"three plain sentences. The stall id is {stall.id}.",
    ]
    return "\n".join(lines)


# --- the sweep -----------------------------------------------------------------------------------


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def sweep(*, now: Optional[datetime] = None) -> int:
    """Record the stalls nothing else decides: dead runs, stuck tasks, a loop that stopped moving.

    Runs every `SWEEP_SECONDS` while the Hub is up. Returns how many it reported. Never raises.
    """
    from .db.engine import async_session_factory

    try:
        async with async_session_factory() as db:
            reported = await _sweep(db, now or datetime.now(timezone.utc))
    except Exception:  # noqa: BLE001
        logger.warning("stall sweep failed", exc_info=True)
        return 0
    await drain()
    return reported


async def _sweep(db: AsyncSession, now: datetime) -> int:
    from . import instance_identity
    from .run_liveness import live_run_ids

    window = timedelta(minutes=NO_PROGRESS_MINUTES)
    reported = 0
    running = (
        (await db.execute(select(Run).where(Run.status == "running", Run.agent != MENDER)))
        .scalars()
        .all()
    )
    live_tasks = {run.task_id for run in running if run.task_id}
    # A run is dead when it is recorded running and this Hub is not executing it (F1043). How long
    # it has been quiet says nothing: a run waiting on a 20-minute test suite sends nothing and is
    # well, and the heartbeat this used to read is written by nothing, so every run over ten
    # minutes was reported. The registry holds a run exactly while this process executes it.
    live = live_run_ids()
    here = instance_identity.get()
    await _end_dead_run_stalls_that_recovered(db, live)
    await _end_stuck_task_stalls_that_moved(db)
    for run in running:
        started = _aware(run.started_at)
        if run.id in live or started is None or started > now - DEAD_RUN_GRACE:
            continue
        if run.instance_id and here and run.instance_id != here:
            continue  # another Hub's run; this process cannot see its registry
        report(
            run.project_id,
            cause="dead_run",
            subject=run.id,
            text=(
                f"{run.agent}'s run {run.id} (started {started:%H:%M} UTC) is recorded running, "
                "but this Hub is not executing it: its process ended without the end being "
                "recorded."
            ),
            task_id=run.task_id,
        )
        reported += 1
    stuck = (await db.execute(select(Task).where(Task.status == "in_progress"))).scalars().all()
    for task in stuck:
        updated = _aware(task.updated)
        if task.id in live_tasks or updated is None or updated > now - window:
            continue
        report(
            task.project_id,
            cause="stuck_task",
            subject=task.id,
            text=(
                f"{task.id} ({task.title!r}) has been in progress since {updated:%H:%M} UTC with "
                f"no run working it."
            ),
            task_id=task.id,
        )
        reported += 1
    loops = (
        await db.execute(
            select(Loop, AIJob)
            .join(AIJob, AIJob.id == Loop.job_id)
            .where(
                Loop.stopped_at.is_(None),
                Loop.archived_at.is_(None),
                AIJob.enabled.is_(True),
                AIJob.archived_at.is_(None),
            )
        )
    ).all()
    for loop, job in loops:
        open_work = (
            await db.execute(
                select(func.count())
                .select_from(Task)
                .where(Task.loop_id == loop.id, Task.status.not_in(("approved", "rejected")))
            )
        ).scalar_one()
        if not open_work:
            continue
        last_run = (
            await db.execute(
                select(func.max(Run.started_at)).where(Run.project_id == loop.project_id)
            )
        ).scalar_one()
        last_move = (
            await db.execute(
                select(func.max(TaskTransition.created_at)).where(
                    TaskTransition.project_id == loop.project_id
                )
            )
        ).scalar_one()
        moments = [m for m in (_aware(last_run), _aware(last_move), _aware(loop.created_at)) if m]
        last = max(moments) if moments else None
        key = stall_key("no_progress", loop.id)
        if last is not None and last > now - window:
            existing = await open_stall(db, loop.project_id, key)
            if existing is not None:
                await end(db, existing, "resolved", "The loop moved again.")
            continue
        report(
            loop.project_id,
            cause="no_progress",
            subject=loop.id,
            text=(
                f"The loop {job.name!r} has {open_work} open task(s) and nothing has moved since "
                f"{last:%H:%M} UTC: no run started and no task changed status."
                if last
                else f"The loop {job.name!r} has {open_work} open task(s) and has never moved."
            ),
            loop_id=loop.id,
        )
        reported += 1
    return reported


async def _end_dead_run_stalls_that_recovered(db: AsyncSession, live: set) -> None:
    """End each open `dead_run` stall whose run this Hub is executing, or which has ended."""
    open_stalls = (
        (await db.execute(select(Stall).where(Stall.cause == "dead_run", Stall.ended_at.is_(None))))
        .scalars()
        .all()
    )
    for stall in open_stalls:
        run_id = stall.key.split(":", 1)[-1]
        run = await db.get(Run, run_id)
        if run_id in live:
            await end(db, stall, "resolved", "The run is alive: this Hub is executing it.")
        elif run is None or run.status != "running":
            await end(db, stall, "resolved", "The run has ended.")


async def _end_stuck_task_stalls_that_moved(db: AsyncSession) -> None:
    """End each open `stuck_task` stall whose task is gone or no longer in progress (F1050).

    A transition ends it through `resolve_task`; a deleted task goes through none, and its stall
    stayed open for days on :8000.
    """
    open_stalls = (
        (
            await db.execute(
                select(Stall).where(Stall.cause == "stuck_task", Stall.ended_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    for stall in open_stalls:
        task = await db.get(Task, stall.key.split(":", 1)[-1])
        if task is None:
            await end(db, stall, "resolved", "The task no longer exists.")
        elif task.status != "in_progress":
            await end(db, stall, "resolved", f"The task moved to {task.status}.")


async def sweep_forever() -> None:
    """The Hub's stall sweep, started in `main.lifespan` and cancelled with it."""
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        await sweep()
