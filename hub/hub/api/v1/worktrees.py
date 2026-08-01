"""Workspace-isolation read endpoints — GET /api/v1/worktrees, GET /api/v1/worktrees/conflicts

Read-only views over `worktrees.py`'s git state (task 5, design.md Decision 7): which
writing agents currently have an isolated checkout, and whether any of their branches
would conflict if combined — the "interface identifies which agents diverged" half of
hub-native-runtime's "Divergent changes surface as a conflict" scenario.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ... import worktrees
from ...auth import get_project

router = APIRouter(prefix="/worktrees", tags=["worktrees"])


class WorktreeInfo(BaseModel):
    agent: str
    branch: str
    path: str


class ConflictInfo(BaseModel):
    agents: Tuple[str, str]
    paths: List[str]


@router.get("", response_model=List[WorktreeInfo])
async def list_worktrees(project: Tuple[str, str] = Depends(get_project)) -> List[WorktreeInfo]:
    """List every agent branch currently provisioned under this Hub's repo root.

    Project-scoped in name only today — the Hub runs one project per host repo
    (Decision 1), so `repo_root` (`Path.cwd()`) is the same for every request; kept
    behind the same `get_project` auth dependency as every other endpoint regardless.
    """
    repo_root = Path.cwd()
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
) -> List[ConflictInfo]:
    """Pairwise-check every provisioned agent branch against every other's with
    `git merge-tree` and report which agents diverge, and on which files.
    """
    repo_root = Path.cwd()
    if not worktrees.is_git_repo(repo_root):
        return []
    return [
        ConflictInfo(agents=report.agents, paths=report.paths)
        for report in worktrees.detect_conflicts(repo_root)
    ]
