"""APScheduler integration for AI Jobs in the Hub.

Runs inside the FastAPI lifespan, loads enabled jobs from DB,
and triggers agents when cron expressions match.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import AIJob, JobRun
from .sse import sse_manager
from .utils import persist_event, short_id

logger = logging.getLogger(__name__)

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
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

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
        from sqlalchemy import select, delete
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
        """Fire a job - create message for watchdog to pick up.

        This creates a message in the DB that the host-side watchdog will
        detect and execute using the agent's CLI.
        """
        from .db.models import Message

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
        """Internal: actually fire the job with a given session."""
        from .db.models import Message

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

            # Create run record
            run_id = f"run-{short_id()}"
            run = JobRun(
                id=run_id,
                job_id=job.id,
                project_id=job.project_id,
                fired_at=fired_at,
                status="fired",
                trigger=trigger,
                session_id=job.last_session_id if job.session_mode == "resume" else None,
            )
            session.add(run)

            # Prune old history (keep last 100 runs per job)
            await self._prune_job_history(session, job.id)

            # Build message content with session info
            content_parts = [job.message]
            if job.session_mode == "resume" and job.last_session_id:
                content_parts.append(f"\n\n[Session: {job.last_session_id}]")
            elif job.session_mode == "new":
                content_parts.append("\n\n[NewSession]")

            # Create message for watchdog to pick up
            msg_id = f"msg-{short_id()}"
            msg = Message(
                id=msg_id,
                project_id=job.project_id,
                sender="user",  # Indicates job-triggered message
                recipient=job.agent,
                subject=f"Scheduled job: {job.name}",
                content="\n".join(content_parts),
                type="message",
                timestamp=fired_at,
                read=False,
                session_id=job.last_session_id if job.session_mode == "resume" else None,
            )
            session.add(msg)

            await session.commit()

            # Broadcast events
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

            await sse_manager.broadcast(
                job.project_id,
                "message_created",
                {
                    "id": msg_id,
                    "from": "user",
                    "to": job.agent,
                    "subject": f"Scheduled job: {job.name}",
                    "type": "job_trigger",
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
            logger.error(f"Failed to fire job {job.id}: {e}")
            # Mark run as failed
            if "run" in locals():
                run.status = "failed"
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
