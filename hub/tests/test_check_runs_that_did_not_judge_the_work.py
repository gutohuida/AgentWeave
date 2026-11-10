"""A check run that did not judge the work (`checks-know-their-phase-and-give-way-to-the-user`,
FR-7-FR-10).

Only a result that judged the work counts against the task. A merge conflict goes back to the
builder as merge-needed and is not run again until the branch moves (FR-7); a run the Hub's stop
interrupted is requested again at the next start (FR-8); a Hub fault, or a check out of time naming
no failing test, is retried once and then put on the operator's Needs-you list, the task left where
it is (FR-9, FR-10). A check that named a failing test before its time ran out is the task's, as
before (ac-timeout-named).

Real git repositories and real check subprocesses throughout, through the real agent route and the
real stalls route, as `test_checks_run_before_review` does.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import flow_advance, main, project_checks, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import Stall, Task, TaskCheckRun, TaskTransition

from .test_checks_run_before_review import (
    AGENT_TASKS,
    BUILDER,
    BUILDER_HEADERS,
    TASK,
    _builder_task,
    _complete,
    _configure,
    _flow_task_completed,
    _lint,
    _running_run,
    _runs,
    _script,
    _slow,
    _task,
)
from .test_task_integration import commit_on_branch, git

pytestmark = pytest.mark.asyncio

STALLS = "/api/v1/projects/proj-test/stalls?open=true"


async def _transitions(task_id: str):
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id == task_id)
                    .order_by(TaskTransition.sequence)
                )
            ).scalars()
        )


async def _unjudged_stalls(task_id: str):
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(Stall).where(
                        Stall.cause == project_checks.UNJUDGED_STALL, Stall.task_id == task_id
                    )
                )
            ).scalars()
        )


async def _settle():
    await project_checks.drain()
    await project_checks.drain()  # a return or retry scheduled from a finished run's callback


def _conflicting_main(repo: Path, filename: str = "ledger.py") -> None:
    """Main edits *filename* too, so the task's work no longer merges onto it."""
    commit_on_branch(repo, "main", filename, "x = 'main'\n", create=False)


# ---------------------------------------------------------------------------------------------
# FR-7 conflict-goes-to-builder
# ---------------------------------------------------------------------------------------------


async def test_a_conflict_goes_back_to_its_builder_and_is_not_run_again_until_the_branch_moves(
    app, tmp_path
):
    await _builder_task(tmp_path, content="x = 1\n")
    await _configure([_lint(tmp_path)])
    _conflicting_main(tmp_path)

    completed = await _complete(app)
    assert completed.status_code == 200, completed.text
    await _settle()

    [run] = await _runs()
    assert (run.state, run.ended_by) == ("error", project_checks.ENDED_BY_CONFLICT)
    assert "ledger.py" in run.error
    task = await _task()
    assert (task.status, task.assignee) == ("revision_needed", BUILDER)
    assert "ledger.py" in (task.notes or ""), task.notes
    back = (await _transitions(TASK))[-1]
    assert (back.from_status, back.to_status) == ("completed", "revision_needed")
    assert back.reason_class == "merge-needed" and back.origin == "checks"

    # Nothing re-runs it: not a refresh, not a request, not completing the same work again.
    await project_checks.refresh("proj-test")
    await project_checks.request_run("proj-test", TASK)
    resumed = await app.patch(
        AGENT_TASKS.format(TASK), json={"status": "in_progress"}, headers=BUILDER_HEADERS
    )
    assert resumed.status_code == 200, resumed.text
    again = await _complete(app)
    assert again.status_code == 200, again.text
    await _settle()
    assert [r.id for r in await _runs()] == [run.id], "no run on the same conflicting work"
    assert (await _task()).status == "revision_needed", "sent back again"

    # The builder merges main and resolves the conflict: a commit on its branch is checked.
    branch = worktrees.task_branch_name(TASK)
    git(tmp_path, "checkout", "-q", branch)
    git(tmp_path, "merge", "-q", "main", "-X", "theirs", "-m", "merge main")
    git(tmp_path, "checkout", "-q", "main")
    resumed = await app.patch(
        AGENT_TASKS.format(TASK), json={"status": "in_progress"}, headers=BUILDER_HEADERS
    )
    assert resumed.status_code == 200, resumed.text
    assert (await _complete(app)).status_code == 200
    await _settle()
    runs = await _runs()
    assert [r.state for r in runs] == ["error", "passed"]
    assert (await _task()).status == "completed"


