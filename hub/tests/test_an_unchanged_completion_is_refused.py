"""A sent-back task cannot be completed unchanged; a builder hands over a named blocker instead.

`a-task-that-cannot-move-waits-instead-of-being-rebuilt-and-re-reviewed`, task
`no-new-work-and-blocker-handover`. In build-a24caf7d4f37 TSBVD-5's builder completed unchanged work
to stop the flow re-claiming it, and the project's checks and the reviewer sent it back over and
over. A completion whose own changes against the main branch are what they were at the last
send-back is now refused (FR-4), whoever made that send-back; the honest way out is a hand-over to
the checker naming the blocker, with no check run (FR-7); both moves are taught in the runs'
instructions (FR-10).

The own-changes measurement is real git in `test_the_digest_*`; the route tests stub only that
measurement, so they say what the route does with the answer.
Named by criterion: `-k digest`, `-k refused`, `-k every_send_back`, `-k handover`, `-k taught`.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from hub import own_changes, project_checks
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task, TaskCheckRun, TaskTransition
from hub.task_transition_service import ORIGIN_CHECKS, apply_transition
from hub.task_transitions import SEND_BACK_BROKEN_CHECK, operator

from .test_review_turn import _roster

P = "proj-test"
TASKS = f"/api/v1/projects/{P}/tasks"
AGENT_TASKS = "/api/v1/agent-actions/tasks"
TASK = "task-0123456789ab"
_T0 = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------------------------
# What "own changes" means: real git
# ---------------------------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-b", "main")
    (tmp_path / "base.txt").write_text("base\n")
    _git(tmp_path, "add", "base.txt")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "checkout", "-b", "agentweave/task/task-0123456789ab")
    (tmp_path / "work.txt").write_text("the task's work\n")
    _git(tmp_path, "add", "work.txt")
    _git(tmp_path, "commit", "-m", "the task's work")
    return tmp_path


def test_the_digest_ignores_a_merge_of_main_and_an_empty_commit_but_not_a_real_change(repo):
    sent_back = own_changes.digest(repo, "main", TASK)
    assert sent_back is not None

    # An empty commit moves the tip and nothing else.
    _git(repo, "commit", "--allow-empty", "-m", "nothing")
    assert own_changes.digest(repo, "main", TASK) == sent_back

    # Main moves on, and is merged into the task's branch: the tip moves, the task's changes do not.
    _git(repo, "checkout", "main")
    (repo / "other.txt").write_text("someone else's work\n")
    _git(repo, "add", "other.txt")
    _git(repo, "commit", "-m", "other work lands")
    _git(repo, "checkout", "agentweave/task/task-0123456789ab")
    _git(repo, "merge", "--no-ff", "-m", "Merge main", "main")
    assert own_changes.digest(repo, "main", TASK) == sent_back

    # A change to what the task adds does.
    (repo / "work.txt").write_text("the task's work, changed\n")
    _git(repo, "commit", "-am", "a real change")
    assert own_changes.digest(repo, "main", TASK) != sent_back


def test_the_digest_is_none_where_nothing_can_be_measured(repo):
    assert own_changes.digest(repo, "no-such-branch", TASK) is None
    assert own_changes.digest(repo, "main", "task-ba0123456789") is None


# ---------------------------------------------------------------------------------------------
# The route, with the measurement stubbed
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def measured(monkeypatch):
    """What the task's own changes are 'now'; a send-back records it, a completion compares to it."""
    box = {"value": "D"}

    async def current(session, task, *, snapshot_agent=None):
        return box["value"]

    monkeypatch.setattr(own_changes, "current", current)
    return box


@pytest.fixture
def no_check_run(monkeypatch):
    """A refused or handed-over completion starts no check run: reaching the checks fails the test."""
    started = []

    async def fast_checks(session, task, agent):
        started.append(task.id)
        return project_checks.ChecksSkipped("stubbed")

    monkeypatch.setattr(project_checks, "fast_checks_at_completion", fast_checks)
    return started


async def _people(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "Developer", "QA")


