# ruff: noqa: F811 -- `author_headers` is a fixture imported to be requested by name
"""A spec reads done once its tasks' work is on main, the board says what the queue is holding, and
the build's record lists what its checks caught (F1110). Every assertion reads the route."""

import pytest
from sqlalchemy import update

from hub.builds import LANDS_NOWHERE
from hub.db.engine import async_session_factory
from hub.db.models import Build, TaskCheckRun, TaskLanding
from hub.task_integration import NO_TASK_BRANCH

from .test_a_build_has_a_driver_a_level_and_its_people import (
    P,
    _rows,
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_a_finished_build_leaves_its_flow_working import (
    _all_landed,
    _built_with_a_fix_task,
    _close,
)
from .test_a_spec_shows_building_and_done import _approved, _build, _listed, _task

_order = iter(range(1, 1000))


async def _landing(task_id: str, state: str, reason: str = "") -> None:
    n = next(_order)
    async with async_session_factory() as db:
        db.add(
            TaskLanding(
                id=f"landing-{n}",
                project_id=P,
                task_id=task_id,
                state=state,
                reason=reason,
                order_key=float(n),
            )
        )
        await db.commit()


async def _spec_with_an_approved_task(app, auth_headers) -> tuple[str, str]:
    document_id = await _approved(app, auth_headers)
    await _build(document_id, "finished")
    return document_id, await _task(document_id, "approved")


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["queued", "checking", "landing", "held"])
async def test_approved_work_still_in_the_queue_keeps_the_spec_building(app, auth_headers, state):
    _, task_id = await _spec_with_an_approved_task(app, auth_headers)
    await _landing(task_id, state)

    assert (await _listed(app, auth_headers))["display_phase"] == "building"


@pytest.mark.asyncio
async def test_work_that_failed_to_land_keeps_the_spec_building_until_a_retry_lands_it(
    app, auth_headers
):
    _, task_id = await _spec_with_an_approved_task(app, auth_headers)
    await _landing(task_id, "not_landed", "the checkout has uncommitted changes")

    assert (await _listed(app, auth_headers))["display_phase"] == "building"

    await _landing(task_id, "landed")

    assert (await _listed(app, auth_headers))["display_phase"] == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [NO_TASK_BRANCH, LANDS_NOWHERE])
async def test_a_task_with_nothing_to_land_does_not_hold_the_spec(app, auth_headers, reason):
    _, task_id = await _spec_with_an_approved_task(app, auth_headers)
    await _landing(task_id, "not_landed", reason)

    assert (await _listed(app, auth_headers))["display_phase"] == "done"


@pytest.mark.asyncio
async def test_a_task_that_never_had_a_landing_does_not_hold_the_spec(app, auth_headers):
    await _spec_with_an_approved_task(app, auth_headers)

    assert (await _listed(app, auth_headers))["display_phase"] == "done"


@pytest.mark.asyncio
async def test_the_board_says_an_approved_task_is_waiting_to_land(app, auth_headers):
    _, task_id = await _spec_with_an_approved_task(app, auth_headers)
    await _landing(task_id, "queued")

    read = await app.get(f"/api/v1/projects/{P}/tasks/{task_id}", headers=auth_headers)
    assert read.status_code == 200, read.text
    assert read.json()["waiting_to_land"] is True

    await _landing(task_id, "landed")
    async with async_session_factory() as db:
        await db.execute(
            update(TaskLanding)
            .where(TaskLanding.task_id == task_id, TaskLanding.state == "queued")
            .values(state="landed")
        )
        await db.commit()

    listed = await app.get(f"/api/v1/projects/{P}/tasks", headers=auth_headers)
    (row,) = [t for t in listed.json()["tasks"] if t["id"] == task_id]
    assert row["waiting_to_land"] is False


