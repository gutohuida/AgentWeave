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

from .checkpoint_generation import render_checkpoint
from .checkpoints import latest_checkpoint_for_loop
from .conversations import (
    conversation_for_provider_session,
    inherit_runtime_overrides,
    name_conversation,
    new_conversation,
)
from .db.engine import async_session_factory
from .db.models import Agent, AIJob, Checkpoint, JobRun, Loop, Message, Question, Run, Task
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


_LOOP_PENDING_REQUEST_REASON_CHARS = 300


async def _pending_loop_request(
    session: AsyncSession, job: AIJob, loop: Loop, exclude_run_id: str
) -> Optional[dict]:
    """What the loop's executor was waiting on when its queue drained (design D6).

    A loop job never resumes a conversation — task 8.1 refuses `session_mode="resume"` for one,
    for the entire lifetime of the job, not just at creation — so every firing, including the one
    that just discovered the empty queue, gets a brand-new, still-empty `Conversation`
    (`_do_fire_job` creates it before `_loop_stop_reason` runs, unconditionally). An unanswered
    `Question` this firing's OWN conversation could hold is therefore always none; "the firing's
    conversation" D6 names has to mean the most recent EARLIER firing's conversation — the one an
    `ask_user` call would actually have been asked in, if one was ever asked and never answered.
    Found via the most recent prior `JobRun` for this job that recorded one, excluding this firing
    itself (`exclude_run_id`).

    Checked before the `Message` case: an unanswered `ask_user` is a hard block on the run that
    asked it, closer to "the thing this loop was actually waiting on" than mail sitting unread in
    an inbox nobody has to check. D6 does not state a tiebreak when both exist.
    """
    prior_run_result = await session.execute(
        select(JobRun.conversation_id)
        .where(
            JobRun.job_id == job.id,
            JobRun.id != exclude_run_id,
            JobRun.conversation_id.is_not(None),
        )
        .order_by(JobRun.fired_at.desc())
        .limit(1)
    )
    prior_conversation_id = prior_run_result.scalar_one_or_none()
    if prior_conversation_id is not None:
        question_result = await session.execute(
            select(Question)
            .where(
                Question.conversation_id == prior_conversation_id,
                Question.answered == False,  # noqa: E712
            )
            .order_by(Question.created_at.desc())
        )
        question = question_result.scalars().first()
        if question is not None:
            reason = question.question
            if len(reason) > _LOOP_PENDING_REQUEST_REASON_CHARS:
                reason = reason[:_LOOP_PENDING_REQUEST_REASON_CHARS]
            return {
                "kind": "question",
                # A `Question` has no recipient field of its own — it is addressed to whichever
                # human is watching the operator UI, not to a named agent, so `to` stays null.
                "to": None,
                "reason": reason,
                "created_at": question.created_at.isoformat(),
            }

    # "addressed to the creator" is the Message model's own `recipient` field — the thing that
    # actually decides whose inbox it lands in — not a conversation match; only the Question half
    # of D6's sentence carries the "in the firing's conversation" qualifier grammatically.
    creator_agent: Optional[str] = None
    if loop.created_by_run_id:
        # Same `created_by_run_id` -> `Run.agent` resolution `questions.py`'s
        # `_asking_run_has_ended` already uses for a different row's creator — cited as precedent
        # rather than a second pattern.
        creator_run = await session.get(Run, loop.created_by_run_id)
        if creator_run is not None:
            creator_agent = creator_run.agent
    if creator_agent is not None:
        message_result = await session.execute(
            select(Message)
            .where(
                Message.sender == job.agent,
                Message.recipient == creator_agent,
                Message.read == False,  # noqa: E712
            )
            .order_by(Message.timestamp.desc())
        )
        message = message_result.scalars().first()
        if message is not None:
            reason = message.subject or message.content
            if len(reason) > _LOOP_PENDING_REQUEST_REASON_CHARS:
                reason = reason[:_LOOP_PENDING_REQUEST_REASON_CHARS]
            return {
                "kind": "message",
                "to": message.recipient,
                "reason": reason,
                "created_at": message.timestamp.isoformat(),
            }

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


