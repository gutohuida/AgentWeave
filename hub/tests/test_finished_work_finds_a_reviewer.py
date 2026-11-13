"""Finished work outside a build finds a reviewer (`a-hand-started-task-reaches-review-and-merge`,
FR-2 and FR-3).

Driven on 2026-11-13 through the quickstart: a task the operator started by hand from the board,
with no build behind it, was completed by its builder and then sat `completed` -- nothing staffed a
review, because only a build's flow ran the reviewer ladder. These pin the three outcomes the spec
names (the declared checker, a picked agent, nobody) and that a picked reviewer says so on the
task's story, plus the two places the Hub asks: a check run deciding, and the completing turn's end.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import project_checks, review_on_completion, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, EventLog, InboundQueueEntry, Loop, Run, Task, TaskCheckRun

from .test_a_flow_stages_its_review_in_the_dispatch import _dispatch
from .test_agent_trigger import _init_repo
from .test_flow_fires_a_review_turn import _attribute_completion
from .test_review_turn import (
    _REAL_ENSURE_REVIEW_CHECKOUT,
    _author_commit,
    _reviewable_task,
    _roster,
)

pytestmark = pytest.mark.asyncio

AUTHOR = "builder"
TASK = "task-1"
STORY = f"/api/v1/projects/proj-test/tasks/{TASK}/story"
TASK_URL = f"/api/v1/projects/proj-test/tasks/{TASK}"


async def _finished_by_its_builder(
    app,
    auth_headers,
    bind_runner,
    bind_project_workspace,
    tmp_path,
    monkeypatch,
    *names,
    checker=None,
):
    """A task in no build, with reviewable work, completed by `builder`'s run."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, AUTHOR, *names)
    await _reviewable_task(commit=sha)
    async with async_session_factory() as db:
        await _attribute_completion(db, TASK, AUTHOR)
        task = await db.get(Task, TASK)
        task.assignee = AUTHOR
        task.checker = checker
        await db.commit()


async def _staff():
    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()) as started:
        reviewer = await review_on_completion.staff_review("proj-test", TASK)
    return reviewer, started


async def _review_entries():
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.review_task_id == TASK)
                )
            )
            .scalars()
            .all()
        )


async def _task():
    async with async_session_factory() as db:
        return await db.get(Task, TASK)


# --- ac-auto-declared -----------------------------------------------------------------------------


async def test_the_declared_checker_reviews_it(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        "critic",
        "QA",
        checker="QA",
    )

    reviewer, started = await _staff()

    # `critic` is free too; the story's `declared` below is what says the checker was named.
    assert reviewer == "QA"
    started.assert_awaited_once_with("proj-test", "QA")
    [entry] = await _review_entries()
    assert entry.agent == "QA" and entry.state == "queued"

    await _dispatch("QA")
    task = await _task()
    assert (task.status, task.assignee) == ("under_review", "QA")

    story = (await app.get(STORY, headers=auth_headers)).json()
    [staffed] = [e for e in story["events"] if e["kind"] == "review_staffed"]
    assert staffed["reviewer"] == "QA" and staffed["declared"] is True


async def test_a_declared_checker_that_is_the_author_is_surfaced_not_replaced(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        "critic",
        checker=AUTHOR,
    )

    reviewer, started = await _staff()

    assert reviewer is None
    started.assert_not_awaited()
    assert await _review_entries() == []
    detail = (await app.get(TASK_URL, headers=auth_headers)).json()["stage_detail"]
    assert "names 'builder' as its checker" in detail


# --- ac-auto-picked and ac-picked-visible ---------------------------------------------------------


async def test_with_nobody_declared_another_agent_is_picked_and_the_story_says_so(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "critic"
    )

    reviewer, started = await _staff()

    assert reviewer == "critic"
    started.assert_awaited_once_with("proj-test", "critic")
    [entry] = await _review_entries()
    assert entry.agent == "critic"
    await _dispatch("critic")
    task = await _task()
    assert (task.status, task.assignee) == ("under_review", "critic")

    story = (await app.get(STORY, headers=auth_headers)).json()
    [staffed] = [e for e in story["events"] if e["kind"] == "review_staffed"]
    assert staffed["reviewer"] == "critic"
    assert staffed["declared"] is False
    assert "Nobody was declared" in staffed["reason"]
    assert "critic" in staffed["reason"]


