# ruff: noqa: F811 -- `author_headers` is a fixture imported to be requested by name
"""F1113: a build that finishes does not end a flow with work still in its queue.

On 2026-10-31 approving the build's last task ended `loop-028328d41d99` while the Hub's fix task,
which carries the loop and no build, was under review. Its reviewer sent it back and no firing ever
briefed its builder again. The build may read as finished; the flow ends when its queue drains.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import update

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Build, Loop, Task, TaskLanding
from hub.scheduler import JobScheduler
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

from .test_a_build_has_a_driver_a_level_and_its_people import (
    P,
    _approved,
    _build,
    _document,
    _rows,
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_review_turn import _roster

SCHEDULING = patch(
    "hub.turn_scheduler.schedule_agent",
    AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
)


async def _close(task_id: str) -> None:
    async with async_session_factory() as db:
        row = await db.get(Task, task_id)
        for status in ("in_progress", "completed", "approved"):
            await apply_transition(db, row, status, operator())
        await db.commit()


async def _fire(job_id: str) -> None:
    with SCHEDULING:
        async with async_session_factory() as db:
            job = await db.get(AIJob, job_id)
            await JobScheduler()._do_fire_job(job, "scheduled", db)


async def _all_landed() -> None:
    async with async_session_factory() as db:
        await db.execute(update(TaskLanding).values(state="landed"))
        await db.commit()


async def _built_with_a_fix_task(app, auth_headers, author_headers, bind_runner, **settings):
    """A running flow build holding a fix task as the Hub files one: the loop and no build."""
    await _roster(app, auth_headers, bind_runner, "dev", "qa", "lead")
    await _approved(app, auth_headers, author_headers, _document())
    with SCHEDULING:
        built = await _build(app, auth_headers, level="fast", builders=["dev"], **settings)
    assert built.status_code == 200, built.text
    (loop,) = await _rows(Loop)
    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-the-hubs-fix",
                project_id=P,
                title="Fix a flaky test",
                status="pending",
                priority="critical",
                loop_id=loop.id,
            )
        )
        await db.commit()
    return loop


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings", [{"driver": "flow"}, {"driver": "lead", "lead": "lead"}], ids=["flow", "lead"]
)
async def test_the_flow_works_its_fix_task_after_the_build_finishes(
    app, auth_headers, author_headers, bind_runner, settings
):
    loop = await _built_with_a_fix_task(app, auth_headers, author_headers, bind_runner, **settings)

    for task in (await _tasks_by_key()).values():
        await _close(task.id)

    (build,) = await _rows(Build)
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob)
    assert build.state == "finished"
    assert (loop.ending_state, job.enabled) == (None, True)

    await _fire(job.id)

    async with async_session_factory() as db:
        fix = await db.get(Task, "task-the-hubs-fix")
        assert fix.assignee == "dev"
    (loop,) = await _rows(Loop)
    assert loop.ending_state is None


@pytest.mark.asyncio
async def test_the_flow_ends_when_the_fix_task_closes(
    app, auth_headers, author_headers, bind_runner
):
    await _built_with_a_fix_task(app, auth_headers, author_headers, bind_runner, driver="flow")
    for task in (await _tasks_by_key()).values():
        await _close(task.id)

    async with async_session_factory() as db:
        row = await db.get(Task, "task-the-hubs-fix")
        for status in ("in_progress", "completed", "under_review", "approved"):
            await apply_transition(db, row, status, operator())
        await db.commit()
    await _all_landed()

    (job,) = await _rows(AIJob)
    await _fire(job.id)

    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob)
    assert (loop.ending_state, job.enabled) == ("completed", False)


@pytest.mark.asyncio
async def test_a_finished_builds_queue_still_waits_on_its_cap(
    app, auth_headers, author_headers, bind_runner
):
    await _built_with_a_fix_task(app, auth_headers, author_headers, bind_runner, driver="flow")
    for task in (await _tasks_by_key()).values():
        await _close(task.id)
    async with async_session_factory() as db:
        (build,) = await _rows(Build)
        row = await db.get(Build, build.id)
        row.budget_cap_usd_micros = 0
        await db.commit()

    (job,) = await _rows(AIJob)
    await _fire(job.id)

    async with async_session_factory() as db:
        fix = await db.get(Task, "task-the-hubs-fix")
        assert fix.assignee is None
    (build,) = await _rows(Build)
    (loop,) = await _rows(Loop)
    # Waiting, not stopped: nothing about a finished build is left to resume.
    assert (build.state, loop.ending_state) == ("finished", None)


@pytest.mark.asyncio
async def test_pressing_run_on_a_drained_flow_ends_it_and_says_so(
    app, auth_headers, author_headers, bind_runner, monkeypatch
):
    """The firing now ends such a flow, and one that records nothing read as "Failed to fire job"."""
    await _built_with_a_fix_task(app, auth_headers, author_headers, bind_runner, driver="flow")
    for task in (await _tasks_by_key()).values():
        await _close(task.id)
    async with async_session_factory() as db:
        row = await db.get(Task, "task-the-hubs-fix")
        await apply_transition(db, row, "rejected", operator())
        await db.commit()
    await _all_landed()

    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    (job,) = await _rows(AIJob)
    with SCHEDULING:
        pressed = await app.post(f"/api/v1/projects/{P}/jobs/{job.id}/run", headers=auth_headers)

    assert pressed.status_code != 500, pressed.text
    (loop,) = await _rows(Loop)
    assert loop.ending_state == "completed"
