"""The project view: where the project's work went, by spec, agent, model and level."""

from datetime import datetime
from typing import Optional, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ... import work_tally
from ...auth import get_project
from ...db.engine import get_session

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def get_stats(
    since: Optional[datetime] = None,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """`work_tally.tally` for the project, from `since` on (a date-time; omitted: from the start).
    Read-only; every figure is derived from records the Hub already keeps."""
    project_id, _ = project
    return await work_tally.tally(session, project_id, since=since)
