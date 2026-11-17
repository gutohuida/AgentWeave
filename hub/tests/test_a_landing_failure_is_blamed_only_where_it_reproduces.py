"""A landing failure is blamed on a task only when it reproduces there
(`a-landing-failure-is-blamed-on-a-task-only-when-it-reproduces-there`, task prove-the-culprit).

Real git and a real pytest check, through the fixtures of `test_a_failing_batch_is_narrowed`. A
test that fails a set number of times and then passes keeps its count in a file outside the
repository, so "it failed on the batch and its confirmation, then passed everywhere" is exactly
what happens, not a mock of it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest
from sqlalchemy import select

from hub import landing_queue
from hub.db.engine import async_session_factory
from hub.db.models import KnownFailingTest, Project, Task

from .test_a_failing_batch_is_narrowed import (  # noqa: F401 -- the autouse gather window
    NO_MARKER,
    PYTEST,
    TASKS,
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
from .test_task_integration import commits_on

pytestmark = pytest.mark.asyncio


def _failing_times(name: str, counter: Path, times: int) -> Dict[str, str]:
    """A test file whose one test fails its first *times* runs, counted in *counter*."""
    counter.write_text(str(times), encoding="utf-8")
    return {
        f"test_{name}.py": (
            f"def test_{name}():\n"
            f"    path = r'{counter}'\n"
            "    left = int(open(path).read())\n"
            "    if left > 0:\n"
            "        open(path, 'w').write(str(left - 1))\n"
            f"        assert False, '{name} failed this time'\n"
        )
    }


def _failing_on_full_runs(name: str, state: Path) -> Dict[str, str]:
    """A test file whose one test fails every run of the whole suite and the re-run straight after
    one (its confirmation), and passes any other run of named tests (a probe): in *state*, whether
    the last run was of the whole suite."""
    state.write_text("", encoding="utf-8")
    return {
        f"test_{name}.py": (
            "import sys\n\n\n"
            f"def test_{name}():\n"
            f"    path = r'{state}'\n"
            "    whole = not any('::' in arg for arg in sys.argv)\n"
            "    last = open(path).read()\n"
            "    open(path, 'w').write('whole' if whole else 'named')\n"
            f"    assert not (whole or last == 'whole'), '{name} failed this time'\n"
        )
    }


async def _xunit2() -> None:
    """The project's pytest check writing pytest's default report, which names no test's file: as
    in a real project, every failing test then counts as touched by the work."""
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        command = PYTEST["command"].replace("junit_family=xunit1", "junit_family=xunit2")
        project.checks = [{**PYTEST, "command": command}]
        await session.commit()


async def _listed(test: str) -> list:
    async with async_session_factory() as session:
        return (
            (await session.execute(select(KnownFailingTest).where(KnownFailingTest.test == test)))
            .scalars()
            .all()
        )


async def test_a_regression_is_sent_back_with_its_proof(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-regression-still-blamed and ac-proof-in-note: of three, the second adds the file the suite
    fails on. It goes back, proven on its prefix and passing on the one before it; the note names
    both commands, their exit codes and the failing test; the other two land."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger)
    await _project()
    ids, tips = await _tasks(
        tmp_path,
        [
            ({"one.py": "x = 1\n"}, None),
            ({"broken.txt": "this breaks the suite\n"}, None),
            ({"three.py": "x = 3\n"}, None),
        ],
    )
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert [await _status(task_id) for task_id in ids] == [
        "approved",
        "revision_needed",
        "approved",
    ]
    assert await _merged(ids[1]) == []
    assert tips[1] not in commits_on(tmp_path, "main")
    for task_id, tip in ((ids[0], tips[0]), (ids[2], tips[2])):
        assert [row.commit_sha for row in await _merged(task_id)] == [tip]

    first = (await _batches())[0]
    probed = {step["prefix"]: step for step in first.narrowing}
    assert probed[2]["failed"] is True and probed[1]["failed"] is False, first.narrowing
    assert all(step["tests"] == [NO_MARKER] for step in first.narrowing), first.narrowing
    assert probed[2]["failed_tests"] == [NO_MARKER], probed[2]

    async with async_session_factory() as session:
        notes = str((await session.get(Task, ids[1])).notes)
    for step in (probed[1], probed[2]):
        assert step["command"] in notes, notes
        assert f"exit code {step['exit_code']}" in notes, notes
    assert probed[2]["exit_code"] != 0 and probed[1]["exit_code"] == 0
    assert NO_MARKER in notes
    assert first.override_reason is None


async def test_the_last_prefix_is_not_blamed_by_elimination(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-last-prefix-not-blamed-by-elimination, ac-unreproduced-lands-as-flaky and
    ac-landing-record: a test fails on the batch and its confirmation, then passes on every prefix.
    Nobody is sent back; prefix 2 is probed; the check runs once more, passes, and the batch lands
    with the test on the known-failing list as flaky and its landing saying why."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    counter = tmp_path_factory.mktemp("counter") / "left.txt"
    _repo(tmp_path, ledger, _failing_times("wobbly", counter, 2))
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
    assert {step["prefix"] for step in batch.narrowing} >= {2}, batch.narrowing
    assert not any(step["failed"] for step in batch.narrowing), batch.narrowing

    wobbly = "test_wobbly::test_wobbly"
    async with async_session_factory() as session:
        listed = (
            (await session.execute(select(KnownFailingTest).where(KnownFailingTest.test == wobbly)))
            .scalars()
            .all()
        )
    assert [entry.kind for entry in listed] == ["flaky"], listed

    for task_id in ids:
        read = await app.get(f"{TASKS}/{task_id}/checks", headers=auth_headers)
        landing = read.json()["landing"]
        assert landing["state"] == "landed", landing
        why = landing["override_reason"] or ""
        assert wobbly in why and "reproduced on no task's work" in why, landing
        assert landing["batch"]["override_reason"] == why


async def test_every_failing_test_is_probed(app, auth_headers, tmp_path, tmp_path_factory):
    """ac-probe-runs-all-failed: the batch fails three tests; two pass their confirmation (they
    fail once), one -- broken by the first task -- does not. Narrowing probes all three on prefix
    1, where one fails, and the first task goes back."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    counters = tmp_path_factory.mktemp("counters")
    extra = {
        **_failing_times("once_b", counters / "b.txt", 1),
        **_failing_times("once_c", counters / "c.txt", 1),
    }
    _repo(tmp_path, ledger, extra)
    await _project()
    ids, _tips = await _tasks(
        tmp_path, [({"broken.txt": "breaks\n"}, None), ({"two.py": "x = 2\n"}, None)]
    )
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert await _status(ids[0]) == "revision_needed"
    first = (await _batches())[0]
    probed = {step["prefix"]: step for step in first.narrowing}
    named = {NO_MARKER, "test_once_b::test_once_b", "test_once_c::test_once_c"}
    assert set(probed[1]["tests"]) == named, probed[1]
    assert all(test in probed[1]["command"] for test in named), probed[1]["command"]
    assert probed[1]["failed"] is True
    assert probed[0]["failed"] is False, "the batch's base is the commit before the first task"
    assert (await _landing(ids[0])).state == "sent_back"


