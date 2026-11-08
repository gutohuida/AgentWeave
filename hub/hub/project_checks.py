"""A project's checks, run on the work a task's approval would merge (`approval-runs-the-projects-checks`).

The operator configures checks (`Project.checks`); nothing an agent sends is ever executed here. A run
builds the commit approval would produce -- main's tip with each merge target applied, through
`git merge-tree` and `commit-tree`, touching no checkout (design D1) -- checks it out in a scratch
worktree under `.agentweave/checks/<task_id>` (D2), runs each check there with the Hub's own
configuration removed from the environment (D8), stopping at the first failure that is the task's own
(a failure on the known-failing list does not stop it), and records a `TaskCheckRun` row (D3).

Runs are started in the background, never inside a request (D5): when a task is completed outside a
turn, when a turn bound to a completed task ends (its work is only committed then), and when the
project's main tip moves (`refresh`: the Hub's own merge, or `watch_main_forever` noticing one made
outside it) for a task with no pass of its work. A run main moves past runs to its end and its
result counts (`a-check-run-finishes-when-master-moves`): a pass counts on any tip, and a failure
that is not the task's own is asked again on the tip main moved to. Only a run whose task's work a
new completion replaced is ended, recorded `superseded`, and replaced. At most two run at once per
Hub, and one per task (D4). The approval gate
only *reads* what is recorded (`view`) and starts nothing: a task's run is the gate before review,
and a pass of its work counts on any main tip; landing is gated by the batch's one run on main with
the queued work merged (`landing_queue`, `approved-work-merges-in-batches`).

A check may name the paths it covers (`paths`): where no file the merged work changes matches one, it
is not executed and is recorded skipped, which passes.

A check's result is a function of the tree it ran on and the check itself, so a passing result is
reused for the same merged *tree* and the same check (`check_digest`), whatever commits produced it:
a prerequisite merged into the task branch, or a main move that leaves the merged tree as it was,
re-runs nothing. A different tree is always checked again. A failure is never reused.

A failure is confirmed before it is charged to the task: the failed tests (the ids the check's
JUnit XML report names, re-run through the check's own re-run command) or else the whole check are
run once more on the same tree. The Hub reads no test runner's console output for results and
rewrites no check's command (`checks-report-which-tests-failed-in-any-language`, FR-7). Only a reproduced
failure stands; one that passes the second time passes, and the result records the flake.

Only a result that judged the work counts against the task (`checks-know-their-phase-and-give-way-
to-the-user`, FR-7-FR-10). A run that did not is recorded `error` with what ended it (`ended_by`): a
merge conflict sends the task back to its builder as merge-needed, and no run starts on the same
work again; a Hub fault, or a check that ran out of time naming no failing test, is retried once on
the current tip, and a second in a row is a `checks_unjudged` stall on the operator's Needs-you list,
the task left where it is. A run the Hub's stop interrupted is requested again at the next start.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import flaky_tests, known_failing, readable_ids, traces
from .db.engine import async_session_factory
from .db.models import Project, Run, Task, TaskCheckRun, TaskTransition
from .subprocess_windows import no_console_kwargs
from .utils import short_id

logger = logging.getLogger(__name__)

CHECKS_DIR = Path(".agentweave") / "checks"
MAX_CONCURRENT_RUNS = 2
OUTPUT_TAIL_CHARS = 4000
# How long a check's output may stay open after its process exited before the run stops reading.
OUTPUT_DRAIN_SECONDS = 5
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
#: What ended an `error` run, which did not judge the work (`TaskCheckRun.ended_by`).
ENDED_BY_CONFLICT = "conflict"
ENDED_BY_FAULT = "fault"
ENDED_BY_TIMEOUT = "timeout"
#: The stall a task's second run in a row that did not judge its work raises (FR-9).
UNJUDGED_STALL = "checks_unjudged"
#: How often each project's main tip is read, to notice a move made outside the Hub. Two looks fit
#: inside the 120 seconds the refresh promises.
WATCH_SECONDS = 30.0
#: How many of a project's latest decided runs are searched for a passing result on the same tree.
REUSE_LOOKBACK = 200
#: The longest timeout a check marked fast may have (`checks-run-before-anyone-reviews`, FR-1): an
#: agent's completion waits for the fast checks, so none of them may run for longer than that wait.
FAST_CHECK_MAX_SECONDS = 120
#: How long an agent's completion waits for the fast checks (FR-4, D5). After it the completion is
#: recorded anyway and the checks go on in the same run; a failure found later returns the task
#: (`return_failed_work`). Warn, don't gate: a slow machine never holds a builder. Measured: a run
#: went from creation to a recorded ruff failure in 12.5 s, checkout included (chk-663862d5a7d6).
#: `mcp_server.COMPLETION_REQUEST_TIMEOUT_SECONDS` restates a timeout longer than this.
COMPLETION_BUDGET_SECONDS = 120.0

#: The Hub's own configuration, never handed to a project's command: its credentials, its database,
#: its address. A check runs the *project's* tests; the Hub's settings are not the project's.
_HUB_ONLY_PREFIXES = ("AW_", "HUB_", "AGENTWEAVE_")
_HUB_ONLY_NAMES = ("DATABASE_URL",)
_HUB_ONLY_VALUE_PREFIXES = ("aw_live_", "aw_run_")
_CREDENTIAL_RE = re.compile(r"aw_(?:live|run)_[A-Za-z0-9_\-]+")
_REDACTED = "[redacted]"


# --- configuration -------------------------------------------------------------------------------


#: When a check runs (`checks-know-their-phase-and-give-way-to-the-user`, FR-1): in a task's
#: pre-review run, in a landing batch's run, or in both. A check saved before `phase` was is both.
PHASE_REVIEW = "review"
PHASE_LANDING = "landing"
PHASE_BOTH = "both"
PHASES = (PHASE_REVIEW, PHASE_LANDING, PHASE_BOTH)


def configured_checks(
    project: Optional[Project], phase: Optional[str] = None
) -> List[Dict[str, Any]]:
    """The project's checks, normalised, in the order a run executes them; empty for none (null and
    `[]` mean the same).

    The fast checks first, then the rest, each group in the operator's order (FR-1, D1): an agent's
    completion waits for the fast ones, and they are the start of the task's one check run (D2). A
    check saved before `fast` existed is not fast.

    Each check not marked fast carries the project's `give_way` (FR-5): `run_one` starts it below
    normal priority.

    *phase* `review` keeps the checks a task's pre-review run executes, `landing` those a landing
    batch's run executes (FR-2, FR-3); `None` keeps every check. Every pre-review reader -- the run,
    the review's wait, the approval gate -- asks for `review`, so a landing-only check holds none
    of them."""
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
                    "fast": bool(check.get("fast")),
                    "phase": (check.get("phase") if check.get("phase") in PHASES else PHASE_BOTH),
                    # The report and re-run command (FR-1); `None` for a check without them.
                    "report_path": str(check.get("report_path") or "").strip() or None,
                    "rerun_command": str(check.get("rerun_command") or "").strip() or None,
                    # The command for a change (`a-check-can-run-only-the-tests-for-what-a-task-
                    # changed`, FR-1); `None` for a check without one.
                    "change_command": str(check.get("change_command") or "").strip() or None,
                    # Not part of `check_digest`: priority changes how fast a check runs, not
                    # what it finds, so a pass at either priority stays reusable.
                    # A fast check never gives way: the completion waits on it
                    # (`quick-checks-run-at-normal-priority`, FR-1).
                    "give_way": bool(getattr(project, "checks_give_way", False))
                    and not check.get("fast"),
                }
            )
    if phase is not None:
        excluded = PHASE_LANDING if phase == PHASE_REVIEW else PHASE_REVIEW
        checks = [check for check in checks if check["phase"] != excluded]
    return [check for check in checks if check["fast"]] + [
        check for check in checks if not check["fast"]
    ]


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
    commit, why, _ = merge_for_checks(root, main_sha, target_shas)
    return commit, why


def merge_for_checks(
    root: Path,
    main_sha: str,
    target_shas: Sequence[str],
    generated: Optional[Any] = None,
    regenerated: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Optional[str], str, bool]:
    """`build_merged_commit`, and whether a `None` was a merge conflict (FR-7) rather than git
    failing otherwise; *why* names the conflicting files.

    *generated*, the project's `generated_files.Settings`: a target that conflicts only in those
    paths is merged with them rebuilt, and the rebuild appended to *regenerated*; a rebuild that
    fails is a conflict whose *why* is its report."""
    from . import generated_files

    base = main_sha
    for target in target_shas:
        ancestor = _git(root, "merge-base", "--is-ancestor", target, base)
        if ancestor.returncode == 0:
            continue
        merged = _git(root, "merge-tree", "--write-tree", "--name-only", base, target)
        lines = merged.stdout.splitlines()
        if merged.returncode != 0 or not lines:
            # The conflicted paths follow the tree line, up to a blank line and git's messages.
            paths = []
            for line in lines[1:]:
                if not line.strip():
                    break
                paths.append(line.strip())
            if merged.returncode != 1 or not lines:
                # 1 is a conflict; anything else (a bad object, git itself failing) is a fault.
                return None, f"git merge-tree failed: {merged.stderr.strip()[:300]}", False
            if generated_files.rebuildable(generated, paths):
                outcome = generated_files.rebuild(
                    root,
                    base,
                    target,
                    generated,
                    f"agentweave checks: {target[:12]} onto {base[:12]}",
                    paths,
                )
                if isinstance(outcome, generated_files.Failure):
                    return (
                        None,
                        f"{target[:12]} conflicts onto {base[:12]} only in generated files, and "
                        f"rebuilding them failed: {outcome.report}",
                        True,
                    )
                if regenerated is not None:
                    regenerated.append(outcome.record(target=target))
                base = outcome.commit
                continue
            paths = paths[:10]
            return (
                None,
                (
                    f"{target[:12]} does not merge cleanly onto {base[:12]}"
                    + (f" ({', '.join(paths)})" if paths else "")
                    + ", so there is no merged work to check"
                ),
                True,
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
            return None, f"git commit-tree failed: {commit.stderr.strip()[:300]}", False
        base = commit.stdout.strip()
    return base, "", False


def _checkout_path(root: Path, task_id: str) -> Path:
    return root / CHECKS_DIR / task_id


def _remove_checkout(root: Path, path: Path) -> None:
    # F521: a run killed mid-`add` leaves the registration `locked`. One `--force` does not remove a
    # locked worktree, `prune` skips it, and every later `add` is refused; unlock it first.
    _git(root, "worktree", "unlock", str(path))
    # Links inside it first (F1038): the dependency links `_checkout` makes are junctions where
    # symlinks are refused, and git and `rmtree` both delete through a junction. A link that
    # cannot be removed leaves the checkout in place rather than emptying what it points at.
    from .worktrees import remove_links_in

    if remove_links_in(path):
        return
    _git(
        root,
        "worktree",
        "remove",
        "--force",
        "--force",
        str(path),
        timeout=CHECKOUT_TIMEOUT_SECONDS,
    )
    if path.exists() and not remove_links_in(path):
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
    # `-n auto` sizes pytest-xdist to every CPU, and up to MAX_CONCURRENT_RUNS checks run at once
    # beside the agents: on the operator's 20-CPU machine that was 40+ workers on 20 CPUs, the
    # suite ran 5-12 min, and the timing-sensitive tests flaked (2026-10-25). Each run gets a share
    # with room left for the agents. Only `-n auto` reads it; an explicit `-n 8` is the operator's,
    # and so is a value already in the Hub's environment.
    env.setdefault(XDIST_AUTO_WORKERS_VARIABLE, str(auto_workers()))
    return env, removed


#: pytest-xdist reads this for `-n auto` (xdist/plugin.py, `auto_detect_cpus`).
XDIST_AUTO_WORKERS_VARIABLE = "PYTEST_XDIST_AUTO_NUM_WORKERS"


def auto_workers(cpus: Optional[int] = None) -> int:
    """The xdist workers one check run gets for `-n auto`: the CPUs shared by the runs that may run
    at once and one share kept for everything else (the agents, the Hub)."""
    return max(1, (cpus or os.cpu_count() or 2) // (MAX_CONCURRENT_RUNS + 1))


def scrub(text: str, removed: Sequence[str]) -> str:
    for value in sorted({v for v in removed if len(v) >= 8}, key=len, reverse=True):
        text = text.replace(value, _REDACTED)
    return _CREDENTIAL_RE.sub(_REDACTED, text)


def run_one(check: Dict[str, Any], cwd: Path, owner: Optional[str] = None) -> Dict[str, Any]:
    """Run one check to completion or its timeout; end its whole process tree on a timeout.

    *owner*, a task id, registers the process so `_stop_run_on_older_work` can end its tree from
    the event loop.
    """
    with traces.command(check["command"], name=f"check {check['name']}") as span:
        result = _run_one(check, cwd, owner)
        traces.exited(
            span,
            result["exit_code"],
            why=f"ran past its {check['timeout_seconds']}s timeout" if result["timed_out"] else "",
        )
    return result


def _decode_output(raw: bytes) -> str:
    """A check's output as text: UTF-8 where it is, else the Windows ANSI code page the child wrote
    it in (cp1252), else UTF-8 with the bad bytes replaced -- never a silent U+FFFD for a
    character the check printed in its own code page."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace")


