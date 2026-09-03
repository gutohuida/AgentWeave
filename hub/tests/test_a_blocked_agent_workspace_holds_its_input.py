"""F188: a blocked *agent* workspace spends the queue head's three attempts and destroys it.

F114 established the rule the scheduler now runs on: a refusal that stops the agent running at all
must not count a delivery attempt, because nothing is starving behind the head entry and the
product promised to hold that input until the operator performs the repair (F96). A refusal that
blocks *one entry* must go on counting, because the head entry is in the way of everybody else
(F56).

`Could not prepare isolated worktree for <agent>` is on the wrong side of that line. It is raised
for both workspaces -- the agent's own checkout under `.agentweave/worktrees/<agent>`, and the
separate checkout a task-scheme task takes -- and it carries no flag either way, so it always
counts. When the obstruction is the *agent's* workspace, no turn for that agent can run in any
conversation, nothing is starving behind the entry, and three schedules withdraw the operator's
message with `abandoned_reason` claiming a delivery failed three times that was never attempted
once.

**This file is the reproduction, and it is a gate.** Every test here passes against unmodified
code; that is what makes the change's behaviour claim a measurement rather than an inference from
reading the source. Phases 2-4 change what the first and third tests assert. The second one --
the `NO_RUNNER` contrast -- must keep passing unchanged, because the asymmetry it pins *is* the
finding: two refusals, the same four schedules, opposite outcomes.
"""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.api.v1.agent_trigger import TriggerAgentError
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Project
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT, new_entry
from hub.turn_scheduler import schedule_agent

TRIGGER = "hub.api.v1.agent_trigger.trigger_agent_directly"

#: What `agent_trigger.py:879-883` raises today when `resolve_turn_workspace` cannot provision the
#: agent's own checkout -- the sentence built at that `except`, with the `IsolationUnavailableError`
#: interpolated, and **no flags at all**. Not `agent_wide`, not `transient`, not
#: `workspace_unavailable`. The absence is the defect.
BLOCKED_AGENT_WORKSPACE = TriggerAgentError(
    409,
    "Could not prepare isolated worktree for f188-blocked: refusing existing path "
    "/repo/.agentweave/worktrees/f188-blocked: it is not the registered git worktree "
    "for refs/heads/agentweave/f188-blocked",
)

#: The refusal an agent with no runner bound raises, marked agent-wide by F114. Held here as the
#: control: the same loop, the same count, the opposite outcome.
NO_RUNNER = TriggerAgentError(
    409, "No runner is bound to this agent. Bind one in the Hub UI.", agent_wide=True
)


async def _register(app, auth_headers, agent):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {}}}},
        headers=auth_headers,
    )


async def _seed(agent, conversation_id, content):
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 6
        db.add(
            Conversation(id=conversation_id, project_id="proj-test", agent=agent, lifecycle="open")
        )
        db.add(
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content=content,
                hop_depth=0,
                conversation_id=conversation_id,
            )
        )
        await db.commit()


async def _rows(agent):
    async with async_session_factory() as db:
        result = await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent)
            .order_by(InboundQueueEntry.sequence)
        )
        return [
            (row.state, row.delivery_attempts or 0, row.abandoned_reason)
            for row in result.scalars()
        ]


@pytest.mark.asyncio
async def test_a_blocked_agent_workspace_destroys_the_operators_message(app, auth_headers):
    """1.1 -- the F188 reproduction, at the scheduler.

    One message, one agent whose own checkout cannot be provisioned, `DELIVERY_ATTEMPT_LIMIT`
    schedules -- which is what a trigger, a `Continue` press and an end-of-turn re-drain each cost.
    The message is gone, and the reason it carries is a claim about deliveries that never happened.
    """
    agent = "f188-blocked"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f188-blocked", "the one message")

    with patch(TRIGGER, AsyncMock(side_effect=BLOCKED_AGENT_WORKSPACE)):
        for _ in range(DELIVERY_ATTEMPT_LIMIT):
            await schedule_agent("proj-test", agent)

    state, attempts, reason = (await _rows(agent))[0]
    assert (state, attempts) == ("withdrawn", DELIVERY_ATTEMPT_LIMIT)
    assert reason is not None
    assert f"delivery failed {DELIVERY_ATTEMPT_LIMIT} times" in reason
    assert "the Hub stopped retrying" in reason
    # And the sentence the operator is left with names the agent, so it reads as a fact about the
    # agent -- while the bookkeeping it accompanies is the bookkeeping for an entry-specific fault.
    assert "Could not prepare isolated worktree for f188-blocked" in reason


@pytest.mark.asyncio
async def test_no_runner_holds_the_same_message_under_the_same_schedules(app, auth_headers):
    """1.2 -- the contrast, and the finding.

    Identical seeding, identical loop, one more schedule than the limit. The only difference is
    which refusal the trigger raises. `NO_RUNNER` is flagged `agent_wide`, so F114's term in
    `turn_scheduler.py:204` skips the counter and the input waits for the repair (F96); the
    blocked agent workspace above is flagged nothing, so it does not.

    Both refusals mean *no turn for this agent can run in any conversation*. Only one of them is
    treated that way. **This test must keep passing unchanged through every later phase** -- the
    change is finished when the test above joins it, not when this one moves.
    """
    agent = "f188-control"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f188-control", "the one message")

    with patch(TRIGGER, AsyncMock(side_effect=NO_RUNNER)):
        for _ in range(DELIVERY_ATTEMPT_LIMIT + 1):
            await schedule_agent("proj-test", agent)

    assert await _rows(agent) == [("queued", 0, None)]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


@pytest.fixture
def repo(tmp_path) -> Path:
    """A disposable git repository -- never the real AgentWeave checkout.

    Deliberately a local copy of `test_worktrees.py`'s fixture rather than an import: this file's
    other two tests need the Hub app fixtures, and the two halves share nothing but the finding.
    """
    path = tmp_path / "repo"
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "test")
    (path / "f.txt").write_text("base\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def test_a_plain_directory_in_the_way_refuses_with_no_remedy(repo):
    """1.3 -- the ledger's own case, pinned at the layer where it is cheap to assert.

    F188 was driven by putting an ordinary directory where the agent's worktree belongs. That is
    what `ensure_worktree`'s "not the registered git worktree" branch is for, and the operator who
    hits it is told what is wrong and **not what to do about it** -- no directory to remove, no
    `git worktree prune` to follow it. Phase 4 gives this branch its own remedy, at which point the
    negative half of this assertion flips to a positive one; it is written here so that the change
    can show it moved something real.
    """
    blocked = worktrees.worktree_path(repo, "f188-agent")
    blocked.mkdir(parents=True)
    (blocked / "left-behind.txt").write_text("not a worktree\n")

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(repo, "f188-agent")

    message = str(caught.value)
    assert str(blocked) in message
    assert "not the registered git worktree" in message
    # No remedy today. Checked as vocabulary rather than as one phrase, so that phase 4 cannot
    # satisfy it by rewording: an operator looking for the repair is looking for a verb.
    assert not any(
        word in message.lower() for word in ("remove", "delete", "prune", "rm ", "then run")
    )
