"""Project-scoped workspace-isolation read endpoints.

Read-only views over `worktrees.py`'s git state (task 5, design.md Decision 7): which
writing agents currently have an isolated checkout, and whether any of their branches
would conflict if combined — the "interface identifies which agents diverged" half of
hub-native-runtime's "Divergent changes surface as a conflict" scenario.
"""

from __future__ import annotations

from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, worktrees
from ...auth import get_project
from ...db.engine import get_session

router = APIRouter(prefix="/worktrees", tags=["worktrees"])


class WorktreeInfo(BaseModel):
    agent: str
    branch: str
    path: str


class ConflictInfo(BaseModel):
    agents: Tuple[str, str]
    paths: List[str]


async def _resolve_repo_root(project_id: str, session: AsyncSession):
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return workspace.root


@router.get("", response_model=List[WorktreeInfo])
async def list_worktrees(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> List[WorktreeInfo]:
    """List every agent branch currently provisioned under this project's repo root."""
    project_id, _ = project
    repo_root = await _resolve_repo_root(project_id, session)
    if not worktrees.is_git_repo(repo_root):
        return []
    return [
        WorktreeInfo(
            agent=agent,
            branch=worktrees.branch_name(agent),
            path=str(worktrees.worktree_path(repo_root, agent)),
        )
        for agent in sorted(worktrees.list_agent_branches(repo_root))
    ]


@router.get("/conflicts", response_model=List[ConflictInfo])
async def get_worktree_conflicts(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> List[ConflictInfo]:
    """Pairwise-check every provisioned agent branch against every other's with
    `git merge-tree` and report which agents diverge, and on which files.
    """
    project_id, _ = project
    repo_root = await _resolve_repo_root(project_id, session)
    if not worktrees.is_git_repo(repo_root):
        return []
    return [
        ConflictInfo(agents=report.agents, paths=report.paths)
        for report in worktrees.detect_conflicts(repo_root)
    ]
