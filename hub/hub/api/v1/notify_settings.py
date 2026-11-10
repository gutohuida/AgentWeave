"""GET/PUT /api/v1/notify-settings -- which kinds of notice reach Windows.

Change `windows-notifications-for-what-calls-the-operator` (FR-10, D2): the operator's per-kind
choice, held by the Hub so the launcher's watcher can apply it with no window open, and kept in a
file beside the Hub's database so it survives a restart. Instance-wide and operator-only: an agent's
credential is refused by `get_operator`. Separate from the page's in-app switches.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from ... import operator_notices
from ...auth import get_operator
from ...db.models import OperatorCredential

router = APIRouter(prefix="/notify-settings", tags=["notifications"])


class WindowsKinds(BaseModel):
    """One boolean per kind: question (`ask`), failure (`fail`), `done` and `reply`."""

    model_config = ConfigDict(extra="forbid")

    ask: bool
    fail: bool
    done: bool
    reply: bool


@router.get("", response_model=WindowsKinds)
async def get_notify_settings(operator: OperatorCredential = Depends(get_operator)):
    del operator
    return WindowsKinds(**operator_notices.load_windows_kinds())


@router.put("", response_model=WindowsKinds)
async def put_notify_settings(
    body: WindowsKinds, operator: OperatorCredential = Depends(get_operator)
):
    del operator
    return WindowsKinds(**operator_notices.save_windows_kinds(body.model_dump()))
