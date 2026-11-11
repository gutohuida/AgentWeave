"""A disturbed check run is not a pile of flaky tests (`a-disturbed-check-run-is-not-a-pile-of-flaky-
tests`, task `hub-rules`: FR-1, FR-4, FR-7, FR-8, FR-9). One test per criterion, named after it.

`confirm_failure` is driven with a scripted `run_one` (the rerun's answer), and the result it records
is read by `known_failing.record_run`, as a check run is.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import known_failing, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EventLog, KnownFailingTest, Task

from .test_known_failing_list import TASK, TASK2, _entries, _plain_task, _run_row

pytestmark = pytest.mark.asyncio

SETTINGS = "/api/v1/projects/proj-test/settings"
CHECK = {
    "name": "pytest",
    "command": "run-all",
    "timeout_seconds": 60,
    "report_path": "report.xml",
    "rerun_command": "run-some {tests}",
}


@pytest.fixture(autouse=True)
async def _agents(app):
    async with async_session_factory() as session:
        session.add(Agent(id="ag-builder", project_id="proj-test", name="builder"))
        await session.commit()


def _first_run(tests, messages=None) -> dict:
    return {
        "name": "pytest",
        "exit_code": 1,
        "timed_out": False,
        "duration_seconds": 1.0,
        "output_tail": "first run output",
        "failed_tests": list(tests),
        "test_files": dict.fromkeys(tests, "test_x.py"),
        "failure_messages": messages or {},
    }


def _rerun(monkeypatch, *, still_failing=(), tests=()):
    def run_one(check, cwd, owner):
        failing = list(still_failing)
        return {
            "exit_code": 1 if failing else 0,
            "timed_out": False,
            "duration_seconds": 1.0,
            "output_tail": "rerun output",
            "failed_tests": failing,
            "passed_tests": [t for t in tests if t not in failing],
        }

    monkeypatch.setattr(project_checks, "run_one", run_one)


def _confirmed(monkeypatch, tests, *, still_failing=(), threshold=None, messages=None) -> dict:
    _rerun(monkeypatch, still_failing=still_failing, tests=tests)
    check = {**CHECK, "disturbed_threshold": threshold}
    result = _first_run(tests, messages)
    project_checks.confirm_failure(check, None, result, None, changed=[])  # type: ignore[arg-type]
    return result


def _tests(n):
    return [f"test_x.py::test_{i}" for i in range(n)]


async def _fix_tasks() -> list:
    async with async_session_factory() as session:
        return list(
            (await session.execute(select(Task).where(Task.title.like("Fix %")))).scalars().all()
        )


async def _disturbed_events() -> list:
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == known_failing.DISTURBED_EVENT)
                )
            )
            .scalars()
            .all()
        )


async def test_ac_burst_threshold_failures_that_pass_alone_are_one_disturbed_run(app, monkeypatch):
    await _plain_task(TASK, assignee="builder")
    result = _confirmed(monkeypatch, _tests(3), threshold=3)
    assert result["exit_code"] == 0 and result["disturbed"]["failed"] == 3
    run = await _run_row("chk-burst", [result])
    await known_failing.record_run(run)
    await known_failing.record_run(run)  # read twice: still one event

    assert await _entries() == []
    assert await _fix_tasks() == []
    [event] = await _disturbed_events()
    assert event.data["run_id"] == "chk-burst" and event.data["failed"] == 3


async def test_ac_below_threshold_two_flakes_are_listed_and_the_run_is_not_disturbed(
    app, monkeypatch
):
    await _plain_task(TASK, assignee="builder")
    result = _confirmed(monkeypatch, _tests(2), threshold=3)
    assert "disturbed" not in result
    await known_failing.record_run(await _run_row("chk-two", [result]))

    assert sorted(e.test for e in await _entries()) == _tests(2)
    assert all(e.kind == "flaky" and e.fix_task_id is None for e in await _entries())
    assert await _fix_tasks() == []
    assert await _disturbed_events() == []


async def test_ac_mixed_a_reproduced_failure_means_the_run_is_not_disturbed(app, monkeypatch):
    await _plain_task(TASK, assignee="builder")
    tests = _tests(4)
    result = _confirmed(monkeypatch, tests, still_failing=[tests[3]], threshold=3)
    assert "disturbed" not in result and result["confirmed"]
    assert result["compared_tests"] == [tests[3]] and result["flaky_tests"] == tests[:3]
    await known_failing.record_run(await _run_row("chk-mixed", [result]))

    assert sorted(e.test for e in await _entries()) == tests[:3]
    assert await _disturbed_events() == []


async def test_ac_threshold_the_setting_is_stored_refused_below_two_and_defaults_to_three(
    app, auth_headers
):
    ok = await app.put(
        SETTINGS, json={"checks": [{**CHECK, "disturbed_threshold": 6}]}, headers=auth_headers
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["checks"][0]["disturbed_threshold"] == 6
    from hub.db.models import Project

    async with async_session_factory() as session:
        checks = project_checks.configured_checks(await session.get(Project, "proj-test"))
    assert checks[0]["disturbed_threshold"] == 6

    refused = await app.put(
        SETTINGS, json={"checks": [{**CHECK, "disturbed_threshold": 1}]}, headers=auth_headers
    )
    assert refused.status_code == 422 and "disturbed_threshold" in refused.text
    async with async_session_factory() as session:  # the refusal changed nothing
        checks = project_checks.configured_checks(await session.get(Project, "proj-test"))
    assert checks[0]["disturbed_threshold"] == 6

    await app.put(SETTINGS, json={"checks": [CHECK]}, headers=auth_headers)
    async with async_session_factory() as session:
        checks = project_checks.configured_checks(await session.get(Project, "proj-test"))
    assert checks[0]["disturbed_threshold"] == 3


async def test_ac_threshold_the_stored_threshold_decides_the_next_run(app, monkeypatch):
    six = _confirmed(monkeypatch, _tests(5), threshold=6)
    assert "disturbed" not in six
    five = _confirmed(monkeypatch, _tests(5), threshold=5)
    assert five["disturbed"]["threshold"] == 5


async def test_ac_known_flake_a_listed_flake_still_counts_inside_a_disturbed_run(app, monkeypatch):
    await _plain_task(TASK, assignee="builder")
    tests = _tests(5)
    # `tests[0]` flaked once before, in another run: listed, no task.
    await known_failing.record_run(
        await _run_row("chk-before", [_confirmed(monkeypatch, tests[:1], threshold=3)])
    )
    assert await _fix_tasks() == []

    result = _confirmed(monkeypatch, tests, threshold=3)
    assert result["disturbed"]
    await known_failing.record_run(await _run_row("chk-burst2", [result], task_id=TASK))

    assert [e.test for e in await _entries()] == [tests[0]]
    [fix] = await _fix_tasks()
    assert tests[0] in fix.title


async def test_ac_first_flake_a_task_is_filed_on_the_second_run_and_only_once(app, monkeypatch):
    await _plain_task(TASK, assignee="builder")
    await _plain_task(TASK2, assignee="builder")
    test = _tests(1)
    first = await _run_row("chk-f1", [_confirmed(monkeypatch, test, threshold=3)])
    await known_failing.record_run(first)
    await known_failing.record_run(first)  # the same run read twice
    assert [e.test for e in await _entries()] == test and await _fix_tasks() == []

    second = await _run_row("chk-f2", [_confirmed(monkeypatch, test, threshold=3)], task_id=TASK2)
    await known_failing.record_run(second)
    await known_failing.record_run(second)
    [fix] = await _fix_tasks()
    [entry] = await _entries()
    assert entry.fix_task_id == fix.id
    assert "chk-f2" in fix.description


async def test_ac_own_message_a_fix_task_quotes_its_own_tests_failure(app, monkeypatch):
    await _plain_task(TASK, assignee="builder")
    await _plain_task(TASK2, assignee="builder")
    a, b = _tests(2)
    messages = {a: "AssertionError: A's own message", b: "TimeoutError: B's message"}
    for n in (1, 2):
        # Two failures, below the threshold of 3, both flake: A is filed on its second.
        result = _confirmed(monkeypatch, [a, b], threshold=3, messages=messages)
        await known_failing.record_run(
            await _run_row(f"chk-m{n}", [result], task_id=TASK if n == 1 else TASK2)
        )
    fixes = {t.title: t for t in await _fix_tasks()}
    fix_a = fixes[f"Fix flaky test {a}"]
    assert "A's own message" in fix_a.description and "B's message" not in fix_a.description

    # A report with no message for the test: the check's output, and it says so.
    c = "test_x.py::test_c"
    for n in (1, 2):
        result = _confirmed(monkeypatch, [c], threshold=3)
        await known_failing.record_run(
            await _run_row(f"chk-c{n}", [result], task_id=TASK if n == 1 else TASK2)
        )
    fix_c = {t.title: t for t in await _fix_tasks()}[f"Fix flaky test {c}"]
    assert "no failure message for this test" in fix_c.description
    assert "the check's output" in fix_c.description


async def test_a_disturbed_run_is_never_a_known_failing_entry(app, monkeypatch):
    """D5: an entry with no test would excuse every whole-check failure of the check at the gates."""
    await _plain_task(TASK, assignee="builder")
    await known_failing.record_run(
        await _run_row("chk-d5", [_confirmed(monkeypatch, _tests(4), threshold=3)])
    )
    async with async_session_factory() as session:
        assert (await session.execute(select(KnownFailingTest))).scalars().all() == []
