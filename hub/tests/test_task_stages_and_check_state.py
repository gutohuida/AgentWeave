"""A task's pre-review stage and its latest check state, on the task list and the build read
(`task-stages-in-the-build-view-and-dependency-map`, FR-1..FR-6, FR-13; task
hub-stage-and-check-state).

Every run here is made by `project_checks` (its scheduling, slots, runner and return of failed
work) or by `landing_queue`, with real check subprocesses and real git, as
`test_checks_run_before_review` and `test_a_failing_batch_is_narrowed` do: no run row or result is
written by hand. The stage is compared with `project_checks.review_wait` on the same database, task
by task, and the task list with the build read, so the two reads cannot drift apart.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, Task, TaskCheckRun, TaskLanding
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator, run_actor

from .test_a_check_that_cannot_run import _lint, _passing
from .test_a_failing_batch_is_narrowed import _approve, _project, _repo, _tasks
from .test_checks_run_before_review import (
    BUILDER_RUN,
    TASK,
    _builder_task,
    _complete,
    _completed_outside_a_flow,
    _configure,
    _end_the_builders_turn,
    _runs,
    _script,
    _scripts,
    _slow,
)
from .test_task_integration import commit_on_branch, git

pytestmark = pytest.mark.asyncio

TASKS = "/api/v1/projects/proj-test/tasks"
BUILD = "build-stages0001"
BUILD_TASKS = f"/api/v1/projects/proj-test/project/builds/{BUILD}/tasks"


@pytest.fixture(autouse=True)
def _no_reviewer_is_staffed(monkeypatch):
    """A decided run would hand a completed task to a reviewer; here the task must stay where its
    checks put it, so the stage is read on exactly the state the checks made."""
    from hub import review_on_completion

    monkeypatch.setattr(review_on_completion, "staff_review", AsyncMock(return_value=None))


@pytest.fixture(autouse=True)
def _a_long_gather_window(monkeypatch):
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


async def _wait_for(predicate, seconds: float = 60.0) -> None:
    for _ in range(int(seconds / 0.05)):
        if await predicate():
            return
        await asyncio.sleep(0.05)
    raise AssertionError("timed out")


async def _in_a_build(*task_ids: str) -> None:
    async with async_session_factory() as db:
        if await db.get(Build, BUILD) is None:
            db.add(
                Build(
                    id=BUILD,
                    project_id="proj-test",
                    document_id="spdoc-stages",
                    driver="flow",
                    level="reviewed",
                )
            )
        for task_id in task_ids:
            (await db.get(Task, task_id)).build_id = BUILD
        await db.commit()


async def _reads(app, auth_headers, *task_ids: str) -> Dict[str, Dict[str, Any]]:
    """Each task's `(stage, check_state)` from the task list, asserting the build read agrees."""
    listed = await app.get(TASKS, params={"limit": 1000}, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    built = await app.get(BUILD_TASKS, headers=auth_headers)
    assert built.status_code == 200, built.text
    on_list = {t["id"]: t for t in listed.json()["tasks"]}
    on_build = {t["id"]: t for t in built.json()["tasks"]}
    reads = {}
    for task_id in task_ids:
        row, build_row = on_list[task_id], on_build[task_id]
        assert (row["stage"], row["check_state"]) == (
            build_row["stage"],
            build_row["check_state"],
        ), f"the task list and the build read disagree on {task_id}"
        reads[task_id] = {
            "stage": row["stage"],
            "check": row["check_state"],
            "status": row["status"],
        }
    return reads


async def _review_wait(task_id: str):
    async with async_session_factory() as db:
        return await project_checks.review_wait(db, await db.get(Task, task_id))


def _check(kind: Optional[str], state: Optional[str] = None) -> Optional[Dict[str, str]]:
    return None if kind is None else {"kind": kind, "state": state}


async def _latest_state() -> str:
    runs = await _runs(TASK)
    return runs[-1].state if runs else ""


async def _slot_taken() -> bool:
    runs = await _runs(TASK)
    return bool(runs) and runs[-1].state == "running" and runs[-1].slot_at is not None


async def _queued() -> bool:
    runs = await _runs(TASK)
    return bool(runs) and runs[-1].id in project_checks._waiting_for_slot


# ---------------------------------------------------------------------------------------------
# stage-agrees-with-review-hold, could-not-run-not-failed, check-state-on-the-read
# ---------------------------------------------------------------------------------------------


async def _running(tmp_path: Path, sha: str, monkeypatch) -> None:
    release = _scripts(tmp_path) / "release-running"
    await _configure([_slow(tmp_path, release=release)])
    await project_checks.request_run("proj-test", TASK)
    await _wait_for(_slot_taken)
    return release


async def _queued_for_a_slot(tmp_path: Path, sha: str, monkeypatch):
    await _configure([_slow(tmp_path)])
    slots = project_checks._semaphore()
    for _ in range(project_checks.check_concurrency()):
        await slots.acquire()  # other runs hold every slot
    await project_checks.request_run("proj-test", TASK)
    await _wait_for(_queued)
    return slots


async def _not_yet_run(tmp_path: Path, sha: str, monkeypatch) -> None:
    await _configure([_slow(tmp_path)])


async def _could_not_run(tmp_path: Path, sha: str, monkeypatch) -> None:
    never = _scripts(tmp_path) / "never-installed"
    await _configure([_lint(tmp_path, never), _passing(tmp_path)])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()


async def _in_state_error(tmp_path: Path, sha: str, monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise RuntimeError("the runner broke")

    monkeypatch.setattr(project_checks, "run_one", broken)
    await _configure([_slow(tmp_path)])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    await project_checks.drain()  # its one retry (FR-9), which errs too


async def _interrupted(tmp_path: Path, sha: str, monkeypatch) -> None:
    release = _scripts(tmp_path) / "release-interrupted"
    await _configure([_slow(tmp_path, release=release)])
    await project_checks.request_run("proj-test", TASK)
    await _wait_for(_slot_taken)
    # What a Hub restart does to the run it left running.
    assert await project_checks.interrupt_leftover_runs() == 1
    release.write_text("go", encoding="utf-8")
    await project_checks.drain()


async def _passed(tmp_path: Path, sha: str, monkeypatch) -> None:
    await _configure([_slow(tmp_path)])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()


async def _own_failure(tmp_path: Path, sha: str, monkeypatch) -> None:
    await _configure([_slow(tmp_path, fails_on="ledger.py")])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()


async def _conflicted(tmp_path: Path, sha: str, monkeypatch) -> None:
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "ledger.py").write_text("x = 'main'\n", encoding="utf-8")
    git(tmp_path, "add", "ledger.py")
    git(tmp_path, "commit", "-q", "-m", "main writes the ledger too")
    await _configure([_slow(tmp_path)])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()


SCENARIOS = {
    # name: (setup, status, stage, check, held by review_wait)
    "running": (_running, "completed", "pre_review_checks", _check("pre_review", "running"), True),
    "queued-for-a-slot": (
        _queued_for_a_slot,
        "completed",
        "pre_review_checks",
        _check("pre_review", "waiting"),
        True,
    ),
    "not-yet-run": (
        _not_yet_run,
        "completed",
        "pre_review_checks",
        _check("pre_review", "waiting"),
        True,
    ),
    "could-not-run": (
        _could_not_run,
        "completed",
        "pre_review_checks",
        _check("pre_review", "could_not_run"),
        True,
    ),
    "interrupted": (
        _interrupted,
        "completed",
        "pre_review_checks",
        _check("pre_review", "could_not_run"),
        True,
    ),
    "error": (
        _in_state_error,
        "completed",
        "waiting_for_review",
        _check("pre_review", "could_not_run"),
        False,
    ),
    "passed": (_passed, "completed", "waiting_for_review", _check("pre_review", "passed"), False),
    "own-failure": (
        _own_failure,
        "revision_needed",
        "sent_back",
        _check("pre_review", "failed"),
        False,
    ),
    "conflicted": (
        _conflicted,
        "revision_needed",
        "sent_back",
        _check("pre_review", "failed"),
        False,
    ),
}


@pytest.mark.usefixtures("no_agent_cli_spawn")
@pytest.mark.parametrize("name", list(SCENARIOS))
async def test_the_stage_is_the_review_holds_own_decision(
    name, app, auth_headers, tmp_path, monkeypatch
):
    setup, status, stage, check, held = SCENARIOS[name]
    sha = await _completed_outside_a_flow(tmp_path)
    await _in_a_build(TASK)
    left = await setup(tmp_path, sha, monkeypatch)
    try:
        read = (await _reads(app, auth_headers, TASK))[TASK]
        wait = await _review_wait(TASK) if read["status"] == "completed" else None
        assert read["status"] == status, (name, read, await _runs(TASK))
        assert (read["stage"] == "pre_review_checks") == (wait is not None), (name, read, wait)
        assert (wait is not None) == held, (name, wait)
        assert read["stage"] == stage, (name, read, wait)
        assert read["check"] == check, (name, read, [(r.state, r.results) for r in await _runs()])
    finally:
        if isinstance(left, Path):
            left.write_text("go", encoding="utf-8")
        elif left is not None:
            for _ in range(project_checks.check_concurrency()):
                left.release()
        await project_checks.drain()


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_work_under_review_whose_later_run_fails_stays_in_review_with_that_failure(
    app, auth_headers, tmp_path
):
    await _completed_outside_a_flow(tmp_path)
    await _in_a_build(TASK)
    marker = _scripts(tmp_path) / "now-it-fails"
    suite = _script(
        tmp_path,
        "fails-once-marked",
        f"import os, sys\nif os.path.exists({str(marker)!r}):\n"
        "    print('FAILED tests/test_ledger.py::test_balance - assert 2 == 3')\n"
        "    sys.exit(1)\nprint('suite ok')\n",
    )
    await _configure([{"name": "hub-tests", "command": suite, "timeout_seconds": 120}])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    assert await _latest_state() == "passed"
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        await apply_transition(db, task, "under_review", run_actor("run-checks-qa", "QA"))
        (await db.get(Run, "run-checks-qa")).task_id = TASK  # the reviewer's turn is on it
        await db.commit()

    marker.write_text("yes", encoding="utf-8")
    await project_checks.request_run("proj-test", TASK, force=True)
    await project_checks.drain()

    assert await _latest_state() == "failed"
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["status"], read["stage"]) == ("under_review", "under_review")
    assert read["check"] == _check("pre_review", "failed")


