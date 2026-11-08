"""Generated files are rebuilt when work lands instead of sending it back
(`generated-files-are-rebuilt-when-work-lands-instead-of-sending-it-back`).

A project may declare paths that a tool produces rather than a person writes, and the command that
produces them (`Project.generated_files`, set only by the operator). Where a task's work conflicts
with the branch it merges onto **only** in those paths, the conflict points (the check run before
review, the landing batch, the push to a build's PR, and the merge a project without checks lands
by) call `rebuild` instead of sending the task back: the work is merged in a scratch worktree under
`.agentweave/generated/` with the base's side taken for the conflicting generated paths, the command
runs there the way a check runs (the Hub's configuration withheld, a timeout that ends the whole
process tree), and the result is committed only when the command exited zero and changed nothing
outside the declared paths. The commit's message ends `GENERATED_SUFFIX`; the caller records
`Rebuilt.record()` as `regenerated` and in the task's history (`record_event`).

Anything else -- a conflicting path outside the declared ones, a command that fails, times out or
writes elsewhere -- is a `Failure` whose `report` the caller sends back with, exactly where it sent
back before. Nothing here decides whether the result is good: the rebuilt tree goes through the
same checks any landing does, because it *is* what the caller checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import project_checks
from .utils import short_id

logger = logging.getLogger(__name__)

#: Where the scratch worktrees are made, beside the checks' (`project_checks.CHECKS_DIR`).
GENERATED_DIR = Path(".agentweave") / "generated"
#: What a rebuilt merge commit's message ends with (FR-8).
GENERATED_SUFFIX = " (generated files rebuilt)"
DEFAULT_TIMEOUT_SECONDS = 600
#: The event a rebuild is recorded under, which the task's history reads (FR-8).
EVENT_TYPE = "generated_files_rebuilt"

#: Why a rebuild did not produce a commit (FR-5), as `Failure.reason`.
UNEXPECTED_PATHS = "unexpected_paths"
EXIT = "exit"
TIMEOUT = "timeout"
NOT_GENERATED = "not_generated"
FAULT = "fault"

_TAIL_CHARS = 1500


@dataclass(frozen=True)
class Settings:
    """A project's declared generated paths and the command that rebuilds them."""

    paths: List[str]
    command: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def covers(self, path: str) -> bool:
        return any(project_checks.path_matches(pattern, path) for pattern in self.paths)

    def covers_all(self, paths: Sequence[str]) -> bool:
        """Whether every one of *paths* is a declared generated path. An empty list is not: there is
        nothing to rebuild, and `(unknown path)` -- git naming no file -- never matches."""
        return bool(paths) and all(self.covers(path) for path in paths)