async def test_an_unreproduced_failure_is_listed_when_its_report_names_no_file(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """ac-unreproduced-lands-as-flaky with pytest's default (xunit2) report, which gives no test's
    file, so the run counts every failing test as touched by the work: a failure narrowing showed
    reproduces on no prefix is still listed flaky, and the landing says so."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    counter = tmp_path_factory.mktemp("counter") / "left.txt"
    _repo(tmp_path, ledger, _failing_times("wobbly", counter, 2))
    await _project()
    await _xunit2()
    ids, _tips = await _tasks(tmp_path, [({"one.py": "x = 1\n"}, None), ({"two.py": "x\n"}, None)])
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    await landing_queue.drain()

    assert [await _status(task_id) for task_id in ids] == ["approved", "approved"]
    [batch] = await _batches()
    assert batch.state == "landed", (batch.state, batch.error)
    wobbly = "test_wobbly::test_wobbly"
    assert [entry.kind for entry in await _listed(wobbly)] == ["flaky"]
    assert f"On the known-failing list as flaky: {wobbly}." in (batch.override_reason or "")
    assert "Not on the known-failing list" not in batch.override_reason


async def test_a_failure_again_on_no_prefix_lands_the_batch(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """FR-3, round two: the batch fails on a test no prefix reproduces, its checks run once more and
    fail again, and again on no prefix. Nobody is sent back and nothing is held: the batch lands,
    the test is listed flaky, and the landing says it failed again on no task's prefix."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    state = tmp_path_factory.mktemp("state") / "last.txt"
    _repo(tmp_path, ledger, _failing_on_full_runs("stubborn", state))
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
    assert batch.narrowing and not any(step["failed"] for step in batch.narrowing)
    stubborn = "test_stubborn::test_stubborn"
    assert [entry.kind for entry in await _listed(stubborn)] == ["flaky"]
    why = batch.override_reason or ""
    assert "reproduced on no task's work" in why and "failed again" in why, why
    assert why.count(stubborn) >= 2, "both rounds' failures are named"
