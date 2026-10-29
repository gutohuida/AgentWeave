"""A live run is progress and cannot be reset
(`a-task-s-checks-and-merges-use-its-own-work-and-a-live-run-is-never-reset`, FR-5 and FR-6).

The operator's Hub, 2026-10-29: DeveloperOpus's run on task-799357e3e80e executed from 17:02 to
18:02 without moving the task. The stall scan read an hour with no run started and no status change
as `no_progress`, and the mender, woken for it, reset the task to `assigned` at 17:39 under the live
run. Alive means in this process's run registry (design D3).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub import run_liveness, stalls
from hub.db.engine import async_session_factory
from hub.db.models import Agent, AIJob, Loop, Run, Task, TaskTransition

from .test_a_stalled_project_wakes_the_mender import all_stalls, mender_run

RESET = "/api/v1/agent-actions/mender/tasks/{}/reset"


@pytest.fixture
def executing():
    """Runs this Hub process is executing, as `run_liveness` holds them during a turn."""
    added: list = []

    def add(run_id):
        run_liveness.active_app_server_runs.add(run_id)
        added.append(run_id)

    yield add
    for run_id in added:
        run_liveness.active_app_server_runs.discard(run_id)


async def _flow_with_one_task_being_worked(started, *, status="in_progress"):
    """A loop whose only moving task has a running run bound to it, started at *started*, and no
    status change or other run since."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-live-b", project_id="proj-test", name="builder"))
        session.add(
            AIJob(
                id="job-live",
                project_id="proj-test",
                name="The flow",
                agent="builder",
                message="next",
                cron="*/5 * * * *",
                enabled=True,
                created_at=started,
            )
        )
        session.add(
            Loop(id="loop-live", project_id="proj-test", job_id="job-live", created_at=started)
        )
        session.add(
            Task(
                id="task-live",
                project_id="proj-test",
                title="a long turn",
                status=status,
                assignee="builder",
                loop_id="loop-live",
                created_at=started,
                updated=started,
            )
        )
        session.add(
            Run(
                id="run-live",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                task_id="task-live",
                started_at=started,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_flow_whose_task_has_an_executing_run_is_not_a_no_progress_stall(app, executing):
    """ac-long-run-no-stall."""
    now = datetime.now(timezone.utc)
    await _flow_with_one_task_being_worked(now - timedelta(minutes=stalls.NO_PROGRESS_MINUTES + 30))
    executing("run-live")

    async with async_session_factory() as session:
        assert await stalls._sweep(session, now) == 0
    await stalls.drain()
    assert [row for row in await all_stalls() if row.cause == "no_progress"] == []


@pytest.mark.asyncio
async def test_the_same_flow_with_its_run_not_executing_is_still_reported(app):
    """The guard reads the registry, not the `running` column: a run recorded running that this
    Hub is not executing is no progress (and a dead run)."""
    now = datetime.now(timezone.utc)
    await _flow_with_one_task_being_worked(now - timedelta(minutes=stalls.NO_PROGRESS_MINUTES + 30))

    async with async_session_factory() as session:
        await stalls._sweep(session, now)
    await stalls.drain()
    causes = {row.cause for row in await all_stalls()}
    assert "no_progress" in causes
    assert "dead_run" in causes


@pytest.mark.asyncio
async def test_a_no_progress_stall_ends_once_a_run_executes_on_its_task(app, executing):
    now = datetime.now(timezone.utc)
    await _flow_with_one_task_being_worked(now - timedelta(minutes=stalls.NO_PROGRESS_MINUTES + 30))
    async with async_session_factory() as session:
        await stalls._sweep(session, now)
    await stalls.drain()
    assert any(row.cause == "no_progress" for row in await all_stalls())

    executing("run-live")
    async with async_session_factory() as session:
        await stalls._sweep(session, now)
    [row] = [row for row in await all_stalls() if row.cause == "no_progress"]
    assert row.outcome == "resolved"


async def _history(task_id):
    async with async_session_factory() as session:
        return (
            (
                await session.execute(
                    select(TaskTransition.id).where(TaskTransition.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("to_status", ["assigned", "pending"])
async def test_the_mender_cannot_reset_a_task_whose_run_is_executing(app, executing, to_status):
    """ac-reset-refused."""
    started = datetime(2026, 10, 29, 17, 2, tzinfo=timezone.utc)
    await _flow_with_one_task_being_worked(started)
    executing("run-live")
    mender = await mender_run()
    before = await _history("task-live")

    body = {"status": to_status}
    if to_status == "assigned":
        body["assignee"] = "builder"
    refused = await app.post(RESET.format("task-live"), json=body, headers=mender)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert "run-live" in detail
    assert "builder" in detail
    assert "2026-10-29 17:02" in detail
    async with async_session_factory() as session:
        task = await session.get(Task, "task-live")
        assert (task.status, task.assignee) == ("in_progress", "builder")
    assert await _history("task-live") == before


@pytest.mark.asyncio
async def test_the_mender_resets_the_task_once_its_run_has_ended(app):
    """Without a live run the reset is the move it always was."""
    await _flow_with_one_task_being_worked(datetime.now(timezone.utc) - timedelta(hours=2))
    mender = await mender_run()

    moved = await app.post(
        RESET.format("task-live"),
        json={"status": "assigned", "assignee": "builder"},
        headers=mender,
    )

    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "assigned"


@pytest.mark.asyncio
async def test_the_operator_cannot_reset_a_task_whose_run_is_executing(
    app, auth_headers, executing
):
    """Any route that moves an `in_progress` task back is refused, the operator's included."""
    await _flow_with_one_task_being_worked(datetime.now(timezone.utc) - timedelta(minutes=5))
    executing("run-live")

    refused = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-live",
        json={"status": "assigned"},
        headers=auth_headers,
    )

    assert refused.status_code == 409, refused.text
    assert "run-live" in refused.json()["detail"]
    async with async_session_factory() as session:
        assert (await session.get(Task, "task-live")).status == "in_progress"
