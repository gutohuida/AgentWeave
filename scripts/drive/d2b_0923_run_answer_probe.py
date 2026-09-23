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


async def test_r2_a_firing_that_raises_before_its_row_exists(
    app, auth_headers, bind_runner, live_scheduler
):
    """R2 (D-3b): a decline R1's table did not list. `_do_fire_job`'s `except` marks `run` failed
    only `if "run" in locals()`; an exception raised before the row is built writes nothing, so the
    route meets an earlier firing's row exactly as it does after an in-flight decline."""
    from unittest.mock import patch

    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="r2raise", agent=OWNER)
        job.session_mode = "resume"
        job.last_session_id = "sess-r2raise"
        db.add(
            JobRun(
                id="jobrun-r2raise-earlier",
                job_id=job.id,
                project_id=PROJECT,
                fired_at=datetime.now(timezone.utc) - timedelta(hours=1),
                status="skipped",
                trigger="scheduled",
                error_summary="loop queue is stalled: 1 still awaiting a prerequisite's approval",
                requested_by_run_id="run-r2-sentinel",
            )
        )
        await db.commit()

    async def _boom(*_a, **_k):
        raise RuntimeError("r2 probe: resume lookup failed")

    with patch("hub.scheduler.conversation_for_provider_session", _boom):
        await _press(app, auth_headers, job.id)
    async with async_session_factory() as db:
        from sqlalchemy import select

        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        print(
            f"[r2raise] rows={[(r.id, r.status, r.tick_count, r.requested_by_run_id) for r in rows]}"
        )


async def test_r2_requester_sentinel_survives_a_counted_stall(
    app, auth_headers, bind_runner, live_scheduler
):
    """R2: an operator press carries no run identity, so "the requester is unchanged" is vacuous
    unless the earlier row holds a value a press could overwrite. Seed one and press again."""
    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="r2sent", agent=OWNER)
        task.status = "blocked"
        await db.commit()
    await _press(app, auth_headers, job.id)
    async with async_session_factory() as db:
        from sqlalchemy import select

        row = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().one()
        print(f"[r2sent] after first press requested_by={row.requested_by_run_id!r}")
        row.requested_by_run_id = "run-r2-sentinel"
        await db.commit()
    await _press(app, auth_headers, job.id)
    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        print(f"[r2sent] rows={[(r.id, r.tick_count, r.requested_by_run_id) for r in rows]}")


async def test_r2_a_firing_that_raises_after_its_turn_started(
    app, auth_headers, bind_runner, live_scheduler
):
    """R2: the route's own advice is "ask the route what it returns when the function it calls
    raises". Here the firing writes its row, the turn starts, and a later step raises: the row reads
    `failed`, and the route re-decides the loop before reading it."""
    from unittest.mock import patch

    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="r2late", agent=OWNER)

    async def _start_then_raise(project_id, agent):
        async with async_session_factory() as db:
            await _running_turn(db, agent=agent, suffix="r2late")
        raise RuntimeError("r2 probe: failed after the turn started")

    # Not `_press`: its `_no_spawn` patches the same name and would shadow this one.
    with patch("hub.turn_scheduler.schedule_agent", _start_then_raise):
        res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)
    print(f"\n[{job.id}] {res.status_code} {res.text}")
    async with async_session_factory() as db:
        from sqlalchemy import select

        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        t = await db.get(Task, task.id)
        print(
            f"[r2late] rows={[(r.status, r.error_summary) for r in rows]} task={t.status}/{t.assignee}"
        )


async def test_r2_a_terminal_schedule_failure(app, auth_headers, bind_runner, live_scheduler):
    """R2, adjacent: `schedule_agent` reports that no turn began (`terminal_failure`). The firing
    marks its row `failed` and still returns `True`, so the route takes the success branch."""
    from unittest.mock import AsyncMock, patch

    from hub.turn_scheduler import ScheduleResult

    await _roster(app, auth_headers, bind_runner, OWNER)
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="r2term", agent=OWNER)
    refused = ScheduleResult(waiting_reason="r2 probe: runner refused", terminal_failure=True)
    with patch("hub.turn_scheduler.schedule_agent", AsyncMock(return_value=refused)):
        res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)
    print(f"\n[{job.id}] {res.status_code} {res.text}")
    async with async_session_factory() as db:
        from sqlalchemy import select

        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()
        print(f"[r2term] rows={[(r.status, r.error_summary) for r in rows]}")


