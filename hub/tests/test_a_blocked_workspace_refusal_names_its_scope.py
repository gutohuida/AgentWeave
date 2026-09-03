"""Phase 2 of `a-blocked-agent-workspace-holds-its-input`: which workspace could not be prepared.

`resolve_turn_workspace` provisions one of two things -- the **task's** checkout when
`takes_task_workspace` says so, and the **agent's** own otherwise -- and both arms raise the same
two exception types carrying no scope. Until this phase the `except` that catches them raised one
sentence for both, flagged nothing, and so nothing downstream could tell *this agent cannot work
anywhere* apart from *this task's checkout is blocked* (F188).

**This file asserts the dispatch, not the wording.** Phase 4 rewrites both sentences to carry a
remedy, and a test that pinned today's phrasing would fail for a reason that has nothing to do
with what it is about. So each test asserts the *flags* -- which are what `turn_scheduler` reads --
and touches the text only to confirm each arm names its own subject, since naming the agent while
refusing over a task is the specific confusion this phase ends.

The scope is decided by calling `worktrees.takes_task_workspace`, deliberately (design D1): not by
the exception's type, which is identical for both arms, and not by parsing a path out of its
message, which would break the next time the message improves.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hub import worktrees
from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Task

#: A valid id in the shape `short_id` mints and `validate_task_id` accepts -- `task-` plus hex.
#: An id that function refused would send the turn down the *agent* arm through grandfathering,
#: which is the opposite of what the second test is about.
BOUND_TASK = "task-b10c4ed00001"

#: What `resolve_turn_workspace` raises when the checkout it wanted is blocked. Held as one value
#: used by both tests: the exception is the same either way, which is exactly why the raise site
#: cannot learn the scope from it.
BLOCKED = worktrees.IsolationUnavailableError(
    "refusing existing path /repo/.agentweave/worktrees/x: it is not the registered git worktree"
)


def _git(path: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True, check=False)


def _init_repo(path: Path) -> Path:
    """A disposable repository.

    `takes_task_workspace` asks `is_git_repo`, so a plain directory would send *every* turn down
    the agent arm and the second test below would pass vacuously.
    """
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


async def _conversation(agent: str) -> str:
    async with async_session_factory() as session:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        session.add(conversation)
        await session.commit()
        return conversation.id


async def _refusal(monkeypatch, *, agent: str, **kwargs) -> TriggerAgentError:
    """Drive one turn to the workspace provisioning and return the refusal it raised.

    `resolve_turn_workspace` is replaced rather than obstructed on disk, because what is under
    test is the `except` -- specifically that it reaches its own answer without consulting the
    exception. A stub that raises for *both* schemes is the sharpest form of that: if the dispatch
    ever went back to reading the exception, both tests below would get identical flags.
    """

    def _raise(*_args, **_kwargs):
        raise BLOCKED

    monkeypatch.setattr(worktrees, "resolve_turn_workspace", _raise)
    async with async_session_factory() as session:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            with pytest.raises(TriggerAgentError) as caught:
                await trigger_agent_directly(
                    project_id="proj-test",
                    agent=agent,
                    session=session,
                    **kwargs,
                )
    return caught.value


@pytest.mark.asyncio
async def test_a_turn_bound_to_no_task_is_refused_over_the_agents_own_workspace(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """2.4(a) -- the new flag, on the arm F188 is about.

    A turn bound to no task gets the agent's own checkout, so a failure to provision one is a
    statement about the agent. `agent_workspace_unavailable` is what `turn_scheduler` reads in
    phase 3; the two flags asserted false are the two it must **not** borrow (design D2) --
    `agent_wide`, whose docstring promises it is set only where nothing else could run, and
    `transient`, which would also reclassify job and flow-step outcomes through
    `terminal_failure=not transient`.
    """
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _agent(app, auth_headers, bind_runner, "scope-agent")
    conversation_id = await _conversation("scope-agent")

    refusal = await _refusal(
        monkeypatch,
        agent="scope-agent",
        message="work on it",
        conversation_id=conversation_id,
    )

    assert refusal.status_code == 409
    assert refusal.agent_workspace_unavailable is True
    assert refusal.agent_wide is False
    assert refusal.transient is False
    assert refusal.request_level is False
    assert refusal.workspace_unavailable is False
    # It names its own subject. Not the phrasing -- the subject.
    assert "scope-agent" in refusal.detail


@pytest.mark.asyncio
async def test_a_turn_bound_to_a_task_is_refused_over_that_tasks_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """2.4(b) -- the arm that must not move.

    Same agent shape, same stub, same exception; the only difference is that the turn is bound to
    a task whose checkout it would have taken. This refusal is entry-specific -- another
    conversation's unbound turn for this agent could still run -- so it keeps today's flags
    exactly: none. It counts a delivery attempt as it always has, and F56's starvation argument
    still applies to it.
    """
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _agent(app, auth_headers, bind_runner, "scope-task")
    conversation_id = await _conversation("scope-task")
    async with async_session_factory() as session:
        session.add(
            Task(id=BOUND_TASK, project_id="proj-test", title="blocked task", status="in_progress")
        )
        await session.commit()

    refusal = await _refusal(
        monkeypatch,
        agent="scope-task",
        message="work on it",
        conversation_id=conversation_id,
        task_id=BOUND_TASK,
    )

    assert refusal.status_code == 409
    assert refusal.agent_workspace_unavailable is False
    assert refusal.agent_wide is False
    assert refusal.transient is False
    assert refusal.request_level is False
    assert refusal.workspace_unavailable is False
    # The task is the subject here and the agent is not -- the confusion this phase ends.
    assert BOUND_TASK in refusal.detail
    assert "scope-task" not in refusal.detail
