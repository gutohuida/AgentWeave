"""Project-scoped workspace path listing.

Feeds the composer's `@path` trigger — see
openspec/changes/composer-intelligence/specs/agent-composer/spec.md's "Workspace path listing
endpoint" requirement.
"""

from __future__ import annotations

from typing import List, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace
from ...auth import get_project
from ...db.engine import get_session
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