async def test_a_task_no_check_ever_ran_on_carries_no_check_state(app, auth_headers, tmp_path):
    await _completed_outside_a_flow(tmp_path)
    await _in_a_build(TASK)
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["stage"], read["check"]) == ("waiting_for_review", None)


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_completed_work_is_in_pre_review_checks_before_its_run_is_recorded(
    app, auth_headers, tmp_path
):
    """The drive's gap (TSBVD-8): a builder completes with its work still uncommitted in its
    checkout and no fast check configured, so no run is recorded until its turn ends and the Hub
    commits that work. The review waits for the turn's end, which requests the checks
    (`review_on_completion._still_at_work`, `project_checks.after_run`); the task is in Pre-review
    checks from its move to completed, not Ready for review."""
    await _builder_task(tmp_path, content="x = 1\n")
    branch = worktrees.task_branch_name(TASK)
    git(tmp_path, "branch", "-f", branch, "main")  # the work is not committed yet
    await _configure([_slow(tmp_path)])
    await _in_a_build(TASK)

    completed = await _complete(app)
    assert completed.status_code == 200, completed.text
    assert await _runs(TASK) == []
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["status"], read["stage"]) == ("completed", "pre_review_checks"), read
    assert read["check"] == _check("pre_review", "waiting"), read
    # The review hold itself is unchanged: nothing of the task's own is on its branch to check yet.
    assert await _review_wait(TASK) is None

    # The turn ends and its work is committed: the hold now holds, for the run its end requests.
    commit_on_branch(tmp_path, branch, "ledger.py", "x = 1\n", create=False)
    git(tmp_path, "checkout", "-q", "main")
    await _end_the_builders_turn()
    assert (await _review_wait(TASK)) is not None
    await project_checks._after_run("proj-test", BUILDER_RUN)
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert read["stage"] == "pre_review_checks", read
    assert read["check"]["kind"] == "pre_review", read
    await project_checks.drain()
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["stage"], read["check"]) == (
        "waiting_for_review",
        _check("pre_review", "passed"),
    ), read


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_completed_work_with_nothing_of_its_own_is_ready_once_its_turn_ends(
    app, auth_headers, tmp_path
):
    """The other side of the same gap: a turn that ends with no work of its own on the branch
    requests no run, the hold stays clear, and the stage is Ready for review again."""
    await _builder_task(tmp_path, content="x = 1\n")
    git(tmp_path, "branch", "-f", worktrees.task_branch_name(TASK), "main")
    await _configure([_slow(tmp_path)])
    await _in_a_build(TASK)
    assert (await _complete(app)).status_code == 200
    await _end_the_builders_turn()
    await project_checks._after_run("proj-test", BUILDER_RUN)
    assert await _runs(TASK) == []
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["stage"], read["check"]) == ("waiting_for_review", None), read


