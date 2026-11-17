"""GET/PUT /api/v1/hub-settings -- the Hub's own settings, not a project's.

`landing-time-and-test-flakiness-are-measured`, FR-10: how many check runs the Hub runs at once,
held in `hub_settings` so it survives a restart, and applied to the runs that take a slot after the
change without one (`project_checks.set_check_concurrency`). Instance-wide and operator-only: an
agent's credential is refused by `get_operator`. `check_concurrency` null puts back the default.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import project_checks
from ...auth import get_operator
from ...db.engine import get_session
from ...db.models import HubSettings, OperatorCredential

router = APIRouter(prefix="/hub-settings", tags=["hub-settings"])


class HubSettingsView(BaseModel):
    #: What the operator set, or null for the default.
    check_concurrency: Optional[int]
    #: The limit in force now: the setting, else the default.
    check_concurrency_in_force: int
    check_concurrency_default: int


class HubSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_concurrency: Optional[int] = Field(
        default=None, ge=1, le=project_checks.MAX_CHECK_CONCURRENCY
    )


def _view(row: Optional[HubSettings]) -> HubSettingsView:
    return HubSettingsView(
        check_concurrency=row.check_concurrency if row is not None else None,
        check_concurrency_in_force=project_checks.check_concurrency(),
        check_concurrency_default=project_checks.DEFAULT_CHECK_CONCURRENCY,
    )


@router.get("", response_model=HubSettingsView)
async def get_hub_settings(
    operator: OperatorCredential = Depends(get_operator),
    session: AsyncSession = Depends(get_session),
):
    del operator
    return _view(await session.get(HubSettings, 1))


@router.put("", response_model=HubSettingsView)
async def put_hub_settings(
    body: HubSettingsUpdate,
    operator: OperatorCredential = Depends(get_operator),
    session: AsyncSession = Depends(get_session),
):
    del operator
    row = await session.get(HubSettings, 1)
    if row is None:
        row = HubSettings(id=1)
        session.add(row)
    row.check_concurrency = body.check_concurrency
    await session.commit()
    project_checks.set_check_concurrency(body.check_concurrency)
    return _view(row)
