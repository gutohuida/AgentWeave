"""Checks wait less (`checks-wait-less-...`): stale results are refreshed when main moves, not when
someone approves, and a check may be scoped to the paths it covers.

Real git repositories and real check subprocesses, as in `test_project_checks_run.py`: a refresh
that "would have started" is not evidence that one starts.
"""

import asyncio
import time

import pytest

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskTransition
from hub.worktrees import task_branch_name

from .test_project_checks_gate import _approve
from .test_project_checks_run import PASS, PY, _project, _runs, _task_with_work
from .test_task_integration import commit_on_branch, commits_on, git

pytestmark = pytest.mark.asyncio


async def _another_task(tmp_path, task_id, filename, *, status="completed"):
    """A second task in `_task_with_work`'s loop, whose branch holds one commit to *filename*."""
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                loop_id="loop-checks",
                project_id="proj-test",
                title=f"Work {task_id}",
                description="",
                status=status,
                assignee="builder",
            )
        )
        await session.commit()
    work = commit_on_branch(tmp_path, task_branch_name(task_id), filename, "y = 2\n")
    git(tmp_path, "checkout", "-q", "main")
    return work


def _tip(tmp_path):
    return git(tmp_path, "rev-parse", "main").stdout.strip()


def _move_main(tmp_path, name="later.txt"):
    """A commit on main made with git directly, not through the Hub (the operator's own merge)."""
    (tmp_path / name).write_text("main moved\n", encoding="utf-8")
    git(tmp_path, "add", name)
    git(tmp_path, "commit", "-q", "-m", f"main moves on ({name})")
    return _tip(tmp_path)


async def _checked(*task_ids):
    for task_id in task_ids:
        await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()


# --- FR-1: main moving refreshes the results waiting for review ---------------------------------


async def test_landing_a_refreshes_b_without_bs_approval_being_asked(app, auth_headers, tmp_path):
    """ac-land-a-refreshes-b, the acceptance drive."""
    task_a, work_a = await _task_with_work(tmp_path)
    task_b = "task-c0ffee000002"
    await _another_task(tmp_path, task_b, "other.py")
    await _project([PASS])
    await _checked(task_a, task_b)
    before = _tip(tmp_path)
    assert [r.state for r in await _runs(task_b)] == ["passed"]

    approved = await _approve(app, auth_headers, task_a)
    assert approved.status_code == 200, approved.text
    assert work_a in commits_on(tmp_path, "main")
    after = _tip(tmp_path)
    assert after != before

    # Nobody has asked to approve B: the refresh is the Hub's own, started by A landing.
    await project_checks.drain()
    runs = await _runs(task_b)
    assert [r.state for r in runs] == ["passed", "passed"]
    assert runs[-1].main_sha == after

    started = time.monotonic()
    approved_b = await _approve(app, auth_headers, task_b)
    assert approved_b.status_code == 200, approved_b.text
    assert time.monotonic() - started < 30
    assert len(await _runs(task_b)) == 2, "approval started no run of its own"


async def test_a_task_in_progress_is_not_refreshed(app, tmp_path):
    """ac-in-progress-not-refreshed."""
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    await _checked(task_id)
    async with async_session_factory() as session:
        (await session.get(Task, task_id)).status = "in_progress"
        await session.commit()
    _move_main(tmp_path)

    await project_checks.refresh("proj-test")
    await project_checks.drain()

    assert len(await _runs(task_id)) == 1


# --- FR-2: a move made outside the Hub is noticed ------------------------------------------------


async def test_a_commit_made_with_git_directly_is_refreshed_by_the_watcher(
    app, tmp_path, monkeypatch
):
    """ac-outside-merge: the watcher the Hub starts, run as it runs, with a short interval."""
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    await _checked(task_id)
    assert project_checks.WATCH_SECONDS <= 60, "the 120s promise needs two looks inside it"
    monkeypatch.setattr(project_checks, "WATCH_SECONDS", 0.2)
    watcher = asyncio.create_task(project_checks.watch_main_forever())
    try:
        await asyncio.sleep(1)  # the watcher has seen main as it is
        tip = _move_main(tmp_path)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if any(r.main_sha == tip for r in await _runs(task_id)):
                break
            await asyncio.sleep(0.2)
    finally:
        watcher.cancel()
        with pytest.raises(asyncio.CancelledError):
            await watcher
    await project_checks.drain()
    runs = await _runs(task_id)
    assert runs[-1].main_sha == tip and runs[-1].state == "passed"