# ---------------------------------------------------------------------------------------------
# new-run-clears-failure, and a superseded newest run
# ---------------------------------------------------------------------------------------------


async def _send_back_then_complete_again(tmp_path: Path, content: str) -> None:
    """The builder fixes its work on its branch and completes it again."""
    commit_on_branch(tmp_path, worktrees.task_branch_name(TASK), "ledger.py", content, create=False)
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        await apply_transition(db, task, "in_progress", operator())
        await db.commit()
        task = await db.get(Task, TASK)
        await apply_transition(db, task, "completed", run_actor("run-dev-fix", "DeveloperA"))
        await db.commit()


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_failure_stops_showing_once_the_task_is_completed_again_and_its_run_starts(
    app, auth_headers, tmp_path
):
    await _completed_outside_a_flow(tmp_path)
    await _in_a_build(TASK)
    release = _scripts(tmp_path) / "release-second"
    # Fails while the ledger holds the builder's first attempt; held once it is fixed.
    fails = _slow(tmp_path, fails_on="ledger.py")
    await _configure([fails])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["stage"], read["check"]) == ("sent_back", _check("pre_review", "failed"))

    await _send_back_then_complete_again(tmp_path, "x = 2\n")
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert read["status"] == "completed"
    assert (read["stage"], read["check"]) == (
        "pre_review_checks",
        _check("pre_review", "waiting"),
    ), "the earlier failure is not shown once the task is completed again"

    await _configure([_slow(tmp_path, release=release)])
    await project_checks.request_run("proj-test", TASK)
    await _wait_for(_slot_taken)
    try:
        read = (await _reads(app, auth_headers, TASK))[TASK]
        assert (read["stage"], read["check"]) == (
            "pre_review_checks",
            _check("pre_review", "running"),
        )
    finally:
        release.write_text("go", encoding="utf-8")
        await project_checks.drain()
    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["stage"], read["check"]) == ("waiting_for_review", _check("pre_review", "passed"))


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_superseded_newest_run_is_skipped_and_an_older_failure_is_not_shown(
    app, auth_headers, tmp_path, monkeypatch
):
    await _completed_outside_a_flow(tmp_path)
    await _in_a_build(TASK)
    await _configure([_slow(tmp_path, fails_on="ledger.py")])
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    await _send_back_then_complete_again(tmp_path, "x = 2\n")

    release = _scripts(tmp_path) / "release-superseded"
    await _configure([_slow(tmp_path, release=release)])
    await project_checks.request_run("proj-test", TASK)
    await _wait_for(_slot_taken)
    # A new completion replaced the work under the run: it ends superseded, as `_execute` records,
    # and is read before the run replacing it has started.
    monkeypatch.setattr(project_checks, "_replace", AsyncMock(return_value=None))
    project_checks._superseded[TASK] = project_checks._NEW_WORK
    release.write_text("go", encoding="utf-8")
    await project_checks.drain()
    project_checks._superseded.pop(TASK, None)
    states = [run.state for run in await _runs(TASK)]
    assert states == ["failed", "superseded"], states

    read = (await _reads(app, auth_headers, TASK))[TASK]
    assert (read["stage"], read["check"]) == (
        "pre_review_checks",
        _check("pre_review", "waiting"),
    )