@pytest.mark.asyncio
async def test_a_cap_holding_a_fix_task_shows_on_its_card_and_the_build_still_reads_finished(
    app, auth_headers, author_headers, bind_runner
):
    await _built_with_a_fix_task(app, auth_headers, author_headers, bind_runner, driver="flow")
    tasks = await _tasks_by_key()
    (build,) = await _rows(Build)
    document_id, build_id = (build.document_id, build.id)
    async with async_session_factory() as db:
        db.add(
            TaskCheckRun(
                id="check-1",
                project_id=P,
                task_id=next(iter(tasks.values())).id,
                main_sha="a" * 40,
                target_shas=[],
                state="failed",
                results=[
                    {
                        "name": "hub-tests",
                        "exit_code": 1,
                        "preexisting": True,
                        "shared_tests": ["tests/a.py::t"],
                        "own_tests": [],
                        # The known-failing entry it went past, as the gate records it.
                        "listed": [
                            {
                                "id": "kf-a",
                                "check": "hub-tests",
                                "test": "tests/a.py::t",
                                "kind": "fails on main",
                                "fix_task_id": "task-the-hubs-fix",
                            }
                        ],
                    }
                ],
            )
        )
        await db.commit()
    for task in tasks.values():
        await _close(task.id)
    await _all_landed()
    async with async_session_factory() as db:
        (await db.get(Build, build_id)).budget_cap_usd_micros = 0
        await db.commit()

    card = await app.get(f"/api/v1/projects/{P}/tasks/task-the-hubs-fix", headers=auth_headers)
    assert "cap" in card.json()["queue_held_reason"], card.text

    documents = await app.get(f"/api/v1/projects/{P}/project/documents", headers=auth_headers)
    (document,) = [d for d in documents.json()["documents"] if d["id"] == document_id]
    read = await app.get(
        f"/api/v1/projects/{P}/project/spec",
        params={"path": document["path"]},
        headers=auth_headers,
    )
    assert read.status_code == 200, read.text
    (shown,) = read.json()["builds"]
    assert shown["state"] == "finished"
    assert shown["open_fix_tasks"] == ["task-the-hubs-fix"]
    assert "cap" in shown["fix_held_reason"]
    (caught,) = shown["caught"]
    assert (caught["test"], caught["origin"], caught["changed_by_build"]) == (
        "tests/a.py::t",
        "caught",
        False,
    )
    assert caught["fix_task"]["id"] == "task-the-hubs-fix"
    assert caught["fix_task"]["open"] is True
    # The fix task does not hold the spec: its own tasks are closed and nothing is landing.
    assert document["display_phase"] == "done"


@pytest.mark.asyncio
async def test_a_failure_of_the_builds_own_work_reads_as_introduced(
    app, auth_headers, author_headers, bind_runner
):
    await _built_with_a_fix_task(app, auth_headers, author_headers, bind_runner, driver="flow")
    task = next(iter((await _tasks_by_key()).values()))
    (build,) = await _rows(Build)
    async with async_session_factory() as db:
        db.add(
            TaskCheckRun(
                id="check-own",
                project_id=P,
                task_id=task.id,
                main_sha="a" * 40,
                target_shas=[],
                state="failed",
                results=[
                    {
                        "name": "hub-tests",
                        "exit_code": 1,
                        "own_tests": ["tests/b.py::t"],
                        "shared_tests": ["tests/c.py::t"],
                        "listed": [
                            {
                                "id": "kf-c",
                                "check": "hub-tests",
                                "test": "tests/c.py::t",
                                "kind": "fails on main",
                                "fix_task_id": None,
                            }
                        ],
                        "touched_tests": ["tests/c.py::t"],
                    }
                ],
            )
        )
        await db.commit()
        row = await db.get(Build, build.id)
        from hub.build_caught import caught_during

        caught = {c["test"]: c for c in await caught_during(db, row)}

    assert caught["tests/b.py::t"]["origin"] == "introduced"
    assert caught["tests/b.py::t"]["found_on"] == task.id
    # It fails on main too, but this work changed the file: not the build's to wave through.
    assert caught["tests/c.py::t"]["origin"] == "introduced"
    assert caught["tests/c.py::t"]["changed_by_build"] is True
