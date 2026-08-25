"""`loop-notices-and-reacts` group 1 — a firing is refused while its loop's agent is running.

The measured failure (proposal §1): five firings during one live turn produced five queued entries
and five `JobRun`s, which the agent then drains as five separate turns all briefed on the same
task. `schedule_agent` does refuse to *start* a second turn (`turn_scheduler.py:44`), but by then
the firing has already claimed and queued — the refusal happens one step too late to prevent the
work, and turning the cron *up* multiplies the waste.

Design D4 puts the guard before the claim and before `new_entry`, and has it record **nothing at
all**: no `JobRun`, no event. A busy tick carries no information the `in_progress` `JobRun` does
not already carry, and writing one would both duplicate that fact and evict real history through
`_prune_job_history`'s 100-row window.

**Scoped to loops deliberately.** The requirement says "A loop's agent runs one turn at a time",
and a plain scheduled job is a different thing: its message is a standing instruction that is still
true when the agent frees up, so queuing it is the inbound queue working as designed. A loop's
briefing is not — it re-briefs the same claimed task, and a second copy is stale before it is read.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, JobRun, Loop, Run, Task
from hub.scheduler import JobScheduler

pytestmark = pytest.mark.asyncio


async def _make_loop_job(db, *, suffix, agent="busy-agent"):
    job = AIJob(
        id=f"job-busy-{suffix}",
        project_id="proj-test",
        name=f"Busy {suffix}",
        agent=agent,
        message="hello from a scheduled job",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-busy-{suffix}", project_id="proj-test", job_id=job.id, purpose="busy probe"
    )
    db.add(loop)
    await db.commit()
    task = Task(
        id=f"task-busy-{suffix}",
        project_id="proj-test",
        title=f"work for {suffix}",
        status="pending",
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return job, loop, task


async def _running_turn(db, *, agent, suffix):
    """A `Run` in `running` — the exact state `schedule_agent` refuses a second turn for."""
    run = Run(
        id=f"run-busy-{suffix}",
        project_id="proj-test",
        agent=agent,
        status="running",
    )
    db.add(run)
    await db.commit()
    return run


async def _counts(db, *, job_id, agent):
    entries = await db.scalar(
        select(func.count()).select_from(InboundQueueEntry).where(InboundQueueEntry.agent == agent)
    )
    runs = await db.scalar(select(func.count()).select_from(JobRun).where(JobRun.job_id == job_id))
    return entries, runs


# ---------------------------------------------------------------------------
# 1.1 — the measured failure
# ---------------------------------------------------------------------------


async def test_five_firings_during_one_turn_queue_nothing_and_record_nothing(app):
    """The proposal's measurement, as an assertion. Before the guard this produces five of each.

    Asserts the queue entries *directly* rather than inferring them from a `JobRun` status, which
    is task 7.4's requirement applied to the case it was written for.
    """
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="five")
        await _running_turn(db, agent="busy-agent", suffix="five")

    scheduler = JobScheduler()
    outcomes = []
    for _ in range(5):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            outcomes.append(
                await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
            )

    async with async_session_factory() as db:
        entries, runs = await _counts(db, job_id=job.id, agent="busy-agent")
        # Counts first: they are the observable damage, and the return value is only how the
        # firing reports it. Asserted in this order so a regression names the number it produced.
        assert entries == 0, f"a refused firing must queue no input; got {entries}"
        assert runs == 0, f"a busy refusal writes no execution record (D4); got {runs}"
        assert outcomes == [False] * 5

        fresh_task = await db.get(Task, task.id)
        assert fresh_task.status == "pending", "a refused firing leaves task status untouched"
        assert fresh_task.assignee is None, "a refused firing assigns nobody"


async def test_the_job_stays_enabled_and_keeps_its_schedule(app):
    """1.5, and the difference between *refused* and *stopped*: the operator resolving the
    condition must be enough, with no further action. `next_run` still advances — a refused firing
    that left `next_run` in the past would be its own lie (the note `_do_fire_job` already carries
    about `job.last_run`)."""
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="enabled")
        await _running_turn(db, agent="busy-agent", suffix="enabled")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert await scheduler._fire_job_internal(fresh_job, "scheduled", session=db) is False

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert fresh_job.enabled is True
        assert fresh_job.next_run is not None, "the schedule must still advance"
        assert fresh_job.run_count == 0, "a refused firing is not a run"
        assert fresh_job.last_run is None


async def test_a_busy_refusal_does_not_stamp_the_loop_as_stopped(app):
    """Busy is not a stop condition. A loop that acquires a `stop_reason` here would need an
    operator to restart it, which is precisely what `remove_job` cannot undo."""
    async with async_session_factory() as db:
        job, loop, _task = await _make_loop_job(db, suffix="notstopped")
        await _running_turn(db, agent="busy-agent", suffix="notstopped")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        await scheduler._fire_job_internal(fresh_job, "scheduled", session=db)

    async with async_session_factory() as db:
        fresh_loop = await db.get(Loop, loop.id)
        assert fresh_loop.stop_reason is None
        assert fresh_loop.stopped_at is None
        assert fresh_loop.ending_state is None


# ---------------------------------------------------------------------------
# 1.2 — it refuses, it does not disable
# ---------------------------------------------------------------------------


async def test_a_firing_after_the_turn_ends_claims_normally(app):
    """The guard's other half. A refusal that outlived its cause would be a stall dressed as a
    guard, so this is what proves it is conditional rather than a switch."""
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="after")
        run = await _running_turn(db, agent="busy-agent", suffix="after")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        assert await scheduler._fire_job_internal(fresh_job, "scheduled", session=db) is False

    # The turn ends.
    async with async_session_factory() as db:
        finished = await db.get(Run, run.id)
        finished.status = "completed"
        await db.commit()

    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        # No runner is bound, so the firing will not reach a spawned agent — but it must get past
        # the guard and claim, which is what this asserts. The claim is observable on the task.
        await scheduler._fire_job_internal(fresh_job, "scheduled", session=db)

    async with async_session_factory() as db:
        fresh_task = await db.get(Task, task.id)
        assert fresh_task.status != "pending", (
            "once the agent is free the firing must reach the claim; the task should have been "
            "moved out of pending by it"
        )
        assert fresh_task.assignee == "busy-agent"


async def test_a_run_for_another_agent_does_not_refuse_this_loop(app):
    """The guard is per agent. Two loops owned by different agents must not block each other —
    a project-wide reading would make a busy project look like a stopped one."""
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="other", agent="quiet-agent")
        await _running_turn(db, agent="somebody-else", suffix="other")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        await scheduler._fire_job_internal(fresh_job, "scheduled", session=db)

    async with async_session_factory() as db:
        fresh_task = await db.get(Task, task.id)
        assert (
            fresh_task.assignee == "quiet-agent"
        ), "another agent's running turn must not refuse this loop's firing"
