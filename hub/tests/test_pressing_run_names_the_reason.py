"""`pressing-run-names-the-reason-that-held` — pressing Run names the condition that refused, and
answers from a record only where this press wrote it or counted into it.

Route cases (tasks 1.1-1.5, 1.7-1.9a, 1.12-1.14) and the guard's unit cases (1.10). The two
assertions in `test_board_agent_role.py` that moved with design D2 are task 1.6.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import JobRun, Run, SpecDocument, Task
from hub.scheduler import (
    BUSY_EMPTY_QUEUE,
    BUSY_LOOP_SCOPE,
    BUSY_NO_FREE_AGENT,
    JobScheduler,
    LoopBusyRefusal,
    _loop_flow_busy_reason,
    _loop_flow_busy_refusal,
)

from .test_a_task_nothing_will_move_holds_nobody import _no_spawn
from .test_loop_busy_guard import _make_loop_job, _running_turn
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"
SCOPE = "this loop's work goes only to"
ROSTER_CLAUSE = "no other agent is free"


@pytest.fixture
def live_scheduler(monkeypatch):
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _declare_document(db, loop, suffix):
    db.add(
        SpecDocument(
            id=f"doc-press-{suffix}",
            project_id=PROJECT,
            path=f"spec/press-{suffix}.html",
            title=f"Press {suffix}",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()
    loop.spec_document_id = f"doc-press-{suffix}"
    await db.commit()


async def _run(app, auth_headers, job):
    return await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)


async def _rows(job_id):
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
        )


async def _seed_row(job_id, *, status, reason, ticks=1):
    async with async_session_factory() as db:
        db.add(
            JobRun(
                id=f"jobrun-press-{job_id}",
                job_id=job_id,
                project_id=PROJECT,
                fired_at=datetime.now(timezone.utc) - timedelta(hours=1),
                status=status,
                trigger="scheduled",
                error_summary=reason,
                tick_count=ticks,
                requested_by_run_id="run-sentinel",
            )
        )
        await db.commit()


# --- D2: one clause per condition -------------------------------------------------------


async def test_documentless_open_task_with_a_sibling_free_names_the_scope(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.1 (F400)."""
    await _roster(app, auth_headers, bind_runner, "press-owner", "press-sibling")
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="press-1", agent="press-owner")
        await _running_turn(db, agent="press-owner", suffix="press-1")
    with _no_spawn():
        res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "press-owner is already running a turn" in detail
    assert f"{SCOPE} press-owner, the agent its job names" in detail
    assert "Nothing was started" in detail
    assert ROSTER_CLAUSE not in detail


async def test_documentless_open_task_alone_on_the_roster_names_the_scope(
    app, auth_headers, live_scheduler
):
    """1.2."""
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="press-2", agent="press-solo")
        await _running_turn(db, agent="press-solo", suffix="press-2")
    res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert SCOPE in detail
    assert ROSTER_CLAUSE not in detail


