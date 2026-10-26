"""Flaky tests the approval checks find are raised to the operator, not only to the reviewer.

The gate re-runs a failure once and lets approval go on when the second attempt passes
(`project_checks.confirm_failure`). Before `flaky_tests`, the only trace of that was the run's own
result and one sentence in the reviewer's briefing: nobody was ever asked to fix the test, so the
same flakes cost a gate run each, flow after flow (loop-df5f74816122 hit three of them in one day).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from hub import flaky_tests, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, Task, TaskCheckRun

from .test_checks_reuse_a_pass_and_confirm_a_failure import _counting
from .test_project_checks_run import _project, _task_with_work

P = "/api/v1/projects/proj-test"


def _flaky_result(name: str, tests: list) -> dict:
    return {
        "name": name,
        "exit_code": 0,
        "timed_out": False,
        "duration_seconds": 3.0,
        "output_tail": "[flaky: ...]",
        "flaky": {
            "how": "tests" if tests else "check",
            "tests": tests,
            "exit_code": 0,
            "first": {"exit_code": 1, "failed_tests": tests},
        },
    }


async def _run_row(task_id: str, results: list, *, started_at: datetime) -> str:
    async with async_session_factory() as session:
        run_id = f"chk-{abs(hash((task_id, started_at))) % 10**12:012d}"
        session.add(
            TaskCheckRun(
                id=run_id,
                project_id="proj-test",
                task_id=task_id,
                main_sha="0" * 40,
                target_shas=[],
                state="passed",
                results=results,
                started_at=started_at,
                ended_at=started_at,
            )
        )
        await session.commit()
    return run_id


async def _task(task_id: str) -> None:
    async with async_session_factory() as session:
        session.add(Task(id=task_id, project_id="proj-test", title=task_id, status="under_review"))
        await session.commit()


async def test_the_gate_raises_a_flake_it_records(app, auth_headers, tmp_path, tmp_path_factory):
    repo, counter = tmp_path, tmp_path_factory.mktemp("count") / "count.txt"
    task_id, _ = await _task_with_work(repo)
    await _project([_counting("suite", counter, fail_first=1)])

    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == flaky_tests.FLAKY_EVENT)
                )
            )
            .scalars()
            .all()
        )
    assert [e.data["check"] for e in events] == ["suite"]
    assert events[0].data["task_id"] == task_id and events[0].severity == "warn"

    r = await app.get(f"{P}/checks/flaky", headers=auth_headers)
    assert r.status_code == 200, r.text
    [entry] = r.json()["flaky"]
    assert entry["check"] == "suite" and entry["test"] is None and entry["occurrences"] == 1
    assert entry["task_ids"] == [task_id]


async def test_flakes_are_listed_per_test_most_recent_first(app, auth_headers):
    now = datetime.now(timezone.utc)
    for t in ("task-a", "task-b"):
        await _task(t)
    await _run_row(
        "task-a",
        [_flaky_result("hub-tests", ["t.py::test_x"])],
        started_at=now - timedelta(hours=5),
    )
    await _run_row(
        "task-b",
        [_flaky_result("hub-tests", ["t.py::test_x", "t.py::test_y"])],
        started_at=now - timedelta(hours=1),
    )
    await _run_row(
        "task-b", [_flaky_result("hub-tests", ["t.py::old"])], started_at=now - timedelta(days=40)
    )

    body = (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()
    by_test = {f["test"]: f for f in body["flaky"]}
    assert set(by_test) == {
        "t.py::test_x",
        "t.py::test_y",
    }, "a flake outside the window is not listed"
    assert by_test["t.py::test_x"]["occurrences"] == 2
    assert by_test["t.py::test_x"]["task_ids"] == ["task-a", "task-b"]
    assert body["flaky"][0]["last_seen"] >= body["flaky"][1]["last_seen"]


async def test_handing_the_list_to_a_task_names_every_test_and_quiets_it_until_one_flakes_again(
    app, auth_headers
):
    now = datetime.now(timezone.utc)
    await _task("task-a")
    await _run_row(
        "task-a",
        [_flaky_result("hub-tests", ["t.py::test_x"]), _flaky_result("lint", [])],
        started_at=now - timedelta(hours=2),
    )

    r = await app.post(
        f"{P}/checks/flaky/handled", json={"create_task": True}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    task_id = r.json()["task_id"]
    task = (await app.get(f"{P}/tasks/{task_id}", headers=auth_headers)).json()
    assert task["status"] == "pending" and task["assignee"] is None
    assert "Fix 2 flaky tests" in task["title"]
    assert "`t.py::test_x`" in task["description"] and "check `lint`" in task["description"]

    after = (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()
    assert after["flaky"] == [] and after["handled"]["task_id"] == task_id

    # The fix did not hold: the same test flakes again, and is open again.
    await _run_row(
        "task-a",
        [_flaky_result("hub-tests", ["t.py::test_x"])],
        started_at=now + timedelta(seconds=1),
    )
    again = (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()
    assert [f["test"] for f in again["flaky"]] == ["t.py::test_x"]


async def test_dismissing_makes_no_task_and_an_empty_list_cannot_be_handled(app, auth_headers):
    now = datetime.now(timezone.utc)
    await _task("task-a")
    await _run_row("task-a", [_flaky_result("hub-tests", ["t.py::test_x"])], started_at=now)

    r = await app.post(
        f"{P}/checks/flaky/handled", json={"create_task": False}, headers=auth_headers
    )
    assert r.status_code == 200 and r.json()["task_id"] is None
    assert (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()["flaky"] == []
    assert (
        await app.post(f"{P}/checks/flaky/handled", json={}, headers=auth_headers)
    ).status_code == 409


def test_a_whole_check_flake_and_a_named_test_flake_are_both_read():
    found = flaky_tests.flakes_in(
        [_flaky_result("a", []), _flaky_result("b", ["x::y"]), {"name": "c", "exit_code": 0}]
    )
    assert found == [("a", [], "check"), ("b", ["x::y"], "tests")]
