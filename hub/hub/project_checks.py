"""A project's checks, run on the work a task's approval would merge (`approval-runs-the-projects-checks`).

The operator configures checks (`Project.checks`); nothing an agent sends is ever executed here. A run
builds the commit approval would produce -- main's tip with each merge target applied, through
`git merge-tree` and `commit-tree`, touching no checkout (design D1) -- checks it out in a scratch
worktree under `.agentweave/checks/<task_id>` (D2), runs each check there with the Hub's own
configuration removed from the environment (D8), stopping at the first failure that is the task's own
(a failure main shares does not stop it), and records a `TaskCheckRun` row (D3).

Runs are started in the background, never inside a request (D5): when a task is completed outside a
turn, when a turn bound to a completed task ends (its work is only committed then), and when the
project's main tip moves (`refresh`: the Hub's own merge, or `watch_main_forever` noticing one made
outside it) for a task with no pass of its work. A run main moved past is ended, recorded
`superseded`, and replaced. At most two run at once per Hub, and one per task (D4). The approval gate
only *reads* what is recorded (`view`) and starts nothing: a task's run is the gate before review,
and a pass of its work counts on any main tip; landing is gated by the batch's one run on main with
the queued work merged (`landing_queue`, `approved-work-merges-in-batches`).

A check may name the paths it covers (`paths`): where no file the merged work changes matches one, it
is not executed and is recorded skipped, which passes.

A check's result is a function of the tree it ran on and the check itself, so a passing result is
reused for the same merged *tree* and the same check (`check_digest`), whatever commits produced it:
a prerequisite merged into the task branch, or a main move that leaves the merged tree as it was,
re-runs nothing. A different tree is always checked again. A failure is never reused.

A failure is confirmed before it is charged to the task: the failed tests (pytest node ids parsed
from the output) or else the whole check are run once more on the same tree. Only a reproduced
failure stands; one that passes the second time passes, and the result records the flake.
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
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import flaky_tests, traces
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
#: How many of a project's latest decided runs are searched for a passing result on the same tree.
REUSE_LOOKBACK = 200
#: A failing check's failed tests are re-run by node id only up to this many; more re-runs the check.
MAX_RERUN_TESTS = 50
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


def configured_checks(project: Optional[Project]) -> List[Dict[str, Any]]:
    """The project's checks, normalised, in the order a run executes them; empty for none (null and
    `[]` mean the same).

    The fast checks first, then the rest, each group in the operator's order (FR-1, D1): an agent's
    completion waits for the fast ones, and they are the start of the task's one check run (D2). A
    check saved before `fast` existed is not fast."""
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
                }
            )
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


def _run_one(check: Dict[str, Any], cwd: Path, owner: Optional[str] = None) -> Dict[str, Any]:
    from .pty_runner import IS_WINDOWS, terminate_process_tree

    env, removed = check_environment()
    # A Python child writes a pipe in the console's ANSI code page on Windows: ask for UTF-8 so a
    # '…' in an assertion message arrives as itself (C2); `_decode_output` covers the rest.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.monotonic()
    if owner is not None and owner in _superseded:
        # Main moved while this run was still building its checkout: `supersede` found no process
        # to end, and the caller discards this result as superseded. Nothing is started.
        return {
            "name": check["name"],
            "exit_code": None,
            "timed_out": False,
            "duration_seconds": 0.0,
            "output_tail": "",
        }
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
        if owner in _superseded:
            # `supersede` sets `_superseded` before it reads `_processes`: a move that landed
            # between the check above and this registration found no process, so end it here.
            terminate_process_tree(proc.pid)
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
    text = scrub(_decode_output(output or b""), removed)
    if timed_out:
        text += f"\n[the check ran past its {check['timeout_seconds']}s timeout and was ended]"
    result = {
        "name": check["name"],
        "exit_code": None if timed_out else proc.returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 1),
        "output_tail": text[-OUTPUT_TAIL_CHARS:],
    }
    if not timed_out and proc.returncode not in (0, None):
        # Read from the whole output, not the stored tail: the summary may be longer than it.
        node_ids = failed_test_ids(text)
        if node_ids:
            result["failed_tests"] = node_ids
        excerpt = failure_excerpt(text)
        if excerpt:
            result["failure_excerpt"] = excerpt
    return result


_FAILURES_HEADER_RE = re.compile(r"^=+ (?:FAILURES|ERRORS) =+\s*$", re.MULTILINE)


def failure_excerpt(output: str) -> str:
    """The start of pytest's FAILURES (or ERRORS) section, where the tracebacks are, or `""`.

    The stored tail of a long suite holds only the summary, so a failure's traceback was lost:
    two gate runs on 2026-10-25 kept `FAILED <node id>` and nothing that said why."""
    found = _FAILURES_HEADER_RE.search(output)
    if found is None or len(output) - found.start() <= OUTPUT_TAIL_CHARS:
        return ""  # none, or already inside the tail
    return output[found.start() : found.start() + OUTPUT_TAIL_CHARS]


# --- reuse and confirmation ----------------------------------------------------------------------


def check_digest(check: Dict[str, Any]) -> str:
    """What makes two runs of a check the same check: everything the operator configured that can
    change its result. Not `fast`, which changes when it runs (D1), so marking a check fast keeps
    its passes reusable."""
    payload = json.dumps(
        {key: check.get(key) for key in ("name", "command", "timeout_seconds", "paths")},
        sort_keys=True,
    )
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


#: A pytest short-summary line: `FAILED <node id>[@<xdist group>][ - <message>]`.
_SUMMARY_LINE_RE = re.compile(r"^(?:FAILED|ERROR) (.+?)(?: - .*)?$", re.MULTILINE)
_XDIST_GROUP_RE = re.compile(r"@[^\[\]@:]*$")
_SAFE_NODE_ID_RE = re.compile(r"^[\w./\\:\-\[\]@ ,=+]+$")
_COUNT_RE = re.compile(r"\b(\d+) (passed|failed|errors?|skipped|deselected|xfailed|xpassed)\b")
#: pytest's final line: its counts, then ` in <seconds>s`.
_FINAL_LINE_RE = re.compile(r"\bin \d+(?:\.\d+)?s\b")
#: pytest options whose value is the next word; kept with it when a command is narrowed to node ids.
_VALUE_OPTIONS = frozenset(
    {
        "-n",
        "--numprocesses",
        "--maxprocesses",
        "--dist",
        "--tx",
        "-p",
        "-c",
        "-k",
        "-m",
        "-o",
        "--override-ini",
        "--rootdir",
        "--confcutdir",
        "--basetemp",
        "--tb",
        "-W",
        "--pythonwarnings",
        "--timeout",
        "--timeout-method",
        "--maxfail",
        "--durations",
        "-r",
        "--import-mode",
        "--capture",
        "--color",
        "--log-level",
        "--log-cli-level",
        "--junitxml",
        "--junit-xml",
        "--cov",
        "--cov-report",
        "--ignore",
        "--ignore-glob",
        "--deselect",
        "--max-worker-restart",
        "--asyncio-mode",
    }
)
#: Options that would choose a different set of tests than the node ids given.
_SELECTION_OPTIONS = frozenset(
    {"--lf", "--last-failed", "--ff", "--failed-first", "--sw", "--stepwise", "--stepwise-skip"}
)
_PYTEST_RE = re.compile(r"(?:^|(?<=\s))(?:\S*[\\/])?(?:py\.test|pytest)(?:\.exe)?(?=\s|$)")


def summary_counts(output: str) -> Optional[Dict[str, int]]:
    """The counts on pytest's final line (`2 failed, 8903 passed, ... in 645.88s`), or `None` where
    the output ends without one."""
    for line in reversed(output.strip().splitlines()[-20:]):
        found = _COUNT_RE.findall(line)
        if found and _FINAL_LINE_RE.search(line):
            counts: Dict[str, int] = {}
            for number, kind in found:
                kind = "error" if kind.startswith("error") else kind
                counts[kind] = counts.get(kind, 0) + int(number)
            return counts
    return None


def failed_test_ids(output: str) -> List[str]:
    """The node ids pytest's short summary names as failed or erroring, or `[]` unless every failure
    the final count reports is named (a truncated summary is not a list of the failures)."""
    ids: List[str] = []
    for match in _SUMMARY_LINE_RE.finditer(output):
        node = _XDIST_GROUP_RE.sub("", match.group(1).strip())
        if node and node not in ids:
            ids.append(node)
    counts = summary_counts(output)
    if not ids or counts is None:
        return []
    if counts.get("failed", 0) + counts.get("error", 0) != len(ids) or len(ids) > MAX_RERUN_TESTS:
        return []
    if not all(_SAFE_NODE_ID_RE.match(node) for node in ids):
        return []
    return ids


#: pytest-xdist's options: the worker count, which a narrowed run sets to 0 (serial), and the
#: distribution options, which mean nothing without workers and are dropped (`rerun-on-its-own`).
_WORKER_OPTIONS = frozenset({"-n", "--numprocesses"})
_DISTRIBUTION_OPTIONS = frozenset({"--dist", "--maxprocesses", "--tx"})
_SHORT_WORKERS_RE = re.compile(r"^-n(?!-)\S+$")


def narrowed_command(command: str, node_ids: Sequence[str]) -> Optional[str]:
    """*command* run on *node_ids* alone and serially, or `None` if it is not a plain pytest
    invocation that can be narrowed safely: its options are kept, the paths it names are replaced by
    the node ids, and an xdist worker count is set to 0 with the distribution options dropped
    (`a-red-main-does-not-hold-the-night`, FR-2). A command without `-n` is already serial and gains
    nothing: `-n 0` needs xdist installed.

    The night of 2026-10-26/27 a timing test passed one narrowed rerun under `-n auto` and failed the
    next while another suite ran; serial removes the load the rerun made for itself. The same
    command is what main is asked with, so the two trees are compared like for like."""
    found = _PYTEST_RE.search(command)
    if found is None or not node_ids:
        return None
    prefix, rest = command[: found.end()], command[found.end() :]
    if any(char in rest for char in "&|;<>^%!`$()"):
        return None  # a pipeline or a second command after pytest: not narrowed
    try:
        words = shlex.split(rest, posix=False)
    except ValueError:
        return None
    kept: List[str] = []
    take_value = False
    drop_value = False
    serial = False
    for word in words:
        if take_value:
            kept.append(word)
            take_value = False
        elif drop_value:
            drop_value = False
        elif word.startswith("-"):
            option = word.split("=", 1)[0]
            if option in _SELECTION_OPTIONS:
                continue
            if option in _WORKER_OPTIONS or _SHORT_WORKERS_RE.match(word):
                serial = True
                drop_value = option in _WORKER_OPTIONS and "=" not in word
                continue
            if option in _DISTRIBUTION_OPTIONS:
                drop_value = "=" not in word
                continue
            kept.append(word)
            take_value = word in _VALUE_OPTIONS
        # anything else is a path or node id the original run selected; the node ids replace it
    if take_value or drop_value:
        return None
    if serial:
        kept[:0] = ["-n", "0"]
    quoted = " ".join(f'"{node}"' for node in node_ids)
    return " ".join(part for part in (prefix, *kept, "--", quoted) if part)


def proves_the_tests_pass(result: Dict[str, Any], node_ids: Sequence[str]) -> bool:
    """Whether a narrowed re-run passed and really ran the tests it named: exit 0, nothing failed,
    and at least one passed test per node id (a node id that selects nothing would be no proof)."""
    counts = summary_counts(str(result.get("output_tail") or ""))
    return (
        not failed(result)
        and counts is not None
        and not counts.get("failed")
        and not counts.get("error")
        and counts.get("passed", 0) >= len(node_ids)
    )


def reproduces_a_test_failure(result: Dict[str, Any]) -> bool:
    """Whether a narrowed re-run failed *a test* (pytest's exit 1 with a failure counted), not on
    its own invocation: a usage error (exit 4) or nothing collected (exit 5) proves nothing."""
    counts = summary_counts(str(result.get("output_tail") or ""))
    return (
        result.get("exit_code") == 1
        and counts is not None
        and bool(counts.get("failed") or counts.get("error"))
    )


def _node_key(node_id: str) -> str:
    """A node id as compared across runs and trees: pytest prints the separators of the platform."""
    return node_id.strip().replace("\\", "/")


def test_file(node_id: str) -> str:
    """The repository-relative file a pytest node id names (its path part)."""
    return _node_key(node_id).split("::", 1)[0]


def touched_tests(node_ids: Sequence[str], changed: Optional[Sequence[str]]) -> List[str]:
    """The node ids whose file is among *changed*, the paths the task's merged work changes against
    the run's main commit (FR-4): a test the task touched is the task's to make pass. Unknown changes
    count every id as touched -- an override is never automatic on a guess."""
    if changed is None:
        return list(node_ids)
    paths = {_node_key(path) for path in changed}
    return [node for node in node_ids if test_file(node) in paths]


def _still_failing(again: Dict[str, Any], node_ids: Sequence[str]) -> List[str]:
    """Which of *node_ids* a narrowed rerun that reproduced a failure failed again: the ones its
    summary names, where it names failures among them; else all of them (not known which)."""
    named = {_node_key(node) for node in again.get("failed_tests") or []}
    keys = {_node_key(node) for node in node_ids}
    if not named or not named <= keys:
        return list(node_ids)
    return [node for node in node_ids if _node_key(node) in named]


def confirm_failure(
    check: Dict[str, Any],
    cwd: Path,
    result: Dict[str, Any],
    owner: Optional[str],
    changed: Optional[Sequence[str]] = None,
) -> None:
    """Run a failed check's failure once more on the same tree, and record what happened in
    *result* (blocking; the caller runs it in a thread).

    The failed tests alone, serially, where pytest named every one and the command can be narrowed
    to them (`a-red-main-does-not-hold-the-night`, FR-2), else the whole check. Reproduced: *result*
    keeps its failure and gains `confirmed`, and `compared_tests` names the ids main is asked about
    (`_MainBaseline`): those that failed again, and any in a file the task changed. A named id that
    passed the rerun is recorded in `flaky_tests`. Passed: *result* passes, and `flaky` keeps the
    first attempt -- a flake is recorded, never swallowed -- unless a flaky test is in a file the
    task's work changes (*changed*, FR-4): a task that adds or edits a flaky test introduced it, so
    its failure stands and is compared with main like a reproduced one.
    """
    node_ids = list(result.get("failed_tests") or [])
    narrowed = narrowed_command(check["command"], node_ids) if node_ids else None
    how, again = "check", None
    if narrowed is not None:
        again = run_one({**check, "command": narrowed}, cwd, owner)
        if proves_the_tests_pass(again, node_ids) or reproduces_a_test_failure(again):
            how = "tests"
        else:
            again = None  # the narrowed command proved nothing either way: run the check
    if again is None:
        again = run_one(check, cwd, owner)
    attempt = {
        "how": how,
        "tests": node_ids if how == "tests" else [],
        "exit_code": again["exit_code"],
        "timed_out": again["timed_out"],
        "duration_seconds": again["duration_seconds"],
    }
    if how == "tests":
        touched = touched_tests(node_ids, changed)
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
    """A failure main shares (F605): every test the task's tree failed (after its rerun) fails on
    the main tip the run was cut from too, compared by pytest node id where pytest named them
    (`a-red-main-does-not-hold-the-night`, FR-1), else the same check failed there. A run recorded
    before this field existed reads as not pre-existing, i.e. as before."""
    return failed(result) and bool(result.get("preexisting"))


def own_failure(results: Optional[Sequence[Dict[str, Any]]]) -> bool:
    """Whether a run's results hold a failure that is the task's (not one main shares)."""
    return any(failed(result) and not preexisting(result) for result in results or [])


#: The two kinds of failure that are not the task's (`a-red-main-does-not-hold-the-night`).
FAILS_ON_MAIN = "fails on main"
FLAKY = "flaky"


def not_the_tasks(
    results: Optional[Sequence[Dict[str, Any]]], *, excluded: Sequence[str] = ()
) -> Optional[List[Dict[str, str]]]:
    """Every failure and flake in a run's *results*, as `{"check", "test", "kind"}`, where each one
    is provably not the task's -- the same node id fails on main too, or passed when rerun on its
    own -- else `None` (`a-red-main-does-not-hold-the-night`, FR-1, FR-4). `[]` for a run with
    neither: nothing to override.

    `None` for any failure that is the task's or that cannot be told apart: an id that passes on
    main, a failing or flaky test in a file the task changed, an id in *excluded* (the ids a
    Hub-filed fix task was filed for), and a failure compared check-level -- a non-pytest check, a
    timeout, a truncated summary, more than `MAX_RERUN_TESTS`, a command that cannot be narrowed,
    no main answer. Those keep the answer they had before. A whole-check flake (no test named)
    passes as before and is not listed: there is no test to name."""
    found: List[Dict[str, str]] = []
    for result in results or []:
        if not isinstance(result, dict) or result.get("skipped"):
            continue
        check = str(result.get("name") or "check")
        if failed(result):
            on_main = result.get("on_main") if isinstance(result.get("on_main"), dict) else {}
            shared = list(result.get("shared_tests") or [])
            if (
                not preexisting(result)
                or on_main.get("how") != "tests"
                or result.get("own_tests")
                or result.get("touched_tests")
                or not shared
            ):
                return None
            found += [{"check": check, "test": t, "kind": FAILS_ON_MAIN} for t in shared]
            found += [
                {"check": check, "test": t, "kind": FLAKY} for t in result.get("flaky_tests") or []
            ]
        elif isinstance(result.get("flaky"), dict) and result["flaky"].get("how") == "tests":
            if result.get("touched_tests"):
                return None  # cannot pass with one; read defensively
            tests = result.get("flaky_tests") or result["flaky"].get("tests") or []
            found += [{"check": check, "test": t, "kind": FLAKY} for t in tests]
    keys = {_node_key(node) for node in excluded}
    if any(_node_key(entry["test"]) in keys for entry in found):
        return None
    return found


def _record_main_result(result: Dict[str, Any], on_main: Dict[str, Any]) -> None:
    """Main's answer for the whole check: check-level, so it is never an automatic override."""
    result["on_main"] = {
        "exit_code": on_main["exit_code"],
        "timed_out": on_main["timed_out"],
        "how": "check",
    }
    result["preexisting"] = failed(on_main)


def _record_main_tests(
    result: Dict[str, Any], on_main: Dict[str, Any], node_ids: Sequence[str]
) -> bool:
    """Main's answer for exactly *node_ids*, run with the serial narrowed command (FR-1): each id
    that fails there is shared, each that passes is the task's own. Exit codes and counts are never
    compared. `False` where the run named no answer per id (it ran nothing, or failed without naming
    every failure): the caller asks the whole check instead, as before this change."""
    if proves_the_tests_pass(on_main, node_ids):
        failing: List[str] = []
    elif reproduces_a_test_failure(on_main) and on_main.get("failed_tests"):
        failing = list(on_main["failed_tests"])
    else:
        return False
    keys = {_node_key(node) for node in failing}
    shared = [node for node in node_ids if _node_key(node) in keys]
    own = [node for node in node_ids if _node_key(node) not in keys]
    result["on_main"] = {
        "exit_code": on_main["exit_code"],
        "timed_out": on_main["timed_out"],
        "how": "tests",
        "tests": list(node_ids),
        "failed_tests": failing,
    }
    result["shared_tests"], result["own_tests"] = shared, own
    result["preexisting"] = bool(shared) and not own
    return True


class _MainBaseline:
    """The main tip the run was cut from, checked out on the first failure and kept for the rest.

    A failing check is run there at once (F605, D1): its answer decides whether the run goes on.
    Where the task's tree named its failed tests and they stood their serial rerun
    (`compared_tests`), main runs the same serial command narrowed to exactly those ids (FR-1);
    otherwise the whole check. Best-effort: a baseline that cannot be taken leaves the result as it
    was, charged to the task, and `unavailable` (no main answer is never an automatic override).
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
            node_ids = list(result.get("compared_tests") or [])
            narrowed = narrowed_command(check["command"], node_ids) if node_ids else None
            if narrowed is not None:
                on_main = await asyncio.to_thread(
                    run_one, {**check, "command": narrowed}, self.path, self.task_id
                )
                if _record_main_tests(result, on_main, node_ids):
                    return
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
        session, task.project_id, root, tip, target_shas, configured_checks(project)
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
    if fields.get("state") in DECIDED:
        await _after_decided(run_id)


async def _after_decided(run_id: str) -> None:
    """A run has decided: a completed task its own failure fails goes back to its builder (D7);
    any other verdict asks for its flow's firing, which offers the review it was waiting for (D6,
    FR-8) within `flow_advance`'s debounce rather than at the next tick. Never raises.

    First, failures that are not the task's -- main's, or flakes -- get their fix task filed now,
    while the flow's agents are idle (`a-red-main-does-not-hold-the-night`, D5); approval's own
    transaction stays free of task creation. A run with a failure of the task's own files none."""
    from . import flow_advance

    await flaky_tests.file_fix_task(run_id)
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
#: Tasks whose in-flight run main has moved past, to the tip it moved to.
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
#: Recorded in `_superseded` in place of a main tip: the task's work changed under the run (a new
#: completion), not main.
_NEW_WORK = "new-work"


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
                targets = await check_targets(
                    session, task, root, awaiting_review=task.status in AWAITING_REVIEW
                )
            targets = await asyncio.to_thread(unmerged, root, tip, list(targets))
            if not targets:
                return None
            latest = await latest_run(session, task_id)
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
        return merged, tree, changed, planned_results(checks, changed, tree, passes)
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

    async def superseded() -> bool:
        """Whether main moved past this run, or the task's work did; if so it ends recorded
        `superseded`, not failed."""
        new_tip = _superseded.get(task_id)
        if new_tip is None:
            return False
        await _finish(
            run_id,
            state=SUPERSEDED,
            results=list(results),
            error=(
                "the task's work changed (it was completed again) before this run finished; a "
                "run on the new work replaces it"
                if new_tip == _NEW_WORK
                else f"the main branch moved from {main_sha[:12]} to {new_tip[:12]} before this "
                "run finished; a run on the new tip replaces it"
            ),
        )
        return True

    async def run_group(
        group: Sequence[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]],
        merged: str,
        tree: Optional[str],
        changed: Optional[List[str]],
        baseline: _MainBaseline,
    ) -> Optional[str]:
        """Run *group* in order: `None` to go on, `"stop"` where the task's own failure decided
        the run, `"superseded"` where main or the work moved past it."""
        nonlocal path
        for check, already in group:
            if await superseded():
                return "superseded"
            result = already or skipped(check, changed)
            if result is None:
                if path is None:
                    path = await asyncio.to_thread(_checkout, root, task_id, merged)
                result = await asyncio.to_thread(run_one, check, path, task_id)
                if failed(result) and task_id not in _superseded:
                    # Confirmed on the same tree before main is asked (a flake that passes the
                    # second time needs no baseline); only a reproduced failure stands.
                    await asyncio.to_thread(confirm_failure, check, path, result, task_id, changed)
                    if result.get("flaky"):
                        # Raised to the operator, not only to the reviewer (`flaky_tests`).
                        await flaky_tests.record_flake(run_id, result)
                if failed(result) and task_id not in _superseded:
                    await baseline.record(check, result)
                if await superseded():
                    return "superseded"  # its tree was ended for the move: not a result
                result.update(tree=tree, check_digest=check_digest(check))
            results.append(result)
            await _finish(run_id, merged_sha=merged, results=list(results))
            if failed(result) and not preexisting(result):
                # The task's own failure already decides the run; the checks after it would only
                # make its author wait for them (operator, 2026-10-24). A failure main shares does
                # not stop it: it is not the task's, and what follows may still be.
                return "stop"
        return None

    try:
        if await superseded():
            return
        if prepared is not None:
            merged, tree, changed, planned = prepared
        else:
            built, why = await asyncio.to_thread(build_merged_commit, root, main_sha, targets)
            if built is None:
                await _finish(run_id, state="error", error=why)
                return
            merged = built
            tree = await asyncio.to_thread(tree_of, root, merged)
            changed = await asyncio.to_thread(changed_paths, root, main_sha, merged)
            planned = [None] * len(checks)
        pairs = list(zip(checks, planned, strict=True))
        split = sum(1 for check in checks if check.get("fast"))
        baseline = _MainBaseline(root, task_id, main_sha)
        try:
            outcome = await run_group(pairs[:split], merged, tree, changed, baseline)
            if outcome is None:
                # Every fast check passed: the completion waiting on them goes on now, and the rest
                # run after it. A fast failure instead ends the run first (the `finally` below
                # releases the waiter), so the refusal reads a decided run.
                _fast_decided(run_id)
            if outcome is None and pairs[split:]:
                async with _semaphore():
                    outcome = await run_group(pairs[split:], merged, tree, changed, baseline)
            if outcome == "superseded":
                return
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
    finally:
        _fast_decided(run_id)


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
    admits them in that order. `request_run` starts nothing for a result already current, and a pass
    of the task's work is current on any tip (`approved-work-merges-in-batches`, FR-9): only a task
    with no result, an interrupted or errored one, or a failure on an older tip is run again.
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
        failing: Set[str] = set()
        for task_id in waiting:
            latest = await latest_run(session, task_id)
            if latest is not None and latest.state == "failed" and own_failure(latest.results):
                failing.add(task_id)
    for task_id, (owner, _) in list(_inflight_tips.items()):
        if owner == project_id:
            await supersede(task_id, tip)
    for task_id in waiting:
        if is_running(task_id):
            continue  # current, or superseded and replaced when it ends
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
    from . import main_watch
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
                bool(configured_checks(project)),
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
        await blocking.run(worktrees.snapshot_worktree, checkout, agent or task.assignee or "agent")
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
    checks = configured_checks(project)
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
        output = str(result.get("failure_excerpt") or result.get("output_tail") or "").strip()
        lines.append(f"\n{result.get('name')} {how}:\n{output[-OUTPUT_TAIL_CHARS:]}")
    return "\n".join(lines)