# ---------------------------------------------------------------------------------------------
# start-is-broadcast
# ---------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_runs_start_and_its_slot_are_broadcast_after_the_run_is_committed(
    app, auth_headers, tmp_path, monkeypatch
):
    from hub.sse import sse_manager

    await _completed_outside_a_flow(tmp_path)
    seen: List[Dict[str, Any]] = []
    original = sse_manager.broadcast

    async def broadcast(project_id, event_type, data, *args, **kwargs):
        if event_type == "task_checks_started":
            # What a handler's refetch reads: a fresh session, after the event.
            async with async_session_factory() as db:
                run = await db.get(TaskCheckRun, data["run_id"])
            seen.append(
                {
                    **data,
                    "run_state": run.state if run else None,
                    "slot_at": run.slot_at if run else None,
                }
            )
        return await original(project_id, event_type, data, *args, **kwargs)

    monkeypatch.setattr(sse_manager, "broadcast", broadcast)
    await _configure([_slow(tmp_path)])
    run_id = await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()

    assert [(e["task_id"], e["run_id"], e["slot"]) for e in seen] == [
        (TASK, run_id, False),
        (TASK, run_id, True),
    ]
    assert seen[0]["run_state"] == "running", "the start is broadcast after its row is committed"
    assert seen[1]["run_state"] == "running" and seen[1]["slot_at"] is not None