_PROCESS_LIST_TIMEOUT_SECONDS = 20
_PROCESS_LINE_CHARS = 300
#: Every process with its parent and creation time, one JSON object each. A Windows parent id may
#: name a dead process whose id was reused, so a child must also be created after its parent.
_WINDOWS_PROCESS_LIST = (
    "Get-CimInstance Win32_Process | ForEach-Object { [pscustomobject]@{ pid = $_.ProcessId; "
    "ppid = $_.ParentProcessId; created = $_.CreationDate.ToFileTimeUtc(); "
    "command = $_.CommandLine } } | ConvertTo-Json -Compress"
)


def live_process_tree(pid: int) -> str:
    """*pid* and every process descended from it, one `pid  command line` per line, or '' when
    they cannot be listed. Only for a check that timed out, so it may take a few seconds."""
    from .pty_runner import IS_WINDOWS

    try:
        if IS_WINDOWS:
            listed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_PROCESS_LIST],
                capture_output=True,
                timeout=_PROCESS_LIST_TIMEOUT_SECONDS,
                **no_console_kwargs(),
            )
            # Windows PowerShell 5.1 leaves a control character in a command line unescaped.
            rows = json.loads(_decode_output(listed.stdout) or "[]", strict=False)
            if isinstance(rows, dict):
                rows = [rows]
            processes = [
                (int(r["pid"]), int(r["ppid"]), int(r["created"] or 0), r["command"] or "")
                for r in rows
            ]
        else:
            # Piped, `ps` may cut a line at 80 columns: `-ww` asks for all of it.
            listed = subprocess.run(
                ["ps", "-ww", "-eo", "pid=,ppid=,args="],
                capture_output=True,
                timeout=_PROCESS_LIST_TIMEOUT_SECONDS,
            )
            processes = []
            for line in _decode_output(listed.stdout).splitlines():
                parts = line.split(None, 2)
                if len(parts) >= 2:
                    processes.append((int(parts[0]), int(parts[1]), 0, "".join(parts[2:])))
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        return ""
    by_pid = {p[0]: p for p in processes}
    if pid not in by_pid:
        return ""
    tree = [by_pid[pid]]
    for parent in tree:
        tree.extend(
            p for p in processes if p[1] == parent[0] and p[2] >= parent[2] and p not in tree
        )
    return "\n".join(f"{p[0]}  {p[3][:_PROCESS_LINE_CHARS]}" for p in tree)


def _read_all(stream: Any, chunks: List[bytes]) -> None:
    """Append everything *stream* yields to *chunks* until it closes."""
    with stream:
        for chunk in iter(lambda: stream.read1(65536), b""):
            chunks.append(chunk)


#: How far below normal a check gives way on POSIX (FR-5: a niceness of at least 10).
GIVE_WAY_NICENESS = 10


def _spawn_arguments(check: Dict[str, Any]) -> Dict[str, Any]:
    """How to start *check*'s command (the caller adds console suppression): through the shell,
    and, when it gives way to the user (`checks-know-their-phase-and-give-way-to-the-user`, FR-5),
    below normal priority.

    The priority is set on the process the Hub starts, before the command runs, so every process
    the command starts inherits it: on Windows a child of a below-normal process is created
    below-normal unless it asks otherwise (`CreateProcess`, "priority class"); on POSIX niceness
    is inherited across `fork` and `exec`. `nice` rather than a `preexec_fn`, which is unsafe in
    the worker threads checks run on; a machine without `nice` falls back to it."""
    from .pty_runner import IS_WINDOWS

    if not check.get("give_way"):
        return {"args": check["command"], "shell": True}
    if IS_WINDOWS:
        return {
            "args": check["command"],
            "shell": True,
            "creationflags": subprocess.BELOW_NORMAL_PRIORITY_CLASS,
        }
    nice = shutil.which("nice")
    if nice:
        return {
            "args": [nice, "-n", str(GIVE_WAY_NICENESS), "/bin/sh", "-c", check["command"]],
            "shell": False,
        }
    return {
        "args": check["command"],
        "shell": True,
        "preexec_fn": lambda: os.nice(GIVE_WAY_NICENESS),
    }


def _run_one(check: Dict[str, Any], cwd: Path, owner: Optional[str] = None) -> Dict[str, Any]:
    from .pty_runner import IS_WINDOWS, terminate_process_tree

    env, removed = check_environment()
    # A Python child writes a pipe in the console's ANSI code page on Windows: ask for UTF-8 so a
    # '…' in an assertion message arrives as itself (C2); `_decode_output` covers the rest.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.monotonic()
    if owner is not None and owner in _superseded:
        # The task's work changed while this run was still building its checkout: the stop found
        # no process to end, and the caller discards this result as superseded. Nothing starts.
        return {
            "name": check["name"],
            "exit_code": None,
            "timed_out": False,
            "duration_seconds": 0.0,
            "output_tail": "",
        }
    clear_report(check, cwd)
    spawn = _spawn_arguments(check)
    creationflags = spawn.pop("creationflags", 0) | no_console_kwargs().get("creationflags", 0)
    proc = subprocess.Popen(
        **spawn,
        creationflags=creationflags,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=not IS_WINDOWS,
    )
    if owner is not None:
        _processes[owner] = proc
        if owner in _superseded:
            # The stop sets `_superseded` before it reads `_processes`: one that landed between
            # the check above and this registration found no process, so end it here.
            terminate_process_tree(proc.pid)
    # The check ends when its process does, not when its output closes: a process it left behind
    # (or one that inherited the pipe) can hold the output open long after it exited, and waiting
    # for that end timed out a check that had already printed `1 passed` (2026-10-30).
    chunks: List[bytes] = []
    reader = threading.Thread(target=_read_all, args=(proc.stdout, chunks), daemon=True)
    reader.start()
    timed_out = False
    still_running = ""
    try:
        proc.wait(timeout=check["timeout_seconds"])
    except subprocess.TimeoutExpired:
        timed_out = True
        # Name what was still running before ending it: a timeout that printed `1 passed` and
        # then never exited (2026-10-30) could not be reproduced, so its next one says itself.
        still_running = live_process_tree(proc.pid)
        terminate_process_tree(proc.pid)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        if owner is not None and _processes.get(owner) is proc:
            _processes.pop(owner, None)
    reader.join(timeout=OUTPUT_DRAIN_SECONDS)
    output = b"".join(list(chunks))
    text = scrub(_decode_output(output), removed)
    if timed_out:
        text += f"\n[the check ran past its {check['timeout_seconds']}s timeout and was ended]"
        if still_running:
            text += "\n[still running when it was ended]\n" + scrub(still_running, removed)
    result = {
        "name": check["name"],
        "exit_code": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 1),
        "output_tail": text[-OUTPUT_TAIL_CHARS:],
    }
    # The report names the failing tests; the console is for people (FR-2, FR-7).
    _judge_by_report(check, cwd, result, timed_out)
    return result


# --- the check's report (`checks-report-which-tests-failed-in-any-language`) --------------------

#: Where a re-run command takes the ids of the tests to re-run (FR-1, FR-6).
TESTS_PLACEHOLDER = "{tests}"
#: Past this a re-run command with its ids substituted is not run: Windows' command interpreter
#: refuses a command line over 8,191 characters, so the check is re-run as a whole (FR-6).
MAX_RERUN_COMMAND_CHARS = 8000
#: A report larger than this is not read (it is unreadable): the check's own file, but a task's
#: work can write it.
MAX_REPORT_BYTES = 64 * 1024 * 1024
#: Why a failing check names no test (FR-4, FR-5), recorded in its result as `whole_check`.
NO_REPORT_CONFIGURED = "no report configured"
REPORT_MISSING = "report missing"
REPORT_UNREADABLE = "report unreadable"
REPORT_NAMES_NO_FAILURE = "report names no failing test"
#: A report that was there and parsed, as a result's `report`.
REPORT_READ = "read"


@dataclass
class TestReport:
    """What a JUnit XML report says: each testcase's id (`classname::name`, FR-2) and whether it
    failed (`True`), passed (`False`) or was skipped (`None`), and the file a testcase names where it
    names one. An id recorded twice (the same classname and name in two files) failed if either
    did."""

    __test__ = False  # not a pytest test class, whatever its name

    outcomes: Dict[str, Optional[bool]]
    files: Dict[str, str]
    #: What the report says about each failing testcase: its failure (or error) message and text.
    messages: Dict[str, str] = field(default_factory=dict)

    @property
    def failing(self) -> List[str]:
        return [test for test, failed_ in self.outcomes.items() if failed_]


def report_file(check: Dict[str, Any], cwd: Path) -> Optional[Path]:
    """The file *check*'s report is written to when it runs in *cwd*, or `None` for a check without
    one or whose path would leave *cwd* (the settings route refuses those; read defensively)."""
    relative = check.get("report_path")
    if not relative:
        return None
    base = Path(cwd).resolve()
    path = (base / str(relative)).resolve()
    if path == base or base not in path.parents:
        return None
    return path


def clear_report(check: Dict[str, Any], cwd: Path) -> None:
    """Remove whatever is at *check*'s report path before it runs (FR-4), so only a report the run
    itself writes is read: a re-run in the full run's directory would otherwise read the full
    run's report as its own."""
    path = report_file(check, cwd)
    if path is None:
        return
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        logger.warning("could not remove check %s's old report %s", check.get("name"), path)


def _relative_file(value: str, cwd: Path) -> str:
    """A testcase's `file` as a path relative to *cwd* where it lies inside it (Node writes it
    absolute), with forward slashes; else as written."""
    written = value.strip()
    candidate = Path(written)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(Path(cwd).resolve()).as_posix()
        except (OSError, ValueError):
            pass
    text = written.replace("\\", "/")
    return text[2:] if text.startswith("./") else text


def parse_report(text: str, cwd: Path) -> Optional[TestReport]:
    """The testcases of a JUnit XML report's *text*, or `None` where it is not one: empty, not
    XML, declaring a DTD or entities (never expanded: a task's work can write the file), or with a
    root other than `testsuites` or `testsuite`."""
    import xml.etree.ElementTree as ElementTree

    if not text.strip() or "<!DOCTYPE" in text or "<!ENTITY" in text:
        return None
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return None
    if root.tag not in ("testsuites", "testsuite"):
        return None
    outcomes: Dict[str, Optional[bool]] = {}
    files: Dict[str, str] = {}
    messages: Dict[str, str] = {}
    for case in root.iter("testcase"):
        test = f"{case.get('classname') or ''}::{case.get('name') or ''}"
        failed_ = case.find("failure") is not None or case.find("error") is not None
        skipped_ = not failed_ and case.find("skipped") is not None
        if failed_ or test not in outcomes:
            outcomes[test] = None if skipped_ else failed_
        elif outcomes[test] is None and not skipped_:
            outcomes[test] = False
        if case.get("file") and (failed_ or test not in files):
            files[test] = _relative_file(str(case.get("file")), cwd)
        element = case.find("failure")
        if element is None:
            element = case.find("error")
        if element is not None and test not in messages:
            said = [str(element.get("message") or "").strip(), (element.text or "").strip()]
            messages[test] = "\n".join(part for part in said if part)
    return TestReport(outcomes=outcomes, files=files, messages=messages)


