"""A git that does not finish preparing a turn's checkout is a stated, retried refusal.

Replicated on the operator's Hub on 2026-11-21: a flow handed a task to its builder, `git worktree
add` for the task's checkout ran past its 30 s timeout, and `subprocess.TimeoutExpired` escaped
`trigger_agent_directly` -- it is not a `GitCommandError`. `schedule_accepted` logged it and left
the input queued with no reason and no count, nothing re-drained it, and every later firing read
the task as "already being worked" by a turn that never existed.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import turn_scheduler, worktrees
from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Project
from hub.inbound_queue import new_entry
from hub.turn_scheduler import schedule_agent

TIMED_OUT = subprocess.TimeoutExpired(["git", "worktree", "add", "-b", "x", "/repo/x"], 30)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True, check=False)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-q", "-m", "base")
    return path


async def _agent(app, auth_headers, bind_runner, name):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(name, cli="claude")


def _git_times_out(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise TIMED_OUT

    monkeypatch.setattr(worktrees, "resolve_turn_workspace", _raise)


@pytest.mark.asyncio
async def test_the_trigger_refuses_with_a_reason_and_asks_to_be_retried(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _agent(app, auth_headers, bind_runner, "slow-git")
    _git_times_out(monkeypatch)

    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent="slow-git", origin="operator")
        session.add(conversation)
        await session.commit()
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TriggerAgentError) as caught:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="slow-git",
                    session=session,
                    message="work on it",
                    conversation_id=conversation.id,
                )

    refusal = caught.value
    assert refusal.status_code == 409
    assert refusal.retry_later is True
    # Counted, so a git that never finishes gives the input up rather than retrying forever.
    assert refusal.transient is False
    assert refusal.agent_wide is False
    assert "TimeoutExpired" in refusal.detail


@pytest.mark.asyncio
async def test_queued_input_records_the_refusal_counts_it_and_is_retried(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _agent(app, auth_headers, bind_runner, "slow-git-q")
    _git_times_out(monkeypatch)
    retried: list = []
    monkeypatch.setattr(
        turn_scheduler, "retry_refused_later", lambda project, agent: retried.append(agent)
    )
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 6
        conversation = new_conversation(
            project_id="proj-test", agent="slow-git-q", origin="operator"
        )
        db.add(conversation)
        await db.flush()
        db.add(
            new_entry(
                project_id="proj-test",
                agent="slow-git-q",
                origin_type="job",
                content="the briefing",
                hop_depth=0,
                conversation_id=conversation.id,
            )
        )
        await db.commit()

    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        # Before the fix this raised `TimeoutExpired` out of the scheduler.
        result = await schedule_agent("proj-test", "slow-git-q")

    assert result.response is None
    assert "Git did not finish" in (result.waiting_reason or "")
    async with async_session_factory() as db:
        entry = (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.agent == "slow-git-q")
            )
        ).scalar_one()
    assert entry.state == "queued"
    assert entry.delivery_attempts == 1
    assert "Git did not finish" in (entry.waiting_reason or "")
    assert retried == ["slow-git-q"]


def test_worktree_add_is_given_minutes_not_seconds():
    # The suite raises `_GIT_TIMEOUT_SECONDS` by fixture, so the product's 30 s is not compared here.
    assert worktrees._WORKTREE_ADD_TIMEOUT_SECONDS >= 300
    # No git the Hub starts outlives the stale-lock age, or a live lock would be cleared.
    assert worktrees.STALE_INDEX_LOCK_SECONDS >= worktrees._WORKTREE_ADD_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_the_app_can_see_a_checkout_being_prepared_and_its_end(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """While git runs, `GET /workspace/preparing` names the conversation; after, nothing."""
    from hub import workspace_preparation

    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _agent(app, auth_headers, bind_runner, "seen-git")
    seen: list = []

    def _slow(*_args, **_kwargs):
        seen.append([p.conversation_id for p in workspace_preparation.current("proj-test")])
        raise TIMED_OUT

    monkeypatch.setattr(worktrees, "resolve_turn_workspace", _slow)
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent="seen-git", origin="operator")
        session.add(conversation)
        await session.commit()
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TriggerAgentError):
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent="seen-git",
                    session=session,
                    message="work on it",
                    conversation_id=conversation.id,
                )

    assert seen == [[conversation.id]]
    after = await app.get("/api/v1/projects/proj-test/workspace/preparing", headers=auth_headers)
    assert after.status_code == 200
    assert after.json() == []


@pytest.mark.asyncio
async def test_the_route_lists_what_is_being_prepared(app, auth_headers):
    from hub import workspace_preparation

    async with workspace_preparation.preparing(
        "proj-test", agent="a", task_id="task-0000000000aa", conversation_id="conv-x"
    ):
        during = await app.get(
            "/api/v1/projects/proj-test/workspace/preparing", headers=auth_headers
        )
        stages = workspace_preparation.preparing_task_ids("proj-test")
    assert [(p["conversation_id"], p["task_id"]) for p in during.json()] == [
        ("conv-x", "task-0000000000aa")
    ]
    assert "task-0000000000aa" in stages
    assert workspace_preparation.current("proj-test") == []
