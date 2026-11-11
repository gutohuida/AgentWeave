"""A red main or a flake does not hold the night (`a-red-main-does-not-hold-the-night`, slice M),
as the known-failing list now decides it (`failures-already-known-are-on-a-list-not-re-argued`).

Night of 2026-10-26/27 on the operator's Hub: QA approved slice B's T1, and the Hub refused the
approval for 2 h 55 min because one test failed on its merged work and the same *check* failed on
main. Slice M answered by re-running each failure on main and landing over a shared one; the list
replaced that (FR-7, FR-12): a failure on the list is not the work's, one off it is, and nothing is
re-run on main to tell them apart.

Real git repositories, a real pytest check run by the Hub on the merged commit, and the real agent
route (`PATCH /agent-actions/tasks/{id}` with a reviewer's run credential). The check writes a JUnit
report and re-runs its failing tests through the project's own wrapper
(`checks-report-which-tests-failed-in-any-language`, FR-2, FR-6).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select

from hub import landing_queue, project_checks
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EventLog,
    KnownFailingTest,
    Loop,
    Project,
    Run,
    SpecDocument,
    Task,
    TaskTransition,
)
from hub.requirement_gate import approval_held_for_operator
from hub.worktrees import task_branch_name

from .test_a_failing_batch_is_narrowed import RERUN
from .test_task_integration import commit_on_branch, commits_on, git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

PY = f'"{sys.executable}"'
#: The project's check: plain pytest over the checked tree writing a report, as the operator's
#: `hub-tests` is, re-run through the wrapper `_repo` commits.
PYTEST = {
    "name": "pytest",
    "command": f"{PY} -m pytest -q -p no:cacheprovider -p no:randomly "
    "-o junit_family=xunit1 --junitxml=report.xml",
    "timeout_seconds": 120,
    "report_path": "report.xml",
    "rerun_command": f"{PY} rerun.py {{tests}}",
}
#: Main is red: `test_a` fails there. `test_b` passes on main.
LEDGER = "A = 1\nB = 2\n"
TESTS = (
    "import ledger\n\n\n"
    "def test_a():\n    assert ledger.A == 2, 'main is red'\n\n\n"
    "def test_b():\n    assert ledger.B == 2\n"
)
#: The tests as the report names them: `classname::name`.
TEST_A = "test_ledger::test_a"
TEST_B = "test_ledger::test_b"
TASK = "task-c0ffee00a001"
TASK2 = "task-c0ffee00a002"
LOOP = "loop-red-main"
REVIEWER = "reviewer"
AGENT_TASKS = "/api/v1/agent-actions/tasks/{}"
TASKS = "/api/v1/projects/proj-test/tasks"


@pytest.fixture(autouse=True)
def _no_landing_timers():
    yield
    landing_queue.cancel_timers()


async def _landing(app, task_id: str) -> dict:
    """The task's landing as its drawer reads it (`approved-work-merges-in-batches`)."""
    read = await app.get(
        f"{TASKS}/{task_id}/checks", headers={"Authorization": "Bearer aw_live_testkey_abcdefgh"}
    )
    return read.json()["landing"]


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
    for name, content in {
        "ledger.py": LEDGER,
        "test_ledger.py": TESTS,
        "rerun.py": RERUN,
        ".gitignore": "report.xml\n",
        **(files or {}),
    }.items():
        (repo / name).write_text(content, encoding="utf-8")
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", "the ledger and its tests")


async def _loop(*, live: bool = False, loop_id: str = LOOP, needs_evidence=False) -> str:
    """A loop whose work needs no evidence (approval merges the task branch tip); *live* makes it a
    live flow: a document and an enabled job (`flow_advance`'s test). *needs_evidence* `None` is
    the production shape of a flow: undeclared, so its document makes evidence govern."""
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
                work_needs_evidence=needs_evidence,
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


async def _configure(checks=(PYTEST,)) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.checks = list(checks)
        await session.commit()
    await set_main_branch("main")


async def _flaked_before() -> None:
    """The flaky test already listed from an earlier run, with no fix task: the run a test then
    checks is its second flake, which is what files the task (`a-disturbed-check-run-is-not-a-pile-
    of-flaky-tests`, FR-9)."""
    async with async_session_factory() as session:
        session.add(
            KnownFailingTest(
                id="kf-earlier",
                project_id="proj-test",
                check_name="pytest",
                test="test_timing::test_flaky",
                kind="flaky",
                added_by_run="chk-earlier",
            )
        )
        await session.commit()


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
    """The fix tasks the Hub filed (event rows name them)."""
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


