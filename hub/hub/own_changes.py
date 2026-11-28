"""A task's own changes against the main branch, as one digest (`a-task-that-cannot-move-waits-
instead-of-being-rebuilt-and-re-reviewed`, FR-4, D4).

The digest is of `git diff <main>...<task branch>`: the diff from the merge base, so a merge of the
main branch into the task's branch and an empty commit move the tip and leave the digest alone --
which is exactly what a task at 6a2331b was ("master plus merges, adds no work of its own"). Only a
real change to what the task adds changes it.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from . import worktrees
from .db.models import Project, Task

logger = logging.getLogger(__name__)


def digest(root: Path, main_branch: str, task_id: str) -> Optional[str]:
    """The digest of *task_id*'s own changes against *main_branch*, or None where it cannot be
    measured (no branch, no main branch, git failing): an unknown is never a refusal."""
    from .project_checks import _git

    try:
        branch = worktrees.task_branch_name(task_id)
    except ValueError:
        return None
    result = _git(
        root, "diff", "--no-ext-diff", "--no-color", "--binary", f"{main_branch}...{branch}"
    )
    if result.returncode != 0:
        return None
    return hashlib.sha256(result.stdout.encode("utf-8", "replace")).hexdigest()


async def current(
    session: AsyncSession, task: Task, *, snapshot_agent: Optional[str] = None
) -> Optional[str]:
    """The digest now. With *snapshot_agent*, the builder's uncommitted work in the task's checkout
    is committed first, as a turn's end does, so work not yet committed counts as a change."""
    from .project_workspace import ProjectWorkspaceError, resolve_project_workspace

    project = await session.get(Project, task.project_id)
    if project is None or not project.main_branch:
        return None
    try:
        root = (await resolve_project_workspace(session, task.project_id)).root
    except ProjectWorkspaceError:
        return None
    try:
        if snapshot_agent is not None:
            from .project_checks import _snapshot_task_checkout

            await _snapshot_task_checkout(root, task, snapshot_agent)
        return await asyncio.to_thread(digest, root, project.main_branch, task.id)
    except Exception:  # noqa: BLE001 -- an unmeasurable task is not refused
        logger.warning("could not measure the own changes of %s", task.id, exc_info=True)
        return None
