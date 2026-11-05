"""A check run records when it got its check slot, and the record survives a restart
(`the-build-card-shows-where-check-time-went` FR-1, `slot-survives-restart`).

The seams are the two places a run that has a row takes `project_checks._semaphore()`: a task's
run (`project_checks._execute`, through `request_run`) and a landing batch's
(`landing_queue.run_batch_checks`). Before this the wait was held only in memory (`_slot_waited`),
so a restart lost it, and a landing batch's wait was never recorded at all.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import LandingBatch, Task, TaskCheckRun, TaskLanding

from .test_a_landing_timeout_is_unjudged import _batch
from .test_checks_run_before_review import _flow_task_completed, _slow
from .test_task_integration import git

pytestmark = pytest.mark.asyncio


async def _wait_for(predicate, seconds=30.0):
    for _ in range(int(seconds / 0.05)):
        if await predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("timed out")


async def _also_completed(*task_ids: str) -> None:
    async with async_session_factory() as session:
        first = await session.get(Task, "task-1")
        for task_id in task_ids:
            session.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title=task_id,
                    description="",
                    status=first.status,
                    assignee=first.assignee,
                )
            )
        await session.commit()


async def _landing(task_id: str) -> TaskLanding:
    async with async_session_factory() as session:
        session.add(
            TaskLanding(
                id="land-slot0001",
                project_id="proj-test",
                task_id=task_id,
                state="checking",
                order_key=1.0,
                targets=[],
            )
        )
        await session.commit()
        return await session.get(TaskLanding, "land-slot0001")


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_runs_queued_behind_full_slots_record_their_slot_and_it_survives_a_restart(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo, sha, _, _ = await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path)],
    )
    await _also_completed("task-2", "task-3")
    tip = git(repo, "rev-parse", "main").stdout.strip()
    landing = await _landing("task-2")
    await _batch("lbat-slot0001", tip, [landing])

    slots = project_checks._semaphore()
    for _ in range(project_checks.MAX_CONCURRENT_RUNS):
        await slots.acquire()  # two other runs hold both slots
    held = True
    try:
        first = await project_checks.request_run("proj-test", "task-1")
        second = await project_checks.request_run("proj-test", "task-2", targets=[sha])
        cancelled = await project_checks.request_run("proj-test", "task-3", targets=[sha])
        batch = asyncio.get_running_loop().create_task(
            landing_queue.run_batch_checks(
                repo, "proj-test", "lbat-slot0001", tip, sha, [_slow(tmp_path)], [landing]
            )
        )

        async def all_queued() -> bool:
            return len(getattr(slots, "_waiters", None) or ()) == 4

        await _wait_for(all_queued)
        assert {first, second, cancelled} <= set(project_checks._waiting_for_slot)
        # task-3's work changes while its run waits: that run ends without ever getting a slot.
        project_checks._superseded["task-3"] = project_checks._NEW_WORK
        await asyncio.sleep(0.05)  # the slot is strictly later than every queued run's start
        for _ in range(project_checks.MAX_CONCURRENT_RUNS):
            slots.release()
        held = False
        outcome = await batch
        await project_checks.drain()
    finally:
        if held:
            for _ in range(project_checks.MAX_CONCURRENT_RUNS):
                slots.release()
    assert outcome.state == "passed"

    # A restart: whatever the modules held in memory is gone; only the rows remain.
    project_checks._waiting_for_slot.clear()
    project_checks._inflight.clear()
    project_checks._semaphores.clear()

    async with async_session_factory() as db:
        batch_run_id = (await db.get(LandingBatch, "lbat-slot0001")).check_run_id
        rows = {
            row.id: row
            for row in (
                await db.execute(
                    select(TaskCheckRun).where(
                        TaskCheckRun.id.in_([first, second, cancelled, batch_run_id])
                    )
                )
            ).scalars()
        }
    for run_id in (first, second, batch_run_id):
        row = rows[run_id]
        assert row.state == "passed", (run_id, row.state, row.error)
        assert row.slot_at is not None, run_id
        assert row.slot_at > row.started_at, run_id
        assert row.slot_at <= row.ended_at, run_id
    assert rows[cancelled].state == project_checks.SUPERSEDED
    assert rows[cancelled].slot_at is None
