"""D-2b probe, 2026-09-23 (day window): what `POST /jobs/{id}/run` answers for F400 and F373.

Throwaway. Kept as `scripts/drive/d2b_0923_run_answer_probe.py`, which pytest does not collect;
copy it back under `hub/tests/` to re-run it. Asserts nothing about the right answer -- it prints
what the route answers today, so R2/R3 can re-measure after reading the code themselves.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import JobRun, SpecDocument, Task

from .test_a_task_nothing_will_move_holds_nobody import _no_spawn, live_scheduler  # noqa: F401
from .test_loop_busy_guard import _make_loop_job, _running_turn
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"
OWNER = "probe-owner"
FREE = "probe-free"


async def _declare_document(db, loop, suffix):
    db.add(
        SpecDocument(
            id=f"doc-probe-{suffix}",
            project_id=PROJECT,
            path=f"spec/probe-{suffix}.html",
            title=f"Probe {suffix}",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()
    loop.spec_document_id = f"doc-probe-{suffix}"
    await db.commit()


async def _press(app, auth_headers, job_id):
    with _no_spawn():
        res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job_id}/run", headers=auth_headers)
    print(f"\n[{job_id}] {res.status_code} {res.text}")
    return res


async def _board(job_id):
    from hub.api.v1.jobs import _batch_loop_summaries

    async with async_session_factory() as db:
        summary = (await _batch_loop_summaries(db, [job_id]))[job_id]
    print(f"[{job_id}] board stall_reason={summary.stall_reason!r}")
    return summary


async def test_f400_documentless_open_task_sibling_free(
    app, auth_headers, bind_runner, live_scheduler
):
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, loop, _task = await _make_loop_job(db, suffix="f400a", agent=OWNER)
        await _running_turn(db, agent=OWNER, suffix="f400a")
        from hub.scheduler import decide_firing

        decision = await decide_firing(db, loop, default_agent=OWNER)
        print(f"\n[f400a] decision.kind={decision.kind} stall={decision.stall_reason!r}")
    await _board(job.id)
    await _press(app, auth_headers, job.id)


async def test_f400_documentless_empty_queue(app, auth_headers, bind_runner, live_scheduler):
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="f400b", agent=OWNER)
        await db.delete(task)
        await db.commit()
        await _running_turn(db, agent=OWNER, suffix="f400b")
    await _press(app, auth_headers, job.id)


async def test_f400_flow_open_task_nobody_free(app, auth_headers, bind_runner, live_scheduler):
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, loop, _task = await _make_loop_job(db, suffix="f400c", agent=OWNER)
        await _declare_document(db, loop, "f400c")
        await _running_turn(db, agent=OWNER, suffix="f400c")
    await _press(app, auth_headers, job.id)


async def test_f373_in_flight_after_an_earlier_skipped_row(
    app, auth_headers, bind_runner, live_scheduler
):
    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, loop, task = await _make_loop_job(db, suffix="f373", agent=OWNER)
        await _declare_document(db, loop, "f373")
        task.status = "in_progress"
        task.assignee = OWNER
        db.add(
            JobRun(
                id="jobrun-f373-earlier",
                job_id=job.id,
                project_id=PROJECT,
                fired_at=datetime.now(timezone.utc) - timedelta(hours=1),
                status="skipped",
                trigger="scheduled",
                error_summary="loop queue is stalled: 1 still awaiting a prerequisite's approval",
            )
        )
        await db.commit()
        await _running_turn(db, agent=OWNER, suffix="f373")
    await _press(app, auth_headers, job.id)
    async with async_session_factory() as db:
        row = await db.get(JobRun, "jobrun-f373-earlier")
        print(
            f"[f373] earlier row tick_count={row.tick_count} requested_by={row.requested_by_run_id}"
        )


async def test_f373_control_a_continuing_stall(app, auth_headers, bind_runner, live_scheduler):
    """A genuine continuing stall: the route must still answer from the counted row."""
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="f373c", agent=OWNER)
        task.status = "blocked"
        await db.commit()
    first = await _press(app, auth_headers, job.id)
    second = await _press(app, auth_headers, job.id)
    async with async_session_factory() as db:
        from sqlalchemy import select

        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        print(f"[f373c] rows={[(r.id, r.status, r.tick_count, r.error_summary) for r in rows]}")
    assert first.status_code == second.status_code
    _ = Task


async def test_f373_identity_map_mutates_the_earlier_row_in_place(
    app, auth_headers, bind_runner, live_scheduler
):
    """The route passes its own session to `_fire_job_internal`, so a counted stall increments the
    very object the route read before firing: compare against a snapshot, not the object."""
    from hub.api.v1.jobs import _newest_job_run
    from hub.db.models import AIJob
    from hub.scheduler import JobScheduler

    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="f373i", agent=OWNER)
        task.status = "blocked"
        await db.commit()
    await _press(app, auth_headers, job.id)  # writes the first stall row
    async with async_session_factory() as db:
        fresh = await db.get(AIJob, job.id)
        earlier = await _newest_job_run(db, job.id)
        snapshot = earlier.tick_count
        with _no_spawn():
            await JobScheduler()._fire_job_internal(fresh, trigger="manual", session=db)
        latest = await _newest_job_run(db, job.id)
        print(
            f"\n[f373i] same_object={latest is earlier} snapshot={snapshot} "
            f"earlier_now={earlier.tick_count} latest={latest.tick_count}"
        )
