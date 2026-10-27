"""A red main or a flake does not hold the night (`a-red-main-does-not-hold-the-night`, slice M).

Night of 2026-10-26/27 on the operator's Hub: QA approved slice B's T1, and the Hub refused the
approval for 2 h 55 min because one test failed on its merged work and the same *check* failed on
main. Nobody but the operator could land it, and the operator was asleep; three dependent tasks
waited with it. Whether main failed the same *test* was never recorded.

This is the slice's acceptance drive. Real git repositories, a real pytest check run by the Hub on
the merged commit and on main, and the real agent route (`PATCH /agent-actions/tasks/{id}` with a
reviewer's run credential).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import project_checks
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, EventLog, Loop, Project, Run, SpecDocument, Task, TaskTransition
from hub.requirement_gate import PREEXISTING_CHECKS_HOLD_REMEDY, approval_held_for_operator
from hub.worktrees import task_branch_name

from .test_task_integration import commit_on_branch, commits_on, git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

PY = f'"{sys.executable}"'
#: The project's check: plain pytest over the checked tree, as the operator's `hub-tests` is.
PYTEST = {
    "name": "pytest",
    "command": f"{PY} -m pytest -q -p no:cacheprovider -p no:randomly",
    "timeout_seconds": 120,
}
#: Main is red: `test_a` fails there. `test_b` passes on main.
LEDGER = "A = 1\nB = 2\n"
TESTS = (
    "import ledger\n\n\n"
    "def test_a():\n    assert ledger.A == 2, 'main is red'\n\n\n"
    "def test_b():\n    assert ledger.B == 2\n"
)
TEST_A = "test_ledger.py::test_a"
TEST_B = "test_ledger.py::test_b"
TASK = "task-c0ffee00a001"
TASK2 = "task-c0ffee00a002"
LOOP = "loop-red-main"
REVIEWER = "reviewer"
AGENT_TASKS = "/api/v1/agent-actions/tasks/{}"
TASKS = "/api/v1/projects/proj-test/tasks"


def _flaky_test(counter: Path) -> str:
    """A test that fails its first execution and passes every later one (*counter* is outside the
    repository, so it is in no tree)."""
    path = counter.as_posix()
    return (
        "def test_flaky():\n"
        f"    with open(r'{path}', 'a+') as f:\n"
        "        f.seek(0)\n"
        "        seen = len(f.read())\n"
        "        f.write('x')\n"
        "    assert seen >= 1, 'flaked'\n"
    )


def _repo(repo: Path, files=None) -> None:
    """A repository whose main holds the ledger and its tests (red on `test_a`)."""
    make_repo(repo)
    for name, content in {"ledger.py": LEDGER, "test_ledger.py": TESTS, **(files or {})}.items():
        (repo / name).write_text(content, encoding="utf-8")
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", "the ledger and its tests")


async def _loop(*, live: bool = False, loop_id: str = LOOP) -> str:
    """A loop whose work needs no evidence (approval merges the task branch tip); *live* makes it a
    live flow: a document and an enabled job (`flow_advance`'s test)."""
    async with async_session_factory() as session:
        session.add(
            AIJob(
                id=f"job-{loop_id}",
                project_id="proj-test",
                name=loop_id,
                agent="builder",
                message="work",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=live,
            )
        )
        if live:
            session.add(
                SpecDocument(
                    id=f"doc-{loop_id}",
                    project_id="proj-test",
                    path=f"spec/changes/{loop_id}/spec.json",
                    title="Red main",
                    kind="change-spec",
                    phase="approved",
                )
            )
        await session.flush()
        session.add(
            Loop(
                id=loop_id,
                project_id="proj-test",
                job_id=f"job-{loop_id}",
                purpose="work",
                work_needs_evidence=False,
                spec_document_id=f"doc-{loop_id}" if live else None,
            )
        )
        await session.commit()
    return loop_id


async def _task(
    repo: Path,
    task_id: str,
    files: dict,
    *,
    loop_id=LOOP,
    status="completed",
    priority="medium",
) -> str:
    """A task whose branch, cut from main, commits *files*; returns the branch tip."""
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                loop_id=loop_id,
                project_id="proj-test",
                title=f"Work {task_id[-4:]}",
                description="",
                status=status,
                priority=priority,
                assignee="builder",
            )
        )
        await session.commit()
    branch = task_branch_name(task_id)
    git(repo, "checkout", "-q", "-b", branch, "main")
    for name, content in files.items():
        (repo / name).write_text(content, encoding="utf-8")
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", f"work of {task_id}")
    work = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "main")
    return work


