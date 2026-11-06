"""Checks wait less (`checks-wait-less-...`): stale results are refreshed when main moves, not when
someone approves, and a check may be scoped to the paths it covers.

Real git repositories and real check subprocesses, as in `test_project_checks_run.py`: a refresh
that "would have started" is not evidence that one starts.
"""

import asyncio
import time

import pytest

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskTransition
from hub.worktrees import task_branch_name

from .test_project_checks_gate import _approve
from .test_project_checks_run import (
    MAIN_FAIL,
    PASS,
    PY,
    _project,
    _runs,
    _task_with_work,
    listed_whole_check,
)
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


# --- FR-1: main moving refreshes the results waiting for review --------------------------------
# (`approved-work-merges-in-batches`, FR a-passed-task-check-is-not-rerun-when-main-moves: a pass
# counts whatever tip it ran on; a task with no result still gets a run.)


@pytest.fixture(autouse=True)
def _no_landing_timers():
    yield
    landing_queue.cancel_timers()


async def test_main_moving_reruns_no_passed_result_and_runs_a_missing_one(
    app, auth_headers, tmp_path
):
    """stale-pass-not-rerun, the acceptance drive of `stale-pass-counts`."""
    task_a, work_a = await _task_with_work(tmp_path)
    task_b, task_c = "task-c0ffee000002", "task-c0ffee000003"
    await _another_task(tmp_path, task_b, "other.py")
    await _another_task(tmp_path, task_c, "third.py")
    await _project([PASS])
    await _checked(task_b)
    before = _tip(tmp_path)
    assert [r.state for r in await _runs(task_b)] == ["passed"]

    approved = await _approve(app, auth_headers, task_a)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    assert work_a in commits_on(tmp_path, "main")
    after = _tip(tmp_path)
    assert after != before

    # A landing moved main: the Hub's own refresh, started by the landing.
    await project_checks.refresh("proj-test")
    await project_checks.drain()
    assert [r.state for r in await _runs(task_b)] == ["passed"], "a pass is not run again"
    runs_c = await _runs(task_c)
    assert [r.state for r in runs_c] == ["passed"] and runs_c[0].main_sha == after

    # B's pass on the earlier tip still counts for review and approval.
    async with async_session_factory() as session:
        assert await project_checks.review_wait(session, await session.get(Task, task_b)) is None
    approved_b = await _approve(app, auth_headers, task_b)
    assert approved_b.status_code == 200, approved_b.text
    assert len(await _runs(task_b)) == 1, "approval started no run of its own"


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
    """ac-outside-merge: the watcher the Hub starts, run as it runs, with a short interval. The
    task's result is a failure on the known-failing list, which a new tip asks again (a pass would
    count on any tip and not be re-run: `approved-work-merges-in-batches`, FR-9)."""
    task_id, _ = await _task_with_work(tmp_path)
    await _project([MAIN_FAIL])
    await listed_whole_check("suite")
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
    assert runs[-1].main_sha == tip and runs[-1].state == "failed"


async def test_the_hub_starts_the_watcher():
    import inspect

    from hub import main

    assert "watch_main_forever" in inspect.getsource(main.lifespan)


# --- FR-3, superseded by `a-check-run-finishes-when-master-moves`: a run main moves past runs on --


