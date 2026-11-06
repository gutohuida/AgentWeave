"""The instance-wide "what work is running" answer the app window asks before closing stops the Hub.

Change `agentweave-is-its-own-app-on-windows`, FR-9 (`what-counts-as-work`): an agent turn, a check
run, a landing and a build that has not ended count, in any project; an enabled job that is not a
build, with no turn in progress, does not.
"""

import itertools
from datetime import datetime, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Build,
    Project,
    Run,
    SpecDocument,
    Task,
    TaskCheckRun,
    TaskLanding,
)

URL = "/api/v1/work/running"
_n = itertools.count(1)


async def _add(*rows) -> None:
    async with async_session_factory() as session:
        for row in rows:
            session.add(row)
        await session.commit()


def _task(project_id: str = "proj-test") -> Task:
    return Task(
        id=f"task-work-{next(_n)}",
        project_id=project_id,
        title="work",
        status="approved",
        assignee="builder",
    )


def _run(status: str, project_id: str = "proj-test", agent: str = "builder") -> Run:
    return Run(
        id=f"run-work-{next(_n)}",
        project_id=project_id,
        agent=agent,
        status=status,
        started_at=datetime.now(timezone.utc),
    )


def _check_run(task_id: str, state: str) -> TaskCheckRun:
    return TaskCheckRun(
        id=f"chk-work-{next(_n)}",
        project_id="proj-test",
        task_id=task_id,
        main_sha="a" * 40,
        target_shas=["b" * 40],
        state=state,
        results=[],
    )


def _landing(task_id: str, state: str) -> TaskLanding:
    return TaskLanding(
        id=f"land-work-{next(_n)}",
        project_id="proj-test",
        task_id=task_id,
        state=state,
        order_key=float(next(_n)),
    )


def _build(state: str, document_id: str) -> Build:
    return Build(
        id=f"build-work-{next(_n)}",
        project_id="proj-test",
        document_id=document_id,
        state=state,
        driver="flow",
        level="reviewed",
        builders=[],
        reviewers=[],
        landing="main",
    )


async def _answer(app, auth_headers) -> dict:
    resp = await app.get(URL, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_nothing_running_is_idle(app, auth_headers):
    data = await _answer(app, auth_headers)
    assert data["running"] is False
    assert (data["turns"], data["check_runs"], data["landings"], data["builds"]) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_the_answer_needs_the_operator(app):
    assert (await app.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_an_agent_turn_is_work_in_any_project(app, auth_headers):
    await _add(Project(id="proj-other", name="Other"))
    await _add(_run("completed"), _run("running", project_id="proj-other", agent="far"))
    data = await _answer(app, auth_headers)
    assert data["running"] is True
    assert data["turns"] == 1
    assert data["turn_agents"] == [{"agent": "far", "project": "Other"}]


@pytest.mark.asyncio
async def test_a_check_run_is_work(app, auth_headers):
    task = _task()
    await _add(task)
    await _add(_check_run(task.id, "passed"))
    assert (await _answer(app, auth_headers))["running"] is False
    await _add(_check_run(task.id, "running"))
    data = await _answer(app, auth_headers)
    assert data["running"] is True and data["check_runs"] == 1


@pytest.mark.asyncio
async def test_a_landing_on_its_way_is_work_and_a_held_one_is_not(app, auth_headers):
    tasks = [_task() for _ in range(5)]
    await _add(*tasks)
    await _add(
        _landing(tasks[0].id, "landed"),
        _landing(tasks[1].id, "held"),
        _landing(tasks[2].id, "not_landed"),
    )
    assert (await _answer(app, auth_headers))["running"] is False
    await _add(_landing(tasks[3].id, "queued"), _landing(tasks[4].id, "checking"))
    data = await _answer(app, auth_headers)
    assert data["running"] is True and data["landings"] == 2


@pytest.mark.asyncio
async def test_a_build_between_its_firings_is_work_and_named(app, auth_headers):
    """No turn, no check run: a running build alone still makes the close ask, by name."""
    await _add(
        SpecDocument(
            id="spdoc-work",
            project_id="proj-test",
            path="spec/changes/close-means-stop/spec.json",
            title="Close means stop",
            phase="approved",
        )
    )
    await _add(_build("finished", "spdoc-work"), _build("stopped", "spdoc-work"))
    assert (await _answer(app, auth_headers))["running"] is False
    running = _build("running", "spdoc-work")
    await _add(running)
    data = await _answer(app, auth_headers)
    assert data["running"] is True
    assert data["builds"] == 1
    assert data["turns"] == 0
    assert data["build_list"] == [
        {"id": running.id, "title": "Close means stop", "project": "Test Project"}
    ]


@pytest.mark.asyncio
async def test_an_enabled_job_that_is_not_a_build_is_not_work(app, auth_headers):
    """Operator, 2026-11-04: a recurring job just misses its firings while the Hub is stopped."""
    await _add(
        AIJob(
            id="job-work",
            project_id="proj-test",
            name="nightly",
            agent="builder",
            message="go",
            cron="*/5 * * * *",
            enabled=True,
        )
    )
    data = await _answer(app, auth_headers)
    assert data["running"] is False
    # Its turn, while one runs, is a turn like any other.
    await _add(_run("running"))
    assert (await _answer(app, auth_headers))["turns"] == 1
