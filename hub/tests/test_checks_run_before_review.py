"""The project's checks run before anyone reviews (`checks-run-before-anyone-reviews`, slice L).

The night of 2026-10-26/27 on the operator's Hub: reviewers were dispatched seconds after each
completion and judged work the project's checks were already failing. T2's ruff failure was recorded
13 s before its review started, and three reviews (about 52 min of Opus) found what the checks found.

These are the slice's acceptance drive. Real git repositories and real check subprocesses throughout
(the checks are scripts written outside the checkout, so their quoting is not the shell's problem),
through the real agent route (`PATCH /agent-actions/tasks/{id}` with a run credential), the real
flow firing (`_fire_job_internal`) and the real stall recorder.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import flow_advance, mcp_server, project_checks, stalls, worktrees
from hub import scheduler as scheduler_module
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    InboundQueueEntry,
    Loop,
    Project,
    Run,
    Stall,
    Task,
    TaskCheckRun,
    TaskTransition,
)
from hub.scheduler import JobScheduler, decide_firing
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_a_stalled_project_wakes_the_mender import mender_run
from .test_agent_trigger import _init_repo
from .test_flow_fires_a_review_turn import AUTHOR, REVIEWER, _attribute_completion, _flow
from .test_review_turn import _author_commit, _reviewable_task, _roster
from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

PY = f'"{sys.executable}"'
AGENT_TASKS = "/api/v1/agent-actions/tasks/{}"
RESET = "/api/v1/agent-actions/mender/tasks/{}/reset"

TASK = "task-c0ffee0000a1"
BUILDER = "builder"
BUILDER_RUN = "run-checks-builder"
BUILDER_TOKEN = "aw_run_checks-builder"
#: The line the fast check rejects, as ruff rejects an unused import.
BAD_LINE = "import os  # BAD\n"
#: What the fast check prints for it, which the refusal must quote.
LINT_OUTPUT = "F401 `os` imported but unused (a BAD line)"


# --- the checks, as scripts outside the checkout ----------------------------------------------


def _scripts(tmp_path: Path) -> Path:
    """A directory beside the repository: a check checkout is under `tmp_path/.agentweave/checks`,
    and the scripts must be neither in the merged tree nor swept into a snapshot."""
    scripts = tmp_path.parent / f"{tmp_path.name}-scripts"
    scripts.mkdir(exist_ok=True)
    return scripts


def _script(tmp_path: Path, name: str, body: str) -> str:
    path = _scripts(tmp_path) / f"{name}.py"
    path.write_text(body, encoding="utf-8")
    return f'{PY} "{path}"'


def _lint(tmp_path: Path, *, sleep: float = 0.0, fast: bool = True) -> dict:
    """Fails where any Python file of the checked tree holds `# BAD`, like ruff on an unused import."""
    command = _script(
        tmp_path,
        f"lint{int(sleep)}",
        "import pathlib, sys, time\n"
        f"time.sleep({sleep})\n"
        "bad = [p for p in pathlib.Path('.').rglob('*.py')\n"
        "       if '.agentweave' not in p.parts and '# BAD' in p.read_text(encoding='utf-8')]\n"
        "for p in bad:\n"
        f"    print(p.as_posix() + ':1:1: ' + {LINT_OUTPUT!r})\n"
        "sys.exit(1 if bad else 0)\n",
    )
    return {"name": "lint", "command": command, "timeout_seconds": 60, "fast": fast}


def _counted(tmp_path: Path, counter: Path) -> dict:
    """A passing fast check that appends a line to *counter* each time it executes."""
    command = _script(
        tmp_path,
        "counted",
        f"with open({str(counter)!r}, 'a', encoding='utf-8') as f:\n    f.write('ran\\n')\n",
    )
    return {"name": "format", "command": command, "timeout_seconds": 60, "fast": True}


def _slow(tmp_path: Path, *, fails_on: str = "", release: Path = None) -> dict:
    """The suite: not fast. Fails where a file named *fails_on* exists in the tree; waits for
    *release* to exist first, when given (so a test can hold it running)."""
    wait = (
        f"deadline = time.time() + 60\nwhile not os.path.exists({str(release)!r}) "
        "and time.time() < deadline:\n    time.sleep(0.1)\n"
        if release is not None
        else ""
    )
    fail = (
        f"if os.path.exists({fails_on!r}):\n"
        "    print('FAILED tests/test_ledger.py::test_balance - assert 2 == 3')\n"
        "    sys.exit(1)\n"
        if fails_on
        else ""
    )
    command = _script(
        tmp_path,
        f"suite-{fails_on or 'ok'}-{'held' if release else 'free'}",
        f"import os, sys, time\n{wait}{fail}print('suite ok')\n",
    )
    return {"name": "hub-tests", "command": command, "timeout_seconds": 120, "fast": False}


async def _configure(checks, main_branch="main"):
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.checks = checks
        project.main_branch = main_branch
        await session.commit()


# --- a task outside any flow, held by a builder's run -------------------------------------------


async def _builder_task(tmp_path: Path, *, content: str, status="in_progress") -> str:
    """A task outside any flow, held by the builder's running turn, whose task branch holds one
    commit of *content* in `ledger.py`. Its review target is that branch tip (F622)."""
    make_repo(tmp_path)
    await set_main_branch("main")
    commit_on_branch(tmp_path, worktrees.task_branch_name(TASK), "ledger.py", content)
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as session:
        session.add(
            Task(
                id=TASK,
                project_id="proj-test",
                title="Balance the ledger",
                description="",
                status=status,
                assignee=BUILDER,
            )
        )
        session.add(
            Run(
                id=BUILDER_RUN,
                project_id="proj-test",
                agent=BUILDER,
                status="running",
                turn_depth=0,
                task_id=TASK,
                capability_token_hash=hash_run_token(BUILDER_TOKEN),
            )
        )
        await session.commit()
    return TASK


BUILDER_HEADERS = {"Authorization": f"Bearer {BUILDER_TOKEN}"}


async def _complete(app):
    return await app.patch(
        AGENT_TASKS.format(TASK), json={"status": "completed"}, headers=BUILDER_HEADERS
    )


async def _task(task_id=TASK) -> Task:
    async with async_session_factory() as session:
        return await session.get(Task, task_id)


async def _runs(task_id=TASK):
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


async def _end_the_builders_turn():
    async with async_session_factory() as session:
        (await session.get(Run, BUILDER_RUN)).status = "completed"
        await session.commit()


# ---------------------------------------------------------------------------------------------
# fast-checks-run-first
# ---------------------------------------------------------------------------------------------


async def test_a_runs_fast_checks_run_before_its_other_checks(app, tmp_path):
    await _builder_task(tmp_path, content="x = 1\n", status="completed")
    await _configure([_slow(tmp_path), _lint(tmp_path)])

    assert await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()

    [run] = await _runs()
    assert run.state == "passed", run.results
    assert [r["name"] for r in run.results] == ["lint", "hub-tests"]


# ---------------------------------------------------------------------------------------------
# completion-refused-on-master-red, refusal-quotes-output
# ---------------------------------------------------------------------------------------------


async def test_a_completion_whose_fast_check_fails_is_refused_with_its_output(app, tmp_path):
    await _builder_task(tmp_path, content=BAD_LINE)
    await _configure([_lint(tmp_path), _slow(tmp_path)])

    refused = await _complete(app)

    assert refused.status_code == 409, refused.text
    task = await _task()
    assert (task.status, task.assignee) == ("in_progress", BUILDER)
    [run] = await _runs()
    assert run.state == "failed"
    detail = refused.json()["detail"]
    message = detail["message"]
    assert "lint" in message and run.id in message and run.merged_sha[:12] in message
    assert LINT_OUTPUT in message, message
    # What the agent's update_task tool returns is that message (`_readable_detail`).
    assert mcp_server._readable_detail(detail) == message
    assert detail["run_id"] == run.id and detail["merged_sha"] == run.merged_sha
    [failing] = detail["checks"]
    assert failing["name"] == "lint" and failing["exit_code"] == 1
    assert LINT_OUTPUT in failing["output_tail"]


# ---------------------------------------------------------------------------------------------
# uncommitted-work-is-checked
# ---------------------------------------------------------------------------------------------


async def test_the_builders_uncommitted_work_is_committed_and_checked(app, tmp_path):
    await _builder_task(tmp_path, content="x = 1\n")
    await _configure([_lint(tmp_path)])
    checkout = worktrees.task_worktree_path(tmp_path, TASK)
    added = git(tmp_path, "worktree", "add", str(checkout), worktrees.task_branch_name(TASK))
    assert added.returncode == 0, added.stderr
    (checkout / "debug.py").write_text(BAD_LINE, encoding="utf-8")

    refused = await _complete(app)

    assert refused.status_code == 409, refused.text
    tip = git(tmp_path, "rev-parse", worktrees.task_branch_name(TASK)).stdout.strip()
    files = git(tmp_path, "ls-tree", "-r", "--name-only", tip).stdout.split()
    assert "debug.py" in files, "the snapshot put the uncommitted work on the task branch"
    assert git(checkout, "status", "--porcelain").stdout == ""
    [run] = await _runs()
    assert run.target_shas == [tip]


# ---------------------------------------------------------------------------------------------
# slow-fast-check-does-not-hold
# ---------------------------------------------------------------------------------------------


async def test_a_fast_check_past_the_budget_does_not_hold_the_completion(
    app, tmp_path, monkeypatch
):
    monkeypatch.setattr(project_checks, "COMPLETION_BUDGET_SECONDS", 2.0)
    await _builder_task(tmp_path, content=BAD_LINE)
    await _configure([_lint(tmp_path, sleep=6)])

    started = time.monotonic()
    completed = await _complete(app)
    elapsed = time.monotonic() - started

    assert completed.status_code == 200, completed.text
    assert elapsed < 2.0 + 5.0, elapsed
    assert (await _task()).status == "completed"
    [run] = await _runs()
    assert run.state == "running"
    await project_checks.drain()


async def test_a_fast_failure_found_after_the_budget_returns_the_task(app, tmp_path, monkeypatch):
    monkeypatch.setattr(project_checks, "COMPLETION_BUDGET_SECONDS", 2.0)
    await _builder_task(tmp_path, content=BAD_LINE)
    await _configure([_lint(tmp_path, sleep=6)])

    assert (await _complete(app)).status_code == 200
    await project_checks.drain()

    task = await _task()
    assert (task.status, task.assignee) == ("revision_needed", BUILDER)


# ---------------------------------------------------------------------------------------------
# mcp-timeout-covers-budget, tool-says-so
# ---------------------------------------------------------------------------------------------


def _capture_timeouts(monkeypatch):
    from .test_mcp_server import _response

    timeouts = []

    def urlopen(request, timeout=None):
        timeouts.append((request.get_method(), timeout))
        return _response(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_test-key")
    return timeouts


async def test_the_mcp_completion_waits_longer_than_the_hubs_budget(monkeypatch):
    assert mcp_server.COMPLETION_REQUEST_TIMEOUT_SECONDS > project_checks.COMPLETION_BUDGET_SECONDS
    assert mcp_server.HUB_REQUEST_TIMEOUT_SECONDS == 10

    timeouts = _capture_timeouts(monkeypatch)
    mcp_server.update_task("task-1", status="completed")
    mcp_server.update_task("task-1", status="in_progress")
    mcp_server.update_task("task-1", notes="halfway")
    mcp_server.get_task("task-1")

    assert timeouts == [
        ("PATCH", mcp_server.COMPLETION_REQUEST_TIMEOUT_SECONDS),
        ("PATCH", 10),
        ("PATCH", 10),
        ("GET", 10),
    ]


async def test_update_task_says_completing_runs_the_fast_checks():
    described = " ".join((mcp_server.update_task.__doc__ or "").split())
    assert "fast checks" in described
    assert "two minutes" in described
    assert "refused with their output" in described


# ---------------------------------------------------------------------------------------------
# fast-check-executes-once
# ---------------------------------------------------------------------------------------------


async def test_the_fast_checks_at_completion_are_the_start_of_the_one_run(app, tmp_path):
    counter = _scripts(tmp_path) / "format-ran.txt"
    await _builder_task(tmp_path, content="x = 1\n")
    await _configure([_counted(tmp_path, counter), _slow(tmp_path)])

    completed = await _complete(app)
    assert completed.status_code == 200, completed.text
    assert [run.state for run in await _runs()] in (
        ["running"],
        ["passed"],
    ), "the completion started the task's check run"

    await _end_the_builders_turn()
    project_checks.after_run("proj-test", BUILDER_RUN)
    await project_checks.drain()

    [run] = await _runs()
    assert run.state == "passed", run.results
    assert [r["name"] for r in run.results] == ["format", "hub-tests"]
    assert counter.read_text(encoding="utf-8").splitlines() == ["ran"]


# ---------------------------------------------------------------------------------------------
# fast-flag: a project with no fast check completes as before
# ---------------------------------------------------------------------------------------------


async def test_without_a_fast_check_completion_is_as_before(app, tmp_path):
    await _builder_task(tmp_path, content=BAD_LINE)
    await _configure([_lint(tmp_path, fast=False)])

    completed = await _complete(app)

    assert completed.status_code == 200, completed.text
    assert await _runs() == [], "checked at the turn's end, as before"


# =============================================================================================
# review-after-checks
# =============================================================================================


async def _flow_task_completed(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, *, checks
):
    """task-1 of a flow, completed by the author with evidence naming its commit; the author's
    turn has ended. Its checks are *checks*(repo)."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)
    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        job, loop = await _flow(db, suffix="checks", task_id="task-1")
    await _configure(checks(repo))
    return repo, sha, job.id, loop.id


