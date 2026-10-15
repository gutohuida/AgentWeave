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
from ...model_catalog import get_provider, undeclared_model_reason

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
    # The model is judged when it is set, against the runner the job will use, as `POST /runners`
    # judges one; the firing used to be the first to refuse it (F630).
    model = fields.get("model")
    if model is not None:
        row = await manager.get_job_row(session, project_id, key)
        chosen = runner_id if "runner_id" in fields else (row.runner_id if row else None)
        runner = await session.get(Runner, chosen) if chosen else None
        if runner is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Choose the job's runner first: a model is one its runner's CLI declares, "
                    "and this job has no runner."
                ),
            )
        if model != (row.model if row else None):
            provider = get_provider(runner.cli)
            if provider is None or provider.model(model) is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=undeclared_model_reason(runner.cli, model),
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