async def test_asking_twice_queues_one_review(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "critic"
    )

    assert (await _staff())[0] == "critic"
    assert (await _staff())[0] is None
    assert len(await _review_entries()) == 1


# --- ac-auto-none ---------------------------------------------------------------------------------


async def test_a_single_agent_project_says_there_is_nobody_else_to_review_it(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )

    reviewer, started = await _staff()

    assert reviewer is None
    started.assert_not_awaited()
    assert await _review_entries() == []
    shown = (await app.get(TASK_URL, headers=auth_headers)).json()
    assert shown["status"] == "completed"
    assert shown["stage"] == "waiting_for_review"
    assert "no agent other than the author to review this" in shown["stage_detail"]

    # Said once, however often it is asked.
    await _staff()
    async with async_session_factory() as db:
        said = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "review_unstaffed")))
            .scalars()
            .all()
        )
    assert len(said) == 1
    story = (await app.get(STORY, headers=auth_headers)).json()
    assert any(e["kind"] == "review_unstaffed" for e in story["events"])


# --- what this path leaves alone ------------------------------------------------------------------


async def test_a_task_a_live_loop_owns_is_left_to_its_loop(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "critic"
    )
    async with async_session_factory() as db:
        db.add(
            AIJob(
                id="job-f",
                project_id="proj-test",
                name="Flow",
                agent=AUTHOR,
                message="go",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=True,
            )
        )
        await db.commit()
        db.add(Loop(id="loop-f", project_id="proj-test", job_id="job-f", purpose="flow"))
        await db.commit()
        (await db.get(Task, TASK)).loop_id = "loop-f"
        await db.commit()

    assert (await _staff())[0] is None
    assert await _review_entries() == []


async def test_a_turn_still_at_work_on_it_is_waited_for(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "critic"
    )
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-still",
                project_id="proj-test",
                agent=AUTHOR,
                status="running",
                task_id=TASK,
            )
        )
        await db.commit()

    assert (await _staff())[0] is None
    # Its end asks again, and is not itself the turn being waited for.
    with patch("hub.turn_scheduler.schedule_accepted", AsyncMock()):
        assert (
            await review_on_completion.staff_review("proj-test", TASK, ending_run_id="run-still")
            == "critic"
        )


# --- where the Hub asks ---------------------------------------------------------------------------


async def test_the_completing_turns_end_asks(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "critic"
    )
    async with async_session_factory() as db:
        db.add(Run(id="run-end", project_id="proj-test", agent=AUTHOR, status="completed"))
        await db.commit()
        (await db.get(Run, "run-end")).task_id = TASK
        await db.commit()

    with patch.object(review_on_completion, "staff_review", AsyncMock()) as staffed:
        review_on_completion.after_run("proj-test", "run-end")
        await review_on_completion.drain()
    staffed.assert_awaited_once_with("proj-test", TASK, ending_run_id="run-end")


async def test_a_decided_check_run_asks(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _finished_by_its_builder(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, "critic"
    )
    async with async_session_factory() as db:
        db.add(
            TaskCheckRun(
                id="chk-1",
                project_id="proj-test",
                task_id=TASK,
                main_sha="a" * 40,
                target_shas=[],
                state="passed",
            )
        )
        await db.commit()

    with (
        patch.object(project_checks, "return_failed_work", AsyncMock(return_value=False)),
        patch.object(review_on_completion, "staff_review", AsyncMock()) as staffed,
    ):
        await project_checks._after_decided("chk-1")
    staffed.assert_awaited_once_with("proj-test", TASK)


async def test_the_runs_end_hook_is_wired_into_the_trigger():
    """Both run-end paths in `agent_trigger` call it, beside the checks' own hook."""
    from pathlib import Path

    import hub.api.v1.agent_trigger as agent_trigger

    source = Path(agent_trigger.__file__).read_text(encoding="utf-8")
    assert source.count("review_on_completion.after_run(project_id, run_id)") == 2