async def _f373_staging(db, suffix, *, earlier=True):
    """F373's flow: its only task `in_progress` under the busy owner, a sibling free, so the busy
    guard passes and the walk finds everything in flight."""
    job, loop, task = await _make_loop_job(db, suffix=suffix, agent=OWNER)
    await _declare_document(db, loop, suffix)
    task.status = "in_progress"
    task.assignee = OWNER
    if earlier:
        db.add(
            JobRun(
                id=f"jobrun-{suffix}-earlier",
                job_id=job.id,
                project_id=PROJECT,
                fired_at=datetime.now(timezone.utc) - timedelta(hours=1),
                status="skipped",
                trigger="scheduled",
                error_summary="loop queue is stalled: 1 still awaiting a prerequisite's approval",
                requested_by_run_id="run-r3-sentinel",
            )
        )
    await db.commit()
    await _running_turn(db, agent=OWNER, suffix=suffix)
    return job, loop, task


async def _rows_and_events(job_id, tag):
    from sqlalchemy import select

    from hub.db.models import EventLog

    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
        events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "job_run_failed")))
            .scalars()
            .all()
        )
        print(
            f"[{tag}] rows={[(r.id, r.status, r.tick_count, r.requested_by_run_id) for r in rows]} "
            f"job_run_failed={[e.data for e in events if (e.data or {}).get('job_id') == job_id]}"
        )


async def test_r3_a_firing_that_raises_before_its_row_on_an_in_flight_flow(
    app, auth_headers, bind_runner, live_scheduler
):
    """R3 (D-4b): R2's pre-row crash, on a flow whose work is in flight. The route cannot tell a
    crash that wrote nothing from an in-flight decline that wrote nothing, so D3's fallthrough
    re-decides the loop -- which D3 forbids only where a row exists."""
    from unittest.mock import patch

    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop, _task = await _f373_staging(db, "r3raise", earlier=False)
        job.session_mode = "resume"
        job.last_session_id = "sess-r3raise"
        await db.commit()

    async def _boom(*_a, **_k):
        raise RuntimeError("r3 probe: resume lookup failed")

    with patch("hub.scheduler.conversation_for_provider_session", _boom):
        await _press(app, auth_headers, job.id)
    await _rows_and_events(job.id, "r3raise")


async def test_r3_a_firing_that_raises_before_its_row_on_a_busy_loop(
    app, auth_headers, bind_runner, live_scheduler
):
    """R3: the same crash where the owner is mid-turn. The crash is before the firing's own guard,
    so the route's re-ask is the first time the guard is asked at all."""
    from unittest.mock import patch

    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="r3busy", agent=OWNER)
        job.session_mode = "resume"
        job.last_session_id = "sess-r3busy"
        await db.commit()
        await _running_turn(db, agent=OWNER, suffix="r3busy")

    async def _boom(*_a, **_k):
        raise RuntimeError("r3 probe: resume lookup failed")

    with patch("hub.scheduler.conversation_for_provider_session", _boom):
        await _press(app, auth_headers, job.id)
    await _rows_and_events(job.id, "r3busy")


async def test_r3_a_firing_that_raises_after_discarding_its_row(
    app, auth_headers, bind_runner, live_scheduler
):
    """R3: the in-flight branch discards `run` and commits, then emits the staged loop edit. If
    that raises, `"run" in locals()` is true for a row that no longer exists."""
    from unittest.mock import patch

    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, loop, _task = await _f373_staging(db, "r3disc", earlier=False)
        loop.pending_edit_at = datetime.now(timezone.utc)
        loop.pending_purpose = "r3 probe: a staged purpose"
        await db.commit()

    async def _boom(*_a, **_k):
        raise RuntimeError("r3 probe: edit audit failed")

    with patch("hub.scheduler._emit_loop_edit_applied", _boom):
        await _press(app, auth_headers, job.id)
    await _rows_and_events(job.id, "r3disc")


async def test_r3_a_concurrent_ticks_row_is_not_a_failure(
    app, auth_headers, bind_runner, live_scheduler
):
    """R3: `wrote_row` is true for any row that appears between the route's two reads. Simulate a
    cron tick that fired (`in_progress`) while the press itself was refused by the busy guard."""
    from unittest.mock import patch

    from hub.scheduler import JobScheduler

    await _roster(app, auth_headers, bind_runner, OWNER, FREE)
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="r3tick", agent=OWNER)
        await _running_turn(db, agent=OWNER, suffix="r3tick")

    async def _tick_then_refuse(self, fired_job, trigger="scheduled", session=None):
        async with async_session_factory() as other:
            other.add(
                JobRun(
                    id="jobrun-r3tick-cron",
                    job_id=fired_job.id,
                    project_id=PROJECT,
                    fired_at=datetime.now(timezone.utc),
                    status="in_progress",
                    trigger="scheduled",
                )
            )
            await other.commit()
        return False

    with patch.object(JobScheduler, "_fire_job_internal", _tick_then_refuse):
        await _press(app, auth_headers, job.id)
    await _rows_and_events(job.id, "r3tick")
