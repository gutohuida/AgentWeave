"""Approval reads the project's check result (`approval-runs-the-projects-checks`, groups 4.1/4.3)."""

import time

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from hub import project_checks
from hub.api.v1.tasks import update_task_for_actor
from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskCheckRun, TaskTransition
from hub.requirement_gate import REVIEWER_SENDS_BACK_CHECKS, evaluate
from hub.schemas.tasks import TaskUpdate
from hub.task_transitions import Actor

from .test_project_checks_run import FAIL, PASS, _project, _runs, _task_with_work
from .test_task_integration import commits_on, git

TASKS = "/api/v1/projects/proj-test/tasks"


async def _approve(app, auth_headers, task_id, **extra):
    for status in ("under_review",):
        async with async_session_factory() as session:
            if (await session.get(Task, task_id)).status == "completed":
                moved = await app.patch(
                    f"{TASKS}/{task_id}", json={"status": status}, headers=auth_headers
                )
                assert moved.status_code == 200, moved.text
    return await app.patch(
        f"{TASKS}/{task_id}", json={"status": "approved", **extra}, headers=auth_headers
    )


async def _checked(task_id, checks):
    await _project(checks)
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()


@pytest.mark.asyncio
async def test_a_failing_check_refuses_approval_with_its_output_and_the_reviewers_move(
    app, auth_headers, tmp_path
):
    task_id, work = await _task_with_work(tmp_path)
    await _checked(task_id, [FAIL])

    refused = await _approve(app, auth_headers, task_id)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["checks"][0]["state"] == "failed"
    assert "tests" in detail["message"] and "boom: 2 != 3" in detail["message"]
    assert REVIEWER_SENDS_BACK_CHECKS in detail["message"]
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_passing_check_lets_approval_merge(app, auth_headers, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    await _checked(task_id, [PASS])

    approved = await _approve(app, auth_headers, task_id)

    assert approved.status_code == 200, approved.text
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_asking_without_a_result_starts_a_run_and_answers_at_once(
    app, auth_headers, tmp_path
):
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS])
    assert await _runs(task_id) == []

    started = time.monotonic()
    refused = await _approve(app, auth_headers, task_id)
    assert time.monotonic() - started < 2
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["checks"][0]["state"] == "running"
    assert "still running" in refused.json()["detail"]["message"]

    await project_checks.drain()
    assert [r.state for r in await _runs(task_id)] == ["passed"]
    assert (await _approve(app, auth_headers, task_id)).status_code == 200
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_result_on_an_older_main_is_stale_and_re_run(app, auth_headers, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _checked(task_id, [PASS])
    (tmp_path / "later.txt").write_text("main moved\n", encoding="utf-8")
    git(tmp_path, "add", "later.txt")
    git(tmp_path, "commit", "-q", "-m", "main moves on")

    refused = await _approve(app, auth_headers, task_id)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["checks"][0]["state"] == "running"
    await project_checks.drain()
    runs = await _runs(task_id)
    assert [r.state for r in runs] == ["passed", "passed"]
    assert runs[0].main_sha != runs[1].main_sha


@pytest.mark.asyncio
async def test_a_reading_caller_of_the_gate_starts_no_run(app, tmp_path):
    """`approval_held_for_operator`, the scheduler, divergence and the preview read only."""
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    async with async_session_factory() as session:
        refusal, _ = await evaluate(session, await session.get(Task, task_id), acting_run_id=None)
    await project_checks.drain()
    assert refusal.checks[0]["state"] == "not_run"
    assert "have not run" in refusal.detail()
    assert await _runs(task_id) == []


@pytest.mark.asyncio
async def test_the_operator_approves_over_a_failure_with_a_reason_on_record(
    app, auth_headers, tmp_path
):
    task_id, work = await _task_with_work(tmp_path)
    await _checked(task_id, [FAIL])

    approved = await _approve(
        app, auth_headers, task_id, override_checks_reason="flaky on this machine only"
    )

    assert approved.status_code == 200, approved.text
    assert work in commits_on(tmp_path, "main")
    async with async_session_factory() as session:
        reasons = [
            t.override_reason
            for t in (
                await session.execute(
                    select(TaskTransition).where(TaskTransition.task_id == task_id)
                )
            ).scalars()
            if t.to_status == "approved"
        ]
    assert reasons == ["flaky on this machine only"]
    history = await app.get(f"{TASKS}/{task_id}/transitions", headers=auth_headers)
    assert "flaky on this machine only" in history.text


@pytest.mark.asyncio
async def test_a_blank_reason_overrides_nothing(app, auth_headers, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _checked(task_id, [FAIL])
    refused = await _approve(app, auth_headers, task_id, override_checks_reason="   ")
    assert refused.status_code == 409, refused.text
    assert "tests" in refused.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_a_running_result_is_not_overridable(app, auth_headers, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS])
    async with async_session_factory() as session:
        session.add(
            TaskCheckRun(
                id="chk-running0001",
                project_id="proj-test",
                task_id=task_id,
                main_sha=git(tmp_path, "rev-parse", "main").stdout.strip(),
                target_shas=[work],
                state="running",
                results=[],
                error="",
            )
        )
        await session.commit()
    refused = await _approve(app, auth_headers, task_id, override_checks_reason="ship it")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["checks"][0]["state"] == "running"


@pytest.mark.asyncio
async def test_an_agent_cannot_override_checks(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _checked(task_id, [FAIL])
    agent = Actor(kind="run", agent="reviewer", run_id="run-reviewer-x")
    async with async_session_factory() as session:
        with pytest.raises(HTTPException) as refused:
            await update_task_for_actor(
                task_id,
                TaskUpdate(status="approved", override_checks_reason="trust me"),
                project_id="proj-test",
                actor=agent,
                session=session,
            )
    assert refused.value.status_code == 403
    async with async_session_factory() as session:
        assert (await session.get(Task, task_id)).status == "completed"


# --- 5.1: the review briefing states the check result ---------------------------------------


async def _sentence(task_id):
    from hub.review_turn import verdict_evidence_sentence

    async with async_session_factory() as session:
        return await verdict_evidence_sentence(
            session, await session.get(Task, task_id), may_decide=False
        )


@pytest.mark.asyncio
async def test_a_reviewer_is_told_the_checks_failed_and_what_to_do(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _checked(task_id, [FAIL])
    sentence = await _sentence(task_id)
    assert "checks failed" in sentence and "`tests`" in sentence
    assert "`approved` will be refused" in sentence
    assert "`revision_needed`" in sentence
    assert "boom: 2 != 3" in sentence


@pytest.mark.asyncio
async def test_a_reviewer_is_told_the_checks_passed(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _checked(task_id, [PASS])
    assert "checks passed" in await _sentence(task_id)


@pytest.mark.asyncio
async def test_a_reviewer_is_told_the_checks_have_not_finished_and_none_start(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    sentence = await _sentence(task_id)
    await project_checks.drain()
    assert "have not finished" in sentence and "`approved` will be refused" in sentence
    assert await _runs(task_id) == [], "briefing a reviewer starts no run"


@pytest.mark.asyncio
async def test_nothing_is_said_without_checks(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    sentence = await _sentence(task_id)
    assert sentence is None or "checks" not in sentence


@pytest.mark.asyncio
async def test_approving_over_an_errored_result_runs_the_checks_again(
    app, auth_headers, tmp_path, monkeypatch
):
    """F516: on `:8010` a check run's `git worktree add` timed out and recorded `error`, and approval
    refused on it as if it were a verdict. An error is retried by the approval that meets it."""
    task_id, _ = await _task_with_work(tmp_path)
    real = project_checks._checkout
    calls = []

    def flaky(root, task, commit):
        calls.append(commit)
        if len(calls) == 1:
            raise RuntimeError("git worktree add timed out")
        return real(root, task, commit)

    monkeypatch.setattr(project_checks, "_checkout", flaky)
    await _checked(task_id, [PASS])
    assert [r.state for r in await _runs(task_id)] == ["error"]

    refused = await _approve(app, auth_headers, task_id)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["checks"][0]["state"] == "running"
    await project_checks.drain()
    assert [r.state for r in await _runs(task_id)] == ["error", "passed"]
    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
