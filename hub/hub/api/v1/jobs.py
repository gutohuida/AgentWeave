"""AI Jobs endpoints — CRUD + run for scheduled agent tasks."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AIJob, JobRun, Loop, Project, Question, Run, Task
from ...schemas.jobs import JobCreate, JobResponse, JobRunResponse, JobUpdate, LoopSummary
from ...schemas.tasks import TaskCreate
from ...sse import sse_manager
from ...task_transitions import operator, run_actor
from ...utils import persist_event, short_id
from .tasks import create_task_for_actor

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


async def _check_spec_document_conflict(
    session: AsyncSession,
    project_id: str,
    spec_document_id: Optional[str],
    *,
    exclude_loop_id: Optional[str] = None,
) -> None:
    """Design D1: a document already claimed by one loop cannot be claimed by a second.

    A no-op re-declare of a loop's own existing document must not 409 against itself, hence
    `exclude_loop_id` on the update path.
    """
    if spec_document_id is None:
        return
    q = select(Loop).where(Loop.project_id == project_id, Loop.spec_document_id == spec_document_id)
    result = await session.execute(q)
    conflicting = result.scalars().first()
    if conflicting is not None and conflicting.id != exclude_loop_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"document '{spec_document_id}' is already claimed by loop '{conflicting.id}'",
        )


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
            ending_state=loop.ending_state,
            archived_at=loop.archived_at,
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

    # Design D4: a loop's continuity is by checkpoint, not by resumed session. Checked before the
    # job row is created — an error response must not leave a half-created job behind.
    if body.session_mode == "resume" and _loop_opts_in(
        body.purpose, body.stop_at, body.stop_when_queue_empties
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="this job is a loop; continuity is by checkpoint, not by resumed session",
        )

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

    # Design D2's "definition window": `initial_tasks` is validated up front, before any row is
    # created, so one malformed entry cannot leave a job (and its loop) half-created behind a 422.
    initial_task_bodies: List[TaskCreate] = []
    for item in body.initial_tasks or []:
        try:
            initial_task_bodies.append(TaskCreate(**item))
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid initial_tasks entry: {e}",
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
        await _check_spec_document_conflict(session, project_id, body.spec_document_id)
        loop = Loop(
            id=f"loop-{short_id()}",
            project_id=project_id,
            job_id=job.id,
            purpose=body.purpose or "",
            stop_at=body.stop_at,
            stop_when_queue_empties=body.stop_when_queue_empties,
            spec_document_id=body.spec_document_id,
            created_by_run_id=run_identity,
        )
        session.add(loop)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(f"document '{body.spec_document_id}' is already claimed by another loop"),
            ) from e
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

        # Seeds the new loop's queue in the same call that creates it (design D2's "definition
        # window"). `create_task_for_actor` is the single `Task(` construction site — reused here
        # rather than duplicated — and its own loop-authorship gate (`_authorize_loop_task_creation`)
        # is satisfied for free: `job.run_count` is always 0 for a job this call just created, so
        # the "already fired" restriction it enforces never applies here.
        actor = (
            run_actor(run_identity, agent_identity)
            if agent_identity and run_identity
            else operator()
        )
        for task_body in initial_task_bodies:
            task_body.loop_id = loop.id
            await create_task_for_actor(
                task_body,
                project_id=project_id,
                assigner=agent_identity,
                created_by_run_id=run_identity,
                actor=actor,
                session=session,
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
    include_archived: bool = Query(False),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List jobs, optionally filtered by agent. Archived jobs (design D16) are excluded unless
    `include_archived=true` (B2.4) — nothing is deleted, so a caller that wants them can always
    ask."""
    project_id, _ = project
    q = select(AIJob).where(AIJob.project_id == project_id)
    if agent:
        q = q.where(AIJob.agent == agent)
    if not include_archived:
        q = q.where(AIJob.archived_at.is_(None))
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
        "archived_at": job.archived_at,
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

    # Loop fields (design D6): supplying any of the five on a job with no `Loop` row is a 400
    # unless this update is the one that opts the job in for the first time (mirrors create_job's
    # "at least one field" rule). `spec_document_id` alone does NOT opt a job in (design D2 keeps
    # that stricter contract on the agent-facing `create_loop` tool only) — it is still gated on an
    # existing loop or one of the other three fields alongside it, same as `stop_reason`.
    loop_fields_supplied = (
        body.purpose is not None
        or body.stop_at is not None
        or body.stop_when_queue_empties is not None
        or body.stop_reason is not None
        or body.spec_document_id is not None
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
        if body.spec_document_id is not None:
            await _check_spec_document_conflict(
                session, project_id, body.spec_document_id, exclude_loop_id=loop.id
            )
            loop.spec_document_id = body.spec_document_id
        if body.purpose is not None:
            loop.purpose = body.purpose
        if body.stop_at is not None:
            loop.stop_at = body.stop_at
        if body.stop_when_queue_empties is not None:
            loop.stop_when_queue_empties = body.stop_when_queue_empties
        if body.stop_reason is not None:
            loop.stop_reason = body.stop_reason
            # B2.5/D17: an operator stating why this loop stopped is itself "an operator stop" —
            # the one ending path `scheduler.py`'s own stop-condition check cannot see, since it
            # never fires from there. Only set when nothing has recorded an ending yet: editing
            # the prose after the fact must not overwrite a governance fact already recorded.
            if loop.ending_state is None:
                loop.ending_state = "stopped"
        loop.updated_by_run_id = run_identity

    # Design D4: a loop's continuity is by checkpoint, not by resumed session. Checked before
    # job.session_mode is mutated below, against the job's loop status AFTER this request is
    # applied — either the loop just resolved/created above, or (when no loop fields were
    # supplied in this request) whatever Loop row the job already had.
    if body.session_mode == "resume":
        job_is_loop = loop_fields_supplied and loop is not None
        if not job_is_loop:
            existing_loop_result = await session.execute(select(Loop).where(Loop.job_id == job_id))
            job_is_loop = existing_loop_result.scalar_one_or_none() is not None
        if job_is_loop:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="this job is a loop; continuity is by checkpoint, not by resumed session",
            )

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