async def test_a_conflicts_send_back_waits_for_the_completion_to_commit(app, tmp_path, monkeypatch):
    """Completing work that already conflicted is sent back, whenever the background return runs.

    The completion asks for its checks before it commits, so the send-back that request schedules
    reads the task still `in_progress` and gives up; the route asks again once it has committed
    (`update_task_for_actor`, F1084's shape). Here everything the move scheduled runs to its end
    before the commit, every time, so that second ask is what sends it back (AW-55).
    """
    await _builder_task(tmp_path, content="x = 1\n")
    await _configure([_lint(tmp_path)])
    _conflicting_main(tmp_path)
    assert (await _complete(app)).status_code == 200
    await _settle()
    assert (await _task()).status == "revision_needed"
    resumed = await app.patch(
        AGENT_TASKS.format(TASK), json={"status": "in_progress"}, headers=BUILDER_HEADERS
    )
    assert resumed.status_code == 200, resumed.text

    from hub.api.v1 import tasks as task_routes

    real = task_routes.apply_transition

    async def background_first(*args, **kwargs):
        moved = await real(*args, **kwargs)
        await project_checks.drain()  # whatever the move scheduled ends before the route commits
        return moved

    monkeypatch.setattr(task_routes, "apply_transition", background_first)
    again = await _complete(app)
    assert again.status_code == 200, again.text
    await _settle()

    task = await _task()
    assert task.status == "revision_needed", "sent back again"
    back = (await _transitions(TASK))[-1]
    assert (back.from_status, back.to_status, back.reason_class) == (
        "completed",
        "revision_needed",
        "merge-needed",
    )


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_flow_tasks_conflict_asks_its_flow_to_give_the_builder_the_task_back(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo, _sha, _job_id, loop_id = await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path)],
    )
    _conflicting_main(repo)
    asked = []
    real = flow_advance.advance_after_commit
    monkeypatch.setattr(
        flow_advance,
        "advance_after_commit",
        lambda session, loop: (asked.append(loop), real(session, loop))[1],
    )

    await project_checks.request_run("proj-test", "task-1")
    await _settle()

    [run] = await _runs("task-1")
    assert run.ended_by == project_checks.ENDED_BY_CONFLICT
    task = await _task("task-1")
    assert task.status == "revision_needed" and "ledger.py" in (task.notes or "")
    assert (await _transitions("task-1"))[-1].reason_class == "merge-needed"
    assert loop_id in asked, "the builder's turn is requested through the flow"


# ---------------------------------------------------------------------------------------------
# FR-8 hub-stop-reruns
# ---------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_run_the_hubs_stop_interrupted_is_run_again_at_the_next_start(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo, sha, _job_id, _loop_id = await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path)],
    )
    old = await _running_run(repo, sha)
    tip = git(repo, "rev-parse", "main").stdout.strip()

    assert await project_checks.interrupt_leftover_runs() == 1
    project_checks.schedule_rerun_after_hub_stop()
    await _settle()

    runs = await _runs("task-1")
    assert [r.id for r in runs][0] == old
    assert [r.state for r in runs] == ["interrupted", "passed"]
    assert runs[1].main_sha == tip, "main did not move; nothing else asked for it"
    # The startup hook is the lifespan's, straight after the reconcile.
    source = inspect.getsource(main.lifespan)
    assert source.index("interrupt_leftover_runs()") < source.index(
        "schedule_rerun_after_hub_stop()"
    )


# ---------------------------------------------------------------------------------------------
# FR-9 hub-fault-retried-once
# ---------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_hub_fault_is_retried_once_then_put_on_needs_you(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path)],
    )

    def broken(root, task_id, commit):
        raise RuntimeError("git worktree add failed: the disk is full")

    real = project_checks._checkout
    monkeypatch.setattr(project_checks, "_checkout", broken)

    await project_checks.request_run("proj-test", "task-1")
    await _settle()

    runs = await _runs("task-1")
    assert [(r.state, r.ended_by) for r in runs] == [("error", "fault"), ("error", "fault")]
    # No third: not on its own, not on a refresh.
    await project_checks.refresh("proj-test")
    await _settle()
    assert len(await _runs("task-1")) == 2
    assert (await _task("task-1")).status == "completed", "not sent back"

    listed = await app.get(STALLS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    [stall] = [s for s in listed.json()["stalls"] if s["task_id"] == "task-1"]
    assert stall["cause"] == "checks_unjudged"
    assert "the disk is full" in stall["reason"] and runs[1].id in stall["reason"]
    assert stall["conversation_id"] is None, "the mender is not woken"

    # Fixed, and re-run by the operator: the result judges the work, and the notice is over.
    monkeypatch.setattr(project_checks, "_checkout", real)
    await project_checks.request_run("proj-test", "task-1", force=True)
    await _settle()
    assert [r.state for r in await _runs("task-1")][-1] == "passed"
    [ended] = await _unjudged_stalls("task-1")
    assert ended.outcome == "resolved"


# ---------------------------------------------------------------------------------------------
# FR-10 timeout-not-the-tasks
# ---------------------------------------------------------------------------------------------


def _sleeper(tmp_path: Path, *, prints: str = "", only_where: str = "", reports: str = "") -> dict:
    """A check that prints *prints*, writes a JUnit report naming *reports* failed (when given), and
    sleeps past its 2 s limit, where *only_where* exists (or always); elsewhere it passes at once.
    """
    guard = f"if not os.path.exists({only_where!r}):\n    sys.exit(0)\n" if only_where else ""
    report = ""
    if reports:
        classname, name = reports.split("::", 1)
        xml = (
            f'<testsuites><testcase classname="{classname}" name="{name}">'
            "<failure message='assert 1 == 2'/></testcase></testsuites>"
        )
        report = f"open('report.xml', 'w', encoding='utf-8').write({xml!r})\n"
    command = _script(
        tmp_path,
        f"sleeper-{'named' if reports else 'quiet'}-{'printed' if prints else 'silent'}",
        f"import os, sys, time\n{guard}print({prints!r}, flush=True)\n{report}time.sleep(10)\n",
    )
    return {
        "name": "hub-tests",
        "command": command,
        "timeout_seconds": 2,
        "fast": False,
        "report_path": "report.xml",
    }


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_check_out_of_time_naming_no_failure_is_retried_once_not_sent_back(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_sleeper(tmp_path, prints="collected 9000 items")],
    )

    await project_checks.request_run("proj-test", "task-1")
    await _settle()

    runs = await _runs("task-1")
    assert [(r.state, r.ended_by) for r in runs] == [("error", "timeout"), ("error", "timeout")]
    assert "time limit" in runs[1].error and "hub-tests" in runs[1].error
    task = await _task("task-1")
    assert task.status == "completed", "running out of time is not the task's failure"
    listed = await app.get(STALLS, headers=auth_headers)
    [stall] = [s for s in listed.json()["stalls"] if s["task_id"] == "task-1"]
    assert stall["cause"] == "checks_unjudged" and "time limit" in stall["reason"]


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_check_out_of_time_that_named_a_failing_test_is_still_the_tasks(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [
            _sleeper(
                tmp_path,
                prints="FAILED tests/x.py::t - assert 1 == 2",
                only_where="ledger.py",
                reports="tests.x::t",
            )
        ],
    )

    await project_checks.request_run("proj-test", "task-1")
    await _settle()

    [run] = await _runs("task-1")
    assert run.state == "failed" and run.ended_by is None
    task = await _task("task-1")
    assert task.status == "revision_needed"
    assert "tests.x::t" in (task.notes or ""), task.notes
    assert await _unjudged_stalls("task-1") == []


