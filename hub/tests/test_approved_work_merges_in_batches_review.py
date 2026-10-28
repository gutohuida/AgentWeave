"""Review findings on slice E: work sent back does not land, an approval never waits for a batch, a
partial land survives a restart, and a task has one open landing."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.db import models
from hub.db.engine import async_session_factory
from hub.db.models import Task

from .test_a_failing_batch_is_narrowed import (
    _approve,
    _batches,
    _landing,
    _merged,
    _project,
    _repo,
    _status,
    _tasks,
)
from .test_approved_work_merges_in_batches import (
    approve,
    counting_check,
    landings_of,
    merged_rows,
    set_checks,
    tasks_under_review,
)
from .test_task_integration import commits_on, files_on, git


@pytest.fixture(autouse=True)
def _window(monkeypatch):
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


@pytest.mark.asyncio
async def test_work_sent_back_after_its_batch_was_checked_does_not_land(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    """A batch member the operator sends back (approved -> revision_needed) after the batch's check
    ran must not reach main."""
    from hub.task_transition_service import apply_transition
    from hub.task_transitions import operator

    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    for task_id in ids:
        assert (await approve(app, auth_headers, task_id)).status_code == 200

    real = landing_queue.run_batch_checks

    async def checked_then_sent_back(*args, **kwargs):
        outcome = await real(*args, **kwargs)
        async with async_session_factory() as session:
            task = await session.get(Task, ids[1])
            await apply_transition(
                session, task, "revision_needed", operator(), verdict_reason="not good after all"
            )
            await session.commit()
        return outcome

    monkeypatch.setattr(landing_queue, "run_batch_checks", checked_then_sent_back)
    await landing_queue.drain()

    async with async_session_factory() as session:
        status = (await session.get(Task, ids[1])).status
    on_main = git(tmp_path, "rev-list", "main").stdout.split()
    print("status", status, "landing", [row.state for row in await landings_of(ids[1])])
    print("merged rows", [r.commit_sha for r in await merged_rows(ids[1])])
    assert status == "revision_needed"
    assert works[1] not in on_main, "work sent back by the operator was landed on main"


@pytest.mark.asyncio
async def test_an_approval_during_a_running_batch_answers_at_once(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    """With checks, an approval made while a batch is checking must answer at once (queued).

    Ordered, not timed: the check holds until the test releases it, so the second approval either
    returns while the batch is still running or (if it waits for the batch) only after the release
    that comes after it -- never, so the check's own cap ends it and `finished` is there. A 3 s
    wall-clock bound measured the approval's own git work under load instead (3.7 s on a loaded
    local run, 2026-10-28).
    """
    import asyncio
    import sys

    outside = tmp_path_factory.mktemp("held")
    started, release, finished = (outside / n for n in ("started", "release", "finished"))
    script = outside / "held.py"
    script.write_text(
        "import pathlib, sys, time\n"
        "started, release, finished = map(pathlib.Path, sys.argv[1:4])\n"
        "started.touch()\n"
        "deadline = time.monotonic() + 60\n"
        "while not release.exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.05)\n"
        "finished.touch()\n",
        encoding="utf-8",
    )
    command = f'"{sys.executable}" "{script}" "{started}" "{release}" "{finished}"'
    check = {"name": "held", "command": command, "timeout_seconds": 120}
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 0.2)
    assert (await approve(app, auth_headers, ids[0])).status_code == 200
    for _ in range(600):  # the gather window passes and the timer starts the batch's check
        if started.exists():
            break
        await asyncio.sleep(0.05)
    assert started.exists(), "the first approval's batch never started its check"

    second = await approve(app, auth_headers, ids[1])
    batch_still_running = not finished.exists()
    release.touch()
    await landing_queue.drain()
    assert second.status_code == 200, second.text
    assert batch_still_running, "the approval answered only after the batch's check had ended"


@pytest.mark.asyncio
async def test_work_sent_back_while_queued_does_not_land(
    app, auth_headers, tmp_path, tmp_path_factory
):
    from hub.task_transition_service import apply_transition
    from hub.task_transitions import operator

    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 1)
    await set_checks([check])
    assert (await approve(app, auth_headers, ids[0])).status_code == 200
    async with async_session_factory() as session:
        task = await session.get(Task, ids[0])
        await apply_transition(
            session, task, "revision_needed", operator(), verdict_reason="overturned"
        )
        await session.commit()
    await landing_queue.drain()
    print("queued-then-sent-back landing", [row.state for row in await landings_of(ids[0])])
    assert works[0] not in git(tmp_path, "rev-list", "main").stdout.split()


@pytest.mark.asyncio
async def test_a_retry_while_a_landing_is_open_is_refused_and_nothing_is_lost(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """Try again on an approved task whose approval landing is still queued (the route allows it)."""
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 1)
    await set_checks([check])
    assert (await approve(app, auth_headers, ids[0])).status_code == 200
    retried = await app.post(
        f"/api/v1/projects/proj-test/tasks/{ids[0]}/integrations/retry", headers=auth_headers
    )
    assert retried.status_code == 409, retried.text
    assert "open landing" in retried.text
    await landing_queue.drain()
    states = [(row.kind, row.state) for row in await landings_of(ids[0])]
    print("landings", states)
    print("merged", [r.commit_sha for r in await merged_rows(ids[0])])
    assert works[0] in git(tmp_path, "rev-list", "main").stdout.split()
    assert all(state not in ("checking", "landing") for _, state in states), states


@pytest.mark.asyncio
async def test_a_restart_after_a_partial_land_loses_and_repeats_nothing(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    """Narrowing finds task 2; task 1 had a full pass on exactly P1, so P1 lands. Kill between the
    fast-forward and the records, then reconcile."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger)
    await _project()
    ids, tips = await _tasks(
        tmp_path,
        [({"one.py": "x = 1\n"}, None), ({"broken.txt": "b\n"}, None), ({"three.py": "x\n"}, None)],
    )
    # Task 1's own per-task run on the current tip: its merged tree is P1's tree.
    await project_checks.request_run("proj-test", ids[0], targets=[tips[0]])
    await project_checks.drain()
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    class Killed(BaseException):
        """The process dying: not an exception the queue may catch."""

    real = landing_queue._record_landed
    killed = {}

    async def killed_once(*args, **kwargs):
        if not killed:
            killed["at"] = True
            raise Killed()
        return await real(*args, **kwargs)

    monkeypatch.setattr(landing_queue, "_record_landed", killed_once)
    with pytest.raises(Killed):
        await landing_queue.drain()
    first = (await _batches())[0]
    print("after kill: batch", first.state, first.prefixes, first.task_ids)
    for task_id in ids:
        landing = await _landing(task_id)
        print(task_id, landing.state, landing.batch_id)
    main_before = git(tmp_path, "rev-parse", "main").stdout.strip()
    print("main", main_before, "== P1?", main_before == (first.prefixes or [None])[-1])

    error = None
    try:
        counts = await landing_queue.reconcile_at_startup()
        print("reconcile", counts)
    except Exception as exc:  # noqa: BLE001
        error = exc
        print("reconcile raised", type(exc).__name__, exc)
    for task_id in ids:
        landing = await _landing(task_id)
        print("after reconcile", task_id, landing.state, await _status(task_id))
    assert error is None, f"reconcile_at_startup raised: {error!r}"
    await landing_queue.drain()
    assert [row.commit_sha for row in await _merged(ids[0])] == [tips[0]]
    assert [row.commit_sha for row in await _merged(ids[2])] == [tips[2]]
    assert "broken.txt" not in files_on(tmp_path, "main")
    assert tips[1] not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_partial_land_without_a_restart(app, auth_headers, tmp_path, tmp_path_factory):
    """The same narrowing with no kill: P1 lands, 3 lands next, 2 sent back."""
    ledger = tmp_path_factory.mktemp("ledger") / "runs.txt"
    _repo(tmp_path, ledger)
    await _project()
    ids, tips = await _tasks(
        tmp_path,
        [({"one.py": "x = 1\n"}, None), ({"broken.txt": "b\n"}, None), ({"three.py": "x\n"}, None)],
    )
    await project_checks.request_run("proj-test", ids[0], targets=[tips[0]])
    await project_checks.drain()
    for task_id in ids:
        await _approve(app, auth_headers, task_id)
    await landing_queue.drain()
    for b in await _batches():
        print("batch", b.state, b.task_ids, b.error)
    assert [await _status(t) for t in ids] == ["approved", "revision_needed", "approved"]
    assert [row.commit_sha for row in await _merged(ids[0])] == [tips[0]]
    assert [row.commit_sha for row in await _merged(ids[2])] == [tips[2]]
    assert "broken.txt" not in files_on(tmp_path, "main")
    async with async_session_factory() as session:
        left = (
            await session.execute(
                select(models.TaskLanding.state).where(
                    models.TaskLanding.state.in_(("checking", "landing"))
                )
            )
        ).all()
    assert left == []


