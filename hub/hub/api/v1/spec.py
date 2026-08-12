"""Project specification documents, read from the project working directory.

The Hub reads a registered project's files directly through ``ProjectWorkspace``,
so a document's only copy is the file on disk. There is nothing to push and
nothing to reconcile: the cache these endpoints used to serve
(``project_specs``) and the multi-source snapshot that reconciled it
(``project_spec_snapshots``) were both built for a Hub that could not see the
filesystem, and both are gone.

The Hub remains the security boundary. It resolves every path through the
project workspace — which refuses absolute paths, traversal, control characters
and symlink escapes — and re-validates it against the repo-relative spec path
contract, rather than trusting a caller's classification.
"""

from __future__ import annotations

from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, spec_documents, spec_lifecycle, spec_service
from ...auth import get_project
from ...db.engine import get_session
from ...spec_manifest import SpecPathError, validate_spec_path
from ...spec_payload import SCHEMA_VERSION
from ...sse import sse_manager

router = APIRouter(prefix="/project", tags=["spec"])


async def _workspace(session: AsyncSession, project_id: str):
    try:
        return await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Project workspace is unavailable: {exc}",
                "code": exc.code,
                "directory_state": exc.directory_state,
            },
        ) from exc


@router.get("/specs")
async def list_specs(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List the project's specification documents with the index's own state.

    An unreadable or absent index never silences the documents around it — the
    tree is what discovery found, and the index's condition is reported
    alongside it rather than in place of it.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    state = spec_documents.compute_state(workspace)
    return {
        "specs": state.specs,
        "home": state.home,
        "manifest": state.index,
        "missing": state.missing,
        "diagnostics": state.diagnostics,
    }


@router.get("/spec")
async def get_spec(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Return one document's content; 404 when there is no such file."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)

    try:
        content = spec_documents.read_document(workspace, path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except project_workspace.ProjectPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"could not read document: {exc}"
        ) from exc

    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="spec not found")

    return {
        "path": path,
        "content": content,
        "updated_at": spec_documents.document_updated_at(workspace, path),
    }


class DocumentCreate(BaseModel):
    """Starting an exploration.

    Only what identifies the document. Explore is the one phase that would
    otherwise precede its own document, and asking for requirements up front is
    exactly the structure the operator has not worked out yet.
    """

    path: str = Field(max_length=255)
    title: str = Field(default="", max_length=512)
    kind: str = Field(default="change-spec", max_length=32)

    model_config = {"extra": "forbid"}


class PhaseRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)

    model_config = {"extra": "forbid"}


def _document_view(document) -> dict:
    return {
        "id": document.id,
        "path": document.path,
        "title": document.title,
        "kind": document.kind,
        "phase": document.phase,
        "explore_closed": document.explore_closed_at is not None,
        "updated_at": document.updated_at.isoformat(),
    }


def _operator() -> spec_lifecycle.Actor:
    """The operator, established by the project credential this route already required.

    Named rather than taken from a request body — an actor a caller can state is
    an actor a caller can invent.
    """
    return spec_lifecycle.Actor(kind="operator", name="operator")


async def _require_document(session: AsyncSession, project_id: str, path: str):
    try:
        safe = validate_spec_path(path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    document = await spec_lifecycle.get_document(session, project_id, safe)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return document


@router.get("/documents")
async def list_documents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Every document this project tracks, with the phase it is in."""
    project_id, _ = project
    documents = await spec_lifecycle.list_documents(session, project_id)
    return {"documents": [_document_view(document) for document in documents]}


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Start an exploration: an empty document, in `exploring`, that later phases refer to."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)

    try:
        path = validate_spec_path(body.path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        document = await spec_lifecycle.create_document(
            session, project_id, path, actor=_operator(), title=body.title, kind=body.kind
        )
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": document.kind,
        "title": body.title or path.rsplit("/", 1)[-1].removesuffix(".html"),
    }
    result = await spec_service.save_document(
        session, workspace, document, payload, actor=_operator()
    )
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": path, "phase": document.phase})
    return {**_document_view(document), "blocking": result.blocking}


@router.post("/documents/close-exploration")
async def close_exploration(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator declaring exploration finished.

    Whether an exploration is complete enough to propose from is a judgement,
    not a computation. Making it an operator action keeps every model out of the
    path of a gate.
    """
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    try:
        await spec_lifecycle.close_exploration(session, document, actor=_operator())
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    await session.commit()
    return _document_view(document)


@router.post("/documents/propose")
async def propose_document(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Move a document to `proposed`, or report every check that refuses it."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)

    try:
        blocking = await spec_service.propose(session, workspace, document, actor=_operator())
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    await session.commit()
    if blocking:
        return {**_document_view(document), "blocking": blocking}
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return {**_document_view(document), "blocking": []}


@router.post("/documents/phase")
async def set_phase(
    body: PhaseRequest,
    path: str = Query(...),
    to: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """An operator phase decision — approving a document, or reopening one.

    This route requires the project credential, so an agent run cannot reach it:
    a run's token authenticates against `/agent-actions`, which has no phase
    route at all.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)

    try:
        await spec_lifecycle.transition(
            session, document, to_phase=to, actor=_operator(), reason=body.reason
        )
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    await spec_service.rerender_phase(session, workspace, document)
    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return _document_view(document)
