"""A disturbed landing run is run again, not blamed
(`a-landing-failure-is-blamed-on-a-task-only-when-it-reproduces-there`, task disturbed-landing-run,
FR-4).

Real git and a real pytest check, through the fixtures of `test_a_failing_batch_is_narrowed`. Five
tests in files no task of the batch changes fail on the batch's run and its confirmation, as a
loaded machine fails them, and pass after; or a task's work breaks them for real.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Dict

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import KnownFailingTest, Task, TaskCheckRun

from .test_a_failing_batch_is_narrowed import (  # noqa: F401 -- the autouse gather window
    _a_long_gather_window,
    _approve,
    _batches,
    _landing,
    _merged,
    _project,
    _repo,
    _status,
    _tasks,
)
from .test_a_landing_failure_is_blamed_only_where_it_reproduces import _failing_times

pytestmark = pytest.mark.asyncio

NAMES = ("load_a", "load_b", "load_c", "load_d", "load_e")


def _five_failing_times(counters: Path, times: int) -> Dict[str, str]:
    files: Dict[str, str] = {}
    for name in NAMES:
        files.update(_failing_times(name, counters / f"{name}.txt", times))
    return files


def _five_broken_by_marker() -> Dict[str, str]:
    """Five test files, none a task changes, each failing while `broken.txt` exists."""
    return {
        f"test_{name}.py": (
            "import os\n\n\n"
            f"def test_{name}():\n"
            f"    assert not os.path.exists('broken.txt'), '{name} broken'\n"
        )
        for name in NAMES
    }


def _disturbed_steps(batch) -> list:
    return [step for step in batch.narrowing or [] if step.get("disturbed")]


async def test_a_disturbed_run_is_run_again_and_lands(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-disturbed-retried: five failures in test files no batch task changed, threshold 3. The
    batch is not narrowed and nobody is sent back: its checks run once more, which is recorded, and
    pass, and the batch lands saying why it went past the failures."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    counters = tmp_path_factory.mktemp("counters")
    # Each fails the batch's run and its confirmation, then passes.
    _repo(tmp_path, ledger, _five_failing_times(counters, 2))
    await _project()
    ids, tips = await _tasks(tmp_path, [({"one.py": "x = 1\n"}, None), ({"two.py": "x\n"}, None)])
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert [await _status(task_id) for task_id in ids] == ["approved", "approved"]
    for task_id, tip in zip(ids, tips, strict=True):
        assert [row.commit_sha for row in await _merged(task_id)] == [tip]
    [batch] = await _batches()
    assert batch.state == "landed", (batch.state, batch.error)

    [again] = _disturbed_steps(batch)
    tests = {f"test_{name}::test_{name}" for name in NAMES}
    assert set(again["tests"]) == tests, again
    assert again["threshold"] == 3 and again["failed"] == 5, again
    assert again["rerun_state"] == "passed", again
    # No prefix was probed: the run again decided it.
    assert [step for step in batch.narrowing if "prefix" in step] == [], batch.narrowing
    async with async_session_factory() as session:
        first = await session.get(TaskCheckRun, again["run_id"])
        rerun = await session.get(TaskCheckRun, again["rerun_run_id"])
        assert first.state == "failed" and rerun.state == "passed"
        assert batch.check_run_id == rerun.id
        # A disturbed run lists none of its tests.
        assert (await session.execute(select(KnownFailingTest))).scalars().all() == []

    why = batch.override_reason or ""
    assert "disturbed run" in why and again["rerun_run_id"] in why, why
    assert all(test in why for test in tests), why
    for task_id in ids:
        assert (await _landing(task_id)).state == "landed"


async def test_a_disturbed_run_that_fails_again_is_blamed_only_where_it_reproduces(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """FR-4 with FR-1: the second task's work breaks five tests in files it does not change. The run
    is disturbed, so it runs once more first; that fails too, and narrowing proves the second task's
    prefix fails and the first's passes, so the second goes back -- after exactly one run again."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger, _five_broken_by_marker())
    await _project()
    ids, tips = await _tasks(
        tmp_path, [({"one.py": "x = 1\n"}, None), ({"broken.txt": "breaks\n"}, None)]
    )
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert [await _status(task_id) for task_id in ids] == ["approved", "revision_needed"]
    assert [row.commit_sha for row in await _merged(ids[0])] == [tips[0]]
    first = (await _batches())[0]
    [again] = _disturbed_steps(first)
    assert again["rerun_state"] == "failed", again
    probed = {step["prefix"]: step for step in first.narrowing if "prefix" in step}
    assert probed[2]["failed"] is True and probed[1]["failed"] is False, first.narrowing
    async with async_session_factory() as session:
        notes = str((await session.get(Task, ids[1])).notes)
    assert probed[2]["command"] in notes and probed[1]["command"] in notes, notes


async def test_a_run_again_waits_until_no_check_run_holds_a_slot():
    """'When no other check run holds the Hub's check slots': `_every_slot` is not entered while a
    run holds a slot, and while it is held no other run gets one."""
    semaphore = project_checks._semaphore()
    await semaphore.acquire()  # another check run, running
    entered = asyncio.Event()
    leave = asyncio.Event()

    async def quiet_run():
        async with project_checks._every_slot():
            entered.set()
            await leave.wait()

    waiter = asyncio.get_running_loop().create_task(quiet_run())
    await asyncio.sleep(0.05)
    assert not entered.is_set(), "entered while another check run held a slot"
    semaphore.release()
    await asyncio.wait_for(entered.wait(), timeout=5)
    assert semaphore.locked(), "another check run could start beside the run again"
    leave.set()
    await asyncio.wait_for(waiter, timeout=5)
    assert not semaphore.locked()
    project_checks._semaphores.clear()