class _Gate:
    """A check that holds inside its process until the test releases it, so a main move lands while
    it executes without a race against a sleep. *fail_if* / *fail_unless* name a file in the tree
    it checks that decides its exit; *pass_if* passes at once (new work) without holding."""

    def __init__(self, tmp_path, *, fail_if="", fail_unless="", pass_if="", fast=False):
        ctl = tmp_path.parent / f"{tmp_path.name}-ctl"
        ctl.mkdir(exist_ok=True)
        self.inside, self.release = ctl / "inside", ctl / "release"
        script = ctl / "gate.py"
        script.write_text(
            "import os, pathlib, sys, time\n"
            f"if {pass_if!r} and os.path.exists({pass_if!r}):\n"
            "    sys.exit(0)\n"
            f"pathlib.Path({str(self.inside)!r}).touch()\n"
            "end = time.monotonic() + 120\n"
            f"while not pathlib.Path({str(self.release)!r}).exists() and time.monotonic() < end:\n"
            "    time.sleep(0.05)\n"
            f"if {fail_if!r} and os.path.exists({fail_if!r}):\n"
            "    print('fails here'); sys.exit(3)\n"
            f"if {fail_unless!r} and not os.path.exists({fail_unless!r}):\n"
            "    print('fails here'); sys.exit(4)\n",
            encoding="utf-8",
        )
        self.check = {
            "name": "gate",
            "command": f'{PY} "{script}"',
            "timeout_seconds": 150,
            "fast": fast,
        }

    async def entered(self):
        deadline = time.monotonic() + 60
        while not self.inside.exists() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert self.inside.exists(), "the check never started"


async def _executing(tmp_path, **gate):
    """A completed task whose run is executing its (held) check; its run id, the gate, and T1."""
    task_id, _ = await _task_with_work(tmp_path)
    held = _Gate(tmp_path, **gate)
    await _project([held.check])
    tip = _tip(tmp_path)
    first = await project_checks.request_run("proj-test", task_id)
    assert first
    await held.entered()
    assert project_checks.is_running(task_id)
    return task_id, first, held, tip


async def test_a_run_main_moved_past_runs_to_the_end(app, auth_headers, tmp_path):
    """ac-runs-through-a-move (FR-1)."""
    task_id, first, held, cut = await _executing(tmp_path)
    try:
        _move_main(tmp_path)
        await project_checks.refresh("proj-test")
        assert project_checks.is_running(task_id), "the move ended the run"
    finally:
        held.release.touch()
    await project_checks.drain()

    runs = await _runs(task_id)
    assert [(r.id, r.state, r.main_sha) for r in runs] == [(first, "passed", cut)]
    assert not runs[0].error
    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text


async def test_an_outside_commit_does_not_end_the_run(app, tmp_path):
    """ac-outside-move-too (FR-1): a commit made with git directly, noticed by the watcher."""
    task_id, first, held, cut = await _executing(tmp_path)
    try:
        moved = _move_main(tmp_path)
        await project_checks.watch_main_once()
        assert project_checks._seen_tips.get("proj-test") == moved, "the watcher did not look"
        assert project_checks.is_running(task_id), "the outside move ended the run"
    finally:
        held.release.touch()
    await project_checks.drain()

    assert [(r.id, r.state, r.main_sha) for r in await _runs(task_id)] == [(first, "passed", cut)]


async def test_new_work_still_supersedes_the_run(app, tmp_path):
    """ac-new-completion-supersedes (FR-2): completing again with new work ends the run on the old
    work. The gate passes at once on the new work (`more.py`), so only the old run is held."""
    task_id, first, held, _ = await _executing(tmp_path, pass_if="more.py", fast=True)
    try:
        newer = commit_on_branch(
            tmp_path, task_branch_name(task_id), "more.py", "y = 2\n", create=False
        )
        git(tmp_path, "checkout", "-q", "main")
        async with async_session_factory() as session:
            task = await session.get(Task, task_id)
            await project_checks.fast_checks_at_completion(session, task, "builder")
    finally:
        held.release.touch()
    await project_checks.drain()

    runs = await _runs(task_id)
    assert runs[0].id == first and runs[0].state == "superseded"
    assert "completed again" in runs[0].error
    assert [r.state for r in runs[1:]] == ["passed"]
    assert runs[1].target_shas == [newer]


async def test_two_moves_start_no_second_run(app, tmp_path):
    """ac-no-second-run (FR-3)."""
    task_id, first, held, cut = await _executing(tmp_path)
    try:
        for name in ("one.txt", "two.txt"):
            _move_main(tmp_path, name)
            await project_checks.refresh("proj-test")
            await asyncio.sleep(0.2)  # anything the refresh started has recorded its run
            assert [r.id for r in await _runs(task_id)] == [first], f"a run started at {name}"
            assert project_checks.is_running(task_id)
    finally:
        held.release.touch()
    await project_checks.drain()

    assert [(r.id, r.state, r.main_sha) for r in await _runs(task_id)] == [(first, "passed", cut)]