def read_report(check: Dict[str, Any], cwd: Path) -> Tuple[Optional[TestReport], str]:
    """*check*'s report after it ran in *cwd*, and how it read: `read`, or why there is none to
    judge by (`no report configured`, `report missing`, `report unreadable`; FR-4)."""
    if not check.get("report_path"):
        return None, NO_REPORT_CONFIGURED
    path = report_file(check, cwd)
    if path is None or not path.is_file():
        return None, REPORT_MISSING
    try:
        if path.stat().st_size > MAX_REPORT_BYTES:
            return None, REPORT_UNREADABLE
        raw = path.read_bytes()
    except OSError:
        return None, REPORT_UNREADABLE
    report = parse_report(_decode_output(raw), cwd)
    return (report, REPORT_READ) if report is not None else (None, REPORT_UNREADABLE)


def _judge_by_report(
    check: Dict[str, Any], cwd: Path, result: Dict[str, Any], timed_out: bool
) -> None:
    """Record in *result* what *check*'s report names (FR-2, FR-5). The exit code has already
    decided pass or fail; the report only names which tests failed, and a failure it cannot name is
    the whole check's, with the reason (FR-4). A re-run of named tests (`rerun_tests`) also records
    which of them its report shows passing, so that a pass proves they ran."""
    report, how = read_report(check, cwd)
    result["report"] = how
    asked = list(check.get("rerun_tests") or [])
    if asked and report is not None:
        result["passed_tests"] = [test for test in asked if report.outcomes.get(test) is False]
        # Which of them ran at all: one in no file of the tree runs nothing, and says nothing.
        result["ran_tests"] = [test for test in asked if test in report.outcomes]
    watched = list(check.get("watch_tests") or [])
    if watched and report is not None:
        # The listed tests this run ran and passed: a run that did not run one says nothing of it
        # (`failures-already-known-are-on-a-list-not-re-argued`, FR-4; `known_failing.watching`).
        result["watched_passed"] = [test for test in watched if report.outcomes.get(test) is False]
    if timed_out:
        if report is not None and report.failing:
            result["named_failures"] = report.failing
        return
    if not failed(result):
        return  # a report naming failures does not fail a check that exited 0 (FR-5)
    if report is None or not report.failing:
        result["whole_check"] = how if report is None else REPORT_NAMES_NO_FAILURE
        return
    failing = report.failing
    result["failed_tests"] = failing
    # Always set for a report's ids, empty when the report gives no file (pytest's xunit2): an id
    # whose file is unknown counts as touched (`touched_tests`), never as a file guessed from it.
    result["test_files"] = {test: report.files[test] for test in failing if test in report.files}
    excerpt = failure_excerpt(report, failing)
    if excerpt:
        result["failure_excerpt"] = excerpt


def _shell_argument(test: str) -> Optional[str]:
    """*test* quoted as one argument for the shell a check runs in, or `None` where it cannot be
    passed through that shell as itself."""
    from .pty_runner import IS_WINDOWS

    if not test or any(char in test for char in "\r\n\x00"):
        return None
    if IS_WINDOWS:
        # cmd.exe expands `%` even inside quotes, and a quote or a trailing backslash would end
        # the argument early when the program splits its command line.
        if '"' in test or "%" in test or test.endswith("\\"):
            return None
        return f'"{test}"'
    return shlex.quote(test)


def rerun_command(check: Dict[str, Any], tests: Sequence[str]) -> Optional[str]:
    """*check*'s re-run command with `{tests}` replaced by *tests*, each one argument (FR-6), or
    `None` where it has none, an id cannot be passed through the shell, or the command would be
    longer than `MAX_RERUN_COMMAND_CHARS`: the check is then re-run as a whole."""
    template = str(check.get("rerun_command") or "")
    if TESTS_PLACEHOLDER not in template or not tests:
        return None
    quoted = [_shell_argument(test) for test in tests]
    if any(argument is None for argument in quoted):
        return None
    command = template.replace(TESTS_PLACEHOLDER, " ".join(str(q) for q in quoted))
    return command if len(command) <= MAX_RERUN_COMMAND_CHARS else None


def rerun_check(check: Dict[str, Any], tests: Sequence[str]) -> Optional[Dict[str, Any]]:
    """The check that re-runs exactly *tests* -- confirming a failure, asking main, narrowing a
    landing batch -- or `None` to re-run *check* as a whole.

    Only through the check's re-run command (FR-6), its report read by the same rules; a check
    without one is re-run as a whole. The check's own command is never rewritten (FR-7)."""
    command = rerun_command(check, tests)
    if command is None:
        return None
    return {**check, "command": command, "rerun_tests": list(tests)}


# --- the command for a change (`a-check-can-run-only-the-tests-for-what-a-task-changed`) ---------

#: Where a check's command for a change takes the path of the file listing the changed files (FR-1).
CHANGED_FILES_PLACEHOLDER = "{changed_files}"
#: Why a check with a command for a change ran its full command before review (FR-2).
CHANGE_UNKNOWN = "the files the task changed could not be read, so the check ran in full"


def for_change(
    checks: Sequence[Dict[str, Any]], changed: Optional[Sequence[str]]
) -> List[Dict[str, Any]]:
    """*checks* as a task's pre-review run executes them: each one with a command for a change
    carries `changed_files`, the files the task changed, each once (FR-1) -- or, where those are not
    known, `full_because` and its own command (FR-2). Its `command` is left as it is: only
    `sized_command` puts the command for a change in place, so a confirmation, which reads
    `command` and the re-run command, runs as a check without one (FR-3)."""
    sized = []
    for check in checks:
        if check.get("change_command"):
            if changed is None:
                check = {**check, "full_because": CHANGE_UNKNOWN}
            else:
                check = {**check, "changed_files": list(dict.fromkeys(changed))}
        sized.append(check)
    return sized


def changed_files_list(root: Path, task_id: str) -> Path:
    """The file a task's run lists its changed files in: beside the run's checkout, not inside
    it, so the tree the check reads is exactly the merged work."""
    return root / CHECKS_DIR / f"{task_id}.changed-files.txt"


def sized_command(check: Dict[str, Any], listing: Path) -> Optional[Dict[str, Any]]:
    """*check* running its command for a change on the files *listing* names, written here; `None`
    for a check not sized to the change, or a list path the shell cannot be handed (it runs in
    full)."""
    if check.get("changed_files") is None:
        return None
    argument = _shell_argument(str(listing))
    if argument is None:
        return None
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text(
        "".join(f"{path}\n" for path in check["changed_files"]), encoding="utf-8", newline="\n"
    )
    command = str(check["change_command"]).replace(CHANGED_FILES_PLACEHOLDER, argument)
    return {**check, "command": command}