async def finalize_job_run_for_conversation(
    session: AsyncSession, conversation_id: Optional[str], final_status: str
) -> None:
    """Flip a firing's `JobRun` out of "in progress" once its `Run` has ended (design D13,
    task A4.3). `conversation_id` is the only correlation `JobRun` and `Run` share — there is
    no direct foreign key (see `models.py`'s own comment on `JobRun.conversation_id`).

    Most runs are not job firings at all (a message or a delegation starts a `Run` too), so
    finding no matching row here is the common case, not an error. At most one `JobRun` should
    be "in_progress" for a given `conversation_id` at a time — a session-resuming job's earlier
    firings already reached a terminal status before this one was created — but the query still
    orders newest-first and takes one row rather than assuming that invariant holds.
    """
    if conversation_id is None:
        return
    result = await session.execute(
        select(JobRun)
        .where(JobRun.conversation_id == conversation_id, JobRun.status == "in_progress")
        .order_by(JobRun.fired_at.desc())
    )
    job_run = result.scalars().first()
    if job_run is not None:
        job_run.status = final_status


# Consumer-side cap on a rendered checkpoint's contribution to a briefing (design D5). A
# checkpoint body is already a bounded generator-side summary
# (`checkpoint_generation._TRANSCRIPT_CHAR_LIMIT`), so this budget is far smaller: 4,000
# characters comfortably fits one well-formed checkpoint in full, with room left for the claimed
# task and queue summary around it, and only ever truncates the pathological case (a checkpoint
# that failed to stay terse), never the common one.
_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000


def _stage_pending_loop_edit(loop: Loop) -> Optional[dict]:
    """Move a staged edit (design D11, task A2.2) from `loop`'s pending_* columns onto its live
    fields, in memory only — no commit, no event. Returns the audit payload for
    `_emit_loop_edit_applied` below, or `None` if nothing was staged.

    Applied once, at the very top of `_do_fire_job`'s handling of *loop* — before
    `_loop_stop_reason` and before `_compose_loop_briefing` are ever consulted, so both see the
    loop's current definition rather than one waiting on the firing after next. Deliberately does
    not commit or persist an event itself: `_do_fire_job` is about to mutate `run`'s status too,
    and a premature commit here would write that row to the database mid-update (transiently
    "fired" before a stop check turns it "skipped" moments later) — the caller commits everything
    together once its own branch knows the firing's final outcome, then calls
    `_emit_loop_edit_applied`.

    A firing already under way when the edit was staged (task A2.3) is unaffected by construction:
    `_do_fire_job` loads and applies pending edits exactly once, at the start of its own firing —
    nothing re-reads `loop.purpose`/`loop.stop_at`/`loop.stop_when_queue_empties` mid-turn, so a
    `PATCH` landing while an agent is still working on this firing only ever affects the *next*
    one.
    """
    if loop.pending_edit_at is None:
        return None

    changes: dict[str, Any] = {}
    if loop.pending_purpose is not None:
        changes["purpose"] = {"from": loop.purpose, "to": loop.pending_purpose}
        loop.purpose = loop.pending_purpose
    if loop.pending_stop_at is not None:
        changes["stop_at"] = {
            "from": loop.stop_at.isoformat() if loop.stop_at else None,
            "to": loop.pending_stop_at.isoformat(),
        }
        loop.stop_at = loop.pending_stop_at
    if loop.pending_stop_when_queue_empties is not None:
        changes["stop_when_queue_empties"] = {
            "from": loop.stop_when_queue_empties,
            "to": loop.pending_stop_when_queue_empties,
        }
        loop.stop_when_queue_empties = loop.pending_stop_when_queue_empties

    actor = loop.pending_edit_actor
    staged_at = loop.pending_edit_at

    loop.pending_purpose = None
    loop.pending_stop_at = None
    loop.pending_stop_when_queue_empties = None
    loop.pending_edit_actor = None
    loop.pending_edit_at = None

    return {
        "id": loop.id,
        "project_id": loop.project_id,
        "actor": actor,
        "staged_at": staged_at.isoformat() if staged_at else None,
        "changes": changes,
    }


