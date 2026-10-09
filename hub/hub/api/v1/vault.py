"""Vault endpoints -- the project's knowledge vault, as the operator fills and reads it.

`a-vault-the-operator-fills-with-text-and-agents-can-read`: the two settings, uploading a text
source, the map, and reading one entry. The records are files (`hub/hub/vault.py`); agents read the
same map and entries through `agent_actions.py`, and nothing an agent can call writes here.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, vault
from ...auth import get_project
from ...db.engine import get_session

router = APIRouter(prefix="/vault", tags=["vault"])


class SettingsUpdate(BaseModel):
    private_location: Optional[str] = Field(default=None, max_length=1024)
    default_visibility: Optional[str] = Field(default=None, max_length=16)

    model_config = {"extra": "forbid"}


class SourceUpload(BaseModel):
    name: str = Field(max_length=1000)
    type: str = Field(max_length=64)
    content: str
    visibility: Optional[str] = Field(default=None, max_length=16)

    model_config = {"extra": "forbid"}


async def project_root(session: AsyncSession, project_id: str) -> Path:
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Project workspace is unavailable: {exc}",
                "code": exc.code,
                "directory_state": exc.directory_state,
            },
        ) from exc
    return workspace.root


async def roots(session: AsyncSession, project_id: str) -> Tuple[Path, Path]:
    """The project's directory and its effective private location."""
    root = await project_root(session, project_id)
    settings = await vault.get_settings(session, project_id)
    return root, Path(settings["effective_private_location"])


def _refused(exc: vault.VaultError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


async def read_map(session: AsyncSession, project_id: str) -> Dict[str, Any]:
    root, private = await roots(session, project_id)
    return {"entries": await asyncio.to_thread(vault.build_map, root, private)}


async def read_one(
    session: AsyncSession, project_id: str, entry_id: str, offset: int
) -> Dict[str, Any]:
    root, private = await roots(session, project_id)
    entry = await asyncio.to_thread(vault.read_entry, root, private, entry_id, offset)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No entry '{entry_id}'")
    return entry


@router.get("/settings")
async def get_vault_settings(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await vault.get_settings(session, project[0])


@router.put("/settings")
async def put_vault_settings(
    body: SettingsUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project_id = project[0]
    root = await project_root(session, project_id)
    try:
        listed = await vault.set_settings(
            session, project_id, root, body.model_dump(exclude_unset=True)
        )
    except vault.VaultError as exc:
        await session.rollback()
        raise _refused(exc) from exc
    await session.commit()
    return listed


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def upload_vault_source(
    body: SourceUpload,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project_id = project[0]
    root, private = await roots(session, project_id)
    visibility = body.visibility
    if visibility is None:
        visibility = (await vault.get_settings(session, project_id))["default_visibility"]
    try:
        return await asyncio.to_thread(
            vault.add_source,
            root,
            private,
            name=body.name,
            type=body.type,
            content=body.content,
            visibility=visibility,
        )
    except vault.VaultError as exc:
        raise _refused(exc) from exc


@router.get("/map")
async def get_vault_map(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await read_map(session, project[0])


@router.get("/entries/{entry_id}")
async def get_vault_entry(
    entry_id: str,
    offset: int = Query(default=0, ge=0),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return await read_one(session, project[0], entry_id, offset)
