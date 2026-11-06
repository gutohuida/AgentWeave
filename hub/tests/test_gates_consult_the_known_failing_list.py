"""The completion and landing gates judge failures against the known-failing list
(`failures-already-known-are-on-a-list-not-re-argued`, task `gates`: FR-7, FR-9).

Real git repositories and real checks run by the Hub: the ledger repository of
`test_a_red_main_does_not_hold_the_night.py` (main fails `test_a`) with its JUnit-reporting pytest
check, a check that writes no report, and a check that runs out of time on one task's work. Every
checkout a check makes is recorded, so "nothing ran on main" is counted, not inferred.
"""

from __future__ import annotations

import sys

import pytest
from sqlalchemy import func, select

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import LandingBatch, MainCheckRun, Task, TaskTransition

from . import test_a_red_main_does_not_hold_the_night as red
from .test_build_levels import _build_row, _in_build
from .test_project_checks_run import listed_whole_check
from .test_task_integration import commits_on, git

pytestmark = pytest.mark.asyncio

PY = f'"{sys.executable}"'
#: A check that writes no report and fails on every tree.
NO_REPORT = {
    "name": "script",
    "command": f"{PY} -c \"import sys; print('it is broken'); sys.exit(1)\"",
    "timeout_seconds": 60,
}
#: Runs out of time, naming no failing test, wherever `slow.txt` is; passes at once elsewhere.
SLOW = {
    "name": "slow",
    "command": f"{PY} -c \"import os, time; time.sleep(60 if os.path.exists('slow.txt') else 0)\"",
    "timeout_seconds": 3,
}


@pytest.fixture(autouse=True)
def _no_landing_timers():
    yield
    landing_queue.cancel_timers()


async def _status(task_id: str) -> str:
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).status


async def _main_runs() -> int:
    async with async_session_factory() as session:
        return (await session.execute(select(func.count()).select_from(MainCheckRun))).scalar()


async def _decided(task_id: str) -> None:
    """*task_id*'s checks run while it waits for review (`completed`), as after its completion."""
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()


async def test_ac_own_failure_a_gated_build_judges_by_the_list_and_never_by_main(
    app, tmp_path, monkeypatch
):
    """ac-own-failure: two tasks of a Gated build. The first's check fails only test_a, which is on
    the list: it is not sent back. The second's fails test_b too, which is not on the list and
    still fails when re-run: it is sent back as its own failure. No check ran on a checkout of
    main, and no run on main was made."""
    red._repo(tmp_path)  # main fails test_a
    await red._loop()
    await red._task(tmp_path, red.TASK, {"feature.py": "x = 1\n"})
    await red._task(tmp_path, red.TASK2, {"ledger.py": "A = 1\nB = 3\n"})
    build_id = await _build_row("gated", loop_id=red.LOOP)
    for task_id in (red.TASK, red.TASK2):
        await _in_build(task_id, build_id, "gated")
    await red._configure()
    await red._listed()
    base = git(tmp_path, "rev-parse", "main").stdout.strip()
    made = red._main_checkouts(monkeypatch)

    await _decided(red.TASK)
    await _decided(red.TASK2)

    [listed_only] = (await red._latest_run(red.TASK)).results
    assert listed_only["preexisting"] and listed_only["shared_tests"] == [red.TEST_A]
    assert await _status(red.TASK) == "completed", "a listed failure is not sent back"
    [own] = (await red._latest_run(red.TASK2)).results
    assert own["confirmed"] and own["own_tests"] == [red.TEST_B], own
    assert own["shared_tests"] == [red.TEST_A] and not own["preexisting"]
    assert await _status(red.TASK2) == "revision_needed"
    async with async_session_factory() as session:
        back = (
            await session.execute(
                select(TaskTransition).where(
                    TaskTransition.task_id == red.TASK2,
                    TaskTransition.to_status == "revision_needed",
                )
            )
        ).scalar_one()
    assert back.origin == "checks" and back.reason_class, (back.origin, back.reason_class)
    async with async_session_factory() as session:
        notes = str((await session.get(Task, red.TASK2)).notes)
    assert red.TEST_B in notes, notes  # the failure report names the task's own test
    assert red._on_main(made, [base]) == [], made
    assert await _main_runs() == 0


