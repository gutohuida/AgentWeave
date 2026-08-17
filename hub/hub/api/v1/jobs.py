"""AI Jobs endpoints — CRUD + run for scheduled agent tasks."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AgentJobDeletion, AIJob, JobRun, Loop, Project, Question, Run, Task
from ...schemas.jobs import JobCreate, JobResponse, JobRunResponse, JobUpdate, LoopSummary
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _require_agent_job_allowance(
    session: AsyncSession,
    project_id: str,
    agent: Optional[str],
    run_id: Optional[str],
) -> None:
    """Gate agent-originated recurring-work mutations; operator calls have no headers."""
    if agent is None and run_id is None:
        return
    if not agent or not run_id:
        raise HTTPException(status_code=403, detail="Agent job request has incomplete attribution")
    run = await session.get(Run, run_id)
    if run is None or run.project_id != project_id or run.agent != agent or run.status != "running":
        raise HTTPException(status_code=403, detail="Agent job request has stale attribution")
    project = await session.get(Project, project_id)
    if project is None or not project.allow_agent_jobs:
        raise HTTPException(
            status_code=403,
            detail="Scheduled work from agents requires operator approval or an enabled allowance",
        )


def _safe_error_summary(exc: Exception) -> str:
    import re

    return re.sub(
        r"(aw_live_[A-Za-z0-9_=-]+|sk-[A-Za-z0-9_=-]+|[A-Za-z0-9_=-]{32,})",
        "<redacted>",
        str(exc),
    )[:500]


async def _record_job_run_failure(
    session: AsyncSession,
    job: AIJob,
    trigger: str,
    exc: Exception,
    requested_by_run_id: Optional[str] = None,
) -> str:
    error_summary = _safe_error_summary(exc)
    run_id = f"run-{short_id()}"
    run = JobRun(
        id=run_id,
        job_id=job.id,
        project_id=job.project_id,
        fired_at=datetime.now(timezone.utc),
        status="failed",
        trigger=trigger,
        session_id=job.last_session_id if job.session_mode == "resume" else None,
        error_summary=error_summary,
        requested_by_run_id=requested_by_run_id,
    )
    session.add(run)
    await persist_event(
        session,
        job.project_id,
        "job_run_failed",
        {
            "job_id": job.id,
            "job_name": job.name,
            "agent": job.agent,
            "trigger": trigger,
            "run_id": run_id,
            "error_summary": error_summary,
        },
        agent=job.agent,
        severity="error",
    )
    await session.commit()
    return run_id


def _loop_opts_in(purpose: Optional[str], stop_at, stop_when_queue_empties: Optional[bool]) -> bool:
    """Design D6's "at least one field" rule — a bare default does not opt a job in."""
    return purpose is not None or stop_at is not None or stop_when_queue_empties is True