async def _running_run(repo: Path, sha: str, task_id="task-1", started_at=None) -> str:
    """A check run recorded running on exactly the work under review."""
    tip = git(repo, "rev-parse", "main").stdout.strip()
    async with async_session_factory() as db:
        db.add(
            TaskCheckRun(
                id="chk-running0001",
                project_id="proj-test",
                task_id=task_id,
                main_sha=tip,
                target_shas=[sha],
                state="running",
                results=[],
                error="",
                started_at=started_at or datetime.now(timezone.utc),
            )
        )
        await db.commit()
    return "chk-running0001"


async def _fire(scheduler, job_id):
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            await scheduler._fire_job_internal(
                await db.get(AIJob, job_id), trigger="scheduled", session=db
            )
    await stalls.drain()


async def _review_entries(task_id="task-1"):
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.review_task_id == task_id)
                )
            ).scalars()
        )


async def _loop_stalls():
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(Stall).where(Stall.cause == "loop_stalled"))).scalars()
        )


async def _latest_transition(task_id):
    async with async_session_factory() as db:
        return (
            (
                await db.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id == task_id)
                    .order_by(TaskTransition.sequence.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )


# ---------------------------------------------------------------------------------------------
# review-deferred-while-running
# ---------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_flow_defers_the_review_while_the_tasks_checks_run(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo, sha, job_id, loop_id = await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path)],
    )
    run_id = await _running_run(repo, sha)

    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()) as scheduled:
        await _fire(JobScheduler(), job_id)

    assert await _review_entries() == []
    assert scheduled.await_count == 0
    assert await _loop_stalls() == []
    async with async_session_factory() as db:
        loop = await db.get(Loop, loop_id)
        decision = await decide_firing(db, loop, default_agent=AUTHOR)
    assert decision.selections == () and decision.stall_reason is None
    assert [task_id for task_id, _ in decision.deferred] == ["task-1"]
    reason = dict(decision.deferred)["task-1"]
    assert run_id in reason and "checks have run" in reason