async def _configure(checks=(PYTEST,), auto_override=None) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.checks = list(checks)
        if auto_override is not None:
            project.checks_auto_override = auto_override
        await session.commit()
    await set_main_branch("main")


async def _checked(task_id: str) -> None:
    """*task_id*'s checks decided while it is held `under_review` (a failure of its own on
    `completed` work would return it to its builder, slice L), its status then restored."""
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        status, task.status = task.status, "under_review"
        await session.commit()
    await project_checks.request_run("proj-test", task_id)
    await project_checks.drain()
    async with async_session_factory() as session:
        (await session.get(Task, task_id)).status = status
        await session.commit()


async def _reviewer_approves(app, task_id: str):
    """The reviewer's run, bound to the task it reviews, approves it through the agent route."""
    token = f"aw_run_reviewer-{task_id}"
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        task.status, task.assignee = "under_review", REVIEWER
        session.add(
            Run(
                id=f"run-rev-{task_id}",
                project_id="proj-test",
                agent=REVIEWER,
                status="running",
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return await app.patch(
        AGENT_TASKS.format(task_id),
        json={"status": "approved", "notes": "the work does what it says"},
        headers={"Authorization": f"Bearer {token}"},
    )


async def _approval(task_id: str) -> TaskTransition:
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(TaskTransition).where(
                    TaskTransition.task_id == task_id, TaskTransition.to_status == "approved"
                )
            )
        ).scalar_one()


async def _latest_run(task_id: str):
    async with async_session_factory() as session:
        return await project_checks.latest_run(session, task_id)


async def _fix_tasks() -> list:
    """The tasks the Hub filed for failures that were not the task's (event rows name them)."""
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EventLog.data).where(EventLog.event_type == "checks_fix_task_filed")
                )
            )
            .scalars()
            .all()
        )
        ids = [row["task_id"] for row in rows]
        return [await session.get(Task, task_id) for task_id in ids]


# --- the drive ------------------------------------------------------------------------------------


async def test_a_reviewers_approval_lands_over_a_red_main(app, tmp_path):
    """drive-lands-over-red-main. On master bbf3f10 this is 409 'fail on main too', work not on
    main: the whole check failing on main held the approval for the operator."""
    _repo(tmp_path)
    await _loop()
    work = await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _checked(TASK)

    run = await _latest_run(TASK)
    main_sha = run.main_sha
    approved = await _reviewer_approves(app, TASK)

    assert approved.status_code == 200, approved.text
    assert work in commits_on(tmp_path, "main")
    transition = await _approval(TASK)
    assert transition.actor_kind == "run" and transition.actor_agent == REVIEWER
    assert transition.override_by == "hub"
    reason = transition.override_reason or ""
    assert TEST_A in reason and run.id in reason and main_sha[:12] in reason, reason
    [result] = run.results
    assert result["on_main"]["failed_tests"] == [TEST_A]
    assert result["shared_tests"] == [TEST_A] and not result.get("own_tests")


async def test_no_operator_hold_for_failures_not_its_own(app, tmp_path):
    """no-operator-hold: the mender is not woken for it; with the setting off the hold is as
    today."""
    _repo(tmp_path)
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _checked(TASK)

    async with async_session_factory() as session:
        task = await session.get(Task, TASK)
        assert await approval_held_for_operator(session, task, candidate=REVIEWER) is None
        (await session.get(Project, "proj-test")).checks_auto_override = False
        await session.commit()
    async with async_session_factory() as session:
        task = await session.get(Task, TASK)
        hold = await approval_held_for_operator(session, task, candidate=REVIEWER)
    assert hold is not None and hold.remedy == PREEXISTING_CHECKS_HOLD_REMEDY


async def test_different_ids_are_the_tasks(app, tmp_path):
    """different-ids-are-the-tasks: main fails test_a, the task's work fails test_b (and passes
    test_a). On master the run is recorded preexisting and held for the operator."""
    _repo(tmp_path)
    await _loop()
    work = await _task(tmp_path, TASK, {"ledger.py": "A = 2\nB = 3\n"})
    await _configure()
    await _checked(TASK)

    run = await _latest_run(TASK)
    [result] = run.results
    assert result["own_tests"] == [TEST_B], result
    assert not result["preexisting"]
    refused = await _reviewer_approves(app, TASK)
    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert "revision_needed" in message and "fail on main too" not in message, message
    assert work not in commits_on(tmp_path, "main")
    assert await _fix_tasks() == []


