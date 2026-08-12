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
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_workspace, spec_documents
from ...auth import get_project
from ...db.engine import get_session
from ...spec_manifest import SpecPathError

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
