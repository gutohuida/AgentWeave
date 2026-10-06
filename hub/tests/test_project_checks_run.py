"""Checks run in the background on the work approval would merge (`approval-runs-the-projects-checks`).

Real git repositories and real subprocesses throughout: the commit is built with the plumbing the
runner uses, and each check is a real command, because "the runner says it ran" is not evidence.
"""

import sys
import time

import pytest
from sqlalchemy import select

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Project, Run, Task, TaskCheckRun
from hub.worktrees import task_branch_name

from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

PY = f'"{sys.executable}"'
PASS = {"name": "ok", "command": f'{PY} -c "print(1)"', "timeout_seconds": 60}
FAIL = {
    "name": "tests",
    "command": f"{PY} -c \"import sys; print('boom: 2 != 3'); sys.exit(3)\"",
    "timeout_seconds": 60,
}


# --- the plumbing, without the Hub --------------------------------------------------------------


def test_the_merged_commit_is_main_plus_the_target_and_touches_no_checkout(tmp_path):
    main = make_repo(tmp_path)
    work = commit_on_branch(tmp_path, "feature", "feature.py", "x = 1\n")
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "later.txt").write_text("main moved\n", encoding="utf-8")
    git(tmp_path, "add", "later.txt")
    git(tmp_path, "commit", "-q", "-m", "main moves on")
    tip = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    assert tip != main

    merged, why = project_checks.build_merged_commit(tmp_path, tip, [work])

    assert why == "" and merged
    files = set(git(tmp_path, "ls-tree", "-r", "--name-only", merged).stdout.split())
    assert {"README.md", "later.txt", "feature.py"} <= files
    assert git(tmp_path, "rev-parse", "HEAD").stdout.strip() == tip, "no branch moved"
    assert git(tmp_path, "status", "--porcelain").stdout == "", "the checkout is untouched"


def test_a_target_that_conflicts_is_an_error_naming_it(tmp_path):
    make_repo(tmp_path)
    work = commit_on_branch(tmp_path, "feature", "README.md", "theirs\n")
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "README.md").write_text("ours\n", encoding="utf-8")
    git(tmp_path, "commit", "-qam", "conflicting")
    tip = git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    merged, why = project_checks.build_merged_commit(tmp_path, tip, [work])

    assert merged is None
    assert work[:12] in why and "does not merge cleanly" in why


def test_a_failing_check_records_its_exit_code_and_output(tmp_path):
    result = project_checks.run_one(FAIL, tmp_path)
    assert result["exit_code"] == 3 and not result["timed_out"]
    assert "boom: 2 != 3" in result["output_tail"]
    assert project_checks.failed(result)


def test_a_check_past_its_timeout_has_its_process_tree_ended(tmp_path):
    """The grandchild holds the output pipe; `communicate` returns only once it is dead too."""
    hang = {
        "name": "hang",
        "command": (
            f'{PY} -c "import subprocess,sys,time; '
            "subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
            'time.sleep(120)"'
        ),
        "timeout_seconds": 3,
    }
    started = time.monotonic()
    result = project_checks.run_one(hang, tmp_path)
    assert result["timed_out"] and result["exit_code"] is None
    assert time.monotonic() - started < 60, "the tree was not ended"
    assert project_checks.failed(result)


def test_no_hub_configuration_reaches_a_check(tmp_path, monkeypatch):
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_secret-token-value")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///C:/hub/agentweave.db")
    monkeypatch.setenv("SOME_KEY", "aw_live_abcdefghijklmnop")
    monkeypatch.setenv("PROJECT_VAR", "kept")
    dump = {
        "name": "env",
        "command": f'{PY} -c "import os; print(sorted(os.environ.items()))"',
        "timeout_seconds": 60,
    }
    out = project_checks.run_one(dump, tmp_path)["output_tail"]
    assert "AW_RUN_TOKEN" not in out and "DATABASE_URL" not in out
    assert "aw_live_" not in out and "aw_run_" not in out
    assert "PROJECT_VAR" in out


def test_output_naming_a_hub_credential_is_scrubbed():
    text = "token aw_live_0123456789abcdef and aw_run_xyz-1 and secret-value-123"
    scrubbed = project_checks.scrub(text, ["secret-value-123"])
    assert "aw_live_" not in scrubbed and "aw_run_" not in scrubbed
    assert "secret-value-123" not in scrubbed


# --- runs, through the Hub ----------------------------------------------------------------------


async def _project(checks):
    async with async_session_factory() as session:
        (await session.get(Project, "proj-test")).checks = checks
        await session.commit()