# ---------------------------------------------------------------------------------------------
# the pieces, without the Hub
# ---------------------------------------------------------------------------------------------


def test_a_conflict_is_told_apart_from_git_failing(tmp_path):
    from .test_task_integration import make_repo

    make_repo(tmp_path)
    work = commit_on_branch(tmp_path, "feature", "README.md", "theirs\n")
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "README.md").write_text("ours\n", encoding="utf-8")
    git(tmp_path, "commit", "-qam", "conflicting")
    tip = git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    merged, why, conflict = project_checks.merge_for_checks(tmp_path, tip, [work])
    assert merged is None and conflict
    assert "(README.md)" in why, why

    merged, why, conflict = project_checks.merge_for_checks(tmp_path, tip, ["f" * 40])
    assert merged is None and not conflict


def test_a_timeout_names_only_what_its_report_says_not_what_it_printed(tmp_path):
    """FR-7: a check ended at its time limit names the failures its report recorded before it was
    ended; a `FAILED x::t` it printed names nothing."""
    printed = _sleeper(tmp_path, prints="FAILED tests/a.py::two - assert 0")
    result = project_checks.run_one(printed, tmp_path)
    assert result["timed_out"] and "named_failures" not in result
    assert project_checks.unjudged_timeout(result)
    reported = _sleeper(tmp_path, prints="FAILED tests/a.py::two", reports="tests.a::two")
    result = project_checks.run_one(reported, tmp_path)
    assert result["named_failures"] == ["tests.a::two"]


def test_a_timeout_is_unjudged_only_without_a_named_failure():
    assert project_checks.unjudged_timeout({"timed_out": True})
    assert not project_checks.unjudged_timeout({"timed_out": True, "named_failures": ["a::b"]})
    assert not project_checks.unjudged_timeout({"timed_out": False, "exit_code": 1})


async def test_an_unjudged_run_is_not_retried_once_its_task_no_longer_waits_for_review(
    app, tmp_path
):
    """Guards the bound: an unjudged run asks again only while its task still waits for review."""
    await _builder_task(tmp_path, content="x = 1\n", status="in_progress")
    await _configure([_slow(tmp_path)])
    async with async_session_factory() as db:
        db.add(
            TaskCheckRun(
                id="chk-fault0000001",
                project_id="proj-test",
                task_id=TASK,
                main_sha=git(tmp_path, "rev-parse", "main").stdout.strip(),
                target_shas=[
                    git(tmp_path, "rev-parse", worktrees.task_branch_name(TASK)).stdout.strip()
                ],
                state="error",
                ended_by="fault",
                results=[],
                error="boom",
            )
        )
        await db.commit()
    await project_checks._check_shared_failure_again("proj-test", TASK)
    await _settle()
    assert [r.id for r in await _runs()] == ["chk-fault0000001"]
    async with async_session_factory() as db:
        assert (await db.get(Task, TASK)).status == "in_progress"