def settings_of(project: Any) -> Optional[Settings]:
    """*project*'s generated-files setting, or `None` where it is off (unset, or no paths, or no
    command): every conflict is then sent back exactly as it was before this existed (FR-2)."""
    raw = getattr(project, "generated_files", None) if project is not None else None
    if not isinstance(raw, dict):
        return None
    paths = [str(p).strip() for p in raw.get("paths") or [] if str(p).strip()]
    command = str(raw.get("command") or "").strip()
    if not paths or not command:
        return None
    try:
        timeout = int(raw.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    return Settings(paths=paths, command=command, timeout_seconds=max(1, timeout))


def rebuildable(settings: Optional[Settings], paths: Sequence[str]) -> bool:
    """Whether a conflict in *paths* is one `rebuild` takes on, rather than a send-back."""
    return settings is not None and settings.covers_all(paths)


@dataclass
class Rebuilt:
    """A rebuild that produced *commit*: the base and the work merged, with *paths* rebuilt."""

    commit: str
    paths: List[str]
    seconds: float
    output_tail: str = ""

    def record(self, **where: Any) -> Dict[str, Any]:
        """The `regenerated` entry a landing or check-run record carries (FR-8)."""
        return {"paths": list(self.paths), "seconds": self.seconds, "commit": self.commit, **where}


@dataclass
class Failure:
    """A rebuild that committed nothing, and why (FR-5)."""

    reason: str
    report: str
    unexpected_paths: List[str] = field(default_factory=list)
    exit_code: Optional[int] = None
    output_tail: str = ""
    #: Whether the command ran at all (FR-4: never for a conflict outside the declared paths).
    ran: bool = False


Outcome = Rebuilt | Failure


def failure_report(failure: Failure, display_id: str, where: str) -> str:
    """The send-back report for a rebuild that failed at *where* (`landing batch lbat-...`)."""
    return (
        f"Task {display_id}'s work conflicts only in generated files ({where}), and rebuilding "
        f"them failed: {failure.report} Nothing was committed. Merge the main branch into the "
        "task's branch, rebuild the generated files there, and complete the task again."
    )


def _git(cwd: Path, *args: str, timeout: int = project_checks.GIT_TIMEOUT_SECONDS) -> Any:
    return project_checks._git(cwd, *args, timeout=timeout)


def _z(text: str) -> List[str]:
    return [part for part in (text or "").split("\0") if part]


def _scratch(root: Path, base: str) -> Path:
    """A detached scratch worktree at *base*, the Hub's own, with the project's dependency
    directories linked in as a check's checkout has them (`project_checks._checkout`)."""
    from .worktrees import _symlink_shared_dependencies

    path = root / GENERATED_DIR / short_id()
    path.parent.mkdir(parents=True, exist_ok=True)
    added = _git(
        root,
        "worktree",
        "add",
        "--detach",
        "--force",
        str(path),
        base,
        timeout=project_checks.CHECKOUT_TIMEOUT_SECONDS,
    )
    if added.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {added.stderr.strip()[:300]}")
    _symlink_shared_dependencies(root, path)
    return path


def _tail(text: str) -> str:
    return (text or "").strip()[-_TAIL_CHARS:]


def rebuild(
    root: Path,
    base: str,
    head: str,
    settings: Settings,
    message: str,
    conflicting: Sequence[str],
) -> Outcome:
    """Merge *head* onto *base* with the generated files rebuilt, as one commit whose parents are
    *base* and *head* and whose message is *message* with `GENERATED_SUFFIX`. Blocking.

    *conflicting* are the paths `merge-tree` named: a path among them outside the declared globs is
    a `Failure` before anything runs (FR-4)."""
    outside = [path for path in conflicting if not settings.covers(path)]
    if not conflicting or outside:
        return Failure(
            reason=NOT_GENERATED,
            report="it conflicts in files that are not generated: "
            + ", ".join((outside or ["(unknown path)"])[:10])
            + ".",
            unexpected_paths=outside,
        )
    path: Optional[Path] = None
    try:
        path = _scratch(root, base)
        return _rebuild_in(root, path, base, head, settings, message)
    except Exception as exc:  # noqa: BLE001 -- a fault is a failed rebuild, never a commit
        logger.warning("rebuilding generated files failed", exc_info=True)
        return Failure(reason=FAULT, report=f"the Hub could not rebuild them: {exc}.")
    finally:
        if path is not None:
            project_checks._remove_checkout(root, path)


def _rebuild_in(
    root: Path, path: Path, base: str, head: str, settings: Settings, message: str
) -> Outcome:
    from .worktrees import shared_dependency_directories

    merged = _git(path, "merge", "--no-ff", "--no-commit", "-q", head)
    unmerged = _z(_git(path, "diff", "--name-only", "-z", "--diff-filter=U").stdout)
    if merged.returncode != 0 and not unmerged:
        return Failure(reason=FAULT, report=f"git merge failed: {_tail(merged.stderr)}.")
    outside = [p for p in unmerged if not settings.covers(p)]
    if outside:
        # `merge-tree` and a real merge disagree only if the base moved: never resolved here.
        return Failure(
            reason=NOT_GENERATED,
            report="it conflicts in files that are not generated: " + ", ".join(outside[:10]) + ".",
            unexpected_paths=outside,
        )
    for conflicted in unmerged:
        # The base's side for each conflicting generated path; the command rebuilds it.
        if _git(path, "cat-file", "-e", f"{base}:{conflicted}").returncode == 0:
            taken = _git(path, "checkout", base, "--", conflicted)
        else:
            taken = _git(path, "rm", "-f", "-q", "--", conflicted)
        if taken.returncode != 0:
            return Failure(
                reason=FAULT, report=f"could not resolve {conflicted}: {_tail(taken.stderr)}."
            )
    ran = project_checks.run_one(
        {
            "name": "generated files",
            "command": settings.command,
            "timeout_seconds": settings.timeout_seconds,
        },
        path,
    )
    seconds = float(ran.get("duration_seconds") or 0.0)
    tail = _tail(ran.get("output_tail") or "")
    if ran.get("timed_out"):
        return Failure(
            reason=TIMEOUT,
            report=f"the command ran past its {settings.timeout_seconds}s timeout and was ended.",
            output_tail=tail,
            ran=True,
        )
    if ran.get("exit_code") != 0:
        return Failure(
            reason=EXIT,
            report=f"the command exited {ran.get('exit_code')}. Its output ended:\n{tail}",
            exit_code=ran.get("exit_code"),
            output_tail=tail,
            ran=True,
        )
    linked = set(shared_dependency_directories(root))
    changed = sorted(
        {
            *_z(_git(path, "diff", "--name-only", "--no-renames", "-z").stdout),
            *_z(_git(path, "ls-files", "--others", "--exclude-standard", "-z").stdout),
        }
        - linked
        - {name + "/" for name in linked}
    )
    unexpected = [p for p in changed if not settings.covers(p)]
    if unexpected:
        return Failure(
            reason=UNEXPECTED_PATHS,
            report="the command changed files that are not declared generated: "
            + ", ".join(unexpected[:20])
            + ".",
            unexpected_paths=unexpected,
            exit_code=0,
            output_tail=tail,
            ran=True,
        )
    if changed:
        added = _git(path, "add", "-A", "--", *changed)
        if added.returncode != 0:
            return Failure(reason=FAULT, report=f"git add failed: {_tail(added.stderr)}.", ran=True)
    tree = _git(path, "write-tree")
    if tree.returncode != 0:
        return Failure(
            reason=FAULT, report=f"git write-tree failed: {_tail(tree.stderr)}.", ran=True
        )
    commit = _git(
        root,
        "commit-tree",
        tree.stdout.strip(),
        "-p",
        base,
        "-p",
        head,
        "-m",
        message + GENERATED_SUFFIX,
    )
    if commit.returncode != 0:
        return Failure(
            reason=FAULT, report=f"git commit-tree failed: {_tail(commit.stderr)}.", ran=True
        )
    return Rebuilt(
        commit=commit.stdout.strip(),
        paths=sorted(set(unmerged) | set(changed)),
        seconds=seconds,
        output_tail=tail,
    )


async def record_event(
    session: Any, project_id: str, task_id: str, regenerated: Dict[str, Any]
) -> None:
    """Put a rebuild in the task's history (FR-8): `GET /tasks/{id}/transitions` answers these
    beside the moves, as `rebuilds`. The caller commits."""
    from .utils import persist_event

    await persist_event(
        session, project_id, EVENT_TYPE, {"task_id": task_id, **regenerated}, commit=False
    )


async def history(session: Any, task_id: str) -> List[Dict[str, Any]]:
    """The task's recorded rebuilds, oldest first."""
    from sqlalchemy import select

    from .db.models import EventLog

    rows = (
        (
            await session.execute(
                select(EventLog)
                .where(EventLog.event_type == EVENT_TYPE)
                .order_by(EventLog.timestamp.asc(), EventLog.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {**(row.data or {}), "at": row.timestamp.isoformat() if row.timestamp else None}
        for row in rows
        if isinstance(row.data, dict) and row.data.get("task_id") == task_id
    ]
