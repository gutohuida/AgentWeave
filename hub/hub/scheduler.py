"""APScheduler integration for AI Jobs in the Hub.

Runs inside the FastAPI lifespan, loads enabled jobs from DB,
and triggers agents when cron expressions match.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .conversations import (
    conversation_for_provider_session,
    inherit_runtime_overrides,
    name_conversation,
    new_conversation,
)
from .db.engine import async_session_factory
from .db.models import Agent, AIJob, JobRun, Loop, Task
from .run_task_binding import TERMINAL_FOR_BINDING
from .sse import sse_manager
from .task_transition_service import apply_transition
from .task_transitions import operator
from .utils import persist_event, short_id

logger = logging.getLogger(__name__)

_SECRET_RE = re.compile(r"(aw_live_[A-Za-z0-9_=-]+|sk-[A-Za-z0-9_=-]+|[A-Za-z0-9_=-]{32,})")


def _safe_error_summary(exc: Exception) -> str:
    return _SECRET_RE.sub("<redacted>", str(exc))[:500]


async def _job_agent_skip_reason(
    session: AsyncSession, project_id: str, agent: str
) -> Optional[str]:
    """Return why *agent*'s scheduled jobs should not auto-fire, or `None` if they should.

    Mirrors a guard the old watchdog message-trigger path used to enforce
    (`_trigger_agent_from_message`, removed from `src/agentweave/watchdog.py` in task 3.10):
    self-registered poll-mode agents manage their own inbox polling and would double-execute
    if the Hub also spawned them directly. Checked here, against the Hub's own `Agent` table,
    rather than ported into `trigger_agent_directly` itself — that function also backs the
    manual-trigger endpoint, which has never enforced this guard; adding it there would change
    manual trigger behavior too, which nothing asked for.
    """
    from sqlalchemy import select

    result = await session.execute(
        select(Agent).where(Agent.project_id == project_id, Agent.name == agent)
    )
    agent_row = result.scalars().first()
    if agent_row is None:
        return None
    if agent_row.self_registered and agent_row.contact_mode == "poll":
        return f"{agent} is a self-registered poll agent and manages its own execution"
    return None


async def _loop_stop_reason(session: AsyncSession, job: AIJob) -> Optional[str]:
    """Return why *job*'s loop should stop firing, or `None` if it should proceed.

    Only ever prevents a fire the scheduler was already about to make on its own cron or a manual
    trigger (design D4, `2026-08-16-many-named-loops`) — never creates a firing, never decides what
    happens next. A job with no `Loop` row is not a loop at all and always proceeds.
    """
    result = await session.execute(select(Loop).where(Loop.job_id == job.id))
    loop = result.scalars().first()
    if loop is None:
        return None
    now = datetime.now(timezone.utc)
    stop_at = loop.stop_at
    if stop_at is not None:
        # SQLite round-trips `DateTime(timezone=True)` as naive (same trap `agent_status.py`'s
        # `heartbeat_is_stale` already guards against) — compare against an aware `now` only after
        # restoring the UTC tzinfo SQLite dropped, not the raw column value.
        if stop_at.tzinfo is None:
            stop_at = stop_at.replace(tzinfo=timezone.utc)
        if now >= stop_at:
            return f"loop stop time reached ({stop_at.isoformat()})"
    if loop.stop_when_queue_empties:
        open_count = await session.scalar(
            select(func.count(Task.id)).where(
                Task.loop_id == loop.id, Task.status.not_in(TERMINAL_FOR_BINDING)
            )
        )
        if not open_count:
            # "Empty" means *drained*, not *never filled*. A loop is created before its work
            # exists — that is the order "shorter dev loops that keep developing" implies, and
            # arming this condition at creation would disable the loop on its first tick, before
            # it had ever run anything, permanently (`job.enabled = False` below).
            #
            # Derived from the task rows rather than a flag on `Loop`: a task that has reached a
            # terminal status still carries its `loop_id`, so the queue's whole history is already
            # recorded and a column saying the same thing would be a second copy that can drift.
            ever_count = await session.scalar(
                select(func.count(Task.id)).where(Task.loop_id == loop.id)
            )
            if ever_count:
                return "loop queue is empty"
    return None


async def _claim_loop_task(session: AsyncSession, loop: Loop) -> Optional[Task]:
    """The queue item this firing works on (design D3): resume the loop's existing
    `in_progress`/`blocked` task if one exists, else claim the oldest `pending` one.

    Deliberately mirrors `_batch_loop_summaries`'s "current item" derivation
    (`api/v1/jobs.py`, design D7 of `many-named-loops`) rather than re-deriving the ordering:
    same candidate statuses, same priority (an active task, most recently touched, beats an
    untouched pending one; pending ties break oldest-first). Not factored into a shared
    function — the two call sites differ in shape (one loop here vs. a batch of loops there),
    and importing across the api/scheduler layering for three lines was not worth it.
    """
    result = await session.execute(
        select(Task)
        .where(Task.loop_id == loop.id, Task.status.in_(("in_progress", "blocked", "pending")))
        .order_by(
            (Task.status != "pending").desc(),
            Task.updated.desc(),
            Task.created_at.asc(),
        )
        .limit(1)
    )
    return result.scalars().first()


# Singleton scheduler instance
_scheduler_instance: Optional["JobScheduler"] = None


def get_scheduler() -> Optional["JobScheduler"]:
    """Get the global scheduler instance."""
    return _scheduler_instance


async def _scheduled_job_runner(job_id: str) -> None:
    """Module-level function so APScheduler can pickle it for the job store."""
    scheduler = get_scheduler()
    if scheduler:
        await scheduler._fire_job_by_id(job_id)


class JobScheduler:
    """Wraps APScheduler for AI Job execution."""

    def __init__(self) -> None:
        self.scheduler: Optional[Any] = None
        self._job_id_map: dict = {}  # job_id -> apscheduler_job_id

    async def start(self) -> None:
        """Start the scheduler and load all enabled jobs from DB."""
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        # Create job store using our database
        job_store = SQLAlchemyJobStore(
            engine=self._get_sync_engine(),
            tablename="apscheduler_jobs",
        )

        self.scheduler = AsyncIOScheduler(
            jobstores={"default": job_store},
            job_defaults={
                "misfire_grace_time": 60,
                "coalesce": True,
            },
            timezone="UTC",  # Use UTC for consistent scheduling
        )

        self.scheduler.start()

        # Load enabled jobs from DB
        async with async_session_factory() as session:
            q = select(AIJob).where(AIJob.enabled == True)  # noqa: E712
            result = await session.execute(q)
            jobs = result.scalars().all()

            for job in jobs:
                await self.add_job(job)

        logger.info(f"JobScheduler started with {len(jobs)} job(s)")

    def _get_sync_engine(self) -> Any:
        """Get a sync SQLAlchemy engine for APScheduler jobstore."""
        from sqlalchemy import create_engine

        from .config import settings

        # Convert async URL to sync URL
        url = settings.database_url
        if url.startswith("sqlite+aiosqlite"):
            url = url.replace("sqlite+aiosqlite", "sqlite")
        elif url.startswith("postgresql+asyncpg"):
            url = url.replace("postgresql+asyncpg", "postgresql")

        return create_engine(url)

    async def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
            logger.info("JobScheduler shutdown")

    async def add_job(self, job: AIJob) -> bool:
        """Add a job to the scheduler."""
        if not self.scheduler:
            return False

        try:
            from apscheduler.triggers.cron import CronTrigger

            # Parse cron expression
            cron_parts = job.cron.split()
            if len(cron_parts) != 5:
                logger.error(f"Invalid cron expression for job {job.id}: {job.cron}")
                return False

            trigger = CronTrigger(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day=cron_parts[2],
                month=cron_parts[3],
                day_of_week=cron_parts[4],
                timezone="UTC",  # Use UTC for consistent scheduling
            )

            # Add job to scheduler
            aps_job = self.scheduler.add_job(
                func=_scheduled_job_runner,
                trigger=trigger,
                id=job.id,
                args=[job.id],
                replace_existing=True,
            )

            self._job_id_map[job.id] = aps_job.id
            logger.debug(f"Added job {job.id} to scheduler")
            return True

        except Exception as e:
            logger.error(f"Failed to add job {job.id} to scheduler: {e}")
            return False

    async def update_job(self, job: AIJob) -> bool:
        """Update a job in the scheduler (re-add with new cron)."""
        # Remove and re-add to update trigger
        await self.remove_job(job.id)
        if job.enabled:
            return await self.add_job(job)
        return True

    async def remove_job(self, job_id: str) -> bool:
        """Remove a job from the scheduler."""
        if not self.scheduler:
            return False

        try:
            self.scheduler.remove_job(job_id)
            self._job_id_map.pop(job_id, None)
            logger.debug(f"Removed job {job_id} from scheduler")
            return True
        except Exception:
            # Job might not exist in scheduler
            return False

    async def _prune_job_history(self, session: AsyncSession, job_id: str, keep: int = 100) -> None:
        """Prune old job runs, keeping only the most recent `keep` entries.

        Called automatically after each job fire to maintain history size.
        """
        from sqlalchemy import delete, select

        from .db.models import JobRun

        try:
            # Get IDs of runs to delete (all but the most recent `keep`)
            subq = (
                select(JobRun.id)
                .where(JobRun.job_id == job_id)
                .order_by(JobRun.fired_at.desc())
                .offset(keep)
                .subquery()
            )
            delete_stmt = delete(JobRun).where(JobRun.id.in_(select(subq.c.id)))
            result = await session.execute(delete_stmt)
            if result.rowcount:
                logger.debug(f"Pruned {result.rowcount} old runs for job {job_id}")
        except Exception as e:
            # Log but don't fail the job fire if pruning fails
            logger.warning(f"Failed to prune job history for {job_id}: {e}")

    async def _fire_job_by_id(self, job_id: str) -> None:
        """Fire a job by ID (lookup from DB)."""
        async with async_session_factory() as session:
            job = await session.get(AIJob, job_id)
            if job and job.enabled:
                await self._fire_job_internal(job, trigger="scheduled", session=session)

    async def _fire_job_internal(
        self,
        job: AIJob,
        trigger: str = "scheduled",
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """Fire a job through the Hub's direct execution path (task 3.10).

        Delegates to `_do_fire_job`, which spawns the agent directly — no synthetic
        `Message` for the watchdog to detect and re-trigger.
        """
        # If session provided, use it; otherwise create our own
        if session is not None:
            return await self._do_fire_job(job, trigger, session)

        async with async_session_factory() as new_session:
            return await self._do_fire_job(job, trigger, new_session)

    async def _do_fire_job(
        self,
        job: AIJob,
        trigger: str,
        session: AsyncSession,
    ) -> bool:
        """Fire *job* through the Hub's direct execution path (task 3.10).

        No synthetic `Message`, no watchdog message-scanning round trip — the outcome
        (fired, skipped, or a concrete failure reason) is known synchronously, unlike the
        old message-based protocol, which could only ever record "fired" and never learned
        whether the watchdog actually managed to trigger anything.
        """
        from .inbound_queue import new_entry
        from .turn_scheduler import schedule_agent

        try:
            fired_at = datetime.now(timezone.utc)

            # Update job stats
            job.last_run = fired_at
            job.run_count += 1

            # Recompute next run
            try:
                from croniter import croniter

                itr = croniter(job.cron, fired_at)
                job.next_run = itr.get_next(datetime)
            except Exception:
                job.next_run = None

            resume_session_id = job.last_session_id if job.session_mode == "resume" else None
            conversation = None
            if resume_session_id:
                conversation = await conversation_for_provider_session(
                    session,
                    project_id=job.project_id,
                    agent=job.agent,
                    provider_session_id=resume_session_id,
                )
            if conversation is None:
                conversation = new_conversation(
                    project_id=job.project_id, agent=job.agent, origin="job"
                )
                if resume_session_id:
                    conversation.provider_session_id = resume_session_id
                session.add(conversation)
                # A job names no conversation either, and fires unattended — the case where a
                # silently changed posture is least likely to be noticed.
                await inherit_runtime_overrides(session, conversation)
            # Named from the job, not its message: a schedule fires the same message repeatedly,
            # and the job's name is what the operator recognises the thread by.
            name_conversation(conversation, job.name)

            # Create run record
            run_id = f"run-{short_id()}"
            run = JobRun(
                id=run_id,
                job_id=job.id,
                project_id=job.project_id,
                fired_at=fired_at,
                status="fired",
                trigger=trigger,
                session_id=resume_session_id,
                conversation_id=conversation.id,
            )
            session.add(run)

            # Prune old history (keep last 100 runs per job)
            await self._prune_job_history(session, job.id)

            skip_reason = await _job_agent_skip_reason(session, job.project_id, job.agent)
            if skip_reason:
                run.status = "skipped"
                run.error_summary = skip_reason
                await session.commit()
                await persist_event(
                    session,
                    job.project_id,
                    "job_run_skipped",
                    {
                        "job_id": job.id,
                        "job_name": job.name,
                        "agent": job.agent,
                        "trigger": trigger,
                        "run_id": run_id,
                        "reason": skip_reason,
                    },
                    agent=job.agent,
                )
                logger.info(f"Job {job.id} fire skipped: {skip_reason}")
                return False

            loop_stop_reason = await _loop_stop_reason(session, job)
            if loop_stop_reason:
                run.status = "skipped"
                run.error_summary = loop_stop_reason
                loop_result = await session.execute(select(Loop).where(Loop.job_id == job.id))
                loop = loop_result.scalars().first()
                if loop is not None:
                    loop.stop_reason = loop_stop_reason
                    loop.stopped_at = fired_at
                job.enabled = False
                await session.commit()
                await persist_event(
                    session,
                    job.project_id,
                    "job_run_skipped",
                    {
                        "job_id": job.id,
                        "job_name": job.name,
                        "agent": job.agent,
                        "trigger": trigger,
                        "run_id": run_id,
                        "reason": loop_stop_reason,
                    },
                    agent=job.agent,
                )
                loop_stopped_payload = {
                    "job_id": job.id,
                    "loop_id": loop.id if loop is not None else None,
                    "reason": loop_stop_reason,
                }
                await persist_event(
                    session, job.project_id, "loop_stopped", loop_stopped_payload, agent=job.agent
                )
                await sse_manager.broadcast(job.project_id, "loop_stopped", loop_stopped_payload)
                # Remove from the live scheduler so it does not fire again next cron tick only to be
                # skipped again — the same call `remove_job` already makes for a job an operator
                # disables by hand.
                await self.remove_job(job.id)
                logger.info(f"Job {job.id} loop stopped: {loop_stop_reason}")
                return False

            loop_result = await session.execute(select(Loop).where(Loop.job_id == job.id))
            loop = loop_result.scalars().first()
            if loop is not None:
                claimed_task = await _claim_loop_task(session, loop)
                if claimed_task is not None:
                    # `pending` is the only entry status `_claim_loop_task` can return (its
                    # candidate set mirrors `_batch_loop_summaries`, which never includes
                    # `assigned`) — an already-active task is being resumed, not entered, so its
                    # status stays untouched (design D3).
                    if claimed_task.status == "pending":
                        await apply_transition(session, claimed_task, "assigned", operator())
                    claimed_task.assignee = job.agent

            entry = new_entry(
                project_id=job.project_id,
                agent=job.agent,
                origin_type="job",
                content=job.message,
                hop_depth=0,
                session_mode=job.session_mode,
                session_id=resume_session_id,
                conversation_id=conversation.id,
            )
            session.add(entry)
            await session.commit()

            queue_payload = {
                "entry_id": entry.id,
                "agent": job.agent,
                "origin_type": "job",
                "hop_depth": 0,
                "job_id": job.id,
                "conversation_id": conversation.id,
            }
            await persist_event(
                session, job.project_id, "queue_entry_queued", queue_payload, agent=job.agent
            )
            await sse_manager.broadcast(job.project_id, "queue_entry_queued", queue_payload)
            await schedule_agent(job.project_id, job.agent)

            await sse_manager.broadcast(
                job.project_id,
                "job_fired",
                {
                    "id": job.id,
                    "name": job.name,
                    "agent": job.agent,
                    "trigger": trigger,
                    "run_id": run_id,
                },
            )

            await persist_event(
                session,
                job.project_id,
                "job_fired",
                {
                    "job_id": job.id,
                    "job_name": job.name,
                    "agent": job.agent,
                    "trigger": trigger,
                    "run_id": run_id,
                },
                agent=job.agent,
            )

            logger.info(f"Job {job.id} fired (trigger: {trigger})")
            return True

        except Exception as e:
            error_summary = _safe_error_summary(e)
            logger.error(f"Failed to fire job {job.id}: {error_summary}")
            # Mark run as failed
            if "run" in locals():
                run.status = "failed"
                run.error_summary = error_summary
                await persist_event(
                    session,
                    job.project_id,
                    "job_run_failed",
                    {
                        "job_id": job.id,
                        "job_name": job.name,
                        "agent": job.agent,
                        "trigger": trigger,
                        "run_id": run.id,
                        "error_summary": error_summary,
                    },
                    agent=job.agent,
                    severity="error",
                )
                await session.commit()
            return False


async def init_scheduler() -> JobScheduler:
    """Initialize and start the global scheduler."""
    global _scheduler_instance
    _scheduler_instance = JobScheduler()
    await _scheduler_instance.start()
    return _scheduler_instance


async def shutdown_scheduler() -> None:
    """Shutdown the global scheduler."""
    global _scheduler_instance
    if _scheduler_instance:
        await _scheduler_instance.shutdown()
        _scheduler_instance = None