async def test_a_flake_is_recorded_on_approval(app, tmp_path, tmp_path_factory):
    """flake-recorded-on-approval: a run that passed only because its failed test passed when rerun
    on its own lands with the Hub's override naming the test."""
    counter = tmp_path_factory.mktemp("flake") / "count.txt"
    _repo(
        tmp_path,
        {"test_ledger.py": "def test_ok():\n    pass\n", "test_timing.py": _flaky_test(counter)},
    )
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _checked(TASK)

    run = await _latest_run(TASK)
    assert run.state == "passed", run.results
    # a-fix-task-is-filed: a flake gets its fix task too, which marks the flaky list handled.
    from hub import flaky_tests

    [fix] = await _fix_tasks()
    assert "test_timing.py::test_flaky" in fix.title and "flaky" in fix.description
    async with async_session_factory() as session:
        listed = await flaky_tests.report(session, "proj-test")
    assert listed["flaky"] == [] and listed["handled"]["task_id"] == fix.id, listed
    approved = await _reviewer_approves(app, TASK)

    assert approved.status_code == 200, approved.text
    transition = await _approval(TASK)
    assert transition.override_by == "hub"
    reason = transition.override_reason or ""
    assert "test_timing.py::test_flaky" in reason and "passed when rerun on its own" in reason
    assert fix.id in reason


async def test_a_touched_test_is_the_tasks(app, tmp_path, tmp_path_factory):
    """touched-test-is-the-tasks: a test in a file the task changed is never landed over
    automatically -- failing on main too, or flaky."""
    _repo(tmp_path)
    await _loop()
    edited = TESTS + "\n# the task touched this file\n"
    work = await _task(tmp_path, TASK, {"test_ledger.py": edited})
    await _configure()
    await _checked(TASK)

    [result] = (await _latest_run(TASK)).results
    assert result["touched_tests"] == [TEST_A] and result["preexisting"], result
    refused = await _reviewer_approves(app, TASK)
    assert refused.status_code == 409, refused.text
    assert "fail on main too" in refused.json()["detail"]["message"]
    assert work not in commits_on(tmp_path, "main")
    async with async_session_factory() as session:
        hold = await approval_held_for_operator(
            session, await session.get(Task, TASK), candidate=REVIEWER
        )
    assert hold is not None and hold.remedy == PREEXISTING_CHECKS_HOLD_REMEDY
    assert await _fix_tasks() == []

    # A flaky test in a file the task changed fails the run: the task introduced it.
    counter = tmp_path_factory.mktemp("flake") / "count.txt"
    await _task(tmp_path, TASK2, {"test_timing.py": _flaky_test(counter)})
    await _checked(TASK2)
    run = await _latest_run(TASK2)
    assert run.state == "failed", run.results
    [result] = run.results
    assert result["touched_tests"] == ["test_timing.py::test_flaky"]
    refused = await _reviewer_approves(app, TASK2)
    assert refused.status_code == 409, refused.text
    assert await _fix_tasks() == []


async def test_a_fix_task_cannot_land_itself(app, tmp_path):
    """fix-task-cannot-land-itself: the Hub's fix task for test_a, completed with work that leaves
    test_a failing, is not landed over test_a."""
    _repo(tmp_path)
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _checked(TASK)
    [fix] = await _fix_tasks()

    async with async_session_factory() as session:
        (await session.get(Task, fix.id)).status = "completed"
        await session.commit()
    commit_on_branch(tmp_path, task_branch_name(fix.id), "notes.txt", "looked at it\n")
    git(tmp_path, "checkout", "-q", "main")
    await _checked(fix.id)

    refused = await _reviewer_approves(app, fix.id)
    assert refused.status_code == 409, refused.text
    assert "fail on main too" in refused.json()["detail"]["message"]
    async with async_session_factory() as session:
        moved = (
            (await session.execute(select(TaskTransition).where(TaskTransition.task_id == fix.id)))
            .scalars()
            .all()
        )
    assert all(t.override_reason is None for t in moved)
    assert len(await _fix_tasks()) == 1, "the fix task's own run files nothing more"


