"""Workspace path listing — GET /api/v1/workspace/paths

Feeds the composer's `@path` trigger — see
openspec/changes/composer-intelligence/specs/agent-composer/spec.md's "Workspace path listing
endpoint" requirement.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from fastapi import APIRouter, Depends

from ...auth import get_project
from ...workspace_paths import list_workspace_paths

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/paths", response_model=List[str])
async def get_workspace_paths(project: Tuple[str, str] = Depends(get_project)) -> List[str]:
    """List every git-tracked-or-untracked-but-not-ignored path under this Hub's working
    directory.

    Project-scoped in name only today, like `GET /api/v1/worktrees` — the Hub runs one
    project per host repo, so `Path.cwd()` is the same for every request regardless.
    """
    return list_workspace_paths(Path.cwd())