async def test_the_hub_starts_the_watcher():
    import inspect

    from hub import main

    assert "watch_main_forever" in inspect.getsource(main.lifespan)


# --- FR-3: a run main has moved past is ended and replaced ---------------------------------------

#: Holds its output pipe through a grandchild, as `test_a_check_past_its_timeout_...` does: the run
#: ends promptly only if the whole tree is ended.
HANG = {
    "name": "slow",
    "command": (
        f'{PY} -c "import subprocess,sys,time,os; '
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']) "
        "if not os.path.exists('later.txt') else None; "
        "time.sleep(0 if os.path.exists('later.txt') else 120)\""
    ),
    "timeout_seconds": 300,
}


async def test_a_run_main_moved_past_is_superseded_and_replaced(app, tmp_path):
    """ac-superseded."""
    task_id, _ = await _task_with_work(tmp_path)
    await _project([HANG])
    first = await project_checks.request_run("proj-test", task_id)
    assert first
    # The check is executing: its process exists. A fixed sleep raced the checkout under load.
    deadline = time.monotonic() + 60
    while task_id not in project_checks._processes and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    assert task_id in project_checks._processes, "the check never started"
    assert project_checks.is_running(task_id)
    tip = _move_main(tmp_path)

    started = time.monotonic()
    await project_checks.refresh("proj-test")
    await project_checks.drain()
    assert time.monotonic() - started < 60, "the old run's process tree was not ended"

    runs = await _runs(task_id)
    assert [r.state for r in runs] == ["superseded", "passed"]
    assert runs[0].id == first and runs[0].ended_at is not None
    assert runs[0].results == [], "the ended check is not recorded as a failure"
    assert tip[:12] in runs[0].error
    assert runs[1].main_sha == tip


async def test_a_move_during_the_checkout_still_ends_the_check(app, tmp_path, monkeypatch):
    """The move lands before the check's process exists (its checkout is slow, as under load):
    `supersede` finds nothing to end, so the check must end itself as it starts, not hang."""
    import threading

    entered, release = threading.Event(), threading.Event()
    checkout = project_checks._checkout

    def slow_checkout(*args):
        entered.set()
        release.wait(60)
        return checkout(*args)

    monkeypatch.setattr(project_checks, "_checkout", slow_checkout)
    task_id, _ = await _task_with_work(tmp_path)
    await _project([HANG])
    first = await project_checks.request_run("proj-test", task_id)
    assert first
    assert await asyncio.to_thread(entered.wait, 60), "the run never reached its checkout"
    tip = _move_main(tmp_path)

    started = time.monotonic()
    await project_checks.refresh("proj-test")
    assert task_id not in project_checks._processes
    release.set()
    await project_checks.drain()
    assert time.monotonic() - started < 60, "the check started after the move was not ended"

    runs = await _runs(task_id)
    assert [r.state for r in runs] == ["superseded", "passed"]
    assert runs[0].id == first and runs[0].results == []
    assert runs[1].main_sha == tip


# --- FR-4: oldest completed first ---------------------------------------------------------------


async def test_refresh_starts_the_oldest_completed_first(app, tmp_path):
    """ac-order: three stale tasks, two slots; the newest-completed starts last."""
    first, _ = await _task_with_work(tmp_path)
    second, third = "task-c0ffee000002", "task-c0ffee000003"
    # Created out of order, completed in order: the order is completion, not creation.
    await _another_task(tmp_path, third, "c.py")
    await _another_task(tmp_path, second, "b.py")
    async with async_session_factory() as session:
        for number, task_id in enumerate((first, second, third)):
            session.add(
                TaskTransition(
                    id=f"ttr-order{number}",
                    project_id="proj-test",
                    task_id=task_id,
                    from_status="in_progress",
                    to_status="completed",
                    actor_kind="operator",
                    origin="actor",
                )
            )
            await session.flush()
        await session.commit()
    stamp = {
        "name": "stamp",
        "command": f'{PY} -c "import time; print(time.time()); time.sleep(1.5)"',
        "timeout_seconds": 60,
    }
    await _project([stamp])
    _move_main(tmp_path)

    await project_checks.refresh("proj-test")
    await project_checks.drain()

    began = {}
    for task_id in (first, second, third):
        [run] = await _runs(task_id)
        assert run.state == "passed"
        began[task_id] = float(run.results[0]["output_tail"].split()[0])
    assert began[third] > began[first] and began[third] > began[second]