# ---------------------------------------------------------------------------------------------
# own-failure-returns, history (origin 'checks')
# ---------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_check_run_failing_with_the_tasks_own_failure_returns_it_to_its_builder(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path, fails_on="ledger.py")],
    )

    run_id = await project_checks.request_run("proj-test", "task-1")
    await project_checks.drain()

    [run] = await _runs("task-1")
    assert run.id == run_id and run.state == "failed" and project_checks.own_failure(run.results)
    task = await _task("task-1")
    assert (task.status, task.assignee) == ("revision_needed", AUTHOR)
    latest = await _latest_transition("task-1")
    assert (latest.from_status, latest.to_status) == ("completed", "revision_needed")
    assert latest.origin == "checks" and latest.actor_kind == "operator"
    assert run_id in (latest.note or "")
    assert "assert 2 == 3" in (task.notes or "") and "hub-tests" in task.notes
    assert await _review_entries() == []


# ---------------------------------------------------------------------------------------------
# review-queued-on-pass
# ---------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_passing_run_queues_the_review_without_a_tick(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    release = _scripts(tmp_path) / "release-the-suite"
    _repo, _sha, job_id, _loop_id = await _flow_task_completed(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        checks=lambda repo: [_slow(tmp_path, release=release)],
    )
    scheduler = JobScheduler()
    monkeypatch.setattr(scheduler_module, "_scheduler_instance", scheduler)
    monkeypatch.setattr(flow_advance, "DEBOUNCE_SECONDS", 0)

    assert await project_checks.request_run("proj-test", "task-1")
    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()):
        await _fire(scheduler, job_id)
    assert await _review_entries() == [], "deferred while the run is running"

    release.write_text("go", encoding="utf-8")
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        await project_checks.drain()
        await flow_advance.settled()
    await stalls.drain()

    [run] = await _runs("task-1")
    assert run.state == "passed"
    assert [entry.agent for entry in await _review_entries()] == [REVIEWER]
    assert await _loop_stalls() == []