async def _batch_loop_summaries(
    session: AsyncSession, job_ids: List[str]
) -> Dict[str, LoopSummary]:
    """Compute every job's `loop` block in four fixed queries, never one query per job (design D7)."""
    if not job_ids:
        return {}

    loops_result = await session.execute(select(Loop).where(Loop.job_id.in_(job_ids)))
    loops = loops_result.scalars().all()
    if not loops:
        return {}
    loop_by_job = {loop.job_id: loop for loop in loops}
    loop_ids = [loop.id for loop in loops]

    queue_counts: Dict[str, Dict[str, int]] = {}
    counts_result = await session.execute(
        select(Task.loop_id, Task.status, func.count())
        .where(Task.loop_id.in_(loop_ids))
        .group_by(Task.loop_id, Task.status)
    )
    for loop_id, task_status, count in counts_result.all():
        queue_counts.setdefault(loop_id, {})[task_status] = count

    current_task_by_loop: Dict[str, Dict[str, str]] = {}
    candidates_result = await session.execute(
        select(Task)
        .where(Task.loop_id.in_(loop_ids), Task.status.in_(("in_progress", "blocked", "pending")))
        .order_by(
            Task.loop_id,
            (Task.status != "pending").desc(),
            Task.updated.desc(),
            Task.created_at.asc(),
        )
    )
    for task in candidates_result.scalars().all():
        if task.loop_id not in current_task_by_loop:
            current_task_by_loop[task.loop_id] = {
                "id": task.id,
                "title": task.title,
                "status": task.status,
            }

    # Distinct (job_id, conversation_id) pairs first, so a resume-mode job that fired more than
    # once on the same conversation does not join the same question row once per firing.
    conv_subq = (
        select(JobRun.job_id.label("job_id"), JobRun.conversation_id.label("conversation_id"))
        .where(JobRun.job_id.in_(job_ids), JobRun.conversation_id.isnot(None))
        .distinct()
        .subquery()
    )
    open_questions_by_job: Dict[str, int] = {}
    questions_result = await session.execute(
        select(conv_subq.c.job_id, func.count(Question.id))
        .join(Question, Question.conversation_id == conv_subq.c.conversation_id)
        .where(Question.answered.is_(False), Question.declined.is_(False))
        .group_by(conv_subq.c.job_id)
    )
    for job_id, count in questions_result.all():
        open_questions_by_job[job_id] = count

    summaries: Dict[str, LoopSummary] = {}
    for job_id, loop in loop_by_job.items():
        summaries[job_id] = LoopSummary(
            id=loop.id,
            purpose=loop.purpose,
            stop_at=loop.stop_at,
            stop_when_queue_empties=loop.stop_when_queue_empties,
            stop_reason=loop.stop_reason,
            stopped_at=loop.stopped_at,
            queue=queue_counts.get(loop.id, {}),
            current_task=current_task_by_loop.get(loop.id),
            open_questions=open_questions_by_job.get(job_id, 0),
        )
    return summaries


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
):
    """Create a new AI job."""
    project_id, _ = project
    await _require_agent_job_allowance(session, project_id, agent_identity, run_identity)

    # Validate cron using croniter
    try:
        from croniter import croniter

        croniter(body.cron)
    except ImportError:
        # croniter not installed - skip validation
        pass
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression: {e}",
        ) from e

    job_id = f"job-{short_id()}"

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
        created_by_run_id=run_identity,
    )

    session.add(job)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job with ID '{job_id}' already exists",
        ) from e
    await session.refresh(job)

    # Loop opt-in (design D6): a `Loop` row is created iff at least one of the three fields was
    # supplied non-default.
    loop_summary: Optional[LoopSummary] = None
    if _loop_opts_in(body.purpose, body.stop_at, body.stop_when_queue_empties):
        loop = Loop(
            id=f"loop-{short_id()}",
            project_id=project_id,
            job_id=job.id,
            purpose=body.purpose or "",
            stop_at=body.stop_at,
            stop_when_queue_empties=body.stop_when_queue_empties,
            created_by_run_id=run_identity,
        )
        session.add(loop)
        await session.commit()
        loop_summary = LoopSummary(
            id=loop.id,
            purpose=loop.purpose,
            stop_at=loop.stop_at,
            stop_when_queue_empties=loop.stop_when_queue_empties,
            stop_reason=loop.stop_reason,
            stopped_at=loop.stopped_at,
            queue={},
            current_task=None,
            open_questions=0,
        )

    # Add to scheduler if enabled
    try:
        from ...scheduler import get_scheduler

        scheduler = get_scheduler()
        if scheduler and job.enabled:
            await scheduler.add_job(job)
    except Exception:
        pass  # Scheduler might not be initialized yet

    await sse_manager.broadcast(project_id, "job_created", {"id": job_id, "name": body.name})
    await persist_event(
        session,
        project_id,
        "job_created",
        {"id": job_id, "name": body.name, "agent": body.agent},
        agent=body.agent,
    )

    job.loop = loop_summary
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
    jobs = result.scalars().all()
    loop_summaries = await _batch_loop_summaries(session, [job.id for job in jobs])
    for job in jobs:
        job.loop = loop_summaries.get(job.id)
    return jobs


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
    q = select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.fired_at.desc()).limit(10)
    result = await session.execute(q)
    runs = result.scalars().all()

    # `loop`: reuses the same batch functions as `list_jobs` with a one-element id list (design
    # D7) — no separate single-job code path to keep in sync with the batch one.
    loop_summaries = await _batch_loop_summaries(session, [job_id])

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
        "loop": loop_summaries.get(job_id),
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
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
):
    """Update job fields (enabled, name, message, cron, session_mode)."""
    project_id, _ = project
    await _require_agent_job_allowance(session, project_id, agent_identity, run_identity)
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")

    # Loop fields (design D6): supplying any of the four on a job with no `Loop` row is a 400
    # unless this update is the one that opts the job in for the first time (mirrors create_job's
    # "at least one field" rule).
    loop_fields_supplied = (
        body.purpose is not None
        or body.stop_at is not None
        or body.stop_when_queue_empties is not None
        or body.stop_reason is not None
    )
    if loop_fields_supplied:
        loop_result = await session.execute(select(Loop).where(Loop.job_id == job_id))
        loop = loop_result.scalar_one_or_none()
        if loop is None:
            if not _loop_opts_in(body.purpose, body.stop_at, body.stop_when_queue_empties):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "this job is not a loop; create it with a purpose or stop condition "
                        "to make it one"
                    ),
                )
            loop = Loop(
                id=f"loop-{short_id()}",
                project_id=project_id,
                job_id=job_id,
                purpose="",
            )
            session.add(loop)
        if body.purpose is not None:
            loop.purpose = body.purpose
        if body.stop_at is not None:
            loop.stop_at = body.stop_at
        if body.stop_when_queue_empties is not None:
            loop.stop_when_queue_empties = body.stop_when_queue_empties
        if body.stop_reason is not None:
            loop.stop_reason = body.stop_reason
        loop.updated_by_run_id = run_identity

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
                ) from e

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

    job.updated_by_run_id = run_identity

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

    await sse_manager.broadcast(project_id, "job_updated", {"id": job_id, "enabled": job.enabled})

    loop_summaries = await _batch_loop_summaries(session, [job_id])
    job.loop = loop_summaries.get(job_id)
    return job


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
):
    """Delete a job and its history."""
    project_id, _ = project
    await _require_agent_job_allowance(session, project_id, agent_identity, run_identity)
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")

    if run_identity and agent_identity:
        session.add(
            AgentJobDeletion(
                id=f"job-delete-{short_id()}",
                job_id=job.id,
                project_id=project_id,
                agent=agent_identity,
                run_id=run_identity,
            )
        )

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

    q = select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.fired_at.desc()).limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


