"""Approval reads the project's check result (`approval-runs-the-projects-checks`, groups 4.1/4.3)."""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.api.v1.tasks import update_task_for_actor
from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskCheckRun, TaskTransition
from hub.requirement_gate import (
    OPERATOR_ON_FAILING_CHECKS,
    REVIEWER_SENDS_BACK_CHECKS,
    GateRefusal,
    evaluate,
)
from hub.schemas.tasks import TaskUpdate
from hub.task_transitions import Actor

from .test_project_checks_run import FAIL, MAIN_FAIL, PASS, _project, _runs, _task_with_work
from .test_task_integration import commit_on_branch, commits_on, git

TASKS = "/api/v1/projects/proj-test/tasks"


@pytest.fixture(autouse=True)
def _no_landing_timers():
    yield
    landing_queue.cancel_timers()


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
    """*task_id*'s checks decided, the task left in the status it had.

    Run while the task is held `under_review`: a run deciding a failure of the task's own on
    *completed* work returns it to its builder (`checks-run-before-anyone-reviews`, D7), and these
    tests are about what the approval gate then says about a recorded failure."""
    await _project(checks)
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        status, task.status = task.status, "under_review"
        await session.commit()
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    async with async_session_factory() as session:
        (await session.get(Task, task_id)).status = status
        await session.commit()


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
    # F731 (6): the operator approved here, so the next step is said to the operator.
    assert OPERATOR_ON_FAILING_CHECKS in detail["message"]
    assert REVIEWER_SENDS_BACK_CHECKS not in detail["message"]
    assert work not in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_passing_check_lets_approval_merge(app, auth_headers, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    await _checked(task_id, [PASS])

    approved = await _approve(app, auth_headers, task_id)

    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_asking_without_a_result_queues_the_landing_and_answers_at_once(
    app, auth_headers, tmp_path
):
    """`approved-work-merges-in-batches` FR-1: no result holds nothing and starts no run; the
    landing is queued, and the batch's one run is what checks it."""
    task_id, work = await _task_with_work(tmp_path)
    await _project([PASS])
    assert await _runs(task_id) == []

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    await project_checks.drain()
    assert await _runs(task_id) == [], "approving started no per-task run"
    assert work not in commits_on(tmp_path, "main"), "queued, not merged yet"

    await landing_queue.drain()
    assert work in commits_on(tmp_path, "main")
    assert [r.state for r in await _runs(task_id)] == ["passed"], "the batch's one run"


@pytest.mark.asyncio
async def test_a_pass_on_an_older_main_counts(app, auth_headers, tmp_path):
    """FR-9: a pass of the task's work counts on any main tip, and approval re-runs nothing."""
    task_id, _ = await _task_with_work(tmp_path)
    await _checked(task_id, [PASS])
    (tmp_path / "later.txt").write_text("main moved\n", encoding="utf-8")
    git(tmp_path, "add", "later.txt")
    git(tmp_path, "commit", "-q", "-m", "main moves on")

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    await project_checks.drain()
    assert [r.state for r in await _runs(task_id)] == ["passed"]


@pytest.mark.asyncio
async def test_a_reading_caller_of_the_gate_starts_no_run(app, tmp_path):
    """`approval_held_for_operator`, the scheduler, divergence and the preview read only."""
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])
    async with async_session_factory() as session:
        refusal, _ = await evaluate(session, await session.get(Task, task_id), acting_run_id=None)
    await project_checks.drain()
    assert refusal.checks == [], "no result holds nothing"
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
async def test_a_running_result_does_not_hold_approval(app, auth_headers, tmp_path):
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
    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    assert work not in commits_on(tmp_path, "main"), "queued for its batch"


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
    assert "have not finished" in sentence and "does not hold approval" in sentence
    assert await _runs(task_id) == [], "briefing a reviewer starts no run"


