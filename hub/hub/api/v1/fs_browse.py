"""GET /api/v1/fs/list — directory browsing for the project dialog's path picker.

Not project-scoped: it backs choosing a project directory *before* a project exists, so
project-scoped auth (`get_project`) is the wrong dependency here. Requires operator
authentication like every other Hub endpoint (`local-project-workspace` spec: "Directory
listing is authenticated and bounded").
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...auth import get_operator
from ...db.models import OperatorCredential
from ...fs_browse import DirectoryBrowseError, list_directory
from ...schemas.fs_browse import DirectoryEntryResponse, DirectoryListingResponse

router = APIRouter(prefix="/fs", tags=["fs"])


@router.get("/list", response_model=DirectoryListingResponse)
async def list_fs_directory(
    path: str = Query(..., min_length=1, max_length=4096),
    operator: OperatorCredential = Depends(get_operator),
):
    del operator
    try:
        listing = list_directory(path)
    except DirectoryBrowseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return DirectoryListingResponse(
        path=listing.path,
        parent=listing.parent,
        entries=[DirectoryEntryResponse(name=e.name, path=e.path) for e in listing.entries],
        reason=listing.reason,
    )
