"""GET/POST /api/v1/fs/native-dialog/* — the host's own folder dialog (composer/chrome
refinement §7).

Not project-scoped: like `fs/list`, choosing a project directory precedes a project
existing, so `get_project` (project-scoped auth) is the wrong dependency — `get_operator`,
matching every other operator-scoped endpoint.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from ... import native_dialog
from ...auth import get_operator
from ...db.models import OperatorCredential
from ...schemas.native_dialog import DialogAvailabilityResponse, DialogOpenResponse

router = APIRouter(prefix="/fs/native-dialog", tags=["fs"])


@router.get("/availability", response_model=DialogAvailabilityResponse)
async def get_native_dialog_availability(
    operator: OperatorCredential = Depends(get_operator),
):
    del operator
    result = native_dialog.check_availability()
    return DialogAvailabilityResponse(available=result.available, reason=result.reason)


@router.post("/open", response_model=DialogOpenResponse)
async def open_native_dialog(
    operator: OperatorCredential = Depends(get_operator),
):
    del operator
    try:
        result = await native_dialog.open_folder_dialog()
    except native_dialog.DialogBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return DialogOpenResponse(outcome=result.outcome, path=result.path, detail=result.detail)