async def _task(task_id, status, *, baseline=None, assignee=None):
    async with async_session_factory() as db:
        db.add(
            Task(
                id=task_id,
                project_id=P,
                title=f"Task {task_id}",
                status=status,
                assignee=assignee or ("QA" if status == "under_review" else "Developer"),
                builder="Developer",
                checker="QA",
                send_back_changes=baseline,
            )
        )
        await db.commit()


async def _run(run_id, agent, task_id, *, minutes=0):
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id=P,
                agent=agent,
                task_id=task_id,
                status="running",
                turn_depth=0,
                started_at=_T0 + timedelta(minutes=minutes),
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _read(task_id):
    async with async_session_factory() as db:
        return await db.get(Task, task_id)


async def _transitions_to(task_id, status):
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count())
            .select_from(TaskTransition)
            .where(TaskTransition.task_id == task_id, TaskTransition.to_status == status)
        )


@pytest.mark.asyncio
async def test_an_unchanged_completion_is_refused_and_a_changed_one_is_not(
    app, auth_headers, bind_runner, measured, no_check_run
):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "in_progress", baseline="D")
    builder = await _run("run-dev", "Developer", "task-w")

    refused = await app.patch(
        f"{AGENT_TASKS}/task-w", json={"status": "completed"}, headers=builder
    )
    assert refused.status_code == 409, refused.text
    said = str(refused.json()["detail"])
    assert "commit a change" in said and "blocker" in said and "ask_user" in said
    assert (await _read("task-w")).status == "in_progress"  # stays where it was
    assert no_check_run == []  # and no check run starts

    measured["value"] = "E"  # a commit that changes the task's own changes
    done = await app.patch(f"{AGENT_TASKS}/task-w", json={"status": "completed"}, headers=builder)
    assert done.status_code == 200, done.text
    assert (await _read("task-w")).status == "completed"
    assert no_check_run == ["task-w"]  # the ordinary completion ran its checks


@pytest.mark.asyncio
async def test_a_task_with_no_send_back_on_record_completes_normally(
    app, auth_headers, bind_runner, measured, no_check_run
):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "in_progress", baseline=None)
    builder = await _run("run-dev", "Developer", "task-w")

    done = await app.patch(f"{AGENT_TASKS}/task-w", json={"status": "completed"}, headers=builder)
    assert done.status_code == 200, done.text


@pytest.mark.asyncio
@pytest.mark.parametrize("by", ["reviewer", "checks", "operator"])
async def test_every_send_back_records_the_baseline(
    app, auth_headers, bind_runner, measured, no_check_run, by
):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "under_review" if by == "reviewer" else "completed")
    measured["value"] = "D"

    if by == "reviewer":
        qa = await _run("run-qa", "QA", "task-w")
        sent = await app.patch(
            f"{AGENT_TASKS}/task-w",
            json={"status": "revision_needed", "reason_class": "defect", "notes": "wrong"},
            headers=qa,
        )
        assert sent.status_code == 200, sent.text
    elif by == "operator":
        sent = await app.patch(
            f"{TASKS}/task-w",
            json={"status": "revision_needed", "reason_class": "defect", "notes": "wrong"},
            headers=auth_headers,
        )
        assert sent.status_code == 200, sent.text
    else:
        async with async_session_factory() as db:
            task = await db.get(Task, "task-w")
            await apply_transition(
                db,
                task,
                "revision_needed",
                operator(),
                origin=ORIGIN_CHECKS,
                note="its checks failed",
                reason_class=SEND_BACK_BROKEN_CHECK,
                reason="its checks failed",
            )
            await db.commit()

    assert (await _read("task-w")).send_back_changes == "D"

    # Its builder takes it up again and completes it with nothing changed: refused.
    moved = await _read("task-w")
    assert moved.status == "revision_needed"
    async with async_session_factory() as db:
        (await db.get(Task, "task-w")).status = "in_progress"
        await db.commit()
    builder = await _run("run-dev", "Developer", "task-w", minutes=5)
    refused = await app.patch(
        f"{AGENT_TASKS}/task-w", json={"status": "completed"}, headers=builder
    )
    assert refused.status_code == 409, refused.text
    assert no_check_run == []


# ---------------------------------------------------------------------------------------------
# FR-7: the hand-over
# ---------------------------------------------------------------------------------------------


