"""F1076: a loop whose open task has a check run in flight is not stalled.

The operator's Hub, 2026-10-28 and the night of 2026-11-03: the stall sweep read a loop whose
finished tasks were waiting on their check runs, one queued for a slot behind another, as
`no_progress`, and the mender woken for it called a healthy suite "possibly hung" (stalls
stall-72ea858deaa3, stall-115d9ecc89b5, stall-1c1281267c8f, stall-f2ff27828b0f). In flight means in
this Hub's check registry (`project_checks.is_running`); a row left `running` with nothing behind it
is still reported.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from hub import project_checks, stalls
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, Loop, Task, TaskCheckRun

from .test_a_stalled_project_wakes_the_mender import all_stalls


@pytest.fixture
async def in_flight():
    """Check runs this Hub process holds in flight, as `request_run` registers them."""
    jobs: list = []

    def add(task_id):
        job = asyncio.get_running_loop().create_task(asyncio.Event().wait())
        project_checks._inflight[task_id] = job
        jobs.append((task_id, job))

    yield add
    for task_id, job in jobs:
        job.cancel()
        project_checks._inflight.pop(task_id, None)


async def _flow_waiting_on_its_checks(quiet_since):
    """A loop whose only task was completed at *quiet_since* and has a check run recorded running
    since then, with no run started and no status change after it."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-chk-b", project_id="proj-test", name="builder"))
        session.add(
            AIJob(
                id="job-chk",
                project_id="proj-test",
                name="The flow",
                agent="builder",
                message="next",
                cron="*/5 * * * *",
                enabled=True,
                created_at=quiet_since,
            )
        )
        session.add(
            Loop(id="loop-chk", project_id="proj-test", job_id="job-chk", created_at=quiet_since)
        )
        session.add(
            Task(
                id="task-chk",
                project_id="proj-test",
                title="finished, being checked",
                status="completed",
                assignee="builder",
                loop_id="loop-chk",
                created_at=quiet_since,
                updated=quiet_since,
            )
        )
        await session.commit()
        session.add(
            TaskCheckRun(
                id="chk-f1076",
                project_id="proj-test",
                task_id="task-chk",
                main_sha="a" * 40,
                target_shas=["b" * 40],
                state="running",
                results=[],
                error="",
                started_at=quiet_since,
            )
        )
        await session.commit()


def _quiet_since(now):
    return now - timedelta(minutes=stalls.NO_PROGRESS_MINUTES + 30)


async def _no_progress_stalls():
    return [row for row in await all_stalls() if row.cause == "no_progress"]


@pytest.mark.asyncio
async def test_a_loop_whose_task_has_a_check_run_in_flight_is_not_stalled(app, in_flight):
    now = datetime.now(timezone.utc)
    await _flow_waiting_on_its_checks(_quiet_since(now))
    in_flight("task-chk")

    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 0
    await stalls.drain()
    assert await _no_progress_stalls() == []


@pytest.mark.asyncio
async def test_a_check_run_recorded_running_with_nothing_behind_it_is_still_a_stall(app):
    """The gate reads the registry, not the `running` column: a run no job is executing is dead,
    and the loop waiting on it is reported."""
    now = datetime.now(timezone.utc)
    await _flow_waiting_on_its_checks(_quiet_since(now))

    async with async_session_factory() as session:
        await stalls._sweep(session, now)
    await stalls.drain()
    assert [row.loop_id for row in await _no_progress_stalls()] == ["loop-chk"]


@pytest.mark.asyncio
async def test_a_no_progress_stall_ends_once_a_check_run_is_in_flight(app, in_flight):
    now = datetime.now(timezone.utc)
    await _flow_waiting_on_its_checks(_quiet_since(now))
    async with async_session_factory() as session:
        await stalls._sweep(session, now)
    await stalls.drain()
    assert len(await _no_progress_stalls()) == 1

    in_flight("task-chk")
    async with async_session_factory() as session:
        await stalls._sweep(session, now)
    [row] = await _no_progress_stalls()
    assert row.outcome == "resolved"