@pytest.mark.asyncio
async def test_a_batch_that_raises_is_failed_and_queued_again_not_left_checking(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    for task_id in ids:
        assert (await approve(app, auth_headers, task_id)).status_code == 200

    real = landing_queue.run_batch_checks

    async def broken(*args, **kwargs):
        raise ValueError("the checkout could not be made")

    monkeypatch.setattr(landing_queue, "run_batch_checks", broken)
    await landing_queue.drain()
    for task_id in ids:
        assert [row.state for row in await landings_of(task_id)] == ["queued"]
    failed = (await _batches())[0]
    assert failed.state == "interrupted"
    assert "checkout could not be made" in failed.error

    monkeypatch.setattr(landing_queue, "run_batch_checks", real)
    await landing_queue.drain()
    on_main = git(tmp_path, "rev-list", "main").stdout.split()
    assert all(work in on_main for work in works)


@pytest.mark.asyncio
async def test_the_operators_override_merge_records_its_reason_on_the_integration(
    app, auth_headers, tmp_path, tmp_path_factory
):
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 1, status="approved")
    await set_checks([check])
    async with async_session_factory() as session:
        task = await session.get(Task, ids[0])
        targets = await landing_queue.resolve_targets(session, task)
        landing_queue.stage(
            session,
            task,
            actor_kind="operator",
            actor="operator",
            kind="approval",
            targets=targets,
            unchecked=True,
            override_reason="the suite is red for reasons outside this work",
            override_by="operator",
        )
        await session.commit()
    await landing_queue.drain()
    rows = await merged_rows(ids[0])
    assert [row.commit_sha for row in rows] == [works[0]]
    assert rows[0].override_reason == "the suite is red for reasons outside this work"


@pytest.mark.asyncio
async def test_a_land_that_finds_main_moved_says_it_did_not_land(
    app, auth_headers, tmp_path, tmp_path_factory
):
    from hub.db.models import LandingBatch

    ids, works = await tasks_under_review(tmp_path, 1, status="approved")
    async with async_session_factory() as session:
        task = await session.get(Task, ids[0])
        targets = await landing_queue.resolve_targets(session, task)
        row = landing_queue.stage(
            session,
            task,
            actor_kind="operator",
            actor="operator",
            kind="approval",
            targets=targets,
        )
        row.state, row.batch_id = "checking", "lbat-stale"
        session.add(
            LandingBatch(
                id="lbat-stale",
                project_id="proj-test",
                base_sha="0" * 40,
                state="held",
                task_ids=[ids[0]],
                prefixes=[works[0]],
                results=[],
                narrowing=[],
            )
        )
        await session.commit()
        landing = row
    landed = await landing_queue._land_batch(
        tmp_path,
        "main",
        "lbat-stale",
        "0" * 40,
        [landing],
        [works[0]],
        1,
        landing_queue.Chain(),
        None,
    )
    assert landed is False
    assert works[0] not in git(tmp_path, "rev-list", "main").stdout.split()
