"""Vault endpoints -- the project's knowledge vault, as the operator fills and reads it.

`a-vault-the-operator-fills-with-text-and-agents-can-read`: the two settings, uploading a text
source, the map, and reading one entry. The records are files (`hub/hub/vault.py`); agents read the
same map and entries through `agent_actions.py`, and nothing an agent can call writes here.

`the-manager-distils-vault-sources-into-cited-facts`: an upload is distilled into facts after it
is answered, when the job is on, and the distil route runs that again for one source.

`images-and-pdfs-are-vault-sources-too`: a PDF or image is uploaded as a raw body (`/files`) and
its bytes are served back (`/sources/{id}/file`).

`sources-that-disagree-are-pointed-out`: an upload may say when it was said (`dated`), the
contradictions the distillation's check recorded are listed, and the operator resolves one.

`a-working-agent-tells-the-manager-an-entry-is-wrong`: the reports agents filed (through
`agent_actions.py`, the one agent route that writes to the vault) are listed, and the operator
closes one the manager referred.

`a-requirement-is-checked-against-what-the-vault-recorded`: a spec document's warnings from the
vault (`vault_spec_check.py`), and checking a document again now.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import distillation, project_workspace, spec_lifecycle, vault, vault_spec_check
from ...auth import get_project
from ...db.engine import get_session
from ...spec_manifest import SpecPathError, validate_spec_path

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
    # YYYY-MM-DD, checked by the vault so a wrong format answers 400 with the reason.
    dated: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


class Resolution(BaseModel):
    stands: Optional[str] = Field(max_length=64)  # required; null means neither fact stands
    note: str = Field(max_length=4000)

    model_config = {"extra": "forbid"}


class ReportClose(BaseModel):
    note: str = Field(max_length=4000)

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
    background: BackgroundTasks,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project_id = project[0]
    root, private = await roots(session, project_id)
    visibility = body.visibility
    if visibility is None:
        visibility = (await vault.get_settings(session, project_id))["default_visibility"]
    try:
        entry = await asyncio.to_thread(
            vault.add_source,
            root,
            private,
            name=body.name,
            type=body.type,
            content=body.content,
            visibility=visibility,
            dated=body.dated,
        )
    except vault.VaultError as exc:
        raise _refused(exc) from exc
    # After the answer is sent; a no-op when the job is off, has no runner, or the source is a
    # decision.
    background.add_task(
        distillation.distil_in_background,
        project_id,
        entry["id"],
        trigger=distillation.UPLOADED,
    )
    return entry


@router.post("/files", status_code=status.HTTP_201_CREATED)
async def upload_vault_file(
    request: Request,
    background: BackgroundTasks,
    name: str = Query(default=""),
    type: str = Query(default=""),  # noqa: A002 -- the field's own name
    visibility: Optional[str] = Query(default=None),
    dated: Optional[str] = Query(default=None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Store a PDF or an image sent as the raw request body, its fields in the query. 415 for
    another Content-Type, 400 for bytes that are not that type or fields a text upload would
    refuse, 413 above 10 MiB (the size cap is lifted for this route alone, in `main.py`)."""
    project_id = project[0]
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type not in vault.FILE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"A file source is one of {', '.join(vault.FILE_TYPES)}, not {media_type!r}.",
        )
    data = await request.body()
    root, private = await roots(session, project_id)
    if visibility is None:
        visibility = (await vault.get_settings(session, project_id))["default_visibility"]
    try:
        entry = await asyncio.to_thread(
            vault.add_file,
            root,
            private,
            name=name,
            type=type,
            media_type=media_type,
            data=data,
            visibility=visibility,
            dated=dated,
        )
    except vault.VaultError as exc:
        raise _refused(exc) from exc
    background.add_task(
        distillation.distil_in_background,
        project_id,
        entry["id"],
        trigger=distillation.UPLOADED,
    )
    return entry