async def _handed_over(app, auth_headers, bind_runner):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "in_progress", baseline="D")
    builder = await _run("run-dev", "Developer", "task-w")
    handed = await app.patch(
        f"{AGENT_TASKS}/task-w",
        json={"status": "completed", "blocker": "the loader is missing; see TSBVD-11"},
        headers=builder,
    )
    assert handed.status_code == 200, handed.text
    # The flow takes it into review by its checker.
    moved = await app.patch(
        f"{TASKS}/task-w",
        json={"status": "under_review", "assignee": "QA"},
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text
    return await _run("run-qa", "QA", "task-w", minutes=5)


@pytest.mark.asyncio
async def test_a_builder_hands_over_a_blocker_with_no_check_run(
    app, auth_headers, bind_runner, measured, no_check_run
):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "in_progress", baseline="D")
    builder = await _run("run-dev", "Developer", "task-w")

    handed = await app.patch(
        f"{AGENT_TASKS}/task-w",
        json={"status": "completed", "blocker": "the loader is missing; see TSBVD-11"},
        headers=builder,
    )
    assert handed.status_code == 200, handed.text

    task = await _read("task-w")
    assert task.status == "completed"
    assert "the loader is missing" in task.notes  # the checker reads it in the notes
    assert task.handover_blocker == "the loader is missing; see TSBVD-11"
    assert no_check_run == []
    async with async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(TaskCheckRun)) == 0
        assert await project_checks.review_wait(db, task) is None  # nothing holds its review


@pytest.mark.asyncio
async def test_a_blocker_over_changed_work_is_an_ordinary_completion(
    app, auth_headers, bind_runner, measured, no_check_run
):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "in_progress", baseline="D")
    measured["value"] = "E"
    builder = await _run("run-dev", "Developer", "task-w")

    done = await app.patch(
        f"{AGENT_TASKS}/task-w",
        json={"status": "completed", "blocker": "not actually blocked"},
        headers=builder,
    )
    assert done.status_code == 200, done.text
    assert no_check_run == ["task-w"]
    assert (await _read("task-w")).handover_blocker is None


@pytest.mark.asyncio
async def test_the_checker_files_the_blocker_and_no_send_back_is_recorded(
    app, auth_headers, bind_runner, measured, no_check_run
):
    qa = await _handed_over(app, auth_headers, bind_runner)

    filed = await app.post(
        AGENT_TASKS, json={"title": "Add the loader", "precedes": ["task-w"]}, headers=qa
    )
    assert filed.status_code == 201, filed.text
    task = await _read("task-w")
    assert task.status == "blocked"
    assert await _transitions_to("task-w", "revision_needed") == 0


@pytest.mark.asyncio
async def test_the_checker_sending_a_handed_over_task_back_records_one(
    app, auth_headers, bind_runner, measured, no_check_run
):
    qa = await _handed_over(app, auth_headers, bind_runner)

    sent = await app.patch(
        f"{AGENT_TASKS}/task-w",
        json={"status": "revision_needed", "reason_class": "defect", "notes": "do it"},
        headers=qa,
    )
    assert sent.status_code == 200, sent.text
    assert await _transitions_to("task-w", "revision_needed") == 1
    assert (await _read("task-w")).handover_blocker is None  # a handover is spent by the verdict


# ---------------------------------------------------------------------------------------------
# FR-10: the runs are taught
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_runs_are_taught_both_moves(app, auth_headers, bind_runner):
    from hub import review_turn, scheduler

    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "under_review")
    checker = "\n".join(review_turn.findings_lines(await _read("task-w")))
    assert "prerequisite" in checker
    assert "create_task" in checker and "precedes" in checker

    await _task("task-b", "revision_needed")
    builder = "\n".join(scheduler._briefing_completion_lines(await _read("task-b"), is_flow=True))
    assert "blocker=" in builder and "update_task" in builder
    assert "hand it to its checker" in builder

    # Not offered where nothing was sent back.
    fresh = "\n".join(scheduler._briefing_completion_lines(await _read("task-w"), is_flow=True))
    assert "blocker=" not in fresh
