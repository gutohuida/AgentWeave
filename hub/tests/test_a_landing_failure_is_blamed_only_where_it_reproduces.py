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
from hub.db.models import KnownFailingTest, Task

from .test_a_failing_batch_is_narrowed import (  # noqa: F401 -- the autouse gather window
    NO_MARKER,
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