# ---------------------------------------------------------------------------------------------
# outside-flow-review-refused, outside-flow-return
# ---------------------------------------------------------------------------------------------


async def _completed_outside_a_flow(tmp_path: Path, *, content="x = 1\n") -> str:
    """A loopless task completed by DeveloperA, its branch tip the work; QA has a running turn."""
    make_repo(tmp_path)
    await set_main_branch("main")
    sha = commit_on_branch(tmp_path, worktrees.task_branch_name(TASK), "ledger.py", content)
    git(tmp_path, "checkout", "-q", "main")
    from hub.db.models import Agent

    async with async_session_factory() as db:
        db.add(Agent(id="ag-qa-checks", project_id="proj-test", name="QA"))
        db.add(Agent(id="ag-dev-checks", project_id="proj-test", name="DeveloperA"))
        task = Task(
            id=TASK,
            project_id="proj-test",
            title="Balance the ledger",
            description="",
            status="in_progress",
            assignee="DeveloperA",
        )
        db.add(task)
        db.add(
            Run(
                id="run-checks-qa",
                project_id="proj-test",
                agent="QA",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_checks-qa"),
            )
        )
        await db.commit()
        await apply_transition(db, task, "completed", run_actor("run-dev-authored", "DeveloperA"))
        await db.commit()
    return sha


