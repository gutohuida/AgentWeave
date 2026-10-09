"""Manager endpoints -- the project's background jobs and what they spawned.

`the-hubs-background-jobs-are-configured-on-a-manager-page`: list the jobs, change one, list the
recent firings. The jobs are `hub/hub/manager.py`'s registry; a job's row holds only the choice.
"""

from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import manager
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Runner

router = APIRouter(prefix="/manager", tags=["manager"])


class JobUpdate(BaseModel):
    enabled: Optional[bool] = None
    runner_id: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=256)

    model_config = {"extra": "forbid"}


@router.get("/jobs")
async def list_manager_jobs(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return {"jobs": await manager.list_jobs(session, project[0])}


@router.patch("/jobs/{key}")
async def update_manager_job(
    key: str,
    body: JobUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project_id = project[0]
    if manager.job_spec(key) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No job '{key}'")
    # Omitted means unchanged and null means cleared, as on the settings route.
    fields = body.model_dump(exclude_unset=True)
    if fields.get("enabled") is None:
        fields.pop("enabled", None)
    runner_id = fields.get("runner_id")
    if runner_id:
        runner = await session.get(Runner, runner_id)
        if runner is None or runner.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown runner '{runner_id}': no runner by that id belongs to this project",
            )
    await manager.set_job(session, project_id, key, **fields)
    await session.commit()
    return await manager.get_job(session, project_id, key)


@router.get("/activity")
async def list_manager_activity(
    job: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return {"firings": await manager.list_firings(session, project[0], job=job, limit=limit)}