async def test_ac_whole_check_the_completion_gate_reads_a_whole_check_entry(app, tmp_path):
    """ac-whole-check, at the completion gate: a check that writes no report fails for a task.
    Without an entry for the whole check the task is sent back; with one, the failure is not the
    task's and it stays waiting for review."""
    red._repo(tmp_path)
    await red._loop()
    await red._task(tmp_path, red.TASK, {"feature.py": "x = 1\n"})
    await red._task(tmp_path, red.TASK2, {"other.py": "y = 1\n"})
    await red._configure(checks=(NO_REPORT,))

    await _decided(red.TASK)
    [unlisted] = (await red._latest_run(red.TASK)).results
    assert not unlisted["preexisting"] and unlisted["listed"] == []
    assert await _status(red.TASK) == "revision_needed"

    entry = await listed_whole_check("script")
    await _decided(red.TASK2)
    [listed] = (await red._latest_run(red.TASK2)).results
    assert listed["preexisting"] and [e["id"] for e in listed["listed"]] == [entry]
    assert await _status(red.TASK2) == "completed"
    assert await _main_runs() == 0


async def test_ac_no_hold_a_batch_timing_out_twice_is_narrowed_to_the_task_that_times_out(
    app, tmp_path
):
    """ac-no-hold, its second batch: three tasks land in one batch, and the second one's work makes
    the check run out of time naming no failing test. The batch is queued again once; the second
    time it is narrowed: the first task lands, the second goes back to its author with the reason
    'timed out', and the third is queued again (and lands after). No batch is held."""
    red._repo(tmp_path, {"ledger.py": "A = 2\nB = 2\n"})
    await red._loop()
    first = await red._task(tmp_path, "task-c0ffee00b001", {"one.py": "x = 1\n"})
    await red._task(tmp_path, "task-c0ffee00b002", {"slow.txt": "slow\n"})
    third = await red._task(tmp_path, "task-c0ffee00b003", {"three.py": "z = 3\n"})
    ids = ["task-c0ffee00b001", "task-c0ffee00b002", "task-c0ffee00b003"]
    await red._configure(checks=(SLOW,))
    # The first task's own run passed on the tree of its prefix: what lets it land on its own.
    await _decided(ids[0])
    assert (await red._latest_run(ids[0])).state == "passed"
    for task_id in ids:
        approved = await red._reviewer_approves(app, task_id)
        assert approved.status_code == 200, approved.text

    await landing_queue.drain()  # the first unjudged timeout: queued again, nobody blamed
    async with async_session_factory() as session:
        [once] = (await session.execute(select(LandingBatch))).scalars().all()
    assert once.error.startswith(landing_queue.UNJUDGED_TIMEOUT) and once.task_ids == ids
    assert [await _status(t) for t in ids] == ["approved"] * 3
    await landing_queue.drain()  # the second: narrowed

    async with async_session_factory() as session:
        batches = (
            (await session.execute(select(LandingBatch).order_by(LandingBatch.created_at)))
            .scalars()
            .all()
        )
    assert "held" not in [b.state for b in batches], [(b.state, b.error) for b in batches]
    narrowed = batches[1]
    assert narrowed.task_ids == ids and [n["prefix"] for n in narrowed.narrowing] == [2, 1]
    assert await _status(ids[1]) == "revision_needed"
    landing = await red._landing(app, ids[1])
    assert landing["state"] == "sent_back" and landing["reason"].startswith("Timed out"), landing
    async with async_session_factory() as session:
        back = (
            await session.execute(
                select(TaskTransition).where(
                    TaskTransition.task_id == ids[1],
                    TaskTransition.to_status == "revision_needed",
                )
            )
        ).scalar_one()
    assert (back.reason or "").startswith("timed out"), back.reason
    assert first in commits_on(tmp_path, "main")
    # The third went back to the queue, not with the culprit, and landed in a batch of its own.
    assert [b.task_ids for b in batches[2:]] == [[ids[2]]]
    assert (await red._landing(app, ids[2]))["state"] == "landed"
    assert third in commits_on(tmp_path, "main")