@pytest.mark.asyncio
async def test_nothing_is_said_without_checks(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    sentence = await _sentence(task_id)
    assert sentence is None or "checks" not in sentence


@pytest.mark.asyncio
async def test_an_errored_result_does_not_hold_approval(app, auth_headers, tmp_path, monkeypatch):
    """F516 under `approved-work-merges-in-batches`: an error is the Hub failing to produce a
    result, not a verdict. It holds no approval and approving starts no run; the batch checks it."""
    task_id, work = await _task_with_work(tmp_path)
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

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    await project_checks.drain()
    assert [r.state for r in await _runs(task_id)] == ["error"]
    await landing_queue.drain()
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_land_refused_for_a_conflict_does_not_restart_the_checks(
    app, auth_headers, tmp_path
):
    """F613: on the sweep each Land press over a conflicting task started another check run, which
    could only error the same way ("does not merge cleanly"). The conflict is already the refusal;
    a run starts again once the work or main moves."""
    task_id, _ = await _task_with_work(tmp_path)
    commit_on_branch(tmp_path, "main", "feature.py", "x = 2\n", create=False)
    await _checked(task_id, [PASS])
    assert [r.state for r in await _runs(task_id)] == ["error"]

    for _ in range(2):
        refused = await _approve(app, auth_headers, task_id)
        assert refused.status_code == 409, refused.text
        await project_checks.drain()

    detail = refused.json()["detail"]
    assert detail["unmergeable"], detail
    assert "does not merge cleanly" in detail["message"]
    assert [r.state for r in await _runs(task_id)] == ["error"]


# --- F605 (fix-D13): a check that fails on main too is not the task's -----------------------------


@pytest.mark.asyncio
async def test_a_check_failing_on_main_too_is_recorded_as_preexisting(app, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    # MAIN_FAIL before FAIL: a failure main shares does not stop the run, the task's own does.
    await _checked(task_id, [PASS, MAIN_FAIL, FAIL])

    [run] = await _runs(task_id)
    by_name = {r["name"]: r for r in run.results}
    assert "on_main" not in by_name["ok"], "a passing check is not re-run on main"
    assert by_name["tests"]["on_main"]["exit_code"] == 0 and not by_name["tests"]["preexisting"]
    assert by_name["suite"]["on_main"]["exit_code"] == 1 and by_name["suite"]["preexisting"]


@pytest.mark.asyncio
async def test_only_preexisting_failures_hold_the_landing_for_the_operator(
    app, auth_headers, tmp_path
):
    """On the sweep main's defect failed every task's checks; the gate told the reviewer to send
    each task back and nothing was addressed to the operator. Under `approved-work-merges-in-
    batches` approval answers at once; the batch whose failures main shares (check-level, so the Hub
    cannot override them) waits for the operator, who lands it with one reason."""
    task_id, work = await _task_with_work(tmp_path)
    await _checked(task_id, [MAIN_FAIL])

    landed = await app.post(f"{TASKS}/{task_id}/land", headers=auth_headers)
    assert landed.status_code == 200, landed.text
    await landing_queue.drain()

    read = await app.get(f"{TASKS}/{task_id}/checks", headers=auth_headers)
    landing = read.json()["landing"]
    assert landing["state"] == "held", landing
    assert "fail on main too" in landing["reason"]
    assert work not in commits_on(tmp_path, "main")
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        assert task.status == "approved", "nobody sends it back for main's failure"

    released = await app.post(
        f"{TASKS}/{task_id}/landing/land",
        json={"reason": "main carries the defect"},
        headers=auth_headers,
    )
    assert released.status_code == 200, released.text
    assert work in commits_on(tmp_path, "main")
    assert released.json()["landing"]["state"] == "landed"


@pytest.mark.asyncio
async def test_a_new_failure_beside_a_preexisting_one_stays_the_authors(
    app, auth_headers, tmp_path
):
    task_id, _ = await _task_with_work(tmp_path)
    await _checked(task_id, [MAIN_FAIL, FAIL])

    refused = await _approve(app, auth_headers, task_id)

    detail = refused.json()["detail"]
    assert detail["checks"][0]["state"] == "failed"
    assert OPERATOR_ON_FAILING_CHECKS in detail["message"]
    assert "`suite` exited 1 (and fails on main too)" in detail["message"]
    assert "`tests` exited 3:" in detail["message"]


@pytest.mark.asyncio
async def test_land_takes_the_operators_override_reason(app, auth_headers, tmp_path):
    """The sweep's only exit was four PATCHes; Land now carries the override itself."""
    task_id, work = await _task_with_work(tmp_path)
    await _checked(task_id, [MAIN_FAIL])

    landed = await app.post(
        f"{TASKS}/{task_id}/land",
        json={"override_checks_reason": "main carries the defect"},
        headers=auth_headers,
    )

    assert landed.status_code == 200, landed.text
    assert work in commits_on(tmp_path, "main")
    async with async_session_factory() as session:
        reasons = (
            (
                await session.execute(
                    select(TaskTransition.override_reason).where(
                        TaskTransition.task_id == task_id, TaskTransition.to_status == "approved"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert reasons == ["main carries the defect"]


def test_failing_checks_end_on_the_readers_own_next_step():
    """F731 (6): Land's refusal read as addressed to reviewers; each failing check keeps its lines."""
    checks = [
        {
            "state": "failed",
            "failing": [
                {"name": "tests", "exit_code": 3, "output_tail": "one\ntwo"},
                {"name": "lint", "exit_code": 1, "output_tail": "bad"},
            ],
        }
    ]
    for_reviewer = GateRefusal(checks=checks).detail()
    for_operator = GateRefusal(checks=checks, for_operator=True).detail()

    assert REVIEWER_SENDS_BACK_CHECKS in for_reviewer
    assert OPERATOR_ON_FAILING_CHECKS not in for_reviewer
    assert OPERATOR_ON_FAILING_CHECKS in for_operator
    assert REVIEWER_SENDS_BACK_CHECKS not in for_operator
    assert "`tests` exited 3:\none\ntwo\n\n`lint` exited 1:\nbad" in for_operator


@pytest.mark.asyncio
async def test_land_refused_by_failing_checks_speaks_to_the_operator(app, auth_headers, tmp_path):
    task_id, work = await _task_with_work(tmp_path)
    await _checked(task_id, [FAIL])

    refused = await app.post(f"{TASKS}/{task_id}/land", headers=auth_headers)

    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert OPERATOR_ON_FAILING_CHECKS in message
    assert REVIEWER_SENDS_BACK_CHECKS not in message
    assert work not in commits_on(tmp_path, "main")