@router.delete("/{job_id}")
async def delete_job(
    job_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
):
    """Refuse outright (design D16, B2.1). Nothing is deletable — a job archives instead.

    A caller that asked to destroy data is told plainly that it did not happen, rather than
    having the request silently reinterpreted as an archive: that would leave a caller who
    genuinely meant "gone forever" believing something happened that did not.
    """
    del agent_identity, run_identity  # signature parity with the other job routes only
    project_id, _ = project
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="jobs are archived, not deleted — archive this job instead; nothing was removed",
    )


@router.post("/{job_id}/archive", response_model=JobResponse)
async def archive_job(
    job_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
    agent_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Agent"),
    run_identity: Optional[str] = Header(default=None, alias="X-AgentWeave-Run"),
):
    """Archive a job (design D16/D18). Hides it from default listings; deletes nothing.

    Governed the same way as every other agent-originated job mutation
    (`_require_agent_job_allowance`) — the standing `allow_agent_jobs` project setting is the
    capability gate here. D18's *always ask, independent of the run's permission posture* rule is
    enforced one layer up, at the MCP tool (`archive_job` in `mcp_server.py`, B3.2) — this route
    is the mechanism the tool calls once that has already happened, not the policy itself.

    B3.3: a job with a `Loop` is refused here, for an agent caller only. D18's own text is
    explicit that "archive_job's agent path therefore only ever targets a job with no loop" —
    an agent cannot reach `POST /loops/{id}/archive` at all (no agent credential authenticates
    against it), so without this check an agent could archive the *job* a running loop owns and
    hide that loop from the default listing while it keeps firing. `agent_identity`/`run_identity`
    both absent is how `_require_agent_job_allowance` itself recognises an operator call (it
    returns immediately in that case, a few lines above) — mirrored here rather than restated
    differently, so the two checks agree on what "an agent is calling" means. The operator's own
    path through this same route is intentionally NOT restricted this way and does not require the
    loop to have ended first either (that rule, B2.3, is specific to archiving the *loop* itself) —
    an open question recorded in the change's own log, not resolved here.
    """
    project_id, _ = project
    await _require_agent_job_allowance(session, project_id, agent_identity, run_identity)
    job = await session.get(AIJob, job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.archived_at is not None:
        raise HTTPException(status_code=400, detail="job is already archived")
    if agent_identity is not None or run_identity is not None:
        loop_result = await session.execute(select(Loop).where(Loop.job_id == job_id))
        if loop_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=400,
                detail="this job has a loop; loops are archived by the operator only",
            )

    job.archived_at = datetime.now(timezone.utc)
    job.updated_by_run_id = run_identity

    await session.commit()
    await session.refresh(job)

    await sse_manager.broadcast(project_id, "job_archived", {"id": job_id})
    await persist_event(session, project_id, "job_archived", {"id": job_id}, agent=agent_identity)

    loop_summaries = await _batch_loop_summaries(session, [job_id])
    job.loop = loop_summaries.get(job_id)
    return job


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
