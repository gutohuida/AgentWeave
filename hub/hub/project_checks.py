"""A project's checks, run on the work a task's approval would merge (`approval-runs-the-projects-checks`).

The operator configures checks (`Project.checks`); nothing an agent sends is ever executed here. A run
builds the commit approval would produce -- main's tip with each merge target applied, through
`git merge-tree` and `commit-tree`, touching no checkout (design D1) -- checks it out in a scratch
worktree under `.agentweave/checks/<task_id>` (D2), runs each check there with the Hub's own
configuration removed from the environment (D8), and records a `TaskCheckRun` row (D3).

Runs are started in the background, never inside a request (D5): when a task is completed outside a
turn, when a turn bound to a completed task ends (its work is only committed then), and when approval
finds no current result. At most two run at once per Hub, and one per task (D4). The approval gate only
*reads* what is recorded (`view`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import Project, Run, Task, TaskCheckRun
from .subprocess_windows import no_console_kwargs
from .utils import short_id

logger = logging.getLogger(__name__)

CHECKS_DIR = Path(".agentweave") / "checks"
MAX_CONCURRENT_RUNS = 2
OUTPUT_TAIL_CHARS = 4000
DEFAULT_TIMEOUT_SECONDS = 900
GIT_TIMEOUT_SECONDS = 60

#: Terminal states a gate may judge on, as opposed to `running` and `interrupted`.
DECIDED = ("passed", "failed", "error")

#: The Hub's own configuration, never handed to a project's command: its credentials, its database,
#: its address. A check runs the *project's* tests; the Hub's settings are not the project's.
_HUB_ONLY_PREFIXES = ("AW_", "HUB_", "AGENTWEAVE_")
_HUB_ONLY_NAMES = ("DATABASE_URL",)
_HUB_ONLY_VALUE_PREFIXES = ("aw_live_", "aw_run_")
_CREDENTIAL_RE = re.compile(r"aw_(?:live|run)_[A-Za-z0-9_\-]+")
_REDACTED = "[redacted]"


# --- configuration -------------------------------------------------------------------------------


def configured_checks(project: Optional[Project]) -> List[Dict[str, Any]]:
    """The project's checks, normalised; empty for none (null and `[]` mean the same)."""
    if project is None or not project.checks:
        return []
    checks = []
    for check in project.checks:
        if isinstance(check, dict) and check.get("name") and check.get("command"):
            checks.append(
                {
                    "name": str(check["name"]),
                    "command": str(check["command"]),
                    "timeout_seconds": int(check.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
                }
            )
    return checks


# --- git -----------------------------------------------------------------------------------------


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    from .worktrees import COMMIT_IDENTITY

    return subprocess.run(
        [
            "git",
            "-c",
            f"user.name={COMMIT_IDENTITY[0]}",
            "-c",
            f"user.email={COMMIT_IDENTITY[1]}",
            *args,
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        check=False,
        **no_console_kwargs(),
    )


def main_tip(root: Path, main_branch: str) -> Optional[str]:
    result = _git(root, "rev-parse", "--verify", f"refs/heads/{main_branch}")
    return result.stdout.strip() if result.returncode == 0 else None


def build_merged_commit(
    root: Path, main_sha: str, target_shas: Sequence[str]
) -> Tuple[Optional[str], str]:
    """`(commit, "")` whose tree is *main_sha* with every target merged in order, or `(None, why)`.

    Plumbing only (D1): `merge-tree --write-tree` gives each merged tree and `commit-tree` a commit
    to merge the next target onto. The commits are unreferenced; nothing moves a branch, and no
    checkout or index changes. A target already in the base is skipped, as `integrate` skips it.
    """
    base = main_sha
    for target in target_shas:
        ancestor = _git(root, "merge-base", "--is-ancestor", target, base)
        if ancestor.returncode == 0:
            continue
        merged = _git(root, "merge-tree", "--write-tree", "--name-only", base, target)
        lines = merged.stdout.splitlines()
        if merged.returncode != 0 or not lines:
            paths = [line.strip() for line in lines[1:] if line.strip()][:10]
            return None, (
                f"{target[:12]} does not merge cleanly onto {base[:12]}"
                + (f" ({', '.join(paths)})" if paths else "")
                + ", so there is no merged work to check"
            )
        tree = lines[0].strip()
        commit = _git(
            root,
            "commit-tree",
            tree,
            "-p",
            base,
            "-p",
            target,
            "-m",
            f"agentweave checks: {target[:12]} onto {base[:12]}",
        )
        if commit.returncode != 0:
            return None, f"git commit-tree failed: {commit.stderr.strip()[:300]}"
        base = commit.stdout.strip()
    return base, ""


def _checkout_path(root: Path, task_id: str) -> Path:
    return root / CHECKS_DIR / task_id


def _remove_checkout(root: Path, path: Path) -> None:
    _git(root, "worktree", "remove", "--force", str(path))
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    _git(root, "worktree", "prune")


def _checkout(root: Path, task_id: str, commit: str) -> Path:
    """A detached scratch worktree at *commit*, owned by the Hub and by this task alone (D2)."""
    from .worktrees import _symlink_shared_dependencies

    path = _checkout_path(root, task_id)
    _remove_checkout(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    added = _git(root, "worktree", "add", "--detach", "--force", str(path), commit)
    if added.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {added.stderr.strip()[:300]}")
    _symlink_shared_dependencies(root, path)
    return path


# --- running one check ---------------------------------------------------------------------------


def check_environment() -> Tuple[Dict[str, str], List[str]]:
    """The Hub's environment minus its own configuration (D8), and the values removed."""
    env: Dict[str, str] = {}
    removed: List[str] = []
    for name, value in os.environ.items():
        hub_only = (
            name.upper().startswith(_HUB_ONLY_PREFIXES)
            or name.upper() in _HUB_ONLY_NAMES
            or value.startswith(_HUB_ONLY_VALUE_PREFIXES)
        )
        if hub_only:
            removed.append(value)
        else:
            env[name] = value
    return env, removed


def scrub(text: str, removed: Sequence[str]) -> str:
    for value in sorted({v for v in removed if len(v) >= 8}, key=len, reverse=True):
        text = text.replace(value, _REDACTED)
    return _CREDENTIAL_RE.sub(_REDACTED, text)


def run_one(check: Dict[str, Any], cwd: Path) -> Dict[str, Any]:
    """Run one check to completion or its timeout; end its whole process tree on a timeout."""
    from .pty_runner import IS_WINDOWS, terminate_process_tree

    env, removed = check_environment()
    started = time.monotonic()
    proc = subprocess.Popen(
        check["command"],
        shell=True,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=not IS_WINDOWS,
        **no_console_kwargs(),
    )
    timed_out = False
    try:
        output, _ = proc.communicate(timeout=check["timeout_seconds"])
    except subprocess.TimeoutExpired:
        timed_out = True
        terminate_process_tree(proc.pid)
        try:
            output, _ = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            output = b""
    text = scrub((output or b"").decode("utf-8", "replace"), removed)
    if timed_out:
        text += f"\n[the check ran past its {check['timeout_seconds']}s timeout and was ended]"
    return {
        "name": check["name"],
        "exit_code": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 1),
        "output_tail": text[-OUTPUT_TAIL_CHARS:],
    }


def failed(result: Dict[str, Any]) -> bool:
    return bool(result.get("timed_out")) or result.get("exit_code") != 0


# --- records -------------------------------------------------------------------------------------


async def latest_run(session: AsyncSession, task_id: str) -> Optional[TaskCheckRun]:
    return (
        (
            await session.execute(
                select(TaskCheckRun)
                .where(TaskCheckRun.task_id == task_id)
                .order_by(TaskCheckRun.started_at.desc(), TaskCheckRun.id.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


@dataclass
class CheckView:
    """What the gate may say about a task's checks right now."""

    #: `passed`, `failed`, `error`, `running`, `interrupted`, `stale` or `missing`.
    state: str
    run: Optional[TaskCheckRun] = None


async def view(
    session: AsyncSession, task: Task, root: Path, main_branch: str, target_shas: List[str]
) -> Optional[CheckView]:
    """The task's check result for the work approval would merge now, or `None` where no check
    applies (no checks configured, nothing to merge, no main tip). Reads only; starts nothing."""
    project = await session.get(Project, task.project_id)
    if not configured_checks(project) or not target_shas:
        return None
    tip = await asyncio.to_thread(main_tip, root, main_branch)
    if tip is None:
        return None
    run = await latest_run(session, task.id)
    if run is None:
        return CheckView("missing")
    if run.state in ("running", "interrupted"):
        return CheckView(run.state, run)
    if run.main_sha != tip or list(run.target_shas or []) != list(target_shas):
        return CheckView("stale", run)
    return CheckView(run.state, run)


async def _finish(run_id: str, **fields: Any) -> None:
    async with async_session_factory() as session:
        run = await session.get(TaskCheckRun, run_id)
        if run is None or run.state != "running":
            return
        for name, value in fields.items():
            setattr(run, name, value)
        if fields.get("state") in DECIDED:
            run.ended_at = datetime.now(timezone.utc)
        await session.commit()


# --- the queue -----------------------------------------------------------------------------------

_inflight: Dict[str, "asyncio.Task[None]"] = {}
_starting: Set[str] = set()
_pending: Set["asyncio.Task[Any]"] = set()
_semaphores: Dict[int, asyncio.Semaphore] = {}


def _semaphore() -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _semaphores:
        _semaphores[loop_id] = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
    return _semaphores[loop_id]


def is_running(task_id: str) -> bool:
    current = _inflight.get(task_id)
    return task_id in _starting or (current is not None and not current.done())


async def request_run(project_id: str, task_id: str, *, force: bool = False) -> Optional[str]:
    """Start a run for *task_id* unless one is executing or the latest result is current.

    Returns the id of the run that is or will be current, or `None` where no check applies or one is
    already executing. *force* (the operator's re-run) starts one even over a current result.
    """
    if is_running(task_id):
        return None
    _starting.add(task_id)
    try:
        from . import task_integration
        from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

        async with async_session_factory() as session:
            project = await session.get(Project, project_id)
            task = await session.get(Task, task_id)
            checks = configured_checks(project)
            if not checks or task is None or project is None or not project.main_branch:
                return None
            try:
                root = (await resolve_project_workspace(session, project_id)).root
            except ProjectWorkspaceError:
                return None
            tip = await asyncio.to_thread(main_tip, root, project.main_branch)
            if tip is None:
                return None
            targets = [
                t.commit_sha for t in await task_integration.merge_targets(session, task, root)
            ]
            if not targets:
                return None
            latest = await latest_run(session, task_id)
            if (
                not force
                and latest is not None
                and latest.state in DECIDED
                and latest.main_sha == tip
                and list(latest.target_shas or []) == targets
            ):
                return latest.id
            run = TaskCheckRun(
                id=f"chk-{short_id()}",
                project_id=project_id,
                task_id=task_id,
                main_sha=tip,
                target_shas=targets,
                state="running",
                results=[],
                error="",
            )
            session.add(run)
            await session.commit()
            run_id = run.id
        job = asyncio.get_running_loop().create_task(
            _execute(run_id, task_id, root, tip, targets, checks)
        )
        _inflight[task_id] = job
        job.add_done_callback(lambda done: _inflight.pop(task_id, None))
        return run_id
    finally:
        _starting.discard(task_id)


async def _execute(
    run_id: str,
    task_id: str,
    root: Path,
    main_sha: str,
    targets: List[str],
    checks: List[Dict[str, Any]],
) -> None:
    results: List[Dict[str, Any]] = []
    try:
        async with _semaphore():
            merged, why = await asyncio.to_thread(build_merged_commit, root, main_sha, targets)
            if merged is None:
                await _finish(run_id, state="error", error=why)
                return
            path = await asyncio.to_thread(_checkout, root, task_id, merged)
            try:
                for check in checks:
                    results.append(await asyncio.to_thread(run_one, check, path))
                    await _finish(run_id, merged_sha=merged, results=list(results))
            finally:
                await asyncio.to_thread(_remove_checkout, root, path)
            state = "failed" if any(failed(r) for r in results) else "passed"
            await _finish(run_id, state=state, merged_sha=merged, results=list(results))
    except Exception as exc:  # noqa: BLE001 -- a run must end recorded, never `running` forever
        logger.warning("check run %s failed to complete", run_id, exc_info=True)
        await _finish(
            run_id, state="error", results=list(results), error=f"{type(exc).__name__}: {exc}"
        )


def schedule(project_id: str, task_id: str) -> None:
    """Fire-and-forget `request_run`. Never raises, so it may sit anywhere a wake may."""
    try:
        job = asyncio.get_running_loop().create_task(request_run(project_id, task_id))
    except Exception:  # noqa: BLE001
        logger.warning("could not schedule checks for task %s", task_id, exc_info=True)
        return
    _pending.add(job)
    job.add_done_callback(_pending.discard)


async def _after_run(project_id: str, run_id: str) -> None:
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None or not run.task_id:
            return
        task = await session.get(Task, run.task_id)
        if task is None or task.status != "completed":
            return
    await request_run(project_id, task.id)


async def configured_for(session: AsyncSession, project_id: str) -> bool:
    """Whether *project_id* has checks, read through the caller's session. Never raises."""
    try:
        return bool(configured_checks(await session.get(Project, project_id)))
    except Exception:  # noqa: BLE001
        logger.warning("could not read checks for project %s", project_id, exc_info=True)
        return False


def after_run(project_id: str, run_id: str) -> None:
    """At a run's end, after its snapshot commit: check the completed task it was bound to.

    The commit holding a turn's work is made when the turn ends, so a task an agent completed
    mid-turn is only checkable now. Never raises.
    """
    try:
        job = asyncio.get_running_loop().create_task(_after_run(project_id, run_id))
    except Exception:  # noqa: BLE001
        logger.warning("could not schedule checks after run %s", run_id, exc_info=True)
        return
    _pending.add(job)
    job.add_done_callback(_pending.discard)


async def drain() -> None:
    """Wait for every scheduled request and executing run (tests, and shutdown)."""
    while _pending or any(not job.done() for job in _inflight.values()):
        await asyncio.gather(*list(_pending), *list(_inflight.values()), return_exceptions=True)


async def interrupt_leftover_runs() -> int:
    """Mark runs a previous Hub left `running` as `interrupted` (startup reconcile, D4)."""
    async with async_session_factory() as session:
        result = await session.execute(
            update(TaskCheckRun)
            .where(TaskCheckRun.state == "running")
            .values(
                state="interrupted",
                ended_at=datetime.now(timezone.utc),
                error="the Hub stopped while this run was in progress",
            )
        )
        await session.commit()
        return int(result.rowcount or 0)


def run_view(run: TaskCheckRun) -> Dict[str, Any]:
    """A check run as the task drawer reads it."""
    return {
        "id": run.id,
        "state": run.state,
        "main_sha": run.main_sha,
        "target_shas": list(run.target_shas or []),
        "merged_sha": run.merged_sha,
        "results": list(run.results or []),
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
    }