@router.get("/sources/{source_id}/file")
async def get_vault_file(
    source_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """A file source's bytes with their media type: 404 for an unknown id, a text source or a file
    that is gone, 409 naming the holder when the file is on another machine."""
    root, private = await roots(session, project[0])
    found = await asyncio.to_thread(vault.file_of, root, private, source_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No file '{source_id}'")
    media_type, data, elsewhere = found
    if elsewhere is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This file is private and held on {elsewhere}, not on this machine.",
        )
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No file '{source_id}'")
    return Response(content=data, media_type=media_type)


@router.post("/sources/{source_id}/distil", status_code=status.HTTP_202_ACCEPTED)
async def distil_vault_source(
    source_id: str,
    background: BackgroundTasks,
    project: Tuple[str, str] = Depends(get_project),
) -> dict:
    """Distil one source again, in the background: 404 for an unknown source, 409 naming what to
    do when the job is off, has no runner, or the source's text is on another machine."""
    try:
        plan = await distillation.prepare(project[0], source_id)
    except distillation.CannotDistilError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc
    background.add_task(_distil_quietly, plan)
    return {"source": source_id, "queued": True}


async def _distil_quietly(plan: distillation.Plan) -> None:
    try:
        await distillation.distil(plan, trigger=distillation.REQUESTED)
    except Exception:  # noqa: BLE001 -- the answer has been sent; nothing can raise into it
        distillation.logger.warning("vault distillation failed", exc_info=True)


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


@router.get("/contradictions")
async def get_vault_contradictions(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    root, private = await roots(session, project[0])
    return {"contradictions": await asyncio.to_thread(vault.list_contradictions, root, private)}


@router.post("/contradictions/{contradiction_id}/resolve")
async def resolve_vault_contradiction(
    contradiction_id: str,
    body: Resolution,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The operator's decision: 404 for an unknown contradiction, 409 for one already resolved,
    400 for a fact that is not one of its two or an empty note."""
    root, private = await roots(session, project[0])
    try:
        return await asyncio.to_thread(
            vault.resolve_contradiction,
            root,
            private,
            contradiction_id,
            stands=body.stands,
            note=body.note,
        )
    except vault.VaultError as exc:
        raise _refused(exc) from exc


@router.get("/reports")
async def get_vault_reports(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Every report on this machine, pending and referred first, then newest first."""
    root, private = await roots(session, project[0])
    return {"reports": await asyncio.to_thread(vault.list_reports, root, private)}


@router.post("/reports/{report_id}/close")
async def close_vault_report(
    report_id: str,
    body: ReportClose,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The operator closes a referred report: 404 for an unknown report, 409 for one that is not
    referred, 400 for an empty note."""
    root, private = await roots(session, project[0])
    try:
        return await asyncio.to_thread(vault.close_report, root, private, report_id, body.note)
    except vault.VaultError as exc:
        raise _refused(exc) from exc


@router.get("/warnings")
async def get_vault_warnings(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """A spec document's warnings from the vault: its cited facts' first, then the conflicts of
    its newest spec-vault-check firing. 404 for an unknown document."""
    project_id = project[0]
    try:
        safe = validate_spec_path(path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if await spec_lifecycle.get_document(session, project_id, safe) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    workspace = await project_workspace.resolve_project_workspace(session, project_id)
    return {"warnings": await vault_spec_check.warnings_for(session, workspace, project_id, safe)}


@router.post("/warnings/check", status_code=status.HTTP_202_ACCEPTED)
async def check_vault_warnings(
    background: BackgroundTasks,
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
) -> dict:
    """Check a document against the vault again, in the background: 404 for an unknown document,
    409 naming what to do while the job is off or has no runner."""
    try:
        plan = await vault_spec_check.prepare(project[0], path)
    except vault_spec_check.CannotCheckError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc
    background.add_task(_check_quietly, plan)
    return {"document": plan.path, "queued": True}


async def _check_quietly(plan: vault_spec_check.Plan) -> None:
    try:
        await vault_spec_check.check(plan, trigger=vault_spec_check.REQUESTED)
    except Exception:  # noqa: BLE001 -- the answer has been sent; nothing can raise into it
        vault_spec_check.logger.warning("spec vault check failed", exc_info=True)