async def test_outside_a_flow_no_agent_takes_work_into_review_while_its_checks_run(app, tmp_path):
    sha = await _completed_outside_a_flow(tmp_path)
    await _configure([_slow(tmp_path)])
    run_id = await _running_run(tmp_path, sha, task_id=TASK)
    mender = await mender_run()
    qa = {"Authorization": "Bearer aw_run_checks-qa"}

    taken = await app.patch(AGENT_TASKS.format(TASK), json={"status": "under_review"}, headers=qa)
    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()) as started:
        handed = await app.post(
            RESET.format(TASK), json={"status": "under_review", "assignee": "QA"}, headers=mender
        )

    assert taken.status_code == 409, taken.text
    assert run_id in taken.text and "running" in taken.text
    assert handed.status_code == 409, handed.text
    assert run_id in handed.text
    started.assert_not_awaited()
    assert (await _task()).status == "completed"

    async with async_session_factory() as db:
        run = await db.get(TaskCheckRun, run_id)
        run.state, run.ended_at = "passed", datetime.now(timezone.utc)
        run.results = [{"name": "hub-tests", "exit_code": 0, "timed_out": False}]
        await db.commit()

    taken = await app.patch(AGENT_TASKS.format(TASK), json={"status": "under_review"}, headers=qa)
    assert taken.status_code == 200, taken.text
    task = await _task()
    assert (task.status, task.assignee) == ("under_review", "QA")


