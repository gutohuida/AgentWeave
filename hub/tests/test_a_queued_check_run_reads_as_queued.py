"""F1076, its second half: a check run's age is read from when its checks started, not when it queued.

On 2026-10-28 the mender was told chk-a6633ef823ea's checks had run 70 min (the previous run 41 min)
and recommended killing it; it had waited 33 min for a check slot and finished at 12:29. What the
review wait says is what the mender and the flow read (`project_checks.review_wait`).
"""

import asyncio

import pytest

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskCheckRun

from .test_checks_run_before_review import _flow_task_completed, _slow

pytestmark = pytest.mark.asyncio


async def _wait_for(predicate, seconds=30.0):
    for _ in range(int(seconds / 0.05)):
        if predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("timed out")


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_run_waiting_for_a_slot_says_it_is_queued_not_running(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path)],
    )
    slots = project_checks._semaphore()
    for _ in range(project_checks.MAX_CONCURRENT_RUNS):
        await slots.acquire()  # two other runs hold every slot
    try:
        run_id = await project_checks.request_run("proj-test", "task-1")
        await _wait_for(lambda: run_id in project_checks._waiting_for_slot)
        async with async_session_factory() as db:
            wait = await project_checks.review_wait(db, await db.get(Task, "task-1"))
        assert wait is not None and wait.state == "running" and wait.run_id == run_id
        assert "for a check slot" in wait.reason and "queued is not hung" in wait.reason
        assert "checks have run" not in wait.reason
    finally:
        for _ in range(project_checks.MAX_CONCURRENT_RUNS):
            slots.release()
    await project_checks.drain()
    async with async_session_factory() as db:
        assert (await db.get(TaskCheckRun, run_id)).state == "passed"
    assert run_id not in project_checks._waiting_for_slot
    assert run_id not in project_checks._slot_waited


async def test_a_previous_runs_duration_leaves_out_its_wait_for_a_slot():
    """A decided run that queued 33 min and ran its checks for 41 reads as 41."""
    from datetime import datetime, timedelta, timezone

    started = datetime(2026, 10, 28, 11, 19, tzinfo=timezone.utc)
    run = TaskCheckRun(
        started_at=started,
        ended_at=started + timedelta(minutes=74),
        results=[
            {"name": "ruff", "duration_seconds": 60.0},
            {"name": "hub-tests", "duration_seconds": 40 * 60.0},
        ],
    )
    assert project_checks._checks_took(run) == 41 * 60.0
    assert project_checks._duration(project_checks._checks_took(run)) == "41m"
