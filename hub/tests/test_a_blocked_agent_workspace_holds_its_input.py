"""F188: a blocked *agent* workspace spends the queue head's three attempts and destroys it.

F114 established the rule the scheduler now runs on: a refusal that stops the agent running at all
must not count a delivery attempt, because nothing is starving behind the head entry and the
product promised to hold that input until the operator performs the repair (F96). A refusal that
blocks *one entry* must go on counting, because the head entry is in the way of everybody else
(F56).

`Could not prepare isolated worktree for <agent>` was on the wrong side of that line. It was raised
for both workspaces -- the agent's own checkout under `.agentweave/worktrees/<agent>`, and the
separate checkout a task-scheme task takes -- and it carried no flag either way, so it always
counted. When the obstruction is the *agent's* workspace, no turn for that agent can run in any
conversation, nothing is starving behind the entry, and three schedules withdrew the operator's
message with `abandoned_reason` claiming a delivery failed three times that was never attempted
once.

**This file was the reproduction, and it is now the gate on the fix.** Every test here passed
against unmodified code first -- that is what makes the change's behaviour claim a measurement
rather than an inference from reading the source -- and phases 2-3 then flipped the first one from
`withdrawn` to `queued`, exactly as they were written to. Phase 4 flips the third. The second --
the `NO_RUNNER` contrast -- must keep passing unchanged through every phase, because the asymmetry
it pinned *is* the finding: two refusals, the same four schedules, and outcomes that are now the
same rather than opposite.
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

#: What `agent_trigger.py`'s **agent arm** raises when `resolve_turn_workspace` cannot provision the
#: agent's own checkout: the sentence built below `takes_task_workspace(...)` returns false, with
#: the `IsolationUnavailableError` interpolated, carrying `agent_workspace_unavailable` and nothing
#: else -- not `agent_wide`, not `transient`, not `workspace_unavailable` (phase 2).
#:
#: Phase 1 wrote this stub as the flagless sentence the single `except` raised before the split,
#: which is what made the F188 reproduction below a measurement of shipped behaviour. Phase 2
#: replaced that raise with two, so the stub is repointed here at the real agent-arm refusal --
#: otherwise this file would go on reproducing a refusal the product no longer emits, and the flip
#: below would be a flip of nothing.
#:
#: **Truncated after the diagnosis, and task 5.1 checked that this is still honest.** Phase 4 gave
#: the `worktrees` refusal a remedy clause ("Move or delete that directory (`rm -r ...`) ...", and
#: a different one per obstruction), so the sentence the product raises is longer than the one
#: below. Nothing here reads the text except the `waiting_reason` assertion, which compares it
#: against this same constant, and the remedies are asserted where they are written, in
#: `test_a_blocked_workspace_refusal_states_its_remedy.py`. What this file is about is the
#: **flags** and the queue.
BLOCKED_AGENT_WORKSPACE = TriggerAgentError(
    409,
    "Could not prepare f188-blocked's own workspace: refusing existing path "
    "/repo/.agentweave/worktrees/f188-blocked: it is not the registered git worktree "
    "for refs/heads/agentweave/f188-blocked",
    agent_workspace_unavailable=True,
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


async def _waiting_reasons(agent):
    async with async_session_factory() as db:
        result = await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent)
            .order_by(InboundQueueEntry.sequence)
        )
        return [row.waiting_reason for row in result.scalars()]


@pytest.mark.asyncio
async def test_a_blocked_agent_workspace_holds_the_operators_message(app, auth_headers):
    """1.1, flipped by phase 3 -- what F188 asked for, at the scheduler.

    One message, one agent whose own checkout cannot be provisioned, `DELIVERY_ATTEMPT_LIMIT`
    schedules -- which is what a trigger, a `Continue` press and an end-of-turn re-drain each cost.

    Phase 1 measured this same loop against unmodified code and got `withdrawn` at three attempts,
    with an `abandoned_reason` claiming three deliveries that were never attempted once. Phase 3
    made the scheduler ask whether anything was starving behind the head before counting; nothing
    is, because this agent has exactly one queued entry and no other conversation, so the message
    waits for the repair (F96) exactly as `NO_RUNNER`'s does below.

    The refusal is still recorded -- `waiting_reason` carries the agent-arm sentence, so the queue
    can say *why* it is waiting. Holding input silently would be its own defect.
    """
    agent = "f188-blocked"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f188-blocked", "the one message")

    with patch(TRIGGER, AsyncMock(side_effect=BLOCKED_AGENT_WORKSPACE)):
        for _ in range(DELIVERY_ATTEMPT_LIMIT):
            await schedule_agent("proj-test", agent)

    state, attempts, reason = (await _rows(agent))[0]
    assert (state, attempts) == ("queued", 0)
    assert reason is None
    assert await _waiting_reasons(agent) == [
        "Could not prepare f188-blocked's own workspace: refusing existing path "
        "/repo/.agentweave/worktrees/f188-blocked: it is not the registered git worktree "
        "for refs/heads/agentweave/f188-blocked"
    ]


@pytest.mark.asyncio
async def test_no_runner_holds_the_same_message_under_the_same_schedules(app, auth_headers):
    """1.2 -- the contrast, and the finding.

    Identical seeding, identical loop, one more schedule than the limit. The only difference is
    which refusal the trigger raises. `NO_RUNNER` is flagged `agent_wide`, so F114's term in
    `schedule_agent`'s counting condition skips the counter and the input waits for the repair
    (F96); the blocked agent workspace above was flagged nothing, so it did not.

    Both refusals mean *no turn for this agent can run in any conversation*, and until phase 3 only
    one of them was treated that way. **This test must keep passing unchanged through every later
    phase** -- the change is finished when the test above joins it, not when this one moves. It has
    not moved: the assertion below is byte-identical to the one phase 1 committed.
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


def test_a_plain_directory_in_the_way_says_what_to_remove(repo):
    """1.3, flipped by phase 4 -- the ledger's own case, at the layer where it is cheap to assert.

    **This test was written in phase 1 to flip here**, and its previous half asserted the
    *absence* of any remedy vocabulary in this branch's refusal -- checked as vocabulary rather
    than as one phrase, so that phase 4 could not satisfy it by rewording. F188 was driven by
    putting an ordinary directory where the agent's worktree belongs, which reaches
    `ensure_worktree`'s "not the registered git worktree" branch, so it is that branch's remedy
    the flipped assertion reads.
    """
    blocked = worktrees.worktree_path(repo, "f188-agent")
    blocked.mkdir(parents=True)
    (blocked / "left-behind.txt").write_text("not a worktree\n")

    with pytest.raises(worktrees.IsolationUnavailableError) as caught:
        worktrees.ensure_worktree(repo, "f188-agent")

    message = str(caught.value)
    assert str(blocked) in message
    assert "not the registered git worktree" in message
    # The repair, not just the diagnosis: a verb, the directory it applies to, and what happens
    # afterwards. Still vocabulary rather than one phrase -- the phase-1 half was written that way
    # and inverting it in place keeps the two halves comparable.
    assert any(word in message.lower() for word in ("remove", "delete"))
    assert f"rm -r {blocked}" in message
    assert "prune" in message
