"""Project-scoped token accounting and autonomous budget configuration."""

from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import InboundQueueEntry, Project
from ...schemas.common import RequestModel
from ...sse import sse_manager
from ...usage_accounting import accounting_snapshot, budget_state, conversation_usage
from ...utils import persist_event

router = APIRouter(prefix="/accounting", tags=["accounting"])


class BudgetUpdate(RequestModel):
    token_budget: Optional[int]


@router.get("")
async def get_accounting(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await accounting_snapshot(session, project_id)


@router.get("/conversations/{conversation_id}")
async def get_conversation_accounting(
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await conversation_usage(session, project_id, conversation_id)


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
    event_payload = {"token_budget": body.token_budget}
    await persist_event(session, project_id, "accounting_budget_updated", event_payload)
    await sse_manager.broadcast(project_id, "accounting_budget_updated", event_payload)
    snapshot = await accounting_snapshot(session, project_id, recent_limit=0)
    queued_result = await session.execute(
        select(InboundQueueEntry.agent)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.state == "queued",
        )
        .distinct()
    )
    from ...turn_scheduler import schedule_agent

    for agent in queued_result.scalars().all():
        await schedule_agent(project_id, agent)
    return budget_state(body.token_budget, snapshot["project"]["total_tokens"])
