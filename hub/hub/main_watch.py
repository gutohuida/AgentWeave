"""Main is watched, and a move the Hub did not make is raised (`amendments-main-watch-and-the-next-
slice`, task `main-watch`, design D4/D5).

`project_checks.watch_main_forever` looks every `WATCH_SECONDS` (30 s) at each project with a main
branch: one `git rev-parse` per project, off the event loop (`project_checks._current_tip`). When
the tip differs from the one last accounted for (`Project.main_tip_seen`, persisted, so a restart
neither loses a move made while the Hub was down nor raises one twice), `observe` classifies the
move:

* **The Hub's own**: every first-parent commit from the seen tip to the new one is a merge commit
  an integration recorded (`TaskIntegration.merged_sha`, or `note_own_merge` for one whose record
  has not committed yet). Recognised by sha, never by author or message: the Hub's snapshots on task
  branches carry the same committer identity, so a fast-forward of an agent's branch would pass an
  identity check. Raises nothing.
* **Anything else** -- an agent's commit in the main checkout, the operator's own merge, the
  orchestrator's hand merge (D5: nothing a commit can carry tells them apart, so they are raised
  too) -- is raised: added to the project's open notice, or opening one, listing each commit's short
  sha, subject and author with the old and new tip, and announced (`main_moved`, persisted and
  broadcast for the app's notification). A move whose old tip is no longer an ancestor is a
  **rewrite**.

Nothing is blocked, reverted or retried because of a move, and it is not a stall: a stall wakes the
mender, which cannot act on this. The first look on a project (no seen tip) records the tip and
raises nothing.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import MainNotice, Project, TaskIntegration
from .utils import short_id

logger = logging.getLogger(__name__)

EVENT = "main_moved"
#: How many commits one notice lists; a longer stretch says how many more there were.
MAX_COMMITS = 200
_SEP = "\x1f"

#: Merge commits an integration made whose record may not have committed yet (`note_own_merge`).
_own_merges: Set[str] = set()


def note_own_merge(sha: str) -> None:
    """Called by `task_integration.integrate` the moment its merge succeeds."""
    if sha:
        _own_merges.add(sha)


def forget() -> None:
    """Drop the in-memory state, as a restart does (tests)."""
    _own_merges.clear()


@dataclass
class Move:
    old_tip: str
    new_tip: str
    rewrite: bool
    #: First-parent commits from `old_tip` to `new_tip`, newest first: `{"sha", "subject", "author"}`.
    commits: List[Dict[str, str]] = field(default_factory=list)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    from .subprocess_windows import no_console_kwargs

    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
        **no_console_kwargs(),
    )


def read_move(root: Path, old_tip: str, new_tip: str) -> Move:
    """What moved main from *old_tip* to *new_tip*. Blocking: run it off the loop. Only called when
    the tip changed, so the 30-second poll stays one `rev-parse` per project."""
    ancestor = _git(root, "merge-base", "--is-ancestor", old_tip, new_tip)
    rewrite = ancestor.returncode != 0
    listed = _git(
        root,
        "log",
        "--first-parent",
        f"--max-count={MAX_COMMITS}",
        f"--format=%H{_SEP}%s{_SEP}%an",
        new_tip,
        f"^{old_tip}",
    )
    if listed.returncode != 0:
        # The old tip may be gone altogether (garbage-collected after a rewrite): list the new tip.
        listed = _git(root, "log", "-1", f"--format=%H{_SEP}%s{_SEP}%an", new_tip)
    commits: List[Dict[str, str]] = []
    for line in (listed.stdout or "").splitlines():
        parts = line.split(_SEP)
        if len(parts) == 3:
            commits.append({"sha": parts[0], "subject": parts[1], "author": parts[2]})
    return Move(old_tip=old_tip, new_tip=new_tip, rewrite=rewrite, commits=commits)


async def _recorded_merges(session: AsyncSession, project_id: str, shas: List[str]) -> Set[str]:
    if not shas:
        return set()
    rows = await session.execute(
        select(TaskIntegration.merged_sha).where(
            TaskIntegration.project_id == project_id, TaskIntegration.merged_sha.in_(shas)
        )
    )
    return {sha for sha in rows.scalars().all() if sha}


async def open_notice(session: AsyncSession, project_id: str) -> Optional[MainNotice]:
    return (
        (
            await session.execute(
                select(MainNotice)
                .where(MainNotice.project_id == project_id, MainNotice.seen_at.is_(None))
                .order_by(MainNotice.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


def view(notice: MainNotice) -> Dict[str, Any]:
    def iso(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    return {
        "id": notice.id,
        "project_id": notice.project_id,
        "branch": notice.branch,
        "old_tip": notice.old_tip,
        "new_tip": notice.new_tip,
        "rewrite": bool(notice.rewrite),
        "commits": [
            {
                "sha": c.get("sha", "")[:12],
                "subject": c.get("subject", ""),
                "author": c.get("author", ""),
            }
            for c in (notice.commits or [])
        ],
        "created_at": iso(notice.created_at),
        "updated_at": iso(notice.updated_at),
        "seen_at": iso(notice.seen_at),
        "seen_by": notice.seen_by,
    }


async def observe(project_id: str, tip: str, root: Path) -> Optional[Dict[str, Any]]:
    """Account for *project_id*'s main tip being *tip*: record it, and raise the move when it was
    not the Hub's own. Returns the open notice's view when one was raised, else None."""
    from .db.engine import async_session_factory

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        if project is None or not project.main_branch:
            return None
        seen = project.main_tip_seen
        if seen == tip:
            return None
        if seen is None:
            # The first look: record the tip, raise nothing.
            project.main_tip_seen = tip
            await session.commit()
            return None
        move = await asyncio.to_thread(read_move, root, seen, tip)
        recorded = await _recorded_merges(session, project_id, [c["sha"] for c in move.commits])
        own = recorded | _own_merges
        foreign = [c for c in move.commits if c["sha"] not in own]
        project.main_tip_seen = tip
        if not move.rewrite and not foreign:
            await session.commit()
            return None
        now = datetime.now(timezone.utc)
        notice = await open_notice(session, project_id)
        if notice is None:
            notice = MainNotice(
                id=f"mnot-{short_id()}",
                project_id=project_id,
                branch=project.main_branch,
                old_tip=seen,
                new_tip=tip,
                commits=[],
                rewrite=False,
                created_at=now,
                updated_at=now,
            )
            session.add(notice)
        notice.new_tip = tip
        notice.rewrite = bool(notice.rewrite) or move.rewrite
        notice.commits = (foreign + list(notice.commits or []))[:MAX_COMMITS]
        notice.updated_at = now
        await session.flush()
        payload = {
            **view(notice),
            "moved_from": seen,
            "moved_to": tip,
            "moved_rewrite": move.rewrite,
            "moved_commits": len(foreign),
        }
        await _announce(session, project_id, payload)
        await session.commit()
    return view(notice)


async def _announce(session: AsyncSession, project_id: str, payload: Dict[str, Any]) -> None:
    from .sse import sse_manager
    from .utils import persist_event

    try:
        await persist_event(session, project_id, EVENT, payload, agent=None, severity="warn")
        await sse_manager.broadcast(project_id, EVENT, payload)
    except Exception:  # noqa: BLE001 -- the notice stands whether or not it was announced
        logger.warning("could not announce that main moved in %s", project_id, exc_info=True)


async def mark_seen(
    session: AsyncSession, project_id: str, notice_id: str, by: str
) -> Optional[MainNotice]:
    notice = await session.get(MainNotice, notice_id)
    if notice is None or notice.project_id != project_id:
        return None
    if notice.seen_at is None:
        notice.seen_at = datetime.now(timezone.utc)
        notice.seen_by = by
    return notice