async def test_the_setting_off_restores_today(app, auth_headers, tmp_path):
    """setting-off-restores-today: held for the operator, no fix task, and the operator's landing
    records their reason as theirs."""
    _repo(tmp_path)
    await _loop()
    work = await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure(auto_override=False)
    await _checked(TASK)

    refused = await _reviewer_approves(app, TASK)
    assert refused.status_code == 409, refused.text
    assert "fail on main too" in refused.json()["detail"]["message"]
    assert await _fix_tasks() == []

    landed = await app.patch(
        f"{TASKS}/{TASK}",
        json={"status": "approved", "override_checks_reason": "main carries the defect"},
        headers=auth_headers,
    )
    assert landed.status_code == 200, landed.text
    assert work in commits_on(tmp_path, "main")
    transition = await _approval(TASK)
    assert transition.override_by == "operator"
    assert transition.override_reason == "main carries the defect"


async def test_one_fix_task_for_two_runs_failing_the_same_test_on_main(app, tmp_path):
    """one-fix-task-per-failure: deduplicated by test id, named by both approvals."""
    _repo(tmp_path)
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _task(tmp_path, TASK2, {"other.py": "y = 2\n"})
    await _configure()
    await _checked(TASK)
    first = await _latest_run(TASK)
    await _checked(TASK2)

    [fix] = await _fix_tasks()
    text = f"{fix.title}\n{fix.description}"
    assert TEST_A in text and "pytest" in text and "fails on main" in text, text
    assert first.main_sha[:12] in text and first.id in text, text
    assert fix.status == "pending" and fix.assignee is None and fix.loop_id is None
    for task_id in (TASK, TASK2):
        # The first landing moves main, so the second task's checks run again on the new tip.
        await _checked(task_id)
        approved = await _reviewer_approves(app, task_id)
        assert approved.status_code == 200, approved.text
        assert fix.id in ((await _approval(task_id)).override_reason or "")
    assert [t.id for t in await _fix_tasks()] == [fix.id]


async def test_the_fix_task_heads_the_flows_queue(app, tmp_path):
    """fix-task-first-in-queue: found by a task of a live flow, the fix task is filed in that flow
    as critical, and the next firing staffs it ahead of the older pending tasks."""
    from hub.api.v1.jobs import _batch_loop_summaries
    from hub.scheduler import decide_firing

    _repo(tmp_path)
    await _loop(live=True)
    async with async_session_factory() as session:
        for suffix in ("1", "2"):
            session.add(
                Task(
                    id=f"task-older-pending{suffix}",
                    loop_id=LOOP,
                    project_id="proj-test",
                    title=f"Older {suffix}",
                    description="",
                    status="pending",
                    priority="medium",
                )
            )
        await session.commit()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _checked(TASK)
    async with async_session_factory() as session:
        # The held task is in review; the flow's one free agent is what the firing staffs.
        task = await session.get(Task, TASK)
        task.status, task.assignee = "under_review", REVIEWER
        await session.commit()

    [fix] = await _fix_tasks()
    assert fix.loop_id == LOOP and fix.priority == "critical" and fix.status == "pending"
    async with async_session_factory() as session:
        loop = await session.get(Loop, LOOP)
        decision = await decide_firing(session, loop, default_agent="builder")
        current = (await _batch_loop_summaries(session, [f"job-{LOOP}"]))[f"job-{LOOP}"]
    assert [(s.task.id, s.agent) for s in decision.selections] == [(fix.id, "builder")]
    # The board's current pending item is the same task (the review in flight is listed too).
    pending = [t["id"] for t in current.current_tasks if t["status"] == "pending"]
    assert pending == [fix.id], current.current_tasks


async def test_the_reviewers_briefing_says_the_failure_is_not_the_tasks(app, tmp_path):
    """briefing-says-not-the-tasks."""
    from hub.review_turn import _checks_sentence

    _repo(tmp_path)
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _checked(TASK)
    [fix] = await _fix_tasks()

    async with async_session_factory() as session:
        task = await session.get(Task, TASK)
        task.status = "under_review"
        await session.commit()
        sentence = await _checks_sentence(session, task)
    assert sentence, sentence
    assert "not this task's work" in sentence, sentence
    assert "override the Hub records" in sentence, sentence
    assert fix.id in sentence and TEST_A in sentence, sentence
    assert "end with `revision_needed`" not in sentence, sentence