async def _listed(test=TEST_A, kind="fails on main", *, check="pytest") -> tuple:
    """*test* on the project's known-failing list, owned by a pending fix task: `(entry, fix)`."""
    key = "".join(c for c in f"{check}{test}" if c.isalnum())[-12:]
    fix, entry = f"task-fix-{key}", f"kf-{key}"
    async with async_session_factory() as session:
        session.add(
            Task(
                id=fix,
                project_id="proj-test",
                title=f"Fix {test or check}",
                description="",
                status="pending",
                priority="high",
            )
        )
        session.add(
            KnownFailingTest(
                id=entry,
                project_id="proj-test",
                check_name=check,
                test=test,
                kind=kind,
                fix_task_id=fix,
            )
        )
        await session.commit()
    return entry, fix


def _main_checkouts(monkeypatch) -> list:
    """Every checkout a check makes, as `(owner, commit)`: none on main's tip is what FR-7 asks."""
    made: list = []
    original = project_checks._checkout

    def recording(root, owner, sha):
        made.append((owner, sha))
        return original(root, owner, sha)

    monkeypatch.setattr(project_checks, "_checkout", recording)
    return made


def _on_main(made: list, tips) -> list:
    """The checkouts in *made* of any of *tips*, main's tips while the checks ran. A landing batch
    checks out its merged commit, which main then moves to: that is the work's tree, not main's."""
    return [(owner, sha) for owner, sha in made if sha in set(tips) or owner.endswith(".main")]


# --- the drive ------------------------------------------------------------------------------------


async def test_a_reviewers_approval_lands_over_a_listed_red_main(app, tmp_path, monkeypatch):
    """drive-lands-over-red-main, through the list: main fails test_a, which is listed; the task's
    run fails it too, is not sent back, approval lands it past the entry, the approval and the
    landing name it, and no check ran on a checkout of main."""
    _repo(tmp_path)
    await _loop()
    work = await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    base = git(tmp_path, "rev-parse", "main").stdout.strip()
    entry, fix = await _listed()
    made = _main_checkouts(monkeypatch)
    await project_checks.request_run("proj-test", TASK)
    await project_checks.drain()

    run = await _latest_run(TASK)
    [result] = run.results
    assert result["shared_tests"] == [TEST_A] and not result.get("own_tests"), result
    assert result["preexisting"] and [e["id"] for e in result["listed"]] == [entry], result
    async with async_session_factory() as session:
        assert (await session.get(Task, TASK)).status == "completed", "not sent back"
    approved = await _reviewer_approves(app, TASK)

    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    assert work in commits_on(tmp_path, "main")
    landing = await _landing(app, TASK)
    assert landing["state"] == "landed" and landing["batch"]["override_by"] is None, landing
    assert [(e["test"], e["fix_task_id"]) for e in landing["went_past"]] == [(TEST_A, fix)]
    transition = await _approval(TASK)
    assert transition.actor_kind == "run" and transition.actor_agent == REVIEWER
    assert transition.override_by == "hub"
    reason = transition.override_reason or ""
    assert TEST_A in reason and run.id in reason and fix in reason, reason
    assert _on_main(made, [base]) == [], made


async def test_no_operator_hold_for_failures_on_the_list(app, tmp_path):
    """no-operator-hold: approval of work whose only failure is listed is held for nobody."""
    _repo(tmp_path)
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _listed()
    await _checked(TASK)

    async with async_session_factory() as session:
        task = await session.get(Task, TASK)
        assert await approval_held_for_operator(session, task, candidate=REVIEWER) is None


async def test_an_unlisted_failure_is_the_tasks(app, tmp_path):
    """Main fails test_a, which is listed, and the task's work fails test_b (and passes test_a):
    test_b is not on the list, so it is the task's."""
    _repo(tmp_path)
    await _loop()
    work = await _task(tmp_path, TASK, {"ledger.py": "A = 2\nB = 3\n"})
    await _configure()
    await _listed()
    await _checked(TASK)

    run = await _latest_run(TASK)
    [result] = run.results
    assert result["own_tests"] == [TEST_B], result
    assert not result["preexisting"]
    refused = await _reviewer_approves(app, TASK)
    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert "revision_needed" in message and "known-failing" not in message, message
    assert work not in commits_on(tmp_path, "main")


async def test_a_flake_is_recorded_on_approval(app, tmp_path, tmp_path_factory):
    """flake-recorded-on-approval: a run that passed only because its failed test passed when rerun
    on its own lands, the approval naming the test and the fix task the list filed for it."""
    counter = tmp_path_factory.mktemp("flake") / "count.txt"
    _repo(
        tmp_path,
        {"test_ledger.py": "def test_ok():\n    pass\n", "test_timing.py": _flaky_test(counter)},
    )
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _flaked_before()
    await _checked(TASK)

    run = await _latest_run(TASK)
    assert run.state == "passed", run.results
    # The flake is listed with its fix task.
    from hub import known_failing

    [fix] = await _fix_tasks()
    assert "test_timing::test_flaky" in fix.title and "flaky" in fix.description
    assert fix.loop_id is None and fix.status == "pending"
    async with async_session_factory() as session:
        listed = (await known_failing.view(session, "proj-test"))["entries"]
    assert [(e["kind"], e["fix_task"]["id"]) for e in listed] == [("flaky", fix.id)], listed
    approved = await _reviewer_approves(app, TASK)

    assert approved.status_code == 200, approved.text
    transition = await _approval(TASK)
    assert transition.override_by == "hub"
    reason = transition.override_reason or ""
    assert "test_timing::test_flaky" in reason and "passed when rerun on its own" in reason
    assert fix.id in reason


