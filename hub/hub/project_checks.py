"""A project's checks, run on the work a task's approval would merge (`approval-runs-the-projects-checks`).

The operator configures checks (`Project.checks`); nothing an agent sends is ever executed here. A run
builds the commit approval would produce -- main's tip with each merge target applied, through
`git merge-tree` and `commit-tree`, touching no checkout (design D1) -- checks it out in a scratch
worktree under `.agentweave/checks/<task_id>` (D2), runs each check there with the Hub's own
configuration removed from the environment (D8), stopping at the first failure that is the task's own
(a failure main shares does not stop it), and records a `TaskCheckRun` row (D3).

Runs are started in the background, never inside a request (D5): when a task is completed outside a
turn, when a turn bound to a completed task ends (its work is only committed then), when approval
finds no current result, and when the project's main tip moves (`refresh`: the Hub's own merge, or
`watch_main_forever` noticing one made outside it). A run main moved past is ended, recorded
`superseded`, and replaced. At most two run at once per Hub, and one per task (D4). The approval gate
only *reads* what is recorded (`view`), and still counts only a result for the current tip.

A check may name the paths it covers (`paths`): where no file the merged work changes matches one, it
is not executed and is recorded skipped, which passes.
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

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import traces
from .db.engine import async_session_factory
from .db.models import Project, Run, Task, TaskCheckRun, TaskTransition
from .subprocess_windows import no_console_kwargs
from .utils import short_id

logger = logging.getLogger(__name__)

CHECKS_DIR = Path(".agentweave") / "checks"
MAX_CONCURRENT_RUNS = 2
OUTPUT_TAIL_CHARS = 4000
DEFAULT_TIMEOUT_SECONDS = 900
GIT_TIMEOUT_SECONDS = 60
#: Materialising and removing the scratch worktree writes the whole tree, which on a large repository
#: under load ran past `GIT_TIMEOUT_SECONDS` (F516: 3,300 files, 60s, the run recorded `error`).
CHECKOUT_TIMEOUT_SECONDS = 900

#: Terminal states a gate may judge on, as opposed to `running`, `interrupted` and `superseded`.
DECIDED = ("passed", "failed", "error")
#: A run ended because the main tip it was cut from moved; a run on the new tip replaces it.
SUPERSEDED = "superseded"
#: The task states whose results are refreshed when main moves: those waiting for review.
AWAITING_REVIEW = ("completed", "under_review")
#: How often each project's main tip is read, to notice a move made outside the Hub. Two looks fit
#: inside the 120 seconds the refresh promises.
WATCH_SECONDS = 30.0

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
                    "paths": [str(p) for p in check.get("paths") or [] if str(p).strip()],
                }
            )
    return checks


# --- paths ---------------------------------------------------------------------------------------


def _pattern_regex(pattern: str) -> "re.Pattern[str]":
    """A glob over repository-relative paths: `**` crosses directories, `*` and `?` do not, and a
    pattern ending in `/` names everything beneath that directory."""
    pattern = pattern.strip().replace("\\", "/").lstrip("/")
    if pattern.endswith("/"):
        pattern += "**"
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def path_matches(pattern: str, path: str) -> bool:
    return bool(_pattern_regex(pattern).match(path))


def changed_paths(root: Path, base: str, merged: str) -> Optional[List[str]]:
    """The files that differ between *base* and *merged*, both sides of a rename; `None` if unknown."""
    result = _git(root, "diff", "--name-only", "--no-renames", "-z", base, merged)
    if result.returncode != 0:
        return None
    return [path for path in result.stdout.split("\0") if path]


def skipped(check: Dict[str, Any], changed: Optional[List[str]]) -> Optional[Dict[str, Any]]:
    """The skipped result for *check* where it names paths and no file in *changed* matches one,
    else `None`: it runs. Unknown changes run it; a check is never skipped on a guess."""
    paths = check.get("paths") or []
    if not paths or changed is None:
        return None
    if any(path_matches(pattern, path) for pattern in paths for path in changed):
        return None
    return {
        "name": check["name"],
        "skipped": True,
        "reason": "no changed file matched its paths (" + ", ".join(paths) + ")",
        "exit_code": None,
        "timed_out": False,
        "duration_seconds": 0.0,
        "output_tail": "",
    }


# --- git -----------------------------------------------------------------------------------------


def _git(root: Path, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    from .worktrees import COMMIT_IDENTITY

    return traces.run(
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
        timeout=timeout,
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
    # F521: a run killed mid-`add` leaves the registration `locked`. One `--force` does not remove a
    # locked worktree, `prune` skips it, and every later `add` is refused; unlock it first.
    _git(root, "worktree", "unlock", str(path))
    _git(
        root,
        "worktree",
        "remove",
        "--force",
        "--force",
        str(path),
        timeout=CHECKOUT_TIMEOUT_SECONDS,
    )
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    _git(root, "worktree", "prune")


def _checkout(root: Path, task_id: str, commit: str) -> Path:
    """A detached scratch worktree at *commit*, owned by the Hub and by this task alone (D2)."""
    from .worktrees import _symlink_shared_dependencies

    path = _checkout_path(root, task_id)
    _remove_checkout(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    added = _git(
        root,
        "worktree",
        "add",
        "--detach",
        "--force",
        str(path),
        commit,
        timeout=CHECKOUT_TIMEOUT_SECONDS,
    )
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


def run_one(check: Dict[str, Any], cwd: Path, owner: Optional[str] = None) -> Dict[str, Any]:
    """Run one check to completion or its timeout; end its whole process tree on a timeout.

    *owner*, a task id, registers the process so `supersede` can end its tree from the event loop.
    """
    with traces.command(check["command"], name=f"check {check['name']}") as span:
        result = _run_one(check, cwd, owner)
        traces.exited(
            span,
            result["exit_code"],
            why=f"ran past its {check['timeout_seconds']}s timeout" if result["timed_out"] else "",
        )
    return result


def _run_one(check: Dict[str, Any], cwd: Path, owner: Optional[str] = None) -> Dict[str, Any]:
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
    if owner is not None:
        _processes[owner] = proc
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
    finally:
        if owner is not None and _processes.get(owner) is proc:
            _processes.pop(owner, None)
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
    if result.get("skipped"):
        return False  # no changed file matched its paths, which passes
    return bool(result.get("timed_out")) or result.get("exit_code") != 0


def preexisting(result: Dict[str, Any]) -> bool:
    """A failure main shares (F605): the same check failed on the main tip the run was cut from.
    A run recorded before this field existed reads as not pre-existing, i.e. as before."""
    return failed(result) and bool(result.get("preexisting"))


def _record_main_result(result: Dict[str, Any], on_main: Dict[str, Any]) -> None:
    result["on_main"] = {"exit_code": on_main["exit_code"], "timed_out": on_main["timed_out"]}
    result["preexisting"] = failed(on_main)


class _MainBaseline:
    """The main tip the run was cut from, checked out on the first failure and kept for the rest.

    A failing check is run there at once (F605, D1): its answer decides whether the run goes on.
    Best-effort: a baseline that cannot be taken leaves the result as it was, charged to the task.
    """

    def __init__(self, root: Path, task_id: str, main_sha: str) -> None:
        self.root, self.main_sha, self.task_id = root, main_sha, task_id
        self.name = f"{task_id}.main"
        self.path: Optional[Path] = None
        self.unavailable = False

    async def record(self, check: Dict[str, Any], result: Dict[str, Any]) -> None:
        if self.unavailable:
            return
        try:
            if self.path is None:
                self.path = await asyncio.to_thread(_checkout, self.root, self.name, self.main_sha)
            _record_main_result(
                result, await asyncio.to_thread(run_one, check, self.path, self.task_id)
            )
        except Exception:  # noqa: BLE001 -- the task's own result stands without main's
            self.unavailable = True
            logger.warning("could not run check %s on main", check["name"], exc_info=True)

    async def close(self) -> None:
        if self.path is not None:
            await asyncio.to_thread(_remove_checkout, self.root, self.path)


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


def unmerged(root: Path, tip: str, target_shas: Sequence[str]) -> List[str]:
    """The targets not already in the main tip (F518). A task serving requirements another task
    already landed carries that task's accepted evidence among its merge targets; checking it would
    re-check the main branch and blame its failures on this task. Unknown reachability is kept."""
    from .requirement_evidence import is_reachable_from

    return [sha for sha in target_shas if is_reachable_from(root, sha, tip) is not True]


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
    target_shas = await asyncio.to_thread(unmerged, root, tip, target_shas)
    if not target_shas:
        return None
    run = await latest_run(session, task.id)
    if run is None:
        return CheckView("missing")
    if run.state in ("running", "interrupted"):
        return CheckView(run.state, run)
    if (
        run.state == SUPERSEDED
        or run.main_sha != tip
        or list(run.target_shas or []) != list(target_shas)
    ):
        return CheckView("stale", run)
    return CheckView(run.state, run)


async def _finish(run_id: str, **fields: Any) -> None:
    async with async_session_factory() as session:
        run = await session.get(TaskCheckRun, run_id)
        if run is None or run.state != "running":
            return
        for name, value in fields.items():
            setattr(run, name, value)
        if fields.get("state") in (*DECIDED, SUPERSEDED):
            run.ended_at = datetime.now(timezone.utc)
        await session.commit()


# --- the queue -----------------------------------------------------------------------------------

_inflight: Dict[str, "asyncio.Task[None]"] = {}
#: The project and main tip each in-flight run was cut from, by task.
_inflight_tips: Dict[str, Tuple[str, str]] = {}
#: Tasks whose in-flight run main has moved past, to the tip it moved to.
_superseded: Dict[str, str] = {}
#: The check process each task's run is executing now, so a superseded run's tree can be ended.
_processes: Dict[str, subprocess.Popen] = {}
#: The main tip each project was last seen at, by the watcher or a refresh.
_seen_tips: Dict[str, str] = {}
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


async def request_run(
    project_id: str,
    task_id: str,
    *,
    force: bool = False,
    targets: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """Start a run for *task_id* unless one is executing or the latest result is current.

    Returns the id of the run that is or will be current, or `None` where no check applies or one is
    already executing. *force* (the operator's re-run) starts one even over a current result.

    *targets* are the commits approval would merge, as the caller resolved them. The approval gate
    passes its own (F680): it runs inside the transaction in which the reviewer's verdict has just
    accepted the task's evidence, and this function reads from a session of its own, which cannot
    see that uncommitted acceptance -- resolved here, the targets came out empty, no run started,
    and the gate's refusal rolled the acceptance back, so every retry repeated it. `None` resolves
    them from committed state, which is right for every caller outside a transaction.
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
            if targets is None:
                targets = [
                    t.commit_sha for t in await task_integration.merge_targets(session, task, root)
                ]
                if not targets and task.status in ("completed", "under_review"):
                    # Where evidence governs, `merge_targets` names accepted evidence only, and a
                    # task waiting for its reviewer has none yet: the check ran first at the
                    # approval gate, after the verdict (F773). Check the commit the review is given.
                    reviewed = await task_integration.review_target(session, task, root)
                    targets = [reviewed.commit_sha] if reviewed.resolved else []
            targets = await asyncio.to_thread(unmerged, root, tip, list(targets))
            if not targets:
                return None
            latest = await latest_run(session, task_id)
            if (
                not force
                and latest is not None
                # `error` is the Hub failing to produce a result, not a verdict: retried (F516).
                and latest.state in ("passed", "failed")
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
            traces.within_work(
                "check_run",
                project_id,
                _execute(run_id, task_id, root, tip, targets, checks),
                **{"aw.task.id": task_id, "aw.check_run.id": run_id},
            )
        )
        _inflight[task_id] = job
        _inflight_tips[task_id] = (project_id, tip)
        job.add_done_callback(lambda done: _ended(project_id, task_id, done))
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

    async def superseded() -> bool:
        """Whether main moved past this run; if so it ends recorded `superseded`, not failed."""
        new_tip = _superseded.get(task_id)
        if new_tip is None:
            return False
        await _finish(
            run_id,
            state=SUPERSEDED,
            results=list(results),
            error=(
                f"the main branch moved from {main_sha[:12]} to {new_tip[:12]} before this run "
                "finished; a run on the new tip replaces it"
            ),
        )
        return True

    try:
        async with _semaphore():
            if await superseded():
                return
            merged, why = await asyncio.to_thread(build_merged_commit, root, main_sha, targets)
            if merged is None:
                await _finish(run_id, state="error", error=why)
                return
            changed = await asyncio.to_thread(changed_paths, root, main_sha, merged)
            path: Optional[Path] = None
            baseline = _MainBaseline(root, task_id, main_sha)
            try:
                for check in checks:
                    if await superseded():
                        return
                    result = skipped(check, changed)
                    if result is None:
                        if path is None:
                            path = await asyncio.to_thread(_checkout, root, task_id, merged)
                        result = await asyncio.to_thread(run_one, check, path, task_id)
                        if failed(result) and task_id not in _superseded:
                            await baseline.record(check, result)
                        if await superseded():
                            return  # its tree was ended for the move: not a result
                    results.append(result)
                    await _finish(run_id, merged_sha=merged, results=list(results))
                    if failed(result) and not preexisting(result):
                        # The task's own failure already decides the run; the checks after it
                        # would only make its author wait for them (operator, 2026-10-24). A
                        # failure main shares does not stop it: it is not the task's, and what
                        # follows may still be.
                        break
            finally:
                if path is not None:
                    await asyncio.to_thread(_remove_checkout, root, path)
                await baseline.close()
            if await superseded():
                return
            state = "failed" if any(failed(r) for r in results) else "passed"
            await _finish(run_id, state=state, merged_sha=merged, results=list(results))
    except Exception as exc:  # noqa: BLE001 -- a run must end recorded, never `running` forever
        logger.warning("check run %s failed to complete", run_id, exc_info=True)
        await _finish(
            run_id, state="error", results=list(results), error=f"{type(exc).__name__}: {exc}"
        )


def schedule(project_id: str, task_id: str, targets: Optional[Sequence[str]] = None) -> None:
    """Fire-and-forget `request_run`. Never raises, so it may sit anywhere a wake may.

    *targets*: see `request_run`; a caller inside an open transaction passes the ones it resolved.
    """
    try:
        job = asyncio.get_running_loop().create_task(
            request_run(project_id, task_id, targets=targets)
        )
    except Exception:  # noqa: BLE001
        logger.warning("could not schedule checks for task %s", task_id, exc_info=True)
        return
    _pending.add(job)
    job.add_done_callback(_pending.discard)


# --- main moving -----------------------------------------------------------------------------------


def _ended(project_id: str, task_id: str, job: "asyncio.Task[None]") -> None:
    """A run's job is done: forget it, and replace it if main moved past it."""
    if _inflight.get(task_id) is job:
        _inflight.pop(task_id, None)
        _inflight_tips.pop(task_id, None)
    if _superseded.pop(task_id, None) is not None:
        _background(_replace(project_id, task_id), f"replace the checks of {task_id}")


def _background(coro: Any, what: str) -> None:
    try:
        job = asyncio.get_running_loop().create_task(coro)
    except Exception:  # noqa: BLE001
        coro.close()
        logger.warning("could not %s", what, exc_info=True)
        return
    _pending.add(job)
    job.add_done_callback(_pending.discard)


async def _replace(project_id: str, task_id: str) -> None:
    """The run main moved past is ended; start its replacement if the task still waits for review."""
    try:
        async with async_session_factory() as session:
            task = await session.get(Task, task_id)
            if task is None or task.status not in AWAITING_REVIEW:
                return
        await request_run(project_id, task_id)
    except Exception:  # noqa: BLE001 -- approval still starts one when asked
        logger.warning("could not replace the checks of %s", task_id, exc_info=True)


async def supersede(task_id: str, new_tip: str) -> bool:
    """End *task_id*'s in-flight run if it was cut from a tip other than *new_tip*: its executing
    check's process tree is ended, the run records `superseded`, and `_ended` replaces it."""
    from .pty_runner import terminate_process_tree

    job = _inflight.get(task_id)
    cut = _inflight_tips.get(task_id)
    if job is None or job.done() or cut is None or cut[1] == new_tip:
        return False
    _superseded[task_id] = new_tip
    proc = _processes.get(task_id)
    if proc is not None and proc.poll() is None:
        await asyncio.to_thread(terminate_process_tree, proc.pid)
    return True


async def _awaiting_review_oldest_first(session: AsyncSession, project_id: str) -> List[str]:
    """The project's tasks waiting for review, in the order they last entered `completed`."""
    rows = (
        await session.execute(
            select(Task.id, Task.created_at).where(
                Task.project_id == project_id, Task.status.in_(AWAITING_REVIEW)
            )
        )
    ).all()
    if not rows:
        return []
    completed = dict(
        (
            await session.execute(
                select(TaskTransition.task_id, func.max(TaskTransition.sequence))
                .where(
                    TaskTransition.task_id.in_([row.id for row in rows]),
                    TaskTransition.to_status == "completed",
                )
                .group_by(TaskTransition.task_id)
            )
        ).all()
    )
    # A task with no recorded move to `completed` was created there; it sorts first, by creation.
    rows.sort(key=lambda row: (row.id in completed, completed.get(row.id, 0), row.created_at))
    return [row.id for row in rows]


async def _current_tip(session: AsyncSession, project: Project) -> Optional[str]:
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

    if not project.main_branch:
        return None
    try:
        root = (await resolve_project_workspace(session, project.id)).root
    except ProjectWorkspaceError:
        return None
    return await asyncio.to_thread(main_tip, root, project.main_branch)


async def refresh(project_id: str) -> None:
    """The project's main tip moved, or may have: bring every waiting result up to it.

    Every in-flight run cut from another tip is superseded (and replaced once it has ended), then a
    run is requested for each task waiting for review, oldest completed first, so the semaphore
    admits them in that order. `request_run` starts nothing for a result already current. Nothing
    here is a gate: approval still counts only a result for the tip it reads (`view`).
    """
    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        if project is None or not configured_checks(project):
            return
        tip = await _current_tip(session, project)
        if tip is None:
            return
        _seen_tips[project_id] = tip
        waiting = await _awaiting_review_oldest_first(session, project_id)
    for task_id, (owner, _) in list(_inflight_tips.items()):
        if owner == project_id:
            await supersede(task_id, tip)
    for task_id in waiting:
        if is_running(task_id):
            continue  # current, or superseded and replaced when it ends
        try:
            await request_run(project_id, task_id)
        except Exception:  # noqa: BLE001 -- one task's failure does not hold the others
            logger.warning("could not refresh the checks of %s", task_id, exc_info=True)


def schedule_refresh(project_id: str) -> None:
    """Fire-and-forget `refresh`, for a caller that has just moved main (the Hub's own merge, after
    its commit). Never raises, and nor does what it starts."""
    _background(_refresh_logged(project_id), f"refresh the checks of {project_id}")


async def _refresh_logged(project_id: str) -> None:
    try:
        await refresh(project_id)
    except Exception:  # noqa: BLE001 -- the watcher looks again; approval still starts a run
        logger.warning("could not refresh the checks of %s", project_id, exc_info=True)


async def watch_main_once() -> None:
    """Refresh every project with checks whose main tip is not the one last seen. A first look
    counts as a move: a Hub restarted after a merge has results to bring up to date."""
    async with async_session_factory() as session:
        projects = [
            project
            for project in (await session.execute(select(Project))).scalars()
            if configured_checks(project) and project.main_branch
        ]
        tips: Dict[str, Optional[str]] = {}
        for project in projects:
            try:
                tips[project.id] = await _current_tip(session, project)
            except Exception:  # noqa: BLE001 -- one project's git does not hold the others
                logger.warning("could not read the main tip of %s", project.id, exc_info=True)
    for project_id, tip in tips.items():
        if tip is not None and _seen_tips.get(project_id) != tip:
            await _refresh_logged(project_id)


async def watch_main_forever() -> None:
    """Notice a main tip moved outside the Hub (an operator's own merge or push), started in
    `main.lifespan` and cancelled with it."""
    while True:
        await asyncio.sleep(WATCH_SECONDS)
        try:
            await watch_main_once()
        except Exception:  # noqa: BLE001 -- the next look tries again
            logger.warning("could not look for a moved main branch", exc_info=True)


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
    while True:
        await asyncio.sleep(0)  # a finished run's callback may have scheduled its replacement
        if not (_pending or any(not job.done() for job in _inflight.values())):
            return
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