@router.post("/{job_id}/run")
async def run_job(
    job_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
):
    """Fire a job immediately."""
    project_id, _ = project
    await _require_agent_job_allowance(session, project_id, agent_identity, run_identity)
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
            exc = RuntimeError("Job scheduler not available")
            await _record_job_run_failure(
                session, job, "manual", exc, requested_by_run_id=run_identity
            )
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))

        # Pass the session to avoid duplicate work
        success = await scheduler._fire_job_internal(job, trigger="manual", session=session)

        # Get the run_id from the most recent run we just created
        # (scheduler creates it within the same session)
        from sqlalchemy import select

        from ...db.models import JobRun

        result = await session.execute(
            select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.fired_at.desc()).limit(1)
        )
        latest_run = result.scalar_one_or_none()
        run_id = latest_run.id if latest_run else "unknown"
        if latest_run is not None:
            latest_run.requested_by_run_id = run_identity
            await session.commit()

        if not success:
            # `_fire_job_internal` already persisted the right event (job_run_skipped or
            # job_run_failed) and set the JobRun's own status/error_summary — this branch
            # only translates that into the right HTTP response, it must not persist a
            # second, duplicate event on top of what was already recorded.
            if latest_run and latest_run.status == "skipped":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=latest_run.error_summary or "Job was skipped.",
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    latest_run.error_summary
                    if latest_run and latest_run.error_summary
                    else "Failed to fire job"
                ),
            )

    except HTTPException:
        raise
    except Exception as e:
        await _record_job_run_failure(session, job, "manual", e, requested_by_run_id=run_identity)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fire job: {_safe_error_summary(e)}",
        ) from e

    # Note: sse_manager.broadcast("job_fired") is already done by _fire_job_internal
    # We only return the success response here to avoid duplicate events
    return {"success": True, "job_id": job_id, "run_id": run_id}
