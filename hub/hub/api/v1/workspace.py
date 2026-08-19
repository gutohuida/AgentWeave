"""Project-scoped workspace path listing.

Feeds the composer's `@path` trigger — see
openspec/changes/composer-intelligence/specs/agent-composer/spec.md's "Workspace path listing
endpoint" requirement.
"""

from __future__ import annotations

from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace
from ...auth import get_project
from ...config import settings
from ...db.engine import get_session
from ...schemas.workspace import WorkspaceFileResponse
from ...workspace_file import (
    WorkspaceFileNotFoundError,
    WorkspaceFileTooLargeError,
    read_workspace_file,
)
from ...workspace_paths import list_workspace_paths

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/paths", response_model=List[str])
async def get_workspace_paths(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> List[str]:
    """List every git-tracked-or-untracked-but-not-ignored path under this project's
    registered working directory.
    """
    project_id, _ = project
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return list_workspace_paths(workspace.root)


@router.get("/file", response_model=WorkspaceFileResponse)
async def get_workspace_file(
    path: str = Query(..., min_length=1, max_length=4096),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceFileResponse:
    """Read one file's content, allowlisted by membership of `/workspace/paths`'s
    own listing (design D7) — never a second, independently reasoned traversal check.
    """
    project_id, _ = project
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        result = read_workspace_file(workspace, path, max_size=settings.aw_max_body_size)
    except WorkspaceFileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"path not found in this workspace: {path}"
        ) from exc
    except WorkspaceFileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    return WorkspaceFileResponse(
        path=result.path, binary=result.binary, size=result.size, content=result.content
    )
