"""Project-scoped token accounting and autonomous budget configuration."""

from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Project
from ...usage_accounting import accounting_snapshot, budget_state

router = APIRouter(prefix="/accounting", tags=["accounting"])


class BudgetUpdate(BaseModel):
    token_budget: Optional[int]


@router.get("")
async def get_accounting(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await accounting_snapshot(session, project_id)


@router.patch("/budget")
async def update_budget(
    body: BudgetUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    if body.token_budget is not None and body.token_budget <= 0:
        raise HTTPException(status_code=422, detail="token_budget must be positive or null")
    project_row = await session.get(Project, project_id)
    if project_row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project_row.token_budget = body.token_budget
    await session.commit()
    snapshot = await accounting_snapshot(session, project_id, recent_limit=0)
    return budget_state(body.token_budget, snapshot["project"]["total_tokens"])