async def test_outside_a_flow_a_failed_task_is_returned_to_its_builder(app, tmp_path):
    await _completed_outside_a_flow(tmp_path)
    await _configure([_slow(tmp_path, fails_on="ledger.py")])

    assert await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()

    task = await _task()
    assert (task.status, task.assignee) == ("revision_needed", "DeveloperA")
    assert (await _latest_transition(TASK)).origin == "checks"


# ---------------------------------------------------------------------------------------------
# Review of slice L: re-completing failed work, the return's race, one deadline
# ---------------------------------------------------------------------------------------------


async def test_completing_unchanged_work_again_after_its_run_failed_is_refused(app, tmp_path):
    """The builder's work fails the suite and comes back; completing it again unchanged is refused
    with that run's output (its run is the current verdict for exactly this work, so none starts).
    """
    await _builder_task(tmp_path, content="x = 1\n")
    await _configure([_lint(tmp_path), _slow(tmp_path, fails_on="ledger.py")])

    assert (await _complete(app)).status_code == 200
    await project_checks.drain()
    task = await _task()
    assert (task.status, task.assignee) == ("revision_needed", BUILDER)

    resumed = await app.patch(
        AGENT_TASKS.format(TASK), json={"status": "in_progress"}, headers=BUILDER_HEADERS
    )
    assert resumed.status_code == 200, resumed.text
    again = await _complete(app)
    await project_checks.drain()

    assert again.status_code == 409, again.text
    assert "assert 2 == 3" in again.json()["detail"]["message"]
    assert (await _task()).status == "in_progress"
    [run] = await _runs()
    assert run.state == "failed", "nothing ran again: the recorded verdict answered"


async def test_the_return_does_not_overwrite_a_move_made_while_it_ran(app, tmp_path, monkeypatch):
    """While the return runs git, another session approves the task: the approval stands."""
    await _completed_outside_a_flow(tmp_path)
    await _configure([_slow(tmp_path, fails_on="ledger.py")])
    async with async_session_factory() as db:
        (await db.get(Task, TASK)).status = "under_review"  # so the run's own return does not act
        await db.commit()
    run_id = await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()
    async with async_session_factory() as db:
        (await db.get(Task, TASK)).status = "completed"
        await db.commit()

    original = project_checks.check_targets

    async def approved_meanwhile(session, task, root, *, awaiting_review):
        targets = await original(session, task, root, awaiting_review=awaiting_review)
        async with async_session_factory() as other:
            (await other.get(Task, task.id)).status = "approved"
            await other.commit()
        return targets

    monkeypatch.setattr(project_checks, "check_targets", approved_meanwhile)
    assert await project_checks.return_failed_work(run_id) is False
    assert (await _task()).status == "approved"


async def test_ending_a_run_on_older_work_counts_against_the_budget(app, tmp_path, monkeypatch):
    """A run on older work that does not end when told to must not hold the completion past the
    budget (the MCP client gives up at COMPLETION_REQUEST_TIMEOUT_SECONDS)."""
    import hub.pty_runner as pty_runner

    monkeypatch.setattr(project_checks, "COMPLETION_BUDGET_SECONDS", 2.0)
    monkeypatch.setattr(pty_runner, "terminate_process_tree", lambda pid: None)
    await _builder_task(tmp_path, content="x = 1\n")
    sleeper = _script(tmp_path, "sleeper", "import time\ntime.sleep(12)\n")
    await _configure([{"name": "lint", "command": sleeper, "timeout_seconds": 60, "fast": True}])
    older = git(tmp_path, "rev-parse", worktrees.task_branch_name(TASK)).stdout.strip()
    assert await project_checks.request_run("proj-test", TASK, targets=[older])
    await asyncio.sleep(1.5)  # the older run is inside its check now, which ignores being ended
    commit_on_branch(tmp_path, worktrees.task_branch_name(TASK), "more.py", "y = 2\n", create=False)
    git(tmp_path, "checkout", "-q", "main")

    started = time.monotonic()
    completed = await _complete(app)
    elapsed = time.monotonic() - started
    await project_checks.drain()

    assert completed.status_code == 200, completed.text
    assert elapsed < 2.0 + 5.0, elapsed