# --- FR-5: the gate still wants a result for the current tip -------------------------------------


async def test_a_green_on_an_older_tip_still_does_not_pass(app, auth_headers, tmp_path):
    """ac-stale-still-refused: nothing refreshed it (no watcher here), so approval refuses."""
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS])
    await _checked(task_id)
    _move_main(tmp_path)

    refused = await _approve(app, auth_headers, task_id)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["checks"][0]["state"] == "running"
    assert work not in commits_on(tmp_path, "main")
    await project_checks.drain()


async def test_a_superseded_result_does_not_pass(app, auth_headers, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS])
    await _checked(task_id)
    async with async_session_factory() as session:
        [run] = await _runs(task_id)
        row = await session.get(type(run), run.id)
        row.state = "superseded"
        await session.commit()

    refused = await _approve(app, auth_headers, task_id)
    assert refused.status_code == 409, refused.text
    assert work not in commits_on(tmp_path, "main")
    await project_checks.drain()


# --- FR-7 / FR-8: a check scoped to paths it does not touch is skipped, and passes --------------


async def test_path_patterns_match_as_globs():
    match = project_checks.path_matches
    assert match("hub/**", "hub/hub/a.py")
    assert match("hub/**", "hub/x")
    assert not match("hub/**", "spec/x.json")
    assert not match("hub/**", "hubx/a.py")
    assert match("constraints-dev.txt", "constraints-dev.txt")
    assert not match("constraints-dev.txt", "hub/constraints-dev.txt")
    assert match("**/*.py", "a.py") and match("**/*.py", "hub/hub/a.py")
    assert match("src/*.py", "src/a.py") and not match("src/*.py", "src/x/a.py")
    assert match("hub/", "hub/hub/a.py"), "a directory names everything under it"


SCOPED = {**PASS, "name": "hub-tests", "paths": ["hub/**", "constraints-dev.txt"]}


async def _task_changing(tmp_path, path):
    task_id, _ = await _task_with_work(tmp_path)
    git(tmp_path, "checkout", "-q", task_branch_name(task_id))
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text("z = 3\n", encoding="utf-8")
    git(tmp_path, "rm", "-q", "feature.py")
    git(tmp_path, "add", path)
    git(tmp_path, "commit", "-q", "-m", f"only {path}")
    git(tmp_path, "checkout", "-q", "main")
    return task_id


async def test_a_check_whose_paths_match_nothing_is_skipped_and_passes(app, auth_headers, tmp_path):
    """ac-skip-unmatched and ac-skip-passes-and-shows (the gate half)."""
    task_id = await _task_changing(tmp_path, "spec/x.json")
    await _project([{**SCOPED, "command": f'{PY} -c "import sys; sys.exit(9)"'}])
    await _checked(task_id)

    [run] = await _runs(task_id)
    assert run.state == "passed"
    [result] = run.results
    assert result["skipped"] is True and result["exit_code"] is None
    assert "no changed file matched" in result["reason"] and "hub/**" in result["reason"]
    assert not project_checks.failed(result)

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text


async def test_a_check_whose_paths_match_runs(app, tmp_path):
    """ac-run-matched."""
    task_id = await _task_changing(tmp_path, "hub/hub/a.py")
    await _project([{**SCOPED, "command": f'{PY} -c "import sys; sys.exit(9)"'}])
    await _checked(task_id)

    [run] = await _runs(task_id)
    assert run.results[0]["exit_code"] == 9 and not run.results[0].get("skipped")


async def test_a_check_with_no_paths_always_runs(app, tmp_path):
    """ac-unscoped-always."""
    task_id = await _task_changing(tmp_path, "spec/x.json")
    await _project([{**PASS, "command": f'{PY} -c "import sys; sys.exit(9)"'}])
    await _checked(task_id)

    [run] = await _runs(task_id)
    assert run.results[0]["exit_code"] == 9 and not run.results[0].get("skipped")


async def test_the_checks_route_shows_a_skipped_check(app, auth_headers, tmp_path):
    """The drawer reads this route; a skipped check is in it, not left out."""
    task_id = await _task_changing(tmp_path, "spec/x.json")
    await _project([SCOPED, PASS])
    await _checked(task_id)

    read = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}/checks", headers=auth_headers)
    assert read.status_code == 200, read.text
    results = read.json()["runs"][0]["results"]
    assert [(r["name"], bool(r.get("skipped"))) for r in results] == [
        ("hub-tests", True),
        ("ok", False),
    ]