async def _emit_loop_edit_applied(session: AsyncSession, payload: dict) -> None:
    """Persist and broadcast the audit event (task A2.5) for a pending edit
    `_stage_pending_loop_edit` already applied in memory. Called only after the caller's own
    commit has landed `run`'s final status, so this never forces an early, partial commit."""
    actor = payload["actor"]
    await persist_event(
        session,
        payload["project_id"],
        "loop_edit_applied",
        payload,
        agent=None if actor in (None, "operator") else actor,
        loop_id=payload["id"],
    )
    await sse_manager.broadcast(payload["project_id"], "loop_edit_applied", payload)


async def _compose_loop_briefing(
    session: AsyncSession,
    loop: Loop,
    claimed_task: Optional[Task],
    prior_checkpoint: Optional[Checkpoint],
) -> str:
    """The context a loop firing gets ahead of the operator's own message (design D5): purpose,
    the claimed queue item, the prior firing's checkpoint if one exists, and a one-line queue
    summary — in that order. A prefix, never a replacement: `_do_fire_job` puts `job.message`
    after this unchanged, so the operator's own message template still reads exactly as authored.
    """
    lines: list[str] = ["# Loop briefing", ""]

    if loop.purpose:
        lines.append(f"Purpose: {loop.purpose}")
        lines.append("")

    if claimed_task is not None:
        lines.append(f"## Current task: {claimed_task.title}")
        lines.append("")
        if claimed_task.description:
            lines.append(claimed_task.description)
            lines.append("")
        criteria = claimed_task.acceptance_criteria or []
        if criteria:
            lines.append("Acceptance criteria:")
            lines.extend(f"- {criterion}" for criterion in criteria)
            lines.append("")

    if prior_checkpoint is not None:
        # Reuses the same rendering a human reader gets (`render_checkpoint`) rather than
        # inventing a second serialisation of the same data (design D5). Truncated from the end
        # on overflow — re-ordering `render_checkpoint`'s own section order to drop the oldest
        # content first would only matter for the rare pathological case this cap exists to
        # bound, not worth the complexity for it.
        rendered = render_checkpoint(prior_checkpoint)
        if len(rendered) > _LOOP_BRIEFING_CHECKPOINT_CHARS:
            rendered = rendered[:_LOOP_BRIEFING_CHECKPOINT_CHARS]
        lines.append("## Prior checkpoint")
        lines.append("")
        lines.append(rendered)
        lines.append("")

    # Same per-status group-by `_batch_loop_summaries` already computes (`api/v1/jobs.py:136-143`)
    # recomputed directly here rather than imported — L6's own precedent already rejected an
    # api-layer-to-scheduler cross-import for a similarly small query. Bucketed into open/done
    # using the same `TERMINAL_FOR_BINDING` split `_loop_stop_reason` above already uses to decide
    # whether this loop's queue is empty, rather than a second, differently-drawn line.
    counts_result = await session.execute(
        select(Task.status, func.count()).where(Task.loop_id == loop.id).group_by(Task.status)
    )
    open_count = 0
    done_count = 0
    for task_status, count in counts_result.all():
        if task_status in TERMINAL_FOR_BINDING:
            done_count += count
        else:
            open_count += count
    lines.append(f"Queue: {open_count} open, {done_count} done")
    lines.append("")

    return "\n".join(lines)


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

            loop_result = await session.execute(select(Loop).where(Loop.job_id == job.id))
            loop = loop_result.scalars().first()
            # Design D11 (task A2.2): stage-apply any pending edit in memory before the stop check
            # below and before the briefing is composed further down — both must see this loop's
            # current definition, not one still waiting on the firing after next. The audit event
            # is emitted only after this branch's own commit lands `run`'s final status (below),
            # not here — see `_stage_pending_loop_edit`'s own comment for why.
            pending_edit_payload = _stage_pending_loop_edit(loop) if loop is not None else None

            loop_stop_reason = await _loop_stop_reason(session, job)
            if loop_stop_reason:
                run.status = "skipped"
                run.error_summary = loop_stop_reason
                if loop is not None:
                    loop.stop_reason = loop_stop_reason
                    loop.stopped_at = fired_at
                    # D17/B2.5: the same string `_loop_stop_reason` returns for a drained queue,
                    # already the trigger for `loop_queue_exhausted` below — the one place this
                    # value is known, so it is set here rather than re-derived by a reader later.
                    loop.ending_state = (
                        "completed" if loop_stop_reason == "loop queue is empty" else "stopped"
                    )
                job.enabled = False
                await session.commit()
                if pending_edit_payload is not None:
                    await _emit_loop_edit_applied(session, pending_edit_payload)
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
                    session,
                    job.project_id,
                    "loop_stopped",
                    loop_stopped_payload,
                    agent=job.agent,
                    loop_id=loop.id if loop is not None else None,
                )
                await sse_manager.broadcast(job.project_id, "loop_stopped", loop_stopped_payload)
                if loop is not None and loop_stop_reason == "loop queue is empty":
                    # A second, independent event (design D6) — "the queue is empty" and "was a
                    # request in flight when it emptied" are two facts a reader should not have to
                    # parse out of one payload. `loop_stopped` above is unchanged by this branch.
                    pending_request = await _pending_loop_request(
                        session, job, loop, exclude_run_id=run_id
                    )
                    loop_queue_exhausted_payload = {
                        "job_id": job.id,
                        "loop_id": loop.id,
                        "pending_request": pending_request,
                    }
                    await persist_event(
                        session,
                        job.project_id,
                        "loop_queue_exhausted",
                        loop_queue_exhausted_payload,
                        agent=job.agent,
                        loop_id=loop.id,
                    )
                    await sse_manager.broadcast(
                        job.project_id, "loop_queue_exhausted", loop_queue_exhausted_payload
                    )
                # Remove from the live scheduler so it does not fire again next cron tick only to be
                # skipped again — the same call `remove_job` already makes for a job an operator
                # disables by hand.
                await self.remove_job(job.id)
                logger.info(f"Job {job.id} loop stopped: {loop_stop_reason}")
                return False

            content = job.message
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
                prior_checkpoint = await latest_checkpoint_for_loop(session, loop.id)
                briefing = await _compose_loop_briefing(
                    session, loop, claimed_task, prior_checkpoint
                )
                content = f"{briefing}\n{job.message}"

            entry = new_entry(
                project_id=job.project_id,
                agent=job.agent,
                origin_type="job",
                content=content,
                hop_depth=0,
                session_mode=job.session_mode,
                session_id=resume_session_id,
                conversation_id=conversation.id,
            )
            session.add(entry)
            # The firing genuinely becomes "in progress" here, not at `JobRun` creation above —
            # `status="fired"` there only means "successfully enqueued"; every early-return
            # above this point (skip, loop-stopped) overwrites it with `"skipped"` first, so
            # only a firing that actually reaches a queued entry ever becomes "in_progress"
            # (design D13, task A4.3). `finalize_job_run_for_conversation` flips it to a
            # terminal status once the agent's own `Run` ends (`agent_trigger.py`).
            run.status = "in_progress"
            await session.commit()

            if pending_edit_payload is not None:
                await _emit_loop_edit_applied(session, pending_edit_payload)

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
