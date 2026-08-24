"""`loop-notices-and-reacts` task 7.4 — no refusal, of any kind, queues input for an agent.

The three refusals a firing can make are written in three different places and were added at three
different times: the stop condition (2026-08-16), the stalled queue (2026-08-20) and the busy agent
(this change). Each has its own tests, and each of those tests asserts a *different* observable —
`job.enabled`, a `skipped` `JobRun`, a tick count. None of that is the thing an operator would
actually notice going wrong.

What they would notice is a queued briefing: a refused firing that leaves an `InboundQueueEntry`
behind hands the agent a turn's worth of instructions about work it was just told not to do, and
the agent runs it the next time it drains its queue. The refusal has happened and the work happens
anyway, later, out of order.

So this file asserts the one fact across all three routes, **directly on the row rather than
inferred from a `JobRun` status** — which is exactly what task 7.4 asks for, and is not a
formality: `JobRun` and `InboundQueueEntry` are written at different points in `_do_fire_job`, so
"no run recorded" and "no input queued" are genuinely independent claims. The busy route was the
one measured to break this (five firings, five entries); the other two are asserted here so that a
future reordering of the function cannot quietly break them without a test noticing.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, Loop, Run, Task
from hub.scheduler import JobScheduler

pytestmark = pytest.mark.asyncio


async def _loop_job(db, *, suffix, agent, stop_when_queue_empties=False):
    job = AIJob(
        id=f"job-refuse-{suffix}",
        project_id="proj-test",
        name=f"Refusal {suffix}",
        agent=agent,
        message="the standing instruction",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-refuse-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"refusal probe {suffix}",
        stop_when_queue_empties=stop_when_queue_empties,
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _task(db, *, suffix, loop_id, status):
    db.add(
        Task(
            id=f"task-refuse-{suffix}",
            project_id="proj-test",
            title=f"work {suffix}",
            status=status,
            loop_id=loop_id,
        )
    )
    await db.commit()


async def _queued_for(agent):
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count())
            .select_from(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent)
        )


async def _fire(scheduler, job_id):
    async with async_session_factory() as db:
        fresh = await db.get(AIJob, job_id)
        return await scheduler._fire_job_internal(fresh, trigger="scheduled", session=db)


async def test_a_stalled_queue_refusal_queues_no_input(app):
    """Every non-terminal task unclaimable — the 2026-08-20 route."""
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="stalled", agent="refuse-stalled")
        await _task(db, suffix="stalled", loop_id=loop.id, status="completed")

    scheduler = JobScheduler()
    assert await _fire(scheduler, job.id) is False
    assert await _queued_for("refuse-stalled") == 0


async def test_a_stop_condition_refusal_queues_no_input(app):
    """The queue drained and the loop asked to stop when it did — the 2026-08-16 route.

    Distinct from the stall above in what it does to the job (this one disables it), and that is
    the point: the two branches leave `_do_fire_job` at different places, so the absence of a
    queued entry has to be true of both exits and not just the one that keeps polling.
    """
    async with async_session_factory() as db:
        job, loop = await _loop_job(
            db, suffix="stopped", agent="refuse-stopped", stop_when_queue_empties=True
        )
        await _task(db, suffix="stopped", loop_id=loop.id, status="approved")

    scheduler = JobScheduler()
    assert await _fire(scheduler, job.id) is False
    assert await _queued_for("refuse-stopped") == 0

    async with async_session_factory() as db:
        assert (await db.get(AIJob, job.id)).enabled is False


async def test_a_busy_agent_refusal_queues_no_input(app):
    """The measured failure, restated here so all three routes are asserted in one place.

    `test_loop_busy_guard.py` covers this route in depth; the value of repeating it is that this
    file fails as a group if the queue-entry guarantee is ever weakened for one route while the
    others still hold, rather than looking like an isolated regression in the busy tests.
    """
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="busy", agent="refuse-busy")
        await _task(db, suffix="busy", loop_id=loop.id, status="pending")
        db.add(
            Run(
                id="run-refuse-busy",
                project_id="proj-test",
                agent="refuse-busy",
                status="running",
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    assert await _fire(scheduler, job.id) is False
    assert await _queued_for("refuse-busy") == 0

    async with async_session_factory() as db:
        assert (await db.get(Task, "task-refuse-busy")).status == "pending"


async def test_a_firing_that_proceeds_does_queue_input(app):
    """The positive control, without which the three tests above prove nothing.

    Every one of them asserts a count is zero, and a count is also zero when the mechanism that
    would make it non-zero is absent for some unrelated reason — a fixture that never wires the
    agent up, a `new_entry` call that moved. Measured before this was written: an otherwise
    identical firing with a claimable task and a free agent produces exactly **1** entry, with no
    runner bound and therefore no agent spawned. So the entry is created strictly before the
    launch path, the counter observes the thing it claims to, and the three zeros above are the
    refusals doing their work rather than the harness failing to reach it.
    """
    async with async_session_factory() as db:
        job, loop = await _loop_job(db, suffix="proceeds", agent="refuse-proceeds")
        await _task(db, suffix="proceeds", loop_id=loop.id, status="pending")

    scheduler = JobScheduler()
    await _fire(scheduler, job.id)
    assert await _queued_for("refuse-proceeds") == 1
