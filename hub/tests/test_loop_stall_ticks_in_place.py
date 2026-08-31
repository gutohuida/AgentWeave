"""`loop-notices-and-reacts` group 2 — a repeated stall counts in place instead of appending.

`JobRun` feeds the last-ten-runs view and the "is this loop running" check. A loop whose queue is
stalled writes one row per tick saying the same thing, so at the five-minute cadence this change
adopts it buries the firings that did work under twelve identical rows an hour and a healthy loop
reads as dead.

Design D6: one row for the stall, and each subsequent refusal for *the same* stall increments a
count on it. The precedent is `InboundQueueEntry.delivery_attempts`, which chose a counter over
duplicate rows for the identical problem.

"The same stall" is defined narrowly on purpose — the most recent `JobRun` for this job is a stall
record **and** its reason is unchanged. A stall whose reason changes starts a new row, so a stall
that changes shape stays visible rather than hiding inside a growing number.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, JobRun, Loop, Task
from hub.scheduler import JobScheduler

pytestmark = pytest.mark.asyncio


async def _stalled_loop(db, *, suffix, agent="stall-agent"):
    """A loop whose queue is stalled: an open task in a status no firing may claim.

    `completed` is the canonical case — it is in neither `CLAIMABLE_LOOP_TASK_STATUSES` nor the
    terminal set, so the queue is neither claimable nor drained. This is the exact shape
    `test_loop_whose_tasks_are_all_completed_but_unapproved_spins` reproduced on 2026-08-20.
    """
    job = AIJob(
        id=f"job-stall-{suffix}",
        project_id="proj-test",
        name=f"Stall {suffix}",
        agent=agent,
        message="hello",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-stall-{suffix}", project_id="proj-test", job_id=job.id, purpose="stall probe"
    )
    db.add(loop)
    await db.commit()
    task = Task(
        id=f"task-stall-{suffix}",
        project_id="proj-test",
        title=f"awaiting review {suffix}",
        status="completed",
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return job, loop, task


async def _fire(scheduler, job_id, times=1):
    for _ in range(times):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job_id)
            await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)


async def _runs(db, job_id):
    return (
        (
            await db.execute(
                select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.fired_at.asc())
            )
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# 2.1 — one row, counted
# ---------------------------------------------------------------------------


async def test_repeated_refusals_for_one_stall_produce_one_row_that_counts_them(app):
    async with async_session_factory() as db:
        job, _loop, _task = await _stalled_loop(db, suffix="count")

    scheduler = JobScheduler()
    await _fire(scheduler, job.id, times=5)

    async with async_session_factory() as db:
        rows = await _runs(db, job.id)
        assert len(rows) == 1, f"one stall is one row; got {len(rows)}"
        assert rows[0].status == "skipped"
        assert (
            rows[0].tick_count == 5
        ), f"the count must equal the number of refused firings; got {rows[0].tick_count}"


async def test_the_first_refusal_writes_a_row_reading_one(app):
    """The boundary the default has to get right: a stall seen once is one firing, not zero."""
    async with async_session_factory() as db:
        job, _loop, _task = await _stalled_loop(db, suffix="first")

    scheduler = JobScheduler()
    await _fire(scheduler, job.id)

    async with async_session_factory() as db:
        rows = await _runs(db, job.id)
        assert len(rows) == 1
        assert rows[0].tick_count == 1


# ---------------------------------------------------------------------------
# 2.2 — a stall that changes shape starts a new row
# ---------------------------------------------------------------------------


async def test_a_stall_whose_reason_changes_starts_a_new_row(app):
    """Incrementing on a *changed* reason would hide the change inside a growing number.

    **How the reason is made to change has moved twice.** It was originally a second unclaimable
    task, which changed the count in the queue's status histogram; F142 made the histogram the reason
    of last resort, so a second task stopped changing anything and the test switched to recording an
    agent as completing the task — which moved the walk from the *no recorded completion* arm into
    the evidence gate.

    `approval-waits-for-the-turn-to-end` (design D5) removes both of those arms for this fixture,
    which builds a **loop**: it declares no document, so its finished work is not reviewed at all and
    the reason names the work waiting for the operator. That sentence counts what it names, so the
    original mechanism is the one that works again — a second finished task genuinely changes what
    the operator is told, from one waiting task to two.
    """
    async with async_session_factory() as db:
        job, loop, _task = await _stalled_loop(db, suffix="reason")

    scheduler = JobScheduler()
    await _fire(scheduler, job.id, times=2)

    async with async_session_factory() as db:
        first_rows = await _runs(db, job.id)
        assert len(first_rows) == 1
        first_reason = first_rows[0].error_summary
        assert "1 finished task is waiting for you to land it" in first_reason
        assert first_rows[0].tick_count == 2

        db.add(
            Task(
                id="task-stall-reason-2",
                project_id="proj-test",
                title="a second finished task",
                status="completed",
                loop_id=loop.id,
            )
        )
        await db.commit()

    await _fire(scheduler, job.id)

    async with async_session_factory() as db:
        rows = await _runs(db, job.id)
        assert len(rows) == 2, "a stall that changes shape must be a new row, not a bigger number"
        assert rows[0].error_summary == first_reason
        assert rows[0].tick_count == 2, "the earlier stall keeps its own count"
        assert rows[1].error_summary != first_reason
        assert "2 finished tasks are waiting for you to land them" in rows[1].error_summary
        assert rows[1].tick_count == 1


# ---------------------------------------------------------------------------
# 2.3 — real firings stay visible in the recent window
# ---------------------------------------------------------------------------


async def test_a_long_stall_does_not_bury_the_firings_that_did_work(app):
    """The reason this change exists. Twenty refusals between two real records must leave the
    real records still present and adjacent, not pushed out by twenty rows of nothing."""
    async with async_session_factory() as db:
        job, loop, task = await _stalled_loop(db, suffix="bury")
        # A real, earlier firing to stand for "work that happened".
        db.add(
            JobRun(
                id="run-stall-earlier",
                job_id=job.id,
                project_id="proj-test",
                status="completed",
                trigger="scheduled",
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    await _fire(scheduler, job.id, times=20)

    async with async_session_factory() as db:
        rows = await _runs(db, job.id)
        assert (
            len(rows) == 2
        ), f"20 refusals must add one row, not twenty; the history holds {len(rows)}"
        assert rows[0].id == "run-stall-earlier", "the real firing is still there"
        assert rows[0].status == "completed"
        assert rows[1].tick_count == 20

        total = await db.scalar(
            select(func.count()).select_from(JobRun).where(JobRun.job_id == job.id)
        )
        assert total == 2


async def test_the_counted_row_keeps_the_time_the_stall_began(app):
    """`fired_at` is not moved forward on an increment.

    Two readings are possible and only one is useful. Keeping the first refusal's timestamp makes
    the row say "this stall started then, and has been re-checked N times since" — and, because
    the history view orders by `fired_at`, lets genuine firings that happen later sort above it.
    Moving it would make a stalled loop's row jump to the top of the list every five minutes,
    which is the burying this change exists to stop, achieved by a different means.
    """
    async with async_session_factory() as db:
        job, _loop, _task = await _stalled_loop(db, suffix="time")

    scheduler = JobScheduler()
    await _fire(scheduler, job.id)
    async with async_session_factory() as db:
        first_fired_at = (await _runs(db, job.id))[0].fired_at

    await _fire(scheduler, job.id, times=3)

    async with async_session_factory() as db:
        rows = await _runs(db, job.id)
        assert len(rows) == 1
        assert rows[0].tick_count == 4
        assert rows[0].fired_at == first_fired_at, "an increment must not move the stall's start"


# ---------------------------------------------------------------------------
# 2.7 — the count reaches the API
# ---------------------------------------------------------------------------


async def test_the_history_endpoint_reports_the_tick_count(app, auth_headers):
    async with async_session_factory() as db:
        job, _loop, _task = await _stalled_loop(db, suffix="api")

    scheduler = JobScheduler()
    await _fire(scheduler, job.id, times=3)

    resp = await app.get(f"/api/v1/projects/proj-test/jobs/{job.id}/history", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["tick_count"] == 3
    assert rows[0]["status"] == "skipped"
