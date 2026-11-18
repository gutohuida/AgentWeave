"""Removing chats' and review runs' own worktrees once nothing needs them
(`one-profile-runs-many-turns-at-once-on-different-tasks`, FR-8, FR-14).

A chat the operator opens while the project's "profiles run in parallel" switch is on works in a
worktree of its own on `thread/<agent>/<thread>` (`worktrees.ensure_thread_worktree`). Once its line
of work is archived -- no open conversation left in its lineage -- and its branch has no commit that
is not on the main branch, the worktree is removed; the branch always stays (D6), and a thread with
unmerged work keeps both (`worktrees.release_thread_worktree`).

A review run's own checkout (`worktrees.review_run_path`) is removed when its run ends; one left by a
Hub that stopped mid-run is removed here once no run with that id is running.

Run from the Hub's maintenance pass (`db_maintenance.run_pass`). Every git step goes through
`blocking.run_serialized`, with every other worktree change.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import blocking, project_workspace, worktrees
from .db.engine import async_session_factory
from .db.models import Conversation, Project, Run

logger = logging.getLogger(__name__)


async def archived_threads(session: AsyncSession, project_id: str) -> List[Tuple[str, str]]:
    """`(agent, thread)` of every thread whose line of work has no open conversation left."""
    rows = (
        await session.execute(
            select(
                Conversation.agent, Conversation.lineage_id, Conversation.id, Conversation.lifecycle
            ).where(Conversation.project_id == project_id, Conversation.own_worktree.is_(True))
        )
    ).all()
    lineages: Dict[Tuple[str, str], bool] = {}
    for agent, lineage, conversation_id, lifecycle in rows:
        key = (agent, lineage or conversation_id)
        lineages[key] = lineages.get(key, False) or lifecycle == "open"
    return sorted(key for key, open_ in lineages.items() if not open_)


def _review_run_checkouts(repo_root: Path) -> List[Path]:
    root = worktrees.review_root(repo_root)
    if not root.is_dir():
        return []
    return [
        child
        for child in sorted(root.iterdir())
        if child.is_dir() and worktrees.is_review_run_checkout(repo_root, child)
    ]


async def sweep_project(session: AsyncSession, project_id: str) -> Dict[str, int]:
    """One project's pass. Returns how many thread and review checkouts were removed."""
    removed = {"threads": 0, "reviews": 0}
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError:
        return removed
    repo_root = workspace.root
    if not await blocking.run(worktrees.is_git_repo, repo_root):
        return removed
    project = await session.get(Project, project_id)
    main_branch: Optional[str] = project.main_branch if project is not None else None

    for agent, thread in await archived_threads(session, project_id):
        try:
            result = await blocking.run_serialized(
                worktrees.release_thread_worktree, repo_root, agent, thread, main_branch
            )
        except (ValueError, worktrees.GitCommandError, OSError):
            logger.warning("Could not release thread %s of %s", thread, agent, exc_info=True)
            continue
        if result.removed:
            removed["threads"] += 1
        elif result.kept_reason:
            logger.info("Kept %s's thread worktree %s: %s", agent, thread, result.kept_reason)

    leftovers = await blocking.run(_review_run_checkouts, repo_root)
    if leftovers:
        running: Set[str] = set(
            (
                await session.execute(
                    select(Run.id).where(Run.project_id == project_id, Run.status == "running")
                )
            ).scalars()
        )
        for path in leftovers:
            if path.name.partition(".")[2] in running:
                continue
            try:
                if await blocking.run_serialized(
                    worktrees.release_review_run_checkout, repo_root, path
                ):
                    removed["reviews"] += 1
            except (worktrees.GitCommandError, OSError):
                logger.warning("Could not remove the review checkout %s", path, exc_info=True)
    return removed


async def sweep() -> Dict[str, Dict[str, int]]:
    """Every project's pass. A project whose pass fails is logged and skipped."""
    async with async_session_factory() as session:
        project_ids = list((await session.execute(select(Project.id))).scalars())
    results: Dict[str, Dict[str, int]] = {}
    for project_id in project_ids:
        try:
            async with async_session_factory() as session:
                results[project_id] = await sweep_project(session, project_id)
        except Exception:  # noqa: BLE001 -- one project's failure must not stop the others
            logger.warning("Thread cleanup failed for %s", project_id, exc_info=True)
    return results
