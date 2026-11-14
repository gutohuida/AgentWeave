"""Project-scoped workspace path listing.

Feeds the composer's `@path` trigger — see
openspec/changes/composer-intelligence/specs/agent-composer/spec.md's "Workspace path listing
endpoint" requirement.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ... import changes_view, project_workspace, worktrees
from ...auth import get_project
from ...config import settings
from ...db.engine import get_session
from ...db.models import Project
from ...schemas.workspace import WorkspaceFileResponse, WorkspaceListing
from ...workspace_file import (
    WorkspaceFileNotFoundError,
    WorkspaceFileTooLargeError,
    read_workspace_file,
)
from ...workspace_paths import list_workspace_paths
from .changes import _load, _resolve_target

router = APIRouter(prefix="/workspace", tags=["workspace"])

Location = Literal["worktree", "root"]


def _registered_checkout(repo_root: Path, branch: str, task) -> Optional[Path]:
    """The checkout of *branch* if git really tracks one, else None. Provisions nothing."""
    if task is not None:
        task_id = task.id if hasattr(task, "id") else task
        try:
            path = worktrees.task_worktree_path(repo_root, task_id)
        except ValueError:
            return None
        if not path.is_dir() or path.is_symlink():
            return None
        try:
            registered = worktrees._registered_worktree_branch(repo_root, path)
        except (worktrees.GitCommandError, OSError):
            return None
        return path if registered == f"refs/heads/{branch}" else None
    agent = branch[len(worktrees.BRANCH_PREFIX) :]
    return worktrees.existing_worktree(repo_root, agent)


async def _checkout_for(session: AsyncSession, project_id: str, conversation_id: str):
    """(repo_root, checkout, branch, message): the checkout the Changes tab shows for this
    conversation, resolved read-only and by the Changes route's own rule."""
    conversation, repo_root, runs = await _load(project_id, conversation_id, session)
    branch, task, state, message = await _resolve_target(
        session, project_id, conversation, repo_root, runs
    )
    if branch is None:
        return repo_root, None, None, message
    checkout = await asyncio.to_thread(_registered_checkout, repo_root, branch, task)
    if checkout is None:
        message = f"{conversation.agent} has no checkout yet: {branch} has not been created."
    return repo_root, checkout, branch, message


def _listing_with_changes(repo_root: Path, checkout: Path, branch: str, base_name: Optional[str]):
    paths = set(list_workspace_paths(checkout))
    base = changes_view.resolve_base(repo_root, base_name)
    changed = {}
    if base:
        for entry in changes_view.branch_files(repo_root, base, branch):
            changed[entry.path] = entry.status
    paths.update(p for p, s in changed.items() if s == "D")
    return sorted(paths), changed


@router.get("/paths", response_model=WorkspaceListing | List[str])
async def get_workspace_paths(
    conversation_id: Optional[str] = Query(None),
    location: Optional[Location] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List every git-tracked-or-untracked-but-not-ignored path under this project's
    registered working directory; with `conversation_id`, under the project root or the
    conversation's agent checkout (`location`, defaulting to the checkout when there is one).
    """
    project_id, _ = project
    if conversation_id is None:
        try:
            workspace = await project_workspace.resolve_project_workspace(session, project_id)
        except project_workspace.ProjectWorkspaceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return list_workspace_paths(workspace.root)

    repo_root, checkout, branch, message = await _checkout_for(session, project_id, conversation_id)
    has_checkout = checkout is not None
    if has_checkout and location != "root":
        project_row = await session.get(Project, project_id)
        main_branch = project_row.main_branch if project_row is not None else None
        try:
            paths, changed = await asyncio.to_thread(
                _listing_with_changes, repo_root, checkout, branch, main_branch
            )
        except worktrees.GitCommandError:
            paths, changed = await asyncio.to_thread(list_workspace_paths, checkout), {}
        return WorkspaceListing(
            location="worktree",
            has_checkout=True,
            branch=branch,
            paths=paths,
            changed=changed,
        )
    paths = await asyncio.to_thread(list_workspace_paths, repo_root)
    return WorkspaceListing(
        location="root",
        state="ok" if has_checkout else "no_checkout",
        message=None if has_checkout else message,
        has_checkout=has_checkout,
        branch=branch,
        paths=paths,
    )


@router.get("/file", response_model=WorkspaceFileResponse)
async def get_workspace_file(
    path: str = Query(..., min_length=1, max_length=4096),
    conversation_id: Optional[str] = Query(None),
    location: Optional[Location] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceFileResponse:
    """Read one file's content, allowlisted by membership of `/workspace/paths`'s
    own listing (design D7) — never a second, independently reasoned traversal check.
    With `location=worktree` the listing is the conversation's agent checkout's.
    """
    project_id, _ = project
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if location == "worktree":
        if conversation_id is None:
            raise HTTPException(status_code=422, detail="location=worktree needs conversation_id")
        _, checkout, _, _ = await _checkout_for(session, project_id, conversation_id)
        if checkout is None:
            raise HTTPException(status_code=404, detail=f"path not found in this workspace: {path}")
        workspace = project_workspace.ProjectWorkspace(
            workspace.project_id, checkout, workspace.path_key
        )
    elif conversation_id is not None:
        await _load(project_id, conversation_id, session)  # another project's: 404

    try:
        result = await asyncio.to_thread(
            read_workspace_file, workspace, path, max_size=settings.aw_max_body_size
        )
    except WorkspaceFileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"path not found in this workspace: {path}"
        ) from exc
    except WorkspaceFileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    return WorkspaceFileResponse(
        path=result.path, binary=result.binary, size=result.size, content=result.content
    )