async def test_a_failure_shared_with_an_old_main_is_checked_again(app, tmp_path):
    """ac-old-tip-failure-rerun (FR-4): T1's main fails the check too -- listed, so not the task's
    own -- and T2 fixes it; once the run on T1 has ended, a run on T2 starts with no approval
    asked."""
    await listed_whole_check("gate")
    task_id, first, held, cut = await _executing(tmp_path, fail_unless="fixed.txt")
    try:
        fixed = _move_main(tmp_path, "fixed.txt")
        await project_checks.refresh("proj-test")
    finally:
        held.release.touch()
    await project_checks.drain()

    runs = await _runs(task_id)
    assert [(r.id, r.state, r.main_sha) for r in runs[:1]] == [(first, "failed", cut)]
    assert not project_checks.own_failure(runs[0].results), "the failure is listed"
    assert [(r.state, r.main_sha) for r in runs[1:]] == [("passed", fixed)]
    async with async_session_factory() as session:
        assert (await session.get(Task, task_id)).status == "completed", "nobody approved it"


async def test_an_own_failure_on_an_old_tip_goes_back_once(app, tmp_path):
    """ac-own-failure-returns (FR-5): the task's own failure on T1 returns it, as on the current
    tip, and main having moved to T2 starts nothing more."""
    task_id, first, held, cut = await _executing(tmp_path, fail_if="feature.py")
    try:
        _move_main(tmp_path)
        await project_checks.refresh("proj-test")
    finally:
        held.release.touch()
    await project_checks.drain()

    runs = await _runs(task_id)
    assert [(r.id, r.state, r.main_sha) for r in runs] == [(first, "failed", cut)]
    assert project_checks.own_failure(runs[0].results)
    async with async_session_factory() as session:
        assert (await session.get(Task, task_id)).status == "revision_needed"


async def test_a_move_during_the_checkout_does_not_end_the_check(app, tmp_path, monkeypatch):
    """The move lands before the check's process exists (its checkout is slow, as under load). It
    used to end the check as it started; a main move now ends nothing, so the run goes on to its
    end on the tip it was cut from."""
    import threading

    entered, release = threading.Event(), threading.Event()
    checkout = project_checks._checkout

    def slow_checkout(*args):
        entered.set()
        release.wait(60)
        return checkout(*args)

    monkeypatch.setattr(project_checks, "_checkout", slow_checkout)
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    cut = _tip(tmp_path)
    first = await project_checks.request_run("proj-test", task_id)
    assert first
    assert await asyncio.to_thread(entered.wait, 60), "the run never reached its checkout"
    _move_main(tmp_path)

    await project_checks.refresh("proj-test")
    release.set()
    await project_checks.drain()

    assert [(r.id, r.state, r.main_sha) for r in await _runs(task_id)] == [(first, "passed", cut)]


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


# --- FR-5, superseded by `approved-work-merges-in-batches` FR-9: a pass on an older tip counts ---


async def test_a_green_on_an_older_tip_counts_and_is_not_run_again(app, auth_headers, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS])
    await _checked(task_id)
    _move_main(tmp_path)

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    await project_checks.drain()
    assert len(await _runs(task_id)) == 1
    await landing_queue.drain()
    assert work in commits_on(tmp_path, "main")


async def test_a_superseded_result_holds_nothing_and_the_batch_checks_it(
    app, auth_headers, tmp_path
):
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS])
    await _checked(task_id)
    async with async_session_factory() as session:
        [run] = await _runs(task_id)
        row = await session.get(type(run), run.id)
        row.state = "superseded"
        await session.commit()

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    assert work not in commits_on(tmp_path, "main"), "queued for its batch"
    await landing_queue.drain()
    assert work in commits_on(tmp_path, "main")


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