# ---------------------------------------------------------------------------------------------
# batch-failure-shown-on-each, landing-checks-word, the new landing only
# ---------------------------------------------------------------------------------------------


async def test_a_failed_batch_run_shows_on_every_task_of_the_batch_and_then_only_the_new_one(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    _repo(tmp_path, tmp_path_factory.mktemp("ledger") / "runs.txt")
    await _project()
    ids, _tips = await _tasks(
        tmp_path,
        [
            ({"one.py": "x = 1\n"}, None),
            ({"broken.txt": "this breaks the suite\n"}, None),
            ({"three.py": "x = 3\n"}, None),
        ],
    )
    await _in_a_build(*ids)
    for task_id in ids:
        await _approve(app, auth_headers, task_id)

    at_the_verdict: List[Dict[str, Dict[str, Any]]] = []
    decide = landing_queue._decide

    async def read_then_decide(*args, **kwargs):
        if not at_the_verdict:
            at_the_verdict.append(await _reads(app, auth_headers, *ids))
        return await decide(*args, **kwargs)

    monkeypatch.setattr(landing_queue, "_decide", read_then_decide)
    await landing_queue.drain()

    [first] = at_the_verdict
    for task_id in ids:
        assert first[task_id]["stage"] == "checking", first
        assert first[task_id]["check"] == _check("landing", "failed"), first
    async with async_session_factory() as db:
        landing = (
            (await db.execute(select(TaskLanding).where(TaskLanding.task_id == ids[2])))
            .scalars()
            .first()
        )
    listed = (await app.get(TASKS, headers=auth_headers)).json()["tasks"]
    for row in listed:
        assert "batch" not in " ".join(k for k in row if row.get(k) is not None).lower()
        assert "check_run_id" not in (row.get("check_state") or {})
    assert landing is not None

    after = await _reads(app, auth_headers, *ids)
    assert after[ids[1]]["status"] == "revision_needed"
    for task_id in (ids[0], ids[2]):
        # Landed in the batch after the failed one: its new landing's run, not the failure.
        assert (after[task_id]["stage"], after[task_id]["check"]) == (
            "on_main",
            _check("landing", "passed"),
        ), after
