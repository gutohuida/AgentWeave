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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, worktrees
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Task
from ...launchability import get_agent_config
from ...task_transition_service import TERMINAL_STATUSES
from ...task_workspace import TASK_SCHEME

router = APIRouter(prefix="/worktrees", tags=["worktrees"])


class WorkspaceInfo(BaseModel):
    """One provisioned checkout, and what it belongs to (task 6.3).

    `kind` and `name` rather than `agent`, for the reason `ConflictInfo` gives below: since
    per-task isolation a checkout can belong to a task, and `name` alone puts two namespaces
    in one field with nothing to tell them apart. A task id is not an oddly-named agent.
    """

    kind: str
    name: str
    branch: str
    path: str


class TaskCheckoutInfo(BaseModel):
    """One of an agent's live tasks, and where that task's work happens (task 6.4).

    `grandfathered` is the distinction the operator cannot otherwise draw. A task whose work
    began before per-task isolation keeps running in the agent's own checkout (design D4), so
    it has no directory of its own — and an operator looking for one and finding nothing would
    reasonably conclude the work was lost.
    """

    task_id: str
    title: Optional[str] = None
    status: str
    branch: str
    path: str
    provisioned: bool
    grandfathered: bool


class AgentWorkspaceInfo(BaseModel):
    """Where one agent works on disk, without provisioning anything to find out."""

    agent: str
    repo_root: str
    working_dir: str
    isolated: bool
    branch: Optional[str] = None
    provisioned: bool = False
    unavailable_reason: Optional[str] = None
    # An agent working three tasks has three checkouts and this endpoint used to name one of
    # them, so the operator was shown a place two thirds of the work is not (task 6.4).
    task_checkouts: List[TaskCheckoutInfo] = []


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


@router.get("", response_model=List[WorkspaceInfo])
async def list_worktrees(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> List[WorkspaceInfo]:
    """List every Hub-owned checkout currently provisioned under this project's repo root —
    task checkouts as well as agent checkouts, each saying which it is (task 6.3).

    Reads git's own registration through `list_workspace_branches` rather than composing an
    answer from the pure path functions, so a checkout registered somewhere unexpected is
    absent instead of being reported at the location it does not occupy.

    **Provisions nothing**, the same promise `get_agent_workspace` makes below and for the same
    reason — stated here rather than merely kept, because this endpoint now has a second
    namespace to be tempted into materializing, and a listing that created what it reports would
    make opening a panel a write.
    """
    project_id, _ = project
    repo_root = await _resolve_repo_root(project_id, session)
    if not worktrees.is_git_repo(repo_root):
        return []
    return [
        WorkspaceInfo(
            kind=workspace.kind,
            name=workspace.name,
            branch=workspace.branch,
            path=str(workspace.path),
        )
        for workspace in sorted(
            worktrees.list_workspace_branches(repo_root), key=lambda w: (w.kind, w.name)
        )
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


async def _task_checkouts(
    session: AsyncSession, project_id: str, agent: str, repo_root
) -> List[TaskCheckoutInfo]:
    """The checkouts of the tasks *agent* is currently holding (task 6.4).

    **Live tasks only.** A terminal task's checkout has been released (design D5), so listing it
    would name a directory that is deliberately gone and read as something missing.

    Pure path functions throughout — `task_worktree_path` and `task_branch_name` compute, they do
    not create — so this keeps the endpoint's promise that opening a settings panel provisions
    nothing. `provisioned` is the honest answer for a task whose first turn has not run yet.
    """
    rows = (
        (
            await session.execute(
                select(Task)
                .where(
                    Task.project_id == project_id,
                    Task.assignee == agent,
                    Task.status.notin_(TERMINAL_STATUSES),
                )
                .order_by(Task.id)
            )
        )
        .scalars()
        .all()
    )

    checkouts: List[TaskCheckoutInfo] = []
    for task in rows:
        grandfathered = task.workspace_scheme != TASK_SCHEME
        if grandfathered:
            # No directory of its own: this task's turns run in the agent's own checkout, and
            # saying so is the whole point of the flag. Naming the agent's path here rather than
            # leaving it blank means the operator can still find the work.
            path = worktrees.worktree_path(repo_root, agent)
            branch = worktrees.branch_name(agent)
        else:
            try:
                path = worktrees.task_worktree_path(repo_root, task.id)
                branch = worktrees.task_branch_name(task.id)
            except ValueError:
                # An id this module would refuse to provision a checkout for cannot have one.
                # Skipped rather than reported with a path nothing occupies.
                continue
        checkouts.append(
            TaskCheckoutInfo(
                task_id=task.id,
                title=task.title,
                status=task.status,
                branch=branch,
                path=str(path),
                provisioned=path.exists(),
                grandfathered=grandfathered,
            )
        )
    return checkouts


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
    # Task checkouts are listed only here, and that mirrors `takes_task_workspace` rather than
    # restating it: the two returns above are exactly the cases where no turn gets a task
    # workspace — a read-only agent, and a project that is not a repository — so listing task
    # checkouts there would name directories that will never exist.
    return AgentWorkspaceInfo(
        agent=agent,
        repo_root=str(repo_root),
        working_dir=str(path),
        isolated=True,
        branch=worktrees.branch_name(agent),
        provisioned=path.exists(),
        task_checkouts=await _task_checkouts(session, project_id, agent, repo_root),
    )