async def _task_with_work(tmp_path, status="completed"):
    """A task whose branch holds one commit; its merge target is that branch tip."""
    make_repo(tmp_path)
    await set_main_branch("main")
    async with async_session_factory() as session:
        # A loop declaring its work needs no evidence: approval merges the task's branch tip.
        session.add(
            AIJob(
                id="job-checks",
                project_id="proj-test",
                name="checks",
                agent="builder",
                message="work",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await session.flush()
        session.add(
            Loop(
                id="loop-checks",
                project_id="proj-test",
                job_id="job-checks",
                purpose="work",
                work_needs_evidence=False,
            )
        )
        await session.flush()
        task = Task(
            id="task-c0ffee000001",
            loop_id="loop-checks",
            project_id="proj-test",
            title="Work",
            description="",
            status=status,
            assignee="builder",
        )
        session.add(task)
        await session.commit()
    work = commit_on_branch(tmp_path, task_branch_name(task.id), "feature.py", "x = 1\n")
    git(tmp_path, "checkout", "-q", "main")
    return task.id, work


async def _runs(task_id):
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskCheckRun)
                    .where(TaskCheckRun.task_id == task_id)
                    .order_by(TaskCheckRun.started_at)
                )
            ).scalars()
        )


@pytest.mark.asyncio
async def test_a_failing_check_is_recorded_and_the_root_is_untouched(app, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS, FAIL])

    assert await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    [run] = await _runs(task_id)
    assert run.state == "failed"
    assert run.target_shas == [work]
    assert [r["name"] for r in run.results] == ["ok", "tests"], "every check runs, in order"
    assert run.results[1]["exit_code"] == 3 and "boom" in run.results[1]["output_tail"]
    assert git(tmp_path, "status", "--porcelain").stdout == ""
    assert not (tmp_path / ".agentweave" / "checks" / task_id).exists()


@pytest.mark.asyncio
async def test_a_current_result_is_not_run_again(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    first = await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    again = await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    assert again == first
    assert [r.state for r in await _runs(task_id)] == ["passed"]


@pytest.mark.asyncio
async def test_a_project_without_checks_records_nothing(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    assert await project_checks.request_run("proj-test", task_id) is None
    await project_checks.drain()
    assert await _runs(task_id) == []


@pytest.mark.asyncio
async def test_completing_a_task_outside_a_turn_starts_a_run(app, auth_headers, tmp_path):
    """The operator's move to `completed` returns at once; the run is recorded after."""
    task_id, _ = await _task_with_work(tmp_path, status="in_progress")
    await _project([PASS])

    moved = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{task_id}",
        json={"status": "completed"},
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text
    await project_checks.drain()
    assert [r.state for r in await _runs(task_id)] == ["passed"]


@pytest.mark.asyncio
async def test_a_turn_bound_to_a_completed_task_starts_a_run_at_its_end(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-c0ffee000001",
                project_id="proj-test",
                agent="builder",
                status="completed",
                turn_depth=0,
                task_id=task_id,
            )
        )
        await session.commit()

    project_checks.after_run("proj-test", "run-c0ffee000001")
    await project_checks.drain()
    assert [r.state for r in await _runs(task_id)] == ["passed"]


@pytest.mark.asyncio
async def test_a_restart_interrupts_a_run_left_running(app, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    async with async_session_factory() as session:
        session.add(
            TaskCheckRun(
                id="chk-left000001",
                project_id="proj-test",
                task_id=task_id,
                main_sha="0" * 40,
                target_shas=[work],
                state="running",
                results=[],
                error="",
            )
        )
        await session.commit()

    assert await project_checks.interrupt_leftover_runs() == 1
    [run] = await _runs(task_id)
    assert run.state == "interrupted" and run.ended_at is not None


@pytest.mark.asyncio
async def test_the_drawer_reads_runs_newest_first_and_the_operator_re_runs(
    app, auth_headers, tmp_path
):
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()

    rerun = await app.post(
        f"/api/v1/projects/proj-test/tasks/{task_id}/checks/run", headers=auth_headers
    )
    assert rerun.status_code == 202, rerun.text
    await project_checks.drain()

    read = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}/checks", headers=auth_headers)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["configured"] is True and body["running"] is False
    runs = body["runs"]
    assert [r["state"] for r in runs] == ["passed", "passed"], "a forced re-run is a new run"
    assert runs[0]["id"] == rerun.json()["run_id"], "newest first"
    assert runs[0]["results"][0]["name"] == "ok"
