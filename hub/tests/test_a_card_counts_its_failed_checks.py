"""A card says, before review, how many of its latest checks failed (`task-card-and-story-redesign`
FR-5): the tasks route carries `failed_checks` per task, from the same latest run the Work view
names (`GET /tasks/{id}/checks` lists it first), and null where no check has run.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import TaskCheckRun

pytestmark = pytest.mark.asyncio

TASKS = "/api/v1/projects/proj-test/tasks"
T0 = datetime(2026, 11, 12, 21, 0, tzinfo=timezone.utc)


def _result(name, exit_code=0, **extra):
    return {
        "name": name,
        "exit_code": exit_code,
        "duration_seconds": 1.0,
        "timed_out": False,
        **extra,
    }


async def _run(task_id, run_id, minutes, state, results):
    async with async_session_factory() as db:
        db.add(
            TaskCheckRun(
                id=run_id,
                project_id="proj-test",
                task_id=task_id,
                main_sha="a" * 40,
                target_shas=["b" * 40],
                merged_sha="c" * 40,
                state=state,
                results=results,
                started_at=T0 + timedelta(minutes=minutes),
                ended_at=T0 + timedelta(minutes=minutes + 1),
            )
        )
        await db.commit()


async def _task(app, auth_headers, title):
    created = await app.post(TASKS, json={"title": title}, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def test_a_task_whose_latest_checks_failed_two_of_five_carries_two(app, auth_headers):
    failing = await _task(app, auth_headers, "Checks failed")
    never = await _task(app, auth_headers, "No checks yet")
    passing = await _task(app, auth_headers, "Checks passed")
    # An older run failed everything; only the latest counts.
    await _run(failing, "chk-old", 0, "failed", [_result(f"c{i}", 1) for i in range(5)])
    await _run(
        failing,
        "chk-new",
        10,
        "failed",
        [
            _result("ruff"),
            _result("black", 1),
            _result("mypy"),
            _result("hub-tests", None, timed_out=True),
            _result("ui-lint"),
        ],
    )
    # A failure on the known-failing list is said as "fails on main too", not as the work's.
    await _run(
        passing,
        "chk-pass",
        5,
        "passed",
        [
            _result("ruff"),
            _result("hub-tests", 1, preexisting=True),
            _result("skipped", 1, skipped=True),
        ],
    )

    listed = (await app.get(TASKS, headers=auth_headers)).json()["tasks"]
    counts = {row["id"]: row["failed_checks"] for row in listed}
    assert counts == {failing: 2, never: None, passing: 0}

    board = (await app.get(f"{TASKS}/board", headers=auth_headers)).json()["tasks"]
    assert {row["id"]: row["failed_checks"] for row in board} == counts

    one = (await app.get(f"{TASKS}/{failing}", headers=auth_headers)).json()
    assert one["failed_checks"] == 2

    # The Work view's latest run is the one counted, and it names both failures.
    checks = (await app.get(f"{TASKS}/{failing}/checks", headers=auth_headers)).json()
    latest = checks["runs"][0]
    assert latest["id"] == "chk-new"
    named = [r["name"] for r in latest["results"] if r["exit_code"] != 0 or r["timed_out"]]
    assert named == ["black", "hub-tests"]