def sizing(check: Dict[str, Any], ran: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """What a pre-review result records about its size (FR-2, FR-4): sized to the change and with
    how many files, where *ran* (`sized_command`'s check) ran; in full, and why, where a check with a
    command for a change did not; nothing for a check without one."""
    if not check.get("change_command"):
        return {}
    if ran is not None:
        return {"sized_to_change": True, "changed_file_count": len(check["changed_files"])}
    return {
        "sized_to_change": False,
        "full_because": check.get("full_because")
        or "the list of changed files could not be passed to the command, so the check ran in full",
    }


def failure_excerpt(report: TestReport, failing: Sequence[str]) -> str:
    """What the report says about each of the *failing* tests -- its id, then its failure message and
    text -- up to `OUTPUT_TAIL_CHARS`, or `""` where it says nothing.

    The stored tail of a long suite holds only its end, so a failure's traceback was lost: two gate
    runs on 2026-10-25 kept the failing id and nothing that said why. The report keeps it for every
    runner, so no console output is searched for it (FR-7)."""
    parts = [f"{test}\n{report.messages[test]}" for test in failing if report.messages.get(test)]
    return "\n\n".join(parts)[:OUTPUT_TAIL_CHARS]


# --- reuse and confirmation ----------------------------------------------------------------------


def check_digest(check: Dict[str, Any]) -> str:
    """What makes two runs of a check the same check: everything the operator configured that can
    change its result. Not `fast`, which changes when it runs (D1), so marking a check fast keeps
    its passes reusable."""
    identity = {key: check.get(key) for key in ("name", "command", "timeout_seconds", "paths")}
    # Only where set, so a check without a report keeps the digest (and the passes) it had.
    identity.update({key: check[key] for key in ("report_path", "rerun_command") if check.get(key)})
    if check.get("changed_files") is not None:
        # A run of the command for a change is another check: a pass of it is reused only for the
        # same list of changed files (FR-6), and never as a pass of the full command -- which is
        # what a landing batch looks it up as. The full command's digest leaves the command for a
        # change out, so its passes stay reusable as before.
        identity.update(
            change_command=check["change_command"], changed_files=list(check["changed_files"])
        )
    payload = json.dumps(identity, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def tree_of(root: Path, commit: str) -> Optional[str]:
    result = _git(root, "rev-parse", "--verify", f"{commit}^{{tree}}")
    return result.stdout.strip() if result.returncode == 0 else None


async def passes_on_tree(session: AsyncSession, project_id: str, tree: str) -> Dict[str, Any]:
    """Every check digest with a passing, executed result on *tree*, to the result to reuse.

    Only rows that finished with a verdict are read (a `failed` run's checks before its failure
    ran to completion and passed). A skipped result is not a pass of the tree: whether a check is
    skipped depends on what changed against main, which is decided again for each run."""
    rows = (
        (
            await session.execute(
                select(TaskCheckRun)
                .where(
                    TaskCheckRun.project_id == project_id,
                    TaskCheckRun.state.in_(("passed", "failed")),
                )
                .order_by(TaskCheckRun.started_at.desc(), TaskCheckRun.id.desc())
                .limit(REUSE_LOOKBACK)
            )
        )
        .scalars()
        .all()
    )
    found: Dict[str, Any] = {}
    for run in rows:
        for result in run.results or []:
            digest = result.get("check_digest") if isinstance(result, dict) else None
            if not digest or digest in found or result.get("tree") != tree:
                continue
            if result.get("skipped") or failed(result):
                continue
            found[digest] = {**result, "reused_from": result.get("reused_from") or run.id}
    return found


#: How many of a check's latest passing results its usual duration is read from (FR-11).
USUAL_DURATION_PASSES = 20
#: How many of a project's latest runs are searched for them.
USUAL_DURATION_LOOKBACK = 500


def _clean_pass_duration(result: Any) -> Optional[float]:
    """How long *result* took, where it is a pass that ran here, once: not skipped (nothing ran),
    not reused (its time is the run it came from), not flaky (its time is two attempts)."""
    if not isinstance(result, dict) or not result.get("name"):
        return None
    if result.get("skipped") or result.get("reused_from") or result.get("flaky"):
        return None
    if failed(result):
        return None
    duration = result.get("duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0:
        return None
    return float(duration)


async def usual_durations(
    session: AsyncSession, project_id: str, names: Sequence[str]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """How long each check named in *names* usually takes in this project
    (`checks-know-their-phase-and-give-way-to-the-user`, FR-11): the median and the longest of its
    last `USUAL_DURATION_PASSES` passing results, newest first, and how many that was; `None` for a
    check with no passing result yet."""
    wanted: Dict[str, List[float]] = {name: [] for name in names}
    rows = (
        (
            await session.execute(
                select(TaskCheckRun)
                .where(TaskCheckRun.project_id == project_id, TaskCheckRun.state.in_(DECIDED))
                .order_by(TaskCheckRun.started_at.desc(), TaskCheckRun.id.desc())
                .limit(USUAL_DURATION_LOOKBACK)
            )
        )
        .scalars()
        .all()
    )
    for run in rows:
        for result in run.results or []:
            duration = _clean_pass_duration(result)
            if duration is None:
                continue
            durations = wanted.get(str(result["name"]))
            if durations is not None and len(durations) < USUAL_DURATION_PASSES:
                durations.append(duration)
        if all(len(d) >= USUAL_DURATION_PASSES for d in wanted.values()):
            break
    answer: Dict[str, Optional[Dict[str, Any]]] = {}
    for name, durations in wanted.items():
        answer[name] = (
            {
                "median_seconds": round(statistics.median(durations), 1),
                "longest_seconds": round(max(durations), 1),
                "passes": len(durations),
            }
            if durations
            else None
        )
    return answer


def planned_results(
    checks: Sequence[Dict[str, Any]],
    changed: Optional[List[str]],
    tree: Optional[str],
    passes: Dict[str, Any],
) -> List[Optional[Dict[str, Any]]]:
    """Per check, the result it already has without running -- skipped by its paths, or a pass on
    the same tree reused -- or `None` where it must run."""
    planned: List[Optional[Dict[str, Any]]] = []
    for check in checks:
        result = skipped(check, changed)
        if result is None and tree is not None:
            reused = passes.get(check_digest(check))
            result = dict(reused) if reused is not None else None
        if result is not None:
            result.update(tree=tree, check_digest=check_digest(check))
        planned.append(result)
    return planned


async def covering_results(
    session: AsyncSession,
    project_id: str,
    root: Path,
    main_sha: str,
    target_shas: Sequence[str],
    checks: Sequence[Dict[str, Any]],
) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """`(merged commit, results)` where every check already passes on the tree approval would merge
    now (skipped, or a reused pass of that exact tree), else `None`. Builds the merged commit with
    plumbing only, as a run does; never raises."""
    prepared = await _prepare(session, project_id, root, main_sha, list(target_shas), list(checks))
    if prepared is None or prepared[1] is None or any(r is None for r in prepared[3]):
        return None
    return prepared[0], [result for result in prepared[3] if result is not None]


def unjudged_timeout(result: Dict[str, Any]) -> bool:
    """A check that ran out of time without naming a failing test: it says nothing about the work,
    so it is not the task's failure (FR-10). One that named a failure before its time ran out still
    is, as before."""
    return bool(result.get("timed_out")) and not result.get("named_failures")


def proves_the_tests_pass(result: Dict[str, Any], node_ids: Sequence[str]) -> bool:
    """Whether a re-run of named tests passed and really ran them: exit 0 and its report shows
    every id passing (FR-6). An id that selects nothing, or a re-run with no report, is no proof."""
    passed = set(result.get("passed_tests") or [])
    return not failed(result) and bool(node_ids) and all(test in passed for test in node_ids)


def reproduces_a_test_failure(result: Dict[str, Any]) -> bool:
    """Whether a re-run of named tests failed *a test*: it failed and its report names a failing
    test. A failure it names no test for (a usage error, nothing collected, no report) proves
    nothing (FR-5, FR-6)."""
    return failed(result) and not result.get("timed_out") and bool(result.get("failed_tests"))


def _path_key(path: str) -> str:
    """A repository path as compared with the paths git reports: forward slashes."""
    return path.strip().replace("\\", "/")


def touched_tests(
    node_ids: Sequence[str],
    changed: Optional[Sequence[str]],
    files: Optional[Dict[str, str]] = None,
) -> List[str]:
    """The test ids whose file is among *changed*, the paths the task's merged work changes against
    the run's main commit (FR-4): a test the task touched is the task's to make pass. Unknown changes
    count every id as touched -- an override is never automatic on a guess. An id takes its file
    from the report (*files*, `checks-report-which-tests-failed-in-any-language` FR-2); one whose
    report gives no file is unknown, so touched: an id is never read as a path."""
    if changed is None:
        return list(node_ids)
    paths = {_path_key(path) for path in changed}
    if not paths:
        return []  # the work changes no file: no failing test can be one it touched
    files = files or {}
    return [node for node in node_ids if node not in files or _path_key(files[node]) in paths]


def _still_failing(again: Dict[str, Any], node_ids: Sequence[str]) -> List[str]:
    """Which of *node_ids* a re-run that reproduced a failure failed again: the ones its report
    names, where it names failures among them; else all of them (not known which)."""
    named = set(again.get("failed_tests") or [])
    if not named or not named <= set(node_ids):
        return list(node_ids)
    return [node for node in node_ids if node in named]


def confirm_failure(
    check: Dict[str, Any],
    cwd: Path,
    result: Dict[str, Any],
    owner: Optional[str],
    changed: Optional[Sequence[str]] = None,
) -> None:
    """Run a failed check's failure once more on the same tree, and record what happened in
    *result* (blocking; the caller runs it in a thread).

    The failed tests alone, through the check's re-run command, where its report named them and the
    command with them substituted is short enough (FR-6), else the whole check. Reproduced: *result*
    keeps its failure and gains `confirmed`, and `compared_tests` names the ids the known-failing
    list judges (`known_failing.judge`): those that failed again, and any in a file the task
    changed. A named id that passed the rerun is recorded in `flaky_tests`. Passed: *result* passes,
    and `flaky` keeps the first attempt -- a flake is recorded, never swallowed -- unless a flaky
    test is in a file the task's work changes (*changed*, FR-4): a task that adds or edits a flaky
    test introduced it, so its failure stands and is judged like a reproduced one.
    """
    node_ids = list(result.get("failed_tests") or [])
    narrowed = rerun_check(check, node_ids)
    how, again = "check", None
    if narrowed is not None:
        again = run_one(narrowed, cwd, owner)
        if proves_the_tests_pass(again, node_ids) or reproduces_a_test_failure(again):
            how = "tests"
        else:
            again = None  # the re-run proved nothing either way: run the check
    if again is None:
        again = run_one(check, cwd, owner)
    attempt = {
        "how": how,
        "tests": node_ids if how == "tests" else [],
        "exit_code": again["exit_code"],
        "timed_out": again["timed_out"],
        "duration_seconds": again["duration_seconds"],
    }
    for key in ("report", "whole_check"):
        if key in again:
            attempt[key] = again[key]  # what the re-run's own report said (FR-4)
    if how == "tests":
        touched = touched_tests(node_ids, changed, result.get("test_files"))
        result["touched_tests"] = touched
        stays = _still_failing(again, node_ids) if failed(again) else []
        flaked = [node for node in node_ids if node not in stays and node not in touched]
        compared = [node for node in node_ids if node in stays or node in touched]
        if compared:
            # The failure stands (FR-2): reproduced, or a flake of the task's own (FR-4).
            result["confirmed"] = attempt
            result["compared_tests"] = compared
            if flaked:
                result["flaky_tests"] = flaked
            return
    if failed(again):
        result["confirmed"] = attempt
        return
    first = {
        key: result.get(key)
        for key in ("exit_code", "timed_out", "duration_seconds", "output_tail")
    }
    first["failed_tests"] = node_ids
    result["flaky"] = {**attempt, "first": first}
    if how == "tests":
        result["flaky_tests"] = node_ids
    result["exit_code"], result["timed_out"] = 0, False
    result["duration_seconds"] = round(
        float(result.get("duration_seconds") or 0) + float(again["duration_seconds"] or 0), 1
    )
    note = (
        f"[flaky: the first run failed ({', '.join(node_ids) or 'exit ' + str(first['exit_code'])})"
        f" and the {'failed tests' if how == 'tests' else 'check'} passed when run again]\n"
    )
    result["output_tail"] = (note + str(again.get("output_tail") or ""))[-OUTPUT_TAIL_CHARS:]
    result.pop("failed_tests", None)
    logger.warning(
        "check %s failed once and passed when run again (%s): recorded as flaky",
        check["name"],
        ", ".join(node_ids) or how,
    )


def failed(result: Dict[str, Any]) -> bool:
    if result.get("skipped"):
        return False  # no changed file matched its paths, which passes
    return bool(result.get("timed_out")) or result.get("exit_code") != 0


def preexisting(result: Dict[str, Any]) -> bool:
    """A failure that is not the work's: every test it failed (after its rerun) is on the project's
    known-failing list, or, naming no test, its whole check is (`known_failing.judge`,
    `failures-already-known-are-on-a-list-not-re-argued` FR-7). A run recorded before this field
    existed reads as not pre-existing, i.e. as the work's."""
    return failed(result) and bool(result.get("preexisting"))


def own_failure(results: Optional[Sequence[Dict[str, Any]]]) -> bool:
    """Whether a run's results hold a failure that is the task's (not one on the list)."""
    return any(failed(result) and not preexisting(result) for result in results or [])


def send_back_class(results: Optional[Sequence[Dict[str, Any]]]) -> str:
    """Why the Hub sends work back for these check *results* (FR-9): `flaky` when every failure that
    is the task's passed its confirming re-run (it still counts as the task's: a flaky test in a
    file the task changes, FR-4), else `broken-check`."""
    from .task_transitions import SEND_BACK_BROKEN_CHECK, SEND_BACK_FLAKY

    own = [r for r in results or [] if failed(r) and not preexisting(r)]
    confirmed = [r.get("confirmed") for r in own]
    if own and all(
        isinstance(c, dict) and c.get("exit_code") == 0 and not c.get("timed_out")
        for c in confirmed
    ):
        return SEND_BACK_FLAKY
    return SEND_BACK_BROKEN_CHECK


#: The two kinds of entry on the known-failing list (`known_failing`).
FAILS_ON_MAIN = "fails on main"
FLAKY = "flaky"


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


async def _latest_two(session: AsyncSession, task_id: str) -> List[TaskCheckRun]:
    return list(
        (
            await session.execute(
                select(TaskCheckRun)
                .where(TaskCheckRun.task_id == task_id)
                .order_by(TaskCheckRun.started_at.desc(), TaskCheckRun.id.desc())
                .limit(2)
            )
        )
        .scalars()
        .all()
    )


def conflicted(run: Optional[TaskCheckRun]) -> bool:
    """A run that found the task's work does not merge onto main (FR-7)."""
    return run is not None and run.state == "error" and run.ended_by == ENDED_BY_CONFLICT


def unjudged(run: Optional[TaskCheckRun]) -> bool:
    """A run that ended without judging the work for a reason the Hub retries once (FR-9, FR-10):
    a Hub fault, or a check out of time naming no failing test. A conflict is the builder's, and an
    `error` recorded before `ended_by` existed reads as before."""
    return (
        run is not None
        and run.state == "error"
        and run.ended_by in (ENDED_BY_FAULT, ENDED_BY_TIMEOUT)
    )


async def _unjudged_stands(
    session: AsyncSession, latest: Optional[TaskCheckRun], targets: Sequence[str]
) -> bool:
    """Whether no new run may start on *targets* without the operator's re-run: the latest run on
    exactly this work conflicted (only a new commit changes that, FR-7), or it and the run before it
    both ended without a verdict (FR-9: one retry, then the operator)."""
    if latest is None or list(latest.target_shas or []) != list(targets):
        return False
    if conflicted(latest):
        return True
    if not unjudged(latest):
        return False
    runs = await _latest_two(session, latest.task_id)
    return len(runs) == 2 and unjudged(runs[1]) and list(runs[1].target_shas or []) == list(targets)


@dataclass
class CheckView:
    """What the gate may say about a task's checks right now."""

    #: `passed`, `failed`, `error`, `running`, `interrupted`, `stale` or `missing`.
    state: str
    run: Optional[TaskCheckRun] = None
    #: For a `passed` read from passes of the same tree rather than from *run*: those results.
    reused: Optional[List[Dict[str, Any]]] = None


def unmerged(root: Path, tip: str, target_shas: Sequence[str]) -> List[str]:
    """The targets not already in the main tip (F518): a commit of the task's own that already
    landed (a re-approval, an earlier landing of the same work) would re-check the main branch and
    blame its failures on this task. Unknown reachability is kept."""
    from .requirement_evidence import is_reachable_from

    return [sha for sha in target_shas if is_reachable_from(root, sha, tip) is not True]


async def check_targets(
    session: AsyncSession, task: Task, root: Path, *, awaiting_review: bool
) -> List[str]:
    """The commits a run for *task* checks: what approval would merge, or, for work waiting for
    its review, the commit the review is given and the newest commit on its own branch. One answer
    for every reader -- the run, the completion's fast checks, and the review's wait for them -- so
    they check the same work.

    Every commit here is the task's own (`a-task-s-checks-and-merges-use-its-own-work-...`, FR-1):
    `merge_targets` names only evidence the task recorded, so a sibling serving the same requirement
    can no longer stand in for this task's work, nor, once that stand-in has landed, leave nothing to
    check (FR-2). Work waiting for review that names a commit adds its branch tip, so a completion
    after a send-back is checked on the commit it completes even where its evidence still names an
    older one; a commit another target already contains is dropped, so the run checks each line of
    work once. Naming none, the answer stays empty: the completion checks its branch tip itself
    (`fast_checks_at_completion`), and a turn's end without evidence starts no run (F773)."""
    from . import task_integration, task_workspace

    targets = [t.commit_sha for t in await task_integration.merge_targets(session, task, root)]
    if awaiting_review:
        if not targets:
            # Where evidence governs, `merge_targets` names accepted evidence only, and a task
            # waiting for its reviewer has none yet: the check ran first at the approval gate,
            # after the verdict (F773). Check the commit the review is given.
            reviewed = await task_integration.review_target(session, task, root)
            if reviewed.resolved and reviewed.commit_sha:
                targets = [reviewed.commit_sha]
        if targets and task_workspace.takes_own_checkout(task):
            tip = await asyncio.to_thread(task_integration.task_branch_tip, root, task.id)
            if tip and tip not in targets:
                targets = await asyncio.to_thread(_newest_of, root, [*targets, tip])
    return targets


def _newest_of(root: Path, targets: List[str]) -> List[str]:
    """*targets* less any commit another of them contains, in order. Unknown reachability keeps."""
    from .requirement_evidence import is_reachable_from

    return [
        sha
        for sha in targets
        if not any(
            other != sha and is_reachable_from(root, sha, other) is True for other in targets
        )
    ]


async def view(
    session: AsyncSession, task: Task, root: Path, main_branch: str, target_shas: List[str]
) -> Optional[CheckView]:
    """The task's check result for the work approval would merge now, or `None` where no check
    applies (no checks configured, nothing to merge, no main tip). Reads only; starts nothing."""
    project = await session.get(Project, task.project_id)
    if not configured_checks(project, PHASE_REVIEW) or not target_shas:
        return None
    tip = await asyncio.to_thread(main_tip, root, main_branch)
    if tip is None:
        return None
    target_shas = await asyncio.to_thread(unmerged, root, tip, target_shas)
    if not target_shas:
        return None
    run = await latest_run(session, task.id)
    if run is None:
        state = "missing"
    elif run.state == "running":
        # Not short-cut: a run that could reuse a pass records it at once (`request_run`), so one
        # still running is checking work no pass covered when it started, or is a forced re-run.
        return CheckView(run.state, run)
    elif run.state == "interrupted":
        state = run.state
    elif run.state == "passed" and list(run.target_shas or []) == list(target_shas):
        # A pass of this work counts whatever main tip it ran on (`approved-work-merges-in-
        # batches`, FR-9): the batch's run on the merged result is the landing gate, and this one
        # is the gate before review.
        return CheckView(run.state, run)
    elif (
        run.state == SUPERSEDED
        or run.main_sha != tip
        or list(run.target_shas or []) != list(target_shas)
    ):
        state = "stale"
    else:
        return CheckView(run.state, run)  # a verdict for exactly this work: it stands, as recorded
    # No verdict for these commits, but the tree they merge to may already have passed every check
    # (a prerequisite merged into the branch, an unrelated main move): identical tree, identical
    # inputs, so that pass is this work's. Any other tree is checked again.
    covered = await covering_results(
        session, task.project_id, root, tip, target_shas, configured_checks(project, PHASE_REVIEW)
    )
    if covered is not None:
        return CheckView("passed", run, reused=covered[1])
    return CheckView(state, run)


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
        if fields.get("state") in DECIDED:
            await _announce_finished(session, run)
        project_id, task_id = run.project_id, run.task_id
    if fields.get("state") in ("passed", "failed"):
        await _resolve_unjudged(project_id, task_id)
    if fields.get("state") in DECIDED:
        await _after_decided(run_id)


async def _after_decided(run_id: str) -> None:
    """A run has decided: a completed task its own failure fails goes back to its builder (D7);
    any other verdict asks for its flow's firing, which offers the review it was waiting for (D6,
    FR-8) within `flow_advance`'s debounce rather than at the next tick. Never raises.

    First, the run is read into the known-failing list: a flake it found is listed, with its owner
    fix task filed now, while the flow's agents are idle (`failures-already-known-are-on-a-list-not-
    re-argued`, FR-2, FR-5); approval's own transaction stays free of task creation."""
    from . import flow_advance

    await known_failing.record_run(run_id)
    try:
        if await return_failed_work(run_id):
            return  # the return asked for the flow's firing itself (a hand-off move)
        async with async_session_factory() as session:
            run = await session.get(TaskCheckRun, run_id)
            task = await session.get(Task, run.task_id) if run is not None else None
            loop_id = task.loop_id if task is not None and task.status == "completed" else None
        if loop_id:
            flow_advance.request(loop_id)
    except Exception:  # noqa: BLE001 -- the firing's tick and the stall sweep still look
        logger.warning("could not act on the decided check run %s", run_id, exc_info=True)


async def _announce_finished(session: AsyncSession, run: TaskCheckRun) -> None:
    """Tell the operator's app a task's checks have decided, so a landing that waited can be pressed
    and the operator is called (`every-task-can-always-be-moved-on`, FR-12). Never fails the run."""
    from .sse import sse_manager

    try:
        task = await session.get(Task, run.task_id)
        await sse_manager.broadcast(
            run.project_id,
            "task_checks_finished",
            {
                "task_id": run.task_id,
                "task_title": task.title if task is not None else run.task_id,
                "state": run.state,
            },
        )
    except Exception:  # noqa: BLE001
        logger.debug("checks-finished broadcast failed", exc_info=True)


# --- the queue -----------------------------------------------------------------------------------

_inflight: Dict[str, "asyncio.Task[None]"] = {}
#: The project and main tip each in-flight run was cut from, by task.
_inflight_tips: Dict[str, Tuple[str, str]] = {}
#: Tasks whose in-flight run checks work a new completion replaced (always `_NEW_WORK`).
_superseded: Dict[str, str] = {}
#: The check process each task's run is executing now, so a superseded run's tree can be ended.
_processes: Dict[str, subprocess.Popen] = {}
#: The main tip each project was last seen at, by the watcher or a refresh.
_seen_tips: Dict[str, str] = {}
_starting: Set[str] = set()
_pending: Set["asyncio.Task[Any]"] = set()
_semaphores: Dict[int, asyncio.Semaphore] = {}
#: Set, by run id, once the run's fast checks have all decided (or the run ended): what an agent's
#: completion waits on (D2). Gone once set; a waiter that finds none reads the recorded run.
_fast_waiters: Dict[str, asyncio.Event] = {}
#: By run id, when a run began waiting for a check slot (the semaphore), while it waits (F1076).
_waiting_for_slot: Dict[str, datetime] = {}
#: Recorded in `_superseded` in place of a main tip: the task's work changed under the run (a new
#: completion), not main.
_NEW_WORK = "new-work"


def _semaphore() -> asyncio.Semaphore:
    loop_id = id(asyncio.get_running_loop())
    if loop_id not in _semaphores:
        _semaphores[loop_id] = asyncio.Semaphore(MAX_CONCURRENT_RUNS)
    return _semaphores[loop_id]


async def _took_slot(run_id: str) -> None:
    """Record on *run_id*'s row that it got a check slot now (`slot_at`), where it is still running.

    A row's `started_at` is when it was queued, and a run that waited 33 min behind another read as
    a 70-minute run, which the mender called hung (F1076). Held in memory, the wait was lost at a
    restart; on the row it survives one, and the build's tally splits waiting from running by it
    (`the-build-card-shows-where-check-time-went` FR-1). Called at every place a run takes
    `_semaphore()` -- a task's run here, a landing batch's in `landing_queue` -- and only once it
    holds the slot, so a run ended or superseded while waiting records none."""
    async with async_session_factory() as session:
        run = await session.get(TaskCheckRun, run_id)
        if run is None or run.state != "running":
            return
        run.slot_at = datetime.now(timezone.utc)
        await session.commit()


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
        from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

        async with async_session_factory() as session:
            project = await session.get(Project, project_id)
            task = await session.get(Task, task_id)
            checks = configured_checks(project, PHASE_REVIEW)
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
                targets = await check_targets(
                    session, task, root, awaiting_review=task.status in AWAITING_REVIEW
                )
            targets = await asyncio.to_thread(unmerged, root, tip, list(targets))
            if not targets:
                return None
            latest = await latest_run(session, task_id)
            if not force and await _unjudged_stands(session, latest, targets):
                # The same work conflicted with main, which only its builder can change (FR-7), or
                # ended twice without a verdict and is on the operator's Needs-you list (FR-9).
                if latest is not None and latest.ended_by == ENDED_BY_CONFLICT:
                    schedule_return(task_id)
                return latest.id if latest is not None else None
            if (
                not force
                and latest is not None
                # `error` is the Hub failing to produce a result, not a verdict: retried (F516).
                and latest.state in ("passed", "failed")
                and list(latest.target_shas or []) == targets
                # A pass of this work is current on any main tip (`approved-work-merges-in-
                # batches`, FR-9); a failure is asked again on a new tip, as before.
                and (latest.main_sha == tip or latest.state == "passed")
            ):
                return latest.id
            prepared = (
                None if force else await _prepare(session, project_id, root, tip, targets, checks)
            )
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
            if prepared is not None and all(result is not None for result in prepared[3]):
                # Every check already passes on this exact tree: recorded at once, nothing runs,
                # and nothing waits behind the runs that do (the semaphore is not taken).
                run.state = "passed"
                run.merged_sha = prepared[0]
                run.results = [result for result in prepared[3] if result is not None]
                run.ended_at = datetime.now(timezone.utc)
                session.add(run)
                await session.commit()
                await _resolve_unjudged(project_id, task_id)
                return run.id
            session.add(run)
            await session.commit()
            run_id = run.id
        _fast_waiters[run_id] = asyncio.Event()
        job = asyncio.get_running_loop().create_task(
            traces.within_work(
                "check_run",
                project_id,
                _execute(run_id, task_id, root, tip, targets, checks, prepared),
                **{"aw.task.id": task_id, "aw.check_run.id": run_id},
            )
        )
        _inflight[task_id] = job
        _inflight_tips[task_id] = (project_id, tip)
        job.add_done_callback(lambda done: _ended(project_id, task_id, done))
        return run_id
    finally:
        _starting.discard(task_id)


#: What `request_run` hands a run: the merged commit, its tree, the changed paths, and each check's
#: result where it already has one (skipped by its paths, or a pass of the same tree reused).
Prepared = Tuple[str, Optional[str], Optional[List[str]], List[Optional[Dict[str, Any]]]]


async def _prepare(
    session: AsyncSession,
    project_id: str,
    root: Path,
    tip: str,
    targets: List[str],
    checks: List[Dict[str, Any]],
) -> Optional[Prepared]:
    """The run's `Prepared`, or `None` where it cannot be had here (the run then builds the merged
    commit itself, and records why it could not). Never raises."""
    try:
        merged, _ = await asyncio.to_thread(build_merged_commit, root, tip, targets)
        if merged is None:
            return None
        tree = await asyncio.to_thread(tree_of, root, merged)
        changed = await asyncio.to_thread(changed_paths, root, tip, merged)
        passes = await passes_on_tree(session, project_id, tree) if tree else {}
        planned = planned_results(for_change(checks, changed), changed, tree, passes)
        return merged, tree, changed, planned
    except Exception:  # noqa: BLE001 -- not reusing is always safe: the checks run
        logger.debug("could not prepare a check run", exc_info=True)
        return None


async def _execute(
    run_id: str,
    task_id: str,
    root: Path,
    main_sha: str,
    targets: List[str],
    checks: List[Dict[str, Any]],
    prepared: Optional[Prepared] = None,
) -> None:
    """*prepared*: see `Prepared`; `None` builds it here, reusing nothing.

    **The fast checks first, before the semaphore** (`checks-run-before-anyone-reviews`, D2).
    `configured_checks` puts them at the front; they run as soon as the run starts, and an agent's
    completion is waiting on them (`_fast_waiters`). Only the rest queue for the semaphore, so a
    completion never waits behind two 8-16 minute suites. A fast result is a result of this run,
    so nothing executes twice. The checkout is made once and kept while the rest queue."""
    results: List[Dict[str, Any]] = []
    path: Optional[Path] = None
    #: The check that ran out of time naming no failing test, once one has.
    timed_out: Optional[Dict[str, Any]] = None

    async def superseded() -> bool:
        """Whether the task's work changed under this run (a new completion); if so it ends
        recorded `superseded`, not failed. Main moving never ends it."""
        if task_id not in _superseded:
            return False
        await _finish(
            run_id,
            state=SUPERSEDED,
            results=list(results),
            error=(
                "the task's work changed (it was completed again) before this run finished; a "
                "run on the new work replaces it"
            ),
        )
        return True

    async def run_group(
        group: Sequence[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]],
        merged: str,
        tree: Optional[str],
        changed: Optional[List[str]],
    ) -> Optional[str]:
        """Run *group* in order: `None` to go on, `"stop"` where the task's own failure decided
        the run, `"superseded"` where the task's work changed under it, `"timeout"` where a check
        ran out of time naming no failing test, which judged nothing (FR-10)."""
        nonlocal path, timed_out
        for check, already in group:
            if await superseded():
                return "superseded"
            result = already or skipped(check, changed)
            if already is not None and not already.get("skipped"):
                # A reused pass says what it is a pass of: its digest matched this sizing.
                result.update(sizing(check, check if "changed_files" in check else None))
            if result is None:
                if path is None:
                    path = await asyncio.to_thread(_checkout, root, task_id, merged)
                ran = await asyncio.to_thread(
                    sized_command, check, changed_files_list(root, task_id)
                )
                if ran is None and check.get("changed_files") is not None:
                    # Not sized after all: it runs, and is reused, as the full command.
                    check = {k: v for k, v in check.items() if k != "changed_files"}
                result = await asyncio.to_thread(run_one, ran or check, path, task_id)
                result.update(sizing(check, ran))
                if unjudged_timeout(result) and task_id not in _superseded:
                    # Not confirmed: running out of time again would say no more about the work.
                    # The run is retried instead (FR-9).
                    result.update(tree=tree, check_digest=check_digest(check))
                    results.append(result)
                    timed_out = check
                    return "timeout"
                if failed(result) and task_id not in _superseded:
                    # Confirmed on the same tree first: only a reproduced failure stands.
                    await asyncio.to_thread(confirm_failure, check, path, result, task_id, changed)
                    if result.get("flaky"):
                        # Raised to the operator, not only to the reviewer (`flaky_tests`).
                        await flaky_tests.record_flake(run_id, result)
                if failed(result) and task_id not in _superseded:
                    # Whose it is, the known-failing list decides: nothing runs on main for it but
                    # the twice rule's one test (`failures-already-known-are-on-a-list-not-re-
                    # argued`, FR-7, FR-13).
                    await known_failing.judge(
                        project_id=project_id,
                        task_id=task_id,
                        run_id=run_id,
                        root=root,
                        main_sha=main_sha,
                        check=check,
                        result=result,
                    )
                if await superseded():
                    return "superseded"  # its tree was ended for new work: not a result
                result.update(tree=tree, check_digest=check_digest(check))
            results.append(result)
            await _finish(run_id, merged_sha=merged, results=list(results))
            if failed(result) and not preexisting(result):
                # The task's own failure already decides the run; the checks after it would only
                # make its author wait for them (operator, 2026-10-24). A listed failure does not
                # stop it: it is not the task's, and what follows may still be.
                return "stop"
        return None

    project_id = await _project_of(run_id)
    # Each check is told the tests on the known-failing list, so its report says which it passed.
    checks = await known_failing.watching(project_id, checks)
    try:
        if await superseded():
            return
        if prepared is not None:
            merged, tree, changed, planned = prepared
        else:
            regenerated: List[Dict[str, Any]] = []
            built, why, conflict = await asyncio.to_thread(
                merge_for_checks,
                root,
                main_sha,
                targets,
                await _generated_of(project_id),
                regenerated,
            )
            if built is None:
                await _finish(
                    run_id,
                    state="error",
                    error=why,
                    ended_by=ENDED_BY_CONFLICT if conflict else ENDED_BY_FAULT,
                )
                return
            merged = built
            tree = await asyncio.to_thread(tree_of, root, merged)
            changed = await asyncio.to_thread(changed_paths, root, main_sha, merged)
            planned = [None] * len(checks)
            if regenerated:
                # The run's record says what was rebuilt (FR-8): a result of its own, which passed,
                # ahead of the checks that run on the rebuilt tree.
                results.append(_rebuild_result(regenerated))
                await _finish(run_id, merged_sha=merged, results=list(results))
                await _record_rebuilds(project_id, task_id, run_id, regenerated)
        # Each check with a command for a change is sized to it here, before review only (FR-3).
        checks = for_change(checks, changed)
        pairs = list(zip(checks, planned, strict=True))
        split = sum(1 for check in checks if check.get("fast"))
        try:
            outcome = await run_group(pairs[:split], merged, tree, changed)
            if outcome is None:
                # Every fast check passed: the completion waiting on them goes on now, and the rest
                # run after it. A fast failure instead ends the run first (the `finally` below
                # releases the waiter), so the refusal reads a decided run.
                _fast_decided(run_id)
            if outcome is None and pairs[split:]:
                _waiting_for_slot[run_id] = datetime.now(timezone.utc)
                async with _semaphore():
                    _waiting_for_slot.pop(run_id, None)
                    if await superseded():
                        # Its work changed while it waited: it ends here without running, so it
                        # took no slot (FR-1).
                        outcome = "superseded"
                    else:
                        await _took_slot(run_id)
                        outcome = await run_group(pairs[split:], merged, tree, changed)
            if outcome == "superseded":
                return
        finally:
            if path is not None:
                await asyncio.to_thread(_remove_checkout, root, path)
        if await superseded():
            return
        if outcome == "timeout" and timed_out is not None:
            await _finish(
                run_id,
                state="error",
                ended_by=ENDED_BY_TIMEOUT,
                merged_sha=merged,
                results=list(results),
                error=(
                    f"the check {timed_out['name']} ran past its {timed_out['timeout_seconds']}s "
                    "time limit and named no failing test, so it says nothing about the work"
                ),
            )
            return
        state = "failed" if any(failed(r) for r in results) else "passed"
        await _finish(run_id, state=state, merged_sha=merged, results=list(results))
    except Exception as exc:  # noqa: BLE001 -- a run must end recorded, never `running` forever
        logger.warning("check run %s failed to complete", run_id, exc_info=True)
        await _finish(
            run_id,
            state="error",
            ended_by=ENDED_BY_FAULT,
            results=list(results),
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        _fast_decided(run_id)
        _waiting_for_slot.pop(run_id, None)


#: The name of the result a check run records its generated-files rebuild under (FR-8).
REBUILD_RESULT = "generated files rebuilt"


def _rebuild_result(regenerated: List[Dict[str, Any]]) -> Dict[str, Any]:
    paths = sorted({path for entry in regenerated for path in entry.get("paths") or []})
    seconds = round(sum(float(entry.get("seconds") or 0.0) for entry in regenerated), 1)
    return {
        "name": REBUILD_RESULT,
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": seconds,
        "output_tail": "Rebuilt " + ", ".join(paths),
        "regenerated": {"paths": paths, "seconds": seconds, "rebuilds": regenerated},
    }


async def _generated_of(project_id: str) -> Any:
    from . import generated_files

    async with async_session_factory() as session:
        return generated_files.settings_of(await session.get(Project, project_id))


async def _record_rebuilds(
    project_id: str, task_id: str, run_id: str, regenerated: List[Dict[str, Any]]
) -> None:
    from . import generated_files

    async with async_session_factory() as session:
        for entry in regenerated:
            await generated_files.record_event(
                session,
                project_id,
                task_id,
                {**entry, "where": "check_run", "check_run_id": run_id},
            )
        await session.commit()


async def _project_of(run_id: str) -> str:
    async with async_session_factory() as session:
        run = await session.get(TaskCheckRun, run_id)
        return run.project_id if run is not None else ""


def _fast_decided(run_id: str) -> None:
    """Release whoever waits on *run_id*'s fast checks (idempotent)."""
    event = _fast_waiters.pop(run_id, None)
    if event is not None:
        event.set()


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
    """A run's job is done: forget it, and replace it if new work superseded it; otherwise ask a
    failure of it that is not the task's own again on the current tip (FR-4)."""
    cut = None
    if _inflight.get(task_id) is job:
        _inflight.pop(task_id, None)
        cut = _inflight_tips.pop(task_id, None)
    if _superseded.pop(task_id, None) is not None:
        _background(_replace(project_id, task_id), f"replace the checks of {task_id}")
    elif cut is not None:
        _background(_check_shared_failure_again(project_id, task_id), f"recheck {task_id}")


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
    """Start a run for *task_id* if it still waits for review: a superseded run's replacement, or
    a shared failure asked again on the current tip."""
    try:
        async with async_session_factory() as session:
            task = await session.get(Task, task_id)
            if task is None or task.status not in AWAITING_REVIEW:
                return
        await request_run(project_id, task_id)
    except Exception:  # noqa: BLE001 -- approval still starts one when asked
        logger.warning("could not replace the checks of %s", task_id, exc_info=True)


async def _check_shared_failure_again(project_id: str, task_id: str) -> None:
    """A run has ended. Where it failed with no failure of the task's own, main may have moved past
    the tip it was cut from while it ran, and the failure may be that old main's: a run is requested
    on the current tip (`a-check-run-finishes-when-master-moves`, FR-4). `request_run` starts
    nothing where the failure was found on the current tip. A failure of the task's own goes back to
    its author (`return_failed_work`) and is not run again (FR-5)."""
    try:
        async with async_session_factory() as session:
            latest = await latest_run(session, task_id)
            if unjudged(latest):
                # Did not judge the work (FR-9, FR-10): asked once more on the current tip, unless
                # this was that once, which goes to the operator instead.
                if await _unjudged_stands(session, latest, list(latest.target_shas or [])):
                    await _surface_unjudged(session, latest)
                    return
            elif latest is None or latest.state != "failed" or own_failure(latest.results):
                return
    except Exception:  # noqa: BLE001 -- the next main move or approval asks again
        logger.warning("could not read the ended check run of %s", task_id, exc_info=True)
        return
    await _replace(project_id, task_id)


async def _surface_unjudged(session: AsyncSession, run: TaskCheckRun) -> None:
    """Put *run*, the second in a row on its task's work to end without a verdict, on the
    operator's Needs-you list as a `checks_unjudged` stall: no run is requested, the task is not
    moved, and the mender is not woken -- nothing it can do re-runs a check (FR-9)."""
    from . import stalls

    task = await session.get(Task, run.task_id)
    label = (task.readable_id or task.id) if task is not None else run.task_id
    title = task.title if task is not None else run.task_id
    text = (
        f"The checks of {label} (“{title}”) ended twice in a row without judging its "
        f"work, so they are not run again on their own: {run.error} (check run {run.id}). "
        f"Re-run them from the task once the cause is fixed."
    )
    await stalls.record(
        session,
        run.project_id,
        cause=UNJUDGED_STALL,
        subject=run.task_id,
        text=text,
        task_id=run.task_id,
        loop_id=task.loop_id if task is not None else None,
    )


async def _resolve_unjudged(project_id: str, task_id: str) -> None:
    """A run on the task judged its work: its `checks_unjudged` stall, if open, is over. Never
    raises."""
    from . import stalls

    try:
        async with async_session_factory() as session:
            open_one = await stalls.open_stall(
                session, project_id, stalls.stall_key(UNJUDGED_STALL, task_id)
            )
            if open_one is not None:
                await stalls.end(session, open_one, "resolved", "a later check run judged the work")
    except Exception:  # noqa: BLE001
        logger.warning("could not end the unjudged-checks stall of %s", task_id, exc_info=True)


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

    A run is requested for each task waiting for review, oldest completed first, so the semaphore
    admits them in that order. A task whose run is in flight is left to finish it, whatever tip it
    was cut from (`a-check-run-finishes-when-master-moves`, FR-1, FR-3): a pass counts on any tip,
    and a failure that is not the task's own is asked again on the current tip once the run has
    ended (`_check_shared_failure_again`). `request_run` starts nothing for a result already current, and a pass
    of the task's work is current on any tip (`approved-work-merges-in-batches`, FR-9): only a task
    with no result, an interrupted or errored one, or a failure on an older tip is run again.
    """
    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        if project is None or not configured_checks(project, PHASE_REVIEW):
            return
        tip = await _current_tip(session, project)
        if tip is None:
            return
        _seen_tips[project_id] = tip
        waiting = await _awaiting_review_oldest_first(session, project_id)
        failing: Set[str] = set()
        for task_id in waiting:
            latest = await latest_run(session, task_id)
            if latest is not None and latest.state == "failed" and own_failure(latest.results):
                failing.add(task_id)
    for task_id in waiting:
        if is_running(task_id):
            continue  # it runs to its end; a shared failure is asked again then
        if task_id in failing:
            # Its latest run found a failure of its own, confirmed on its tree: the task goes back
            # to its author whatever main now holds, so checking it again on every main move is
            # spent work. Approval still re-checks a stale result (`view`) before it can pass.
            continue
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
    """Look once at every project with a main branch, checks or not: one `rev-parse` each, off the
    loop. A tip that moved is accounted for by the main watch (`main_watch.observe`: the Hub's own
    merges pass silently, any other move is raised), and a project with checks whose tip is not
    the one last seen has its results refreshed. A first look counts as a move for the refresh: a
    Hub restarted after a merge has results to bring up to date."""
    from . import landing_queue, main_watch
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

    async with async_session_factory() as session:
        projects = [
            project
            for project in (await session.execute(select(Project))).scalars()
            if project.main_branch
        ]
        looks: Dict[str, Tuple[Optional[str], Optional[Path], bool, Optional[str]]] = {}
        for project in projects:
            try:
                root = (await resolve_project_workspace(session, project.id)).root
            except ProjectWorkspaceError:
                continue
            try:
                tip = await asyncio.to_thread(main_tip, root, project.main_branch)
            except Exception:  # noqa: BLE001 -- one project's git does not hold the others
                logger.warning("could not read the main tip of %s", project.id, exc_info=True)
                continue
            looks[project.id] = (
                tip,
                root,
                bool(configured_checks(project, PHASE_REVIEW)),
                project.main_tip_seen,
            )
    for project_id, (tip, root, has_checks, seen) in looks.items():
        if tip is None or root is None:
            continue
        if seen != tip:
            try:
                await main_watch.observe(project_id, tip, root)
            except Exception:  # noqa: BLE001 -- the next look tries again
                logger.warning("could not account for main moving in %s", project_id, exc_info=True)
            # A batch held over failures main shared may pass on the new tip (F1126b).
            landing_queue.kick(project_id)
        if has_checks and _seen_tips.get(project_id) != tip:
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
        return bool(configured_checks(await session.get(Project, project_id), PHASE_REVIEW))
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


async def rerun_after_hub_stop() -> int:
    """At startup, after `interrupt_leftover_runs`: request a run now for every task still waiting
    for its pre-review result whose latest run the Hub's stop interrupted (FR-8). Nothing about its
    work was judged, so it does not wait for main to move or an approval. How many were requested;
    never raises."""
    try:
        async with async_session_factory() as session:
            projects = [
                project.id
                for project in (await session.execute(select(Project))).scalars()
                if project.main_branch and configured_checks(project, PHASE_REVIEW)
            ]
            interrupted: List[Tuple[str, str]] = []
            for project_id in projects:
                for task_id in await _awaiting_review_oldest_first(session, project_id):
                    latest = await latest_run(session, task_id)
                    if latest is not None and latest.state == "interrupted":
                        interrupted.append((project_id, task_id))
    except Exception:  # noqa: BLE001 -- the main watch's first look still refreshes them
        logger.warning("could not read the check runs the Hub's stop interrupted", exc_info=True)
        return 0
    requested = 0
    for project_id, task_id in interrupted:
        try:
            if await request_run(project_id, task_id) is not None:
                requested += 1
        except Exception:  # noqa: BLE001 -- one task's failure does not hold the others
            logger.warning("could not re-run the interrupted checks of %s", task_id, exc_info=True)
    return requested


def schedule_rerun_after_hub_stop() -> None:
    """Fire-and-forget `rerun_after_hub_stop`, for `main.lifespan`. Never raises."""
    _background(rerun_after_hub_stop(), "re-run the check runs the Hub's stop interrupted")


# --- checks before review (`checks-run-before-anyone-reviews`) -----------------------------------


@dataclass
class CompletionChecks:
    """What an agent's completion found when it waited for the fast checks (D2-D5)."""

    run_id: str
    #: Whether every fast check decided within `COMPLETION_BUDGET_SECONDS`.
    decided: bool
    #: The fast checks that failed with a failure of the task's own (not one main shares).
    failing: List[Dict[str, Any]]
    merged_sha: Optional[str] = None
    #: Set only when the verdict is one already recorded for exactly this work (nothing ran for
    #: this completion): the task's checkout relative to the project root, and the commit checked.
    #: The refusal then says so; a retry on unchanged work looked like a stale cache to an agent.
    unchanged_checkout: Optional[str] = None
    unchanged_commit: Optional[str] = None


@dataclass
class ChecksSkipped:
    """Why an agent's completion recorded no check run (FR-2): written on its history row."""

    reason: str

    @property
    def note(self) -> str:
        return f"No check ran at this completion: {self.reason}."


async def _stop_run_on_older_work(task_id: str, timeout: float) -> None:
    """A run still in flight for *task_id* checks work the completion is replacing: end it, recorded
    `superseded`, so the completion's run checks what it completes (one per task, D4)."""
    from .pty_runner import terminate_process_tree

    job = _inflight.get(task_id)
    if job is None or job.done():
        return
    _superseded[task_id] = _NEW_WORK
    proc = _processes.get(task_id)
    if proc is not None and proc.poll() is None:
        await asyncio.to_thread(terminate_process_tree, proc.pid)
    await asyncio.wait({job}, timeout=timeout)


async def _snapshot_task_checkout(root: Path, task: Task, agent: Optional[str]) -> None:
    """Commit the builder's uncommitted work in the task's checkout, as a turn's end does (D3), so a
    branch-tip task is checked with its work. Best-effort: the checks then run on what is there."""
    from . import blocking, worktrees

    checkout = worktrees.task_worktree_path(root, task.id)
    if not checkout.is_dir():
        return
    try:
        who = agent or task.assignee or "agent"
        await blocking.run(
            worktrees.snapshot_worktree,
            checkout,
            who,
            message=(
                f"Auto-snapshot: {who}'s turn on "
                f"{readable_ids.commit_name(task.id, task.readable_id)}"
            ),
        )
    except Exception:  # noqa: BLE001 -- a snapshot failure does not stop the completion
        logger.warning(
            "could not snapshot the checkout of %s at completion", task.id, exc_info=True
        )


async def fast_checks_at_completion(
    session: AsyncSession, task: Task, agent: Optional[str]
) -> CompletionChecks | ChecksSkipped:
    """Start *task*'s check run on the work its review would be given and wait, at most
    `COMPLETION_BUDGET_SECONDS`, for its fast checks (FR-2, D2-D5). `ChecksSkipped` where no fast
    check is configured, nothing is checkable, or no run could be started: the completion is
    recorded as before, saying why no check ran.

    Reads through the caller's session (nothing is staged in it) and starts the run with the targets
    passed explicitly (F680's pattern): the completing transaction has not committed.

    Where no run is recorded for this completion the answer is `ChecksSkipped`, saying why, which
    the completion writes on its history row (`a-task-s-checks-and-merges-use-its-own-work-...`,
    FR-2): a completion never goes unchecked without saying so.

    **One deadline for all of it**: the snapshot, the merged commit, ending a run on older work and
    the fast checks all count against the budget, so the Hub answers inside the MCP client's
    COMPLETION_REQUEST_TIMEOUT_SECONDS however the time is spent.

    **A verdict already recorded for exactly this work is the answer**: completing unchanged work
    again after its run failed with its own failure is refused with that run's output, as a fresh
    fast failure is (any of its checks, not only the fast ones -- the failure is known now)."""
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

    deadline = time.monotonic() + COMPLETION_BUDGET_SECONDS
    project = await session.get(Project, task.project_id)
    checks = configured_checks(project, PHASE_REVIEW)
    if project is None or not project.main_branch:
        return ChecksSkipped("the project has no main branch set, so no check can run")
    if not any(c["fast"] for c in checks):
        return ChecksSkipped(
            "the project configures no fast check"
            + ("; its other checks run before the review" if checks else "")
        )
    try:
        root = (await resolve_project_workspace(session, task.project_id)).root
    except ProjectWorkspaceError as exc:
        return ChecksSkipped(f"the project's repository could not be located ({exc})")
    await _snapshot_task_checkout(root, task, agent)
    targets = await check_targets(session, task, root, awaiting_review=True)
    if not targets:
        # Where evidence governs (a flow's task) and none names a commit yet, the review has no
        # target to name; the work being completed is the task's branch tip, and the fast checks
        # are for that work (the slice L drive: flow completions were recorded before any check).
        from . import task_integration

        branch_tip = await asyncio.to_thread(task_integration.task_branch_tip, root, task.id)
        targets = [branch_tip] if branch_tip else []
    if not targets:
        return ChecksSkipped("the task has no commit of its own to check: its branch has none")
    tip = await asyncio.to_thread(main_tip, root, project.main_branch)
    if tip is None:
        return ChecksSkipped(f"the main branch {project.main_branch} does not resolve to a commit")
    found = targets
    targets = await asyncio.to_thread(unmerged, root, tip, targets)
    if not targets:
        return ChecksSkipped(
            f"its work ({', '.join(sha[:12] for sha in found)}) is already on "
            f"{project.main_branch}"
        )
    recorded = await latest_run(session, task.id)
    if is_running(task.id):
        current = await latest_run(session, task.id)
        if current is None or list(current.target_shas or []) != targets or current.main_sha != tip:
            await _stop_run_on_older_work(task.id, max(0.0, deadline - time.monotonic()))
    run_id = await request_run(task.project_id, task.id, targets=targets)
    if run_id is None:
        current = await latest_run(session, task.id)
        if (
            current is None
            or current.state != "running"
            or not is_running(task.id)
            or list(current.target_shas or []) != targets
            or current.main_sha != tip
        ):
            # Nothing to wait on for this work: a run on older work outlived the stop's share of
            # the budget. The completion is recorded; the review waits for a run on this work.
            return ChecksSkipped(
                "a check run on older work did not end in time; its review waits for a run on "
                f"{', '.join(sha[:12] for sha in targets)}"
            )
        run_id = current.id  # the run already in flight on exactly this work
    decided = True
    event = _fast_waiters.get(run_id)
    if event is not None:
        try:
            await asyncio.wait_for(event.wait(), timeout=max(0.0, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            decided = False
    async with async_session_factory() as fresh:
        run = await fresh.get(TaskCheckRun, run_id)
    if run is None:
        return ChecksSkipped(f"check run {run_id} could not be read back")
    fast = {check["name"] for check in checks if check["fast"]}
    failing = [
        result
        for result in run.results or []
        if result.get("name") in fast and failed(result) and not preexisting(result)
    ]
    if run.state == "failed" and own_failure(run.results):
        # Decided before this completion asked (a re-completion of unchanged work) or within its
        # wait: every failure of the task's own is the builder's to fix now.
        failing = [
            result for result in run.results or [] if failed(result) and not preexisting(result)
        ]
    if run.state == "error":
        failing = []  # the Hub could not produce a result: not the builder's to fix (D6)
    outcome = CompletionChecks(
        run_id=run_id, decided=decided, failing=failing, merged_sha=run.merged_sha
    )
    if failing and recorded is not None and recorded.id == run_id and recorded.state == "failed":
        # The verdict was recorded before this completion asked: nothing ran for it.
        from . import worktrees

        checkout = worktrees.task_worktree_path(root, task.id)
        try:
            outcome.unchanged_checkout = checkout.relative_to(root).as_posix()
        except ValueError:
            outcome.unchanged_checkout = str(checkout)
        outcome.unchanged_commit = targets[0][:12]
    return outcome


def failure_report(
    results: Sequence[Dict[str, Any]], *, run_id: str, merged_sha: Optional[str]
) -> str:
    """The failing checks of a run, the commit checked and their output: what a refused completion
    says and what a returned task's notes carry (FR-3, FR-7)."""
    failing = [r for r in results if failed(r) and not preexisting(r)]
    names = ", ".join(str(r.get("name")) for r in failing) or "a check"
    commit = (merged_sha or "")[:12] or "the merged work"
    lines = [
        f"The project's check{'s' if len(failing) != 1 else ''} {names} failed on {commit} (this "
        f"task's work merged onto the main branch), check run {run_id}."
    ]
    for result in failing:
        how = (
            "ran past its timeout"
            if result.get("timed_out")
            else f"exited {result.get('exit_code')}"
        )
        # The tests its report named (FR-2), whatever the runner printed.
        named = list(result.get("failed_tests") or result.get("named_failures") or [])
        if named:
            how += f"; failing tests: {', '.join(named)}"
        output = str(result.get("failure_excerpt") or result.get("output_tail") or "").strip()
        lines.append(f"\n{result.get('name')} {how}:\n{output[-OUTPUT_TAIL_CHARS:]}")
    return "\n".join(lines)


def _duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds)}s" if seconds < 90 else f"{int(round(seconds / 60))}m"


def _checks_took(run: TaskCheckRun) -> Optional[float]:
    """How long a decided run's checks ran: the sum of its results' durations, which leaves out
    the time it waited for a slot (F1076); its whole age where it records none."""
    durations = [r.get("duration_seconds") for r in (run.results or []) if isinstance(r, dict)]
    if durations and all(isinstance(d, (int, float)) for d in durations):
        return float(sum(durations))
    if run.started_at is None or run.ended_at is None:
        return None
    return (_aware(run.ended_at) - _aware(run.started_at)).total_seconds()


async def _previous_duration(session: AsyncSession, task: Task, before: Optional[str]) -> str:
    """How long the task's previous decided run's checks took, else the project's latest one's;
    `""` if none."""
    for where in (TaskCheckRun.task_id == task.id, TaskCheckRun.project_id == task.project_id):
        query = (
            select(TaskCheckRun)
            .where(where, TaskCheckRun.state.in_(("passed", "failed")))
            .where(TaskCheckRun.ended_at.is_not(None))
            .order_by(TaskCheckRun.started_at.desc())
            .limit(2)
        )
        for run in (await session.execute(query)).scalars():
            took = _checks_took(run) if run.id != before else None
            if took is not None:
                return _duration(took)
    return ""


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


@dataclass
class ReviewWait:
    """Why a review of a completed task waits for its checks (FR-6, D6)."""

    #: `running`, `missing`, `stale`, `interrupted`, `failed` (the task's own failure), or
    #: `conflict` (its work does not merge onto main, FR-7).
    state: str
    run_id: Optional[str]
    reason: str

    @property
    def needs_a_run(self) -> bool:
        return self.state in ("missing", "stale", "interrupted")

    @property
    def returns_the_work(self) -> bool:
        """Whether the work goes back to its builder (`schedule_return`) rather than waiting."""
        return self.state in ("failed", "conflict")


def _conflict_wait(run: TaskCheckRun) -> ReviewWait:
    return ReviewWait(
        "conflict",
        run.id,
        f"its work does not merge onto the main branch ({run.error}; check run {run.id}), so it "
        f"goes back to its builder rather than to a reviewer",
    )


async def review_wait(session: AsyncSession, task: Task) -> Optional[ReviewWait]:
    """Whether a review of *task*'s work must wait for its check run, and why; `None` where it need
    not (no checks apply, or they passed, or decided with no failure of the task's own, or the Hub
    could not produce a result -- the reviewer is told that as today). A run that found the work
    does not merge onto main holds it as `conflict`: it goes back to its builder (FR-7). Reads
    only; starts nothing.
    """
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

    project = await session.get(Project, task.project_id)
    if project is None or not project.main_branch or not configured_checks(project, PHASE_REVIEW):
        return None
    try:
        root = (await resolve_project_workspace(session, task.project_id)).root
    except ProjectWorkspaceError:
        return None
    targets = await check_targets(session, task, root, awaiting_review=True)
    seen = await view(session, task, root, project.main_branch, targets)
    if seen is None or seen.state in ("passed", "error"):
        if seen is not None and seen.state == "error" and conflicted(seen.run):
            return _conflict_wait(seen.run)
        return None
    run = seen.run
    # On an older main tip (`stale`), but no run follows on this work without the operator: it
    # conflicted (FR-7), or ended twice without a verdict (FR-9) and the review goes on.
    if (
        run is not None
        and run.state == "error"
        and run.target_shas
        and await _unjudged_stands(session, run, list(run.target_shas))
    ):
        tip = await asyncio.to_thread(main_tip, root, project.main_branch)
        pending = await asyncio.to_thread(unmerged, root, tip, targets) if tip else []
        if pending == list(run.target_shas):
            return _conflict_wait(run) if conflicted(run) else None
    run_id = run.id if run is not None else None
    if seen.state == "failed":
        if run is None or not own_failure(run.results):
            return None  # a failure main shares, or a flake: slice M's, and the review proceeds
        return ReviewWait(
            "failed",
            run_id,
            f"its checks failed with its own failure (check run {run_id}), so it goes back to "
            f"its builder rather than to a reviewer",
        )
    previous = await _previous_duration(session, task, run_id)
    took = f" (the previous run took {previous})" if previous else ""
    if seen.state == "running" and run is not None and run.id in _waiting_for_slot:
        queued = (datetime.now(timezone.utc) - _waiting_for_slot[run.id]).total_seconds()
        return ReviewWait(
            "running",
            run_id,
            f"its fast checks passed and the rest have waited {_duration(queued)} for a check slot "
            f"behind other runs, at most {MAX_CONCURRENT_RUNS} running at once{took} (check run "
            f"{run_id}); queued is not hung, and its review is offered once they pass",
        )
    if seen.state == "running" and run is not None and run.started_at is not None:
        # From when it got its slot: `started_at` is when it was queued (F1076).
        since = _aware(run.slot_at) if run.slot_at is not None else _aware(run.started_at)
        ran = (datetime.now(timezone.utc) - since).total_seconds()
        return ReviewWait(
            "running",
            run_id,
            f"its checks have run {_duration(ran)}{took} (check run {run_id}); its review is "
            f"offered once they pass",
        )
    why = {
        "missing": "its checks have not run on this work yet",
        "stale": f"its last check run ({run_id}) was for other work or another main tip",
        "interrupted": f"its check run {run_id} was interrupted",
    }.get(seen.state, f"its checks are {seen.state}")
    return ReviewWait(
        seen.state,
        run_id,
        f"{why}; a run is requested{took}, and its review is offered once it passes",
    )


async def return_failed_work(run_id: str) -> bool:
    """A completed task whose check run failed with its own failure goes back to its builder,
    without a review turn (FR-7, D7). Whether it was returned. Never raises.

    Only while the task is still `completed` and the run checked its current review target: work
    already under review keeps its reviewer (briefed with the failure, as today), and a run on older
    work proves nothing about the work waiting now. `completed -> revision_needed` is the operator's
    edge (F832), and the operator configured the checks, so the move is made as the operator, as a
    job's is, with its own origin `checks` and a note naming the run."""
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace
    from .run_task_binding import withdraw_review_entries_for
    from .sse import sse_manager
    from .task_transition_service import ORIGIN_CHECKS, TransitionRefusedError, apply_transition
    from .task_transitions import SEND_BACK_MERGE_NEEDED, operator
    from .utils import persist_event

    try:
        async with async_session_factory() as session:
            run = await session.get(TaskCheckRun, run_id)
            conflict = conflicted(run)
            if run is None or not (
                conflict or (run.state == "failed" and own_failure(run.results))
            ):
                return False
            task = await session.get(Task, run.task_id)
            if task is None or task.status != "completed":
                return False
            latest = await latest_run(session, task.id)
            project = await session.get(Project, task.project_id)
            if latest is None or latest.id != run.id or project is None or not project.main_branch:
                return False
            try:
                root = (await resolve_project_workspace(session, task.project_id)).root
            except ProjectWorkspaceError:
                return False
            tip = await asyncio.to_thread(main_tip, root, project.main_branch)
            if tip is None:
                return False
            targets = await check_targets(session, task, root, awaiting_review=True)
            if await asyncio.to_thread(unmerged, root, tip, targets) != list(run.target_shas or []):
                return False
            if conflict:
                # FR-7: the builder can resolve it; nothing re-runs until its branch moves.
                report = (
                    f"The task's work could not be checked: {run.error} (check run {run.id}). "
                    f"Merge {project.main_branch} into the task's branch, resolve the conflicts "
                    f"and complete the task again; its checks run on the new commit."
                )
                reason_class = SEND_BACK_MERGE_NEEDED
                note = f"the task's work does not merge onto {project.main_branch} (check run {run.id})"
            else:
                report = failure_report(run.results or [], run_id=run.id, merged_sha=run.merged_sha)
                reason_class = send_back_class(run.results)
                note = f"the project's checks failed on check run {run.id}"
            # Read before the write lock: the send-back holds the task's accepted evidence, less
            # what already landed (`a-checks-send-back-returns-the-task-s-accepted-evidence`, FR-2).
            from .requirement_evidence import own_accepted_commits_on_main

            on_main = await own_accepted_commits_on_main(session, task, root, project.main_branch)
            # **Compare-and-set** before the move: everything above read `completed` without a
            # write lock while git ran, and another session (a review, the operator's approval) may
            # have moved the task since. This UPDATE takes the write lock and matches only a task
            # still `completed`; until this transaction commits no other writer can move it, so the
            # refreshed task is the one the move is made on. Nothing matched: it moved, left alone.
            claimed = await session.execute(
                update(Task)
                .where(Task.id == task.id, Task.status == "completed")
                .values(updated=datetime.now(timezone.utc))
                .execution_options(synchronize_session=False)
            )
            if not claimed.rowcount:
                await session.rollback()
                return False
            await session.refresh(task)
            try:
                await apply_transition(
                    session,
                    task,
                    "revision_needed",
                    operator(),
                    origin=ORIGIN_CHECKS,
                    verdict_reason=report,
                    note=note,
                    accepted_on_main=on_main,
                    reason_class=reason_class,
                    reason=f"{note[0].upper()}{note[1:]}.",
                )
            except TransitionRefusedError:
                logger.warning("could not return %s for its failed checks", task.id, exc_info=True)
                return False
            task.notes = report
            task.updated = datetime.now(timezone.utc)
            withdrawn = await withdraw_review_entries_for(session, task)
            await session.commit()
            payload = {"id": task.id, "status": task.status}
            await sse_manager.broadcast(task.project_id, "task_updated", payload)
            for entry in withdrawn:
                await sse_manager.broadcast(task.project_id, "queue_entry_withdrawn", entry)
            await persist_event(
                session, task.project_id, "task_updated", payload, agent=task.assignee
            )
            return True
    except Exception:  # noqa: BLE001 -- the flow's firing is the backstop (`review_wait`)
        logger.warning("could not return the work of check run %s", run_id, exc_info=True)
        return False


async def _return_latest(task_id: str) -> None:
    async with async_session_factory() as session:
        run = await latest_run(session, task_id)
    if run is not None:
        await return_failed_work(run.id)


def schedule_return(task_id: str) -> None:
    """Fire-and-forget: return *task_id* if its latest run already failed with its own failure (the
    firing's backstop, and a completion recorded after its budget ran out). Never raises."""
    _background(_return_latest(task_id), f"return {task_id} for its failed checks")


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