def _duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds)}s" if seconds < 90 else f"{int(round(seconds / 60))}m"


async def _previous_duration(session: AsyncSession, task: Task, before: Optional[str]) -> str:
    """How long the task's previous decided run took, else the project's latest one; `""` if none."""
    for where in (TaskCheckRun.task_id == task.id, TaskCheckRun.project_id == task.project_id):
        query = (
            select(TaskCheckRun)
            .where(where, TaskCheckRun.state.in_(("passed", "failed")))
            .where(TaskCheckRun.ended_at.is_not(None))
            .order_by(TaskCheckRun.started_at.desc())
            .limit(2)
        )
        for run in (await session.execute(query)).scalars():
            if run.id != before and run.started_at is not None and run.ended_at is not None:
                return _duration((_aware(run.ended_at) - _aware(run.started_at)).total_seconds())
    return ""


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


@dataclass
class ReviewWait:
    """Why a review of a completed task waits for its checks (FR-6, D6)."""

    #: `running`, `missing`, `stale`, `interrupted`, or `failed` (the task's own failure).
    state: str
    run_id: Optional[str]
    reason: str

    @property
    def needs_a_run(self) -> bool:
        return self.state in ("missing", "stale", "interrupted")


async def review_wait(session: AsyncSession, task: Task) -> Optional[ReviewWait]:
    """Whether a review of *task*'s work must wait for its check run, and why; `None` where it need
    not (no checks apply, or they passed, or decided with no failure of the task's own, or the Hub
    could not produce a result -- the reviewer is told that as today). Reads only; starts nothing.
    """
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

    project = await session.get(Project, task.project_id)
    if project is None or not project.main_branch or not configured_checks(project):
        return None
    try:
        root = (await resolve_project_workspace(session, task.project_id)).root
    except ProjectWorkspaceError:
        return None
    targets = await check_targets(session, task, root, awaiting_review=True)
    seen = await view(session, task, root, project.main_branch, targets)
    if seen is None or seen.state in ("passed", "error"):
        return None
    run = seen.run
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
    if seen.state == "running" and run is not None and run.started_at is not None:
        ran = (datetime.now(timezone.utc) - _aware(run.started_at)).total_seconds()
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
    from .task_transitions import operator
    from .utils import persist_event

    try:
        async with async_session_factory() as session:
            run = await session.get(TaskCheckRun, run_id)
            if run is None or run.state != "failed" or not own_failure(run.results):
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
            report = failure_report(run.results or [], run_id=run.id, merged_sha=run.merged_sha)
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
                    note=f"the project's checks failed on check run {run.id}",
                    accepted_on_main=on_main,
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
