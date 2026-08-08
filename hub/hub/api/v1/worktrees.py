"""Project-scoped workspace-isolation read endpoints.

Read-only views over `worktrees.py`'s git state (task 5, design.md Decision 7): which
writing agents currently have an isolated checkout, and whether any of their branches
would conflict if combined — the "interface identifies which agents diverged" half of
hub-native-runtime's "Divergent changes surface as a conflict" scenario.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, worktrees
from ...auth import get_project
from ...db.engine import get_session
from ...launchability import get_agent_config

router = APIRouter(prefix="/worktrees", tags=["worktrees"])


class WorktreeInfo(BaseModel):
    agent: str
    branch: str
    path: str


class AgentWorkspaceInfo(BaseModel):
    """Where one agent works on disk, without provisioning anything to find out."""

    agent: str
    repo_root: str
    working_dir: str
    isolated: bool
    branch: Optional[str] = None
    provisioned: bool = False
    unavailable_reason: Optional[str] = None


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


# Declared after `/conflicts`, which would otherwise be claimed by this route's path parameter.
@router.get("/{agent}", response_model=AgentWorkspaceInfo)
async def get_agent_workspace(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> AgentWorkspaceInfo:
    """Where *agent* works, and whether its isolated checkout exists yet.

    Deliberately does not call `ensure_worktree`: opening an agent's configuration must not
    provision anything. `worktree_path` and `branch_name` are pure, so the answer for an agent
    that has never run is "here is where it will work", which is the useful thing to say — an
    empty panel until the first turn would read as a page that failed to load.
    """
    project_id, _ = project
    try:
        worktrees.validate_agent_name(agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo_root = await _resolve_repo_root(project_id, session)
    config = await get_agent_config(project_id, agent, session)
    isolated = worktrees.is_writing_agent(config)

    if not isolated:
        # A read-only agent shares the primary checkout by design — there is no branch to name
        # and nothing to provision, so saying "not provisioned" would imply something is missing.
        return AgentWorkspaceInfo(
            agent=agent,
            repo_root=str(repo_root),
            working_dir=str(repo_root),
            isolated=False,
            provisioned=True,
        )

    if not worktrees.is_git_repo(repo_root):
        # The same condition `resolve_agent_workspace` fails a spawn on. Reported here so the
        # operator reads it before a turn refuses, rather than as a run failure afterwards.
        return AgentWorkspaceInfo(
            agent=agent,
            repo_root=str(repo_root),
            working_dir=str(repo_root),
            isolated=True,
            unavailable_reason=(
                f"{repo_root} is not a git repository, so this agent cannot be given an "
                "isolated checkout. Its turns will be refused until it is one."
            ),
        )

    path = worktrees.worktree_path(repo_root, agent)
    return AgentWorkspaceInfo(
        agent=agent,
        repo_root=str(repo_root),
        working_dir=str(path),
        isolated=True,
        branch=worktrees.branch_name(agent),
        provisioned=path.exists(),
    )
