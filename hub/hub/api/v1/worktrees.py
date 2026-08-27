"""Project-scoped workspace-isolation read endpoints.

Read-only views over `worktrees.py`'s git state (task 5, design.md Decision 7): which
writing agents currently have an isolated checkout, and whether any Hub-owned branch
would conflict with another if combined — the "interface identifies which agents diverged"
half of hub-native-runtime's "Divergent changes surface as a conflict" scenario.

Since per-task isolation the conflict half no longer identifies *agents*: a branch can belong
to a task, and two of one agent's tasks can diverge from each other. It names workspaces, and
`ConflictInfo` says why.
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


class ConflictWorkspaceInfo(BaseModel):
    """One side of a conflict: which checkout it is, and what that checkout belongs to."""

    kind: str
    name: str
    branch: str


class ConflictInfo(BaseModel):
    """`workspaces`, not `agents` (task 6.2).

    A conflict is between two branches, and since per-task isolation a branch can belong to a
    task rather than to an agent — including two tasks held by the *same* agent, which a pair of
    agent names could only have reported as that agent conflicting with itself.
    """

    workspaces: Tuple[ConflictWorkspaceInfo, ConflictWorkspaceInfo]
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
    """Pairwise-check every provisioned Hub-owned branch against every other's with
    `git merge-tree` and report which workspaces diverge, and on which files. Task checkouts
    are included alongside agent checkouts.
    """
    project_id, _ = project
    repo_root = await _resolve_repo_root(project_id, session)
    if not worktrees.is_git_repo(repo_root):
        return []
    return [
        ConflictInfo(
            workspaces=(
                _conflict_workspace(report.workspaces[0]),
                _conflict_workspace(report.workspaces[1]),
            ),
            paths=report.paths,
        )
        for report in worktrees.detect_conflicts(repo_root)
    ]


def _conflict_workspace(workspace: worktrees.WorkspaceBranch) -> ConflictWorkspaceInfo:
    return ConflictWorkspaceInfo(kind=workspace.kind, name=workspace.name, branch=workspace.branch)


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
        # This agent shares the project directory, like a read-only one — but for a different
        # reason, and the difference is the only thing that tells the operator `git init` would
        # change it. So `isolated` is False (it will not get a branch, and reporting True would
        # promise one) and `provisioned` is True (nothing is missing), with the reason carrying
        # the distinction. Not a failure: the turn runs.
        return AgentWorkspaceInfo(
            agent=agent,
            repo_root=str(repo_root),
            working_dir=str(repo_root),
            isolated=False,
            provisioned=True,
            unavailable_reason=(
                f"{repo_root} is not a git repository, so there is no isolated checkout to "
                "give this agent. It works in the project directory, sharing it with any "
                "other agent here."
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
