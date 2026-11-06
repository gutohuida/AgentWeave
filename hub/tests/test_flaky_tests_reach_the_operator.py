"""Flaky tests the approval checks find are raised to the operator, not only to the reviewer.

The gate re-runs a failure once and lets approval go on when the second attempt passes
(`project_checks.confirm_failure`). Before `flaky_tests`, the only trace of that was the run's own
result and one sentence in the reviewer's briefing: nobody was ever asked to fix the test, so the
same flakes cost a gate run each, flow after flow (loop-df5f74816122 hit three of them in one day).

Since the known-failing list (`failures-already-known-are-on-a-list-not-re-argued`, FR-12) the
flaky list is the list's flaky entries: nothing is reconstructed from old check runs or the event
log.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from hub import flaky_tests, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, KnownFailingTest, Task, TaskCheckRun

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


async def _entry(
    test: str, *, check="hub-tests", kind="flaky", seen: datetime, fix_task_id=None
) -> str:
    entry_id = f"kf-{abs(hash((check, test, kind))) % 10**10:010d}"
    async with async_session_factory() as session:
        session.add(
            KnownFailingTest(
                id=entry_id,
                project_id="proj-test",
                check_name=check,
                test=test,
                kind=kind,
                first_seen=seen,
                last_seen=seen,
                added_by_run=f"chk-{entry_id[-6:]}",
                fix_task_id=fix_task_id,
            )
        )
        await session.commit()
    return entry_id


async def _seen_again(entry_id: str, at: datetime) -> None:
    async with async_session_factory() as session:
        (await session.get(KnownFailingTest, entry_id)).last_seen = at
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
        [run] = (await session.execute(select(TaskCheckRun))).scalars().all()
    assert [e.data["check"] for e in events] == ["suite"]
    assert events[0].data["task_id"] == task_id and events[0].severity == "warn"
    assert run.state == "passed" and run.results[0]["flaky"]["how"] == "check"

    # A whole-check flake names no test, so nothing goes on the list (FR-2 lists tests) and the
    # flaky list, read from it, is empty: the Logs row above is its trace.
    r = await app.get(f"{P}/checks/flaky", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["flaky"] == []


async def test_flakes_are_the_lists_flaky_entries_most_recent_first(app, auth_headers):
    now = datetime.now(timezone.utc)
    await _entry("t.py::test_x", seen=now - timedelta(hours=5))
    await _entry("t.py::test_y", seen=now - timedelta(hours=1))
    await _entry("t.py::red", kind="fails on main", seen=now)

    body = (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()
    assert [f["test"] for f in body["flaky"]] == ["t.py::test_y", "t.py::test_x"]
    assert body["flaky"][0]["check"] == "hub-tests"


async def test_no_flake_is_read_back_from_old_check_runs(app, auth_headers):
    """FR-12: the reconstruction of flaky tests from check runs and event logs is gone. A run that
    recorded a flake, with no entry on the list, lists nothing."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        session.add(Task(id="task-a", project_id="proj-test", title="a", status="under_review"))
        session.add(
            TaskCheckRun(
                id="chk-oldflake01",
                project_id="proj-test",
                task_id="task-a",
                main_sha="0" * 40,
                target_shas=[],
                state="passed",
                results=[_flaky_result("hub-tests", ["t.py::test_x"])],
                started_at=now - timedelta(hours=1),
                ended_at=now - timedelta(hours=1),
            )
        )
        await session.commit()

    body = (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()
    assert body["flaky"] == []


async def test_handing_the_list_to_a_task_names_every_test_and_quiets_it_until_one_flakes_again(
    app, auth_headers
):
    now = datetime.now(timezone.utc)
    test_x = await _entry("t.py::test_x", seen=now - timedelta(hours=2))
    await _entry("t.py::test_z", check="lint", seen=now - timedelta(hours=3))

    r = await app.post(
        f"{P}/checks/flaky/handled", json={"create_task": True}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    task_id = r.json()["task_id"]
    task = (await app.get(f"{P}/tasks/{task_id}", headers=auth_headers)).json()
    assert task["status"] == "pending" and task["assignee"] is None
    assert "Fix 2 flaky tests" in task["title"]
    assert "`t.py::test_x`" in task["description"] and "`t.py::test_z`" in task["description"]

    after = (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()
    assert after["flaky"] == [] and after["handled"]["task_id"] == task_id

    # The fix did not hold: the same test flakes again, and is open again.
    await _seen_again(test_x, now + timedelta(seconds=1))
    again = (await app.get(f"{P}/checks/flaky", headers=auth_headers)).json()
    assert [f["test"] for f in again["flaky"]] == ["t.py::test_x"]


async def test_dismissing_makes_no_task_and_an_empty_list_cannot_be_handled(app, auth_headers):
    await _entry("t.py::test_x", seen=datetime.now(timezone.utc))

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
