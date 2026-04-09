"""AI Jobs endpoints — CRUD + run for scheduled agent tasks."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.exc import IntegrityError

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AIJob, JobRun
from ...schemas.jobs import JobCreate, JobResponse, JobRunResponse, JobUpdate
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Create a new AI job."""
    project_id, _ = project

    # Validate cron using croniter
    try:
        from croniter import CroniterBadCronError, croniter
        croniter(body.cron)
    except ImportError:
        # croniter not installed - skip validation
        CroniterBadCronError = ValueError
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression: {e}",
        )

    job_id = body.id or f"job-{short_id()}"

    # Compute next run
    next_run = None
    try:
        from croniter import croniter

        itr = croniter(body.cron, datetime.now(timezone.utc))
        next_run = itr.get_next(datetime)
    except Exception:
        pass

    job = AIJob(
        id=job_id,
        project_id=project_id,
        name=body.name,
        agent=body.agent,
        message=body.message,
        cron=body.cron,
        session_mode=body.session_mode,
        enabled=body.enabled,
        next_run=next_run,
        source=body.source if body.source in ("local", "hub") else "hub",
    )

    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job with ID '{job_id}' already exists",
        )
    await session.refresh(job)

    # Add to scheduler if enabled
    try:
        from ...scheduler import get_scheduler

        scheduler = get_scheduler()
        if scheduler and job.enabled:
            await scheduler.add_job(job)
    except Exception:
        pass  # Scheduler might not be initialized yet

    await sse_manager.broadcast(
        project_id, "job_created", {"id": job_id, "name": body.name}
    )
    await persist_event(
        session,
        project_id,
        "job_created",
        {"id": job_id, "name": body.name, "agent": body.agent},
        agent=body.agent,
    )

    return job


@router.get("", response_model=List[JobResponse])
async def list_jobs(
    agent: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List all jobs, optionally filtered by agent."""
    project_id, _ = project
    q = select(AIJob).where(AIJob.project_id == project_id)
    if agent:
        q = q.where(AIJob.agent == agent)
    q = q.order_by(AIJob.created_at)
    result = await session.execute(q)
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get job details with last 10 run history entries."""
    project_id, _ = project
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")

    # Load last 10 runs
    q = (
        select(JobRun)
        .where(JobRun.job_id == job_id)
        .order_by(JobRun.fired_at.desc())
        .limit(10)
    )
    result = await session.execute(q)
    runs = result.scalars().all()

    # Convert to dict and add history
    job_dict = {
        "id": job.id,
        "project_id": job.project_id,
        "name": job.name,
        "agent": job.agent,
        "message": job.message,
        "cron": job.cron,
        "session_mode": job.session_mode,
        "enabled": job.enabled,
        "created_at": job.created_at,
        "last_run": job.last_run,
        "next_run": job.next_run,
        "run_count": job.run_count,
        "last_session_id": job.last_session_id,
        "history": [
            {
                "id": run.id,
                "job_id": run.job_id,
                "fired_at": run.fired_at,
                "status": run.status,
                "trigger": run.trigger,
                "session_id": run.session_id,
            }
            for run in runs
        ],
    }

    return job_dict


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: str,
    body: JobUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Update job fields (enabled, name, message, cron, session_mode)."""
    project_id, _ = project
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")

    # Track if we need to update scheduler
    update_scheduler = False

    if body.name is not None:
        job.name = body.name
    if body.message is not None:
        job.message = body.message
    if body.cron is not None:
        # Validate cron
        croniter_available = True
        try:
            from croniter import croniter
        except ImportError:
            croniter_available = False

        if croniter_available:
            try:
                croniter(body.cron)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid cron expression: {e}",
                )

            job.cron = body.cron
            # Recompute next_run
            try:
                itr = croniter(body.cron, datetime.now(timezone.utc))
                job.next_run = itr.get_next(datetime)
            except Exception:
                job.next_run = None
        else:
            job.cron = body.cron
            job.next_run = None
        update_scheduler = True

    if body.session_mode is not None:
        job.session_mode = body.session_mode
    if body.enabled is not None:
        job.enabled = body.enabled
        update_scheduler = True

    await session.commit()
    await session.refresh(job)

    # Update scheduler
    if update_scheduler:
        try:
            from ...scheduler import get_scheduler

            scheduler = get_scheduler()
            if scheduler:
                if job.enabled:
                    await scheduler.update_job(job)
                else:
                    await scheduler.remove_job(job_id)
        except Exception:
            pass

    await sse_manager.broadcast(
        project_id, "job_updated", {"id": job_id, "enabled": job.enabled}
    )

    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Delete a job and its history."""
    project_id, _ = project
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")

    # Remove from scheduler first
    try:
        from ...scheduler import get_scheduler

        scheduler = get_scheduler()
        if scheduler:
            await scheduler.remove_job(job_id)
    except Exception:
        pass

    await session.delete(job)
    await session.commit()

    await sse_manager.broadcast(project_id, "job_deleted", {"id": job_id})
    await persist_event(
        session,
        project_id,
        "job_deleted",
        {"id": job_id},
    )

    return None


@router.get("/{job_id}/history", response_model=List[JobRunResponse])
async def get_job_history(
    job_id: str,
    limit: int = Query(100, ge=1, le=1000),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get job run history."""
    project_id, _ = project
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")

    q = (
        select(JobRun)
        .where(JobRun.job_id == job_id)
        .order_by(JobRun.fired_at.desc())
        .limit(limit)
    )
    result = await session.execute(q)
    return result.scalars().all()


@router.post("/{job_id}/run")
async def run_job(
    job_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Fire a job immediately."""
    project_id, _ = project
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job is disabled",
        )

    # Fire the job via scheduler (handles stats, history, next_run, messaging)
    try:
        from ...scheduler import get_scheduler

        scheduler = get_scheduler()
        if not scheduler:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Job scheduler not available",
            )

        # Pass the session to avoid duplicate work
        success = await scheduler._fire_job_internal(job, trigger="manual", session=session)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fire job",
            )

        # Get the run_id from the most recent run we just created
        # (scheduler creates it within the same session)
        from sqlalchemy import select
        from ...db.models import JobRun

        result = await session.execute(
            select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.fired_at.desc()).limit(1)
        )
        latest_run = result.scalar_one_or_none()
        run_id = latest_run.id if latest_run else "unknown"

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fire job: {e}",
        )

    # Note: sse_manager.broadcast("job_fired") is already done by _fire_job_internal
    # We only return the success response here to avoid duplicate events
    return {"success": True, "job_id": job_id, "run_id": run_id}
