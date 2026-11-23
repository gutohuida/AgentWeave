"""Manager endpoints -- the project's background jobs and what they spawned.

`the-hubs-background-jobs-are-configured-on-a-manager-page`: list the jobs, change one, list the
recent firings. The jobs are `hub/hub/manager.py`'s registry; a job's row holds only the choice.
"""

from typing import List, Literal, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ... import build_retrospective, chapters_job, manager, overview_note_job, pre_mortem, stalls
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Runner
from ...model_catalog import get_provider, undeclared_model_reason

router = APIRouter(prefix="/manager", tags=["manager"])


class JobUpdate(BaseModel):
    enabled: Optional[bool] = None
    runner_id: Optional[str] = Field(default=None, max_length=64)
    model: Optional[str] = Field(default=None, max_length=256)
    # A job with a button: fire on its triggers ("automatic") or only on the button ("button").
    mode: Optional[Literal["automatic", "button"]] = None

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
    mode = fields.pop("mode", None)
    if mode is not None:
        if key not in manager.HAS_BUTTON:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="mode chooses between automatic firing and the button, and only the "
                "chapters, build retrospective, pre-mortem and overview note jobs have a button",
            )
        fields["automatic"] = mode == "automatic"
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
    row = await manager.set_job(session, project_id, key, **fields)
    if key == manager.MENDER and row.enabled:
        # The mender is an agent (`stalls.py`): turning it on makes or updates that agent, and a
        # project agent already named `mender` refuses it rather than being taken over.
        from ... import stalls

        agent, refusal = await stalls.ensure_mender(session, project_id)
        if agent is None:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)
    await session.commit()
    return await manager.get_job(session, project_id, key)


@router.post("/jobs/chapters/run", status_code=status.HTTP_202_ACCEPTED)
async def weave_the_thread(
    background: BackgroundTasks,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """'Weave the thread': the operator asks the chapters job to fire now, whatever its automatic
    choice. Refused (409) while the job is off or has no runner; otherwise the firing runs after
    the answer and is recorded as one `manager_job_fired` event."""
    project_id = project[0]
    try:
        await chapters_job.gate(session, project_id, chapters_job.REQUESTED)
    except chapters_job.CannotWeaveError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc
    background.add_task(
        chapters_job.weave_in_background, project_id, trigger=chapters_job.REQUESTED
    )
    return {"started": True}


@router.post("/jobs/overview-note/run", status_code=status.HTTP_202_ACCEPTED)
async def refresh_the_note(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """'Refresh note' on the Overview's Briefing: the overview-note job writes a note now, whatever
    its automatic choice and whether or not anything changed. Refused (409 `{code, reason}`) while
    the job is off (`disabled`), has no runner (`no_runner`, recorded as a failed firing) or is
    already writing one (`already_running`); the firing runs after the answer."""
    project_id = project[0]
    try:
        await overview_note_job.start(session, project_id, trigger=overview_note_job.BUTTON)
    except overview_note_job.CannotWriteNoteError as exc:
        await overview_note_job.refuse(project_id, exc, trigger=overview_note_job.BUTTON)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": exc.code, "reason": exc.reason},
        ) from exc
    return {"started": True}


@router.post("/jobs/build-retrospective/run", status_code=status.HTTP_202_ACCEPTED)
async def review_this_build(
    path: str = Query(..., min_length=1),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """'Review this build': a retrospective of the document *path* now, on an unfinished build too
    and whatever the job's automatic choice. Refused (409) with no runner or while one of this
    document is in progress; the firing runs after the answer and never holds it."""
    try:
        await build_retrospective.request(session, project[0], path)
    except build_retrospective.CannotReviewError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc
    return {"started": True}


@router.get("/jobs/build-retrospective/retrospectives")
async def list_retrospectives(
    path: str = Query(..., min_length=1),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The document's retrospectives, newest first, the failed firings among them."""
    document = await build_retrospective.find_document(session, project[0], path)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No document '{path}'")
    return {
        "retrospectives": await build_retrospective.list_for_document(
            session, project[0], document.id
        )
    }


class PreMortemRun(BaseModel):
    path: str = Field(..., min_length=1)

    model_config = {"extra": "forbid"}


@router.post("/jobs/pre-mortem/run", status_code=status.HTTP_202_ACCEPTED)
async def run_a_pre_mortem(
    body: PreMortemRun,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """'Run a pre-mortem' on the document *path* now. Refused (409) while the job is off or has no
    runner, the document has no requirements, or one of this document is in progress; 404 for an
    unknown document. The firing runs after the answer and never holds it."""
    try:
        await pre_mortem.request(session, project[0], body.path)
    except pre_mortem.CannotRunError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.reason) from exc
    return {"started": True}


@router.get("/jobs/pre-mortem/pre-mortems")
async def list_pre_mortems(
    path: str = Query(..., min_length=1),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The document's pre-mortems, newest first, the failed firings among them."""
    document = await pre_mortem.find_document(session, project[0], path)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No document '{path}'")
    return {"pre_mortems": await pre_mortem.list_for_document(session, project[0], document.id)}


@router.get("/activity")
async def list_manager_activity(
    job: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return {"firings": await manager.list_firings(session, project[0], job=job, limit=limit)}


# --- runs (`background-manager-work-you-can-see` D1-D3) ------------------------------------------


@router.get("/runs/running")
async def list_running_runs(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """The manager runs in progress, oldest first: this process's registry of job runs, plus the
    mender's running `runs` rows. A Hub restart empties the registry with the work it held."""
    runs = manager.running(project[0]) + await stalls.running_mender_runs(session, project[0])
    runs.sort(key=lambda run: str(run.get("started_at") or ""))
    return {"runs": runs}


@router.get("/runs/unseen-failures")
async def list_unseen_failures(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Each item's newest run when it failed and the operator has not seen it, nor has a run on
    the same item started since."""
    return {"failures": await manager.unseen_failures(session, project[0])}


class RunsSeen(BaseModel):
    run_ids: List[str] = Field(default_factory=list, max_length=500)

    model_config = {"extra": "forbid"}


@router.post("/runs/seen", status_code=status.HTTP_204_NO_CONTENT)
async def mark_runs_seen(
    body: RunsSeen,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Mark the named runs' failures seen, once each; unknown ids are ignored."""
    await manager.mark_seen(session, project[0], body.run_ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
