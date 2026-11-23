"""The project's Overview in one read (`overview-at-a-glance-with-dashboard-and-briefing-tabs`, D1).

Read-only: refetching it never moves the visit record (D2)."""

from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from ... import overview as overview_module
from ... import project_workspace
from ...auth import get_project
from ...db.engine import get_session

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
async def get_overview(
    day_start: Optional[str] = Query(None, max_length=64),
    days: int = Query(7, ge=1, le=overview_module.MAX_DAYS),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Everything both Overview tabs show. `day_start` is the operator's local midnight today,
    ISO with its offset (D6); without it, midnight UTC. 422 `bad_day_start` when it is not a time.
    """
    project_id, _ = project
    now = datetime.now(timezone.utc)
    try:
        start = overview_module.parse_day_start(day_start, now)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "bad_day_start", "message": f"day_start is not a time: {exc}"},
        ) from exc
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError:
        # An unavailable workspace is reported elsewhere; the read loses the next-slice offers
        # and the builds' roadmap links rather than turning into an error.
        workspace = None
    return await overview_module.overview(
        session, project_id, day_start=start, days=days, workspace=workspace, now=now
    )