async def test_a_touched_flake_is_the_tasks(app, tmp_path, tmp_path_factory):
    """touched-test-is-the-tasks: a flaky test in a file the task changed fails the run -- the task
    introduced it -- and is not listed as flaky."""
    _repo(tmp_path, {"ledger.py": "A = 2\nB = 2\n"})
    await _loop()
    counter = tmp_path_factory.mktemp("flake") / "count.txt"
    await _task(tmp_path, TASK2, {"test_timing.py": _flaky_test(counter)})
    await _configure()
    await _checked(TASK2)
    run = await _latest_run(TASK2)
    assert run.state == "failed", run.results
    [result] = run.results
    assert result["touched_tests"] == ["test_timing::test_flaky"]
    assert result["own_tests"] == ["test_timing::test_flaky"] and not result["preexisting"]
    assert await _fix_tasks() == []


async def test_a_fix_task_the_list_filed_is_reviewed_and_lands(app, tmp_path, tmp_path_factory):
    """A fix task the list files has no requirement, so it could record no evidence: it is governed
    by its review alone, merging its branch tip, and says so on the task (review of slice M,
    2026-10-27). Driven from filed to landed on main; it is on no loop (FR-6)."""
    from hub import task_integration

    counter = tmp_path_factory.mktemp("flake") / "count.txt"
    _repo(
        tmp_path,
        {"test_ledger.py": "def test_ok():\n    pass\n", "test_timing.py": _flaky_test(counter)},
    )
    await _loop(live=True, needs_evidence=None)
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _flaked_before()
    await _checked(TASK)

    [fix] = await _fix_tasks()
    assert fix.loop_id is None
    fixed = commit_on_branch(tmp_path, task_branch_name(fix.id), "notes.txt", "made it wait\n")
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as session:
        task = await session.get(Task, fix.id)
        task.status = "completed"
        await session.commit()
        target = await task_integration.review_target(session, task)
        assert target.resolved and target.commit_sha == fixed, target
    await _checked(fix.id)

    approved = await _reviewer_approves(app, fix.id)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    assert fixed in commits_on(tmp_path, "main")
    assert getattr(fix, "merges_branch_tip", None) is True, "recorded on the task"


async def test_a_fix_task_and_its_dedup_record_are_one_commit(
    app, tmp_path, tmp_path_factory, monkeypatch
):
    """Review of slice M: the fix task was committed and its dedup event written in a second
    commit, so a failure between them left a fix task the dedup could not see (and a second one
    filed at the next run). A failure after the task's commit now leaves both or neither."""
    from hub.api.v1 import tasks as tasks_route

    async def broken_link(*args, **kwargs):
        raise RuntimeError("the Hub stopped here")

    monkeypatch.setattr(tasks_route, "link", broken_link)
    counter = tmp_path_factory.mktemp("flake") / "count.txt"
    _repo(
        tmp_path,
        {"test_ledger.py": "def test_ok():\n    pass\n", "test_timing.py": _flaky_test(counter)},
    )
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    await _flaked_before()
    await _checked(TASK)

    async with async_session_factory() as session:
        filed = (
            (await session.execute(select(Task).where(Task.title.like("Fix flaky test%"))))
            .scalars()
            .all()
        )
    assert [task.id for task in await _fix_tasks()] == [task.id for task in filed], filed
    assert len(filed) == 1


async def test_the_reviewers_briefing_says_the_failure_is_not_the_tasks(app, tmp_path):
    """briefing-says-not-the-tasks: a listed failure is named, with its fix task, and the reviewer
    is not told to send the task back for it."""
    from hub.review_turn import _checks_sentence

    _repo(tmp_path)
    await _loop()
    await _task(tmp_path, TASK, {"feature.py": "x = 1\n"})
    await _configure()
    _, fix = await _listed()
    await _checked(TASK)

    async with async_session_factory() as session:
        task = await session.get(Task, TASK)
        task.status = "under_review"
        await session.commit()
        sentence = await _checks_sentence(session, task)
    assert sentence, sentence
    assert "not this task's work" in sentence and "known-failing list" in sentence, sentence
    assert fix in sentence and TEST_A in sentence, sentence
    assert "end with `revision_needed`" not in sentence, sentence