async def test_documentless_empty_queue_names_only_the_empty_queue(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.3."""
    await _roster(app, auth_headers, bind_runner, "press-owner3", "press-sibling3")
    async with async_session_factory() as db:
        job, _loop, task = await _make_loop_job(db, suffix="press-3", agent="press-owner3")
        await db.delete(task)
        await db.commit()
        await _running_turn(db, agent="press-owner3", suffix="press-3")
    with _no_spawn():
        res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "this loop's queue holds no open task" in detail
    assert "for another agent to take" not in detail
    assert ROSTER_CLAUSE not in detail
    assert SCOPE not in detail


async def test_a_flows_empty_queue_keeps_its_sentence(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.4, control."""
    await _roster(app, auth_headers, bind_runner, "press-owner4", "press-sibling4")
    async with async_session_factory() as db:
        job, loop, task = await _make_loop_job(db, suffix="press-4", agent="press-owner4")
        await _declare_document(db, loop, "4")
        await db.delete(task)
        await db.commit()
        await _running_turn(db, agent="press-owner4", suffix="press-4")
    with _no_spawn():
        res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    assert res.json()["detail"] == (
        "press-owner4 is already running a turn, and this loop's queue holds no open task "
        "for another agent to take. Nothing was started."
    )


async def test_a_flow_with_nobody_free_keeps_its_sentence(app, auth_headers, live_scheduler):
    """1.5, control."""
    async with async_session_factory() as db:
        job, loop, _task = await _make_loop_job(db, suffix="press-5", agent="press-owner5")
        await _declare_document(db, loop, "5")
        await _running_turn(db, agent="press-owner5", suffix="press-5")
    res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail.endswith(
        "and no other agent is free to take this loop's work. Nothing was started."
    )
    assert "goes only to" not in detail


# --- D1: the guard's labelled answer ----------------------------------------------------


async def test_the_refusal_carries_the_condition(app, auth_headers, bind_runner):
    """1.10."""
    await _roster(app, auth_headers, bind_runner, "press-owner10")
    async with async_session_factory() as db:
        job, loop, _task = await _make_loop_job(db, suffix="press-10", agent="press-owner10")
        assert await _loop_flow_busy_refusal(db, loop, job.agent) is None  # idle
        assert await _loop_flow_busy_reason(db, loop, job.agent) is None
        await _running_turn(db, agent="press-owner10", suffix="press-10")
        refusal = await _loop_flow_busy_refusal(db, loop, job.agent)
        assert isinstance(refusal, LoopBusyRefusal)
        assert refusal.condition == BUSY_LOOP_SCOPE
        assert await _loop_flow_busy_reason(db, loop, job.agent) == refusal.reason
        await _declare_document(db, loop, "10")
        refusal = await _loop_flow_busy_refusal(db, loop, job.agent)
        assert refusal.condition == BUSY_NO_FREE_AGENT
        assert await _loop_flow_busy_reason(db, loop, job.agent) == refusal.reason
        task = (await db.execute(select(Task).where(Task.loop_id == loop.id))).scalars().one()
        await db.delete(task)
        await db.commit()
        refusal = await _loop_flow_busy_refusal(db, loop, job.agent)
        assert refusal.condition == BUSY_EMPTY_QUEUE
        assert await _loop_flow_busy_reason(db, loop, job.agent) == refusal.reason


# --- D3: answer from a record only where this press wrote it or counted into it ----------


async def _flow_all_in_flight(db, suffix, agent):
    """A flow whose only task is in progress with the job's agent, which is mid-turn, and a second
    roster agent free, so the guard passes and the firing declines as in flight."""
    job, loop, task = await _make_loop_job(db, suffix=suffix, agent=agent)
    await _declare_document(db, loop, suffix)
    task.status = "in_progress"
    task.assignee = agent
    await db.commit()
    await _running_turn(db, agent=agent, suffix=suffix)
    return job, loop, task


async def test_an_in_flight_press_is_not_answered_by_an_earlier_stall(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.7 (F373)."""
    await _roster(app, auth_headers, bind_runner, "press-owner7", "press-free7")
    async with async_session_factory() as db:
        job, _loop, _task = await _flow_all_in_flight(db, "press-7", "press-owner7")
    await _seed_row(
        job.id,
        status="skipped",
        reason="loop queue is stalled: 1 still awaiting a prerequisite's approval",
    )
    with _no_spawn():
        res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "Every task on this loop's queue is already being worked" in detail
    assert "awaiting a prerequisite" not in detail
    rows = await _rows(job.id)
    assert len(rows) == 1
    assert rows[0].tick_count == 1
    assert rows[0].requested_by_run_id == "run-sentinel"


async def _stalled_documentless(db, suffix, agent):
    job, _loop, task = await _make_loop_job(db, suffix=suffix, agent=agent)
    task.status = "blocked"
    await db.commit()
    return job


async def test_a_continuing_stall_is_answered_from_its_row(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.8, control."""
    await _roster(app, auth_headers, bind_runner, "press-owner8")
    async with async_session_factory() as db:
        job = await _stalled_documentless(db, "press-8", "press-owner8")
    with _no_spawn():
        first = await _run(app, auth_headers, job)
        rows = await _rows(job.id)
        assert len(rows) == 1
        async with async_session_factory() as db:
            row = await db.get(JobRun, rows[0].id)
            row.requested_by_run_id = "run-sentinel"
            await db.commit()
        second = await _run(app, auth_headers, job)
    assert first.status_code == 409, first.text
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == first.json()["detail"]
    rows = await _rows(job.id)
    assert len(rows) == 1
    assert rows[0].tick_count == 2
    assert rows[0].requested_by_run_id == "run-sentinel"


def _race():
    """A guard that says *not busy* to the firing and *busy* to the route's re-ask."""
    calls = {"n": 0}

    async def refusal(session, loop, agent):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return LoopBusyRefusal("racer is already running a turn", BUSY_LOOP_SCOPE)

    return patch("hub.scheduler._loop_flow_busy_refusal", side_effect=refusal)


@pytest.mark.parametrize("presses", [1, 2])
async def test_a_recorded_stall_is_answered_before_the_busy_re_ask(
    app, auth_headers, bind_runner, live_scheduler, presses
):
    """1.9 (second press: a counted stall) and 1.9a (first press: the press wrote the row)."""
    await _roster(app, auth_headers, bind_runner, "press-owner9")
    async with async_session_factory() as db:
        job = await _stalled_documentless(db, f"press-9-{presses}", "press-owner9")
    with _no_spawn():
        if presses == 2:
            await _run(app, auth_headers, job)
        with _race():
            res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "is already running a turn" not in detail


# --- D3, R2/R3: what an unrecorded or non-decline row must not be read as -----------------


async def test_a_firing_that_raises_before_its_row_is_not_answered_by_an_earlier_reason(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.12."""
    await _roster(app, auth_headers, bind_runner, "press-owner12")
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="press-12", agent="press-owner12")
        job.session_mode = "resume"
        job.last_session_id = "sess-12"
        await db.commit()
    await _seed_row(job.id, status="skipped", reason="loop queue is stalled: earlier reason")
    with (
        _no_spawn(),
        patch("hub.scheduler.conversation_for_provider_session", side_effect=RuntimeError("boom")),
    ):
        res = await _run(app, auth_headers, job)
    assert res.status_code == 500, res.text
    assert "earlier reason" not in res.json()["detail"]
    rows = await _rows(job.id)
    assert len(rows) == 1
    assert rows[0].tick_count == 1
    assert rows[0].requested_by_run_id == "run-sentinel"


async def test_a_firing_that_fails_after_its_turn_started_is_answered_from_its_row(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.13."""
    await _roster(app, auth_headers, bind_runner, "press-owner13")
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="press-13", agent="press-owner13")

    async def crash(*args, **kwargs):
        async with async_session_factory() as other:
            other.add(
                Run(id="run-press-13", project_id=PROJECT, agent="press-owner13", status="running")
            )
            await other.commit()
        raise RuntimeError("spawn crashed")

    with patch("hub.turn_scheduler.schedule_agent", side_effect=crash):
        res = await _run(app, auth_headers, job)
    assert res.status_code == 500, res.text
    detail = res.json()["detail"]
    assert "already being worked" not in detail
    assert "nothing is wrong" not in detail


async def test_a_concurrent_ticks_row_is_not_read_as_a_failure(app, auth_headers, live_scheduler):
    """1.14."""
    async with async_session_factory() as db:
        job, _loop, _task = await _make_loop_job(db, suffix="press-14", agent="press-owner14")
        await _running_turn(db, agent="press-owner14", suffix="press-14")

    async def tick(self, job, trigger="scheduled", session=None):
        async with async_session_factory() as other:
            other.add(
                JobRun(
                    id="jobrun-press-tick",
                    job_id=job.id,
                    project_id=PROJECT,
                    status="in_progress",
                    trigger="scheduled",
                )
            )
            await other.commit()
        return False

    with patch.object(JobScheduler, "_fire_job_internal", tick):
        res = await _run(app, auth_headers, job)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "is already running a turn" in detail
    assert SCOPE in detail
