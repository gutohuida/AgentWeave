"""F114: the operator's own attempts to find out why nothing is happening destroyed their message.

An agent with no runner bound queues its input on purpose, so that binding a runner delivers it
(F96). But `schedule_agent` counted a delivery attempt against the queue head on every non-transient
refusal, and it runs on every trigger, every `POST /conversations/{id}/continue`, and every re-drain
at the end of any turn in the project. Three of those consumed the three attempts the abandonment
counter exists for, and the first message was withdrawn with `abandoned_reason` claiming
"delivery failed 3 times" — for a delivery nobody ever made.

**The half this file has to protect just as hard is the half that still counts.** Round 2 of the
change falsified its own first design here: a refusal that blocks *one entry* rather than the whole
agent must go on counting, because `schedule_agent` always builds its turn from the oldest eligible
entry, so an entry that can never be delivered sits at the head and starves every other
conversation. That is F56's scenario and it is real. `test_an_entry_specific_refusal_still_counts_and_still_gives_up`
is the test that keeps this change from reintroducing it.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub.api.v1.agent_trigger import TriggerAgentError
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Project
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT, new_entry
from hub.turn_scheduler import schedule_agent

TRIGGER = "hub.api.v1.agent_trigger.trigger_agent_directly"

#: The refusal an agent with no runner bound actually raises, marked agent-wide.
NO_RUNNER = TriggerAgentError(
    409, "No runner is bound to this agent. Bind one in the Hub UI.", agent_wide=True
)
#: A refusal that blocks this entry only — the task's checkout could not be prepared.
#:
#: Repointed by task 5.1 of `a-blocked-agent-workspace-holds-its-input`. This used to read
#: *"Could not prepare isolated worktree for builder: object not found"* — F188's exact sentence,
#: from the days when one `except` in `agent_trigger` covered both workspaces and raised one
#: wording for both. That change split the `except` in two, and the arm this file needs is the
#: **task** one: it is the arm that stays flagless, so it is the arm whose entry is still in the
#: way of everything queued behind it. The old sentence is now raised nowhere, and an entry-specific
#: example that the product cannot produce is not an example of anything.
#:
#: The wording below is the real thing: `agent_trigger`'s task arm wrapping the
#: `IsolationUnavailableError` `worktrees.ensure_task_worktree` raises for a directory that is not
#: the registered checkout. Truncated after the diagnosis — the remedy the sentence now carries is
#: asserted where it is written, in `test_a_blocked_workspace_refusal_states_its_remedy.py`, and
#: nothing here reads the text. What this file reads is the **flags**, which is the point: no
#: `agent_wide`, no `agent_workspace_unavailable`, so the counter treats it exactly as it did
#: before either flag existed.
BAD_CHECKOUT = TriggerAgentError(
    409,
    "Could not prepare the checkout for task task-f114bad: refusing existing path "
    "/repo/.agentweave/tasks/task-f114bad: it is not the registered git worktree "
    "for refs/heads/agentweave/task/task-f114bad",
)


async def _register(app, auth_headers, agent):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {}}}},
        headers=auth_headers,
    )


async def _seed(agent, conversation_id, contents):
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 6
        db.add(
            Conversation(id=conversation_id, project_id="proj-test", agent=agent, lifecycle="open")
        )
        entries = [
            new_entry(
                project_id="proj-test",
                agent=agent,
                origin_type="operator",
                content=content,
                hop_depth=0,
                conversation_id=conversation_id,
            )
            for content in contents
        ]
        db.add_all(entries)
        await db.commit()
        return [entry.id for entry in entries]


async def _rows(agent):
    async with async_session_factory() as db:
        result = await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent)
            .order_by(InboundQueueEntry.sequence)
        )
        return [(row.content, row.state, row.delivery_attempts or 0) for row in result.scalars()]


@pytest.mark.asyncio
async def test_an_agent_wide_refusal_never_counts_an_attempt(app, auth_headers):
    """2.2 — however many times the agent is scheduled, nothing was ever delivered."""
    agent = "f114-agent-wide"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f114-wide", ["the one message"])

    with patch(TRIGGER, AsyncMock(side_effect=NO_RUNNER)):
        for _ in range(DELIVERY_ATTEMPT_LIMIT + 2):
            await schedule_agent("proj-test", agent)

    assert await _rows(agent) == [("the one message", "queued", 0)]


@pytest.mark.asyncio
async def test_sending_more_messages_does_not_destroy_the_first(app, auth_headers):
    """2.3 — the F114 reproduction, at the scheduler.

    Five messages to an agent that cannot launch. Each `POST /agent/trigger` schedules the agent,
    which is what used to spend the earlier messages' allowance; here the scheduling is explicit so
    the test asserts the mechanism rather than the route's timing.
    """
    agent = "f114-five"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f114-five", [f"message {n}" for n in range(1, 6)])

    with patch(TRIGGER, AsyncMock(side_effect=NO_RUNNER)):
        for _ in range(5):
            await schedule_agent("proj-test", agent)

    rows = await _rows(agent)
    assert [state for _, state, _ in rows] == ["queued"] * 5
    assert {attempts for _, _, attempts in rows} == {0}


@pytest.mark.asyncio
async def test_continue_does_not_consume_the_work_it_offers_to_start(app, auth_headers):
    """2.4 — the button says "start it without sending a message"; twice used to delete it."""
    agent = "f114-continue"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f114-continue", ["the one message"])

    with patch(TRIGGER, AsyncMock(side_effect=NO_RUNNER)):
        for _ in range(3):
            resp = await app.post(
                "/api/v1/projects/proj-test/conversations/conv-f114-continue/continue",
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["started"] is False

    assert await _rows(agent) == [("the one message", "queued", 0)]


@pytest.mark.asyncio
async def test_the_input_survives_until_the_agent_can_run(app, auth_headers):
    """2.3a, and the requirement's own observable rather than the mechanism's.

    Round 3 found three of the delta's scenarios asserting "no delivery attempt is counted", which
    a test can satisfy by mirroring the implementation. This is the one a reader can check against
    the product: the operator sends several messages to an agent that cannot run, presses Continue,
    then makes it able to run — and gets **every** message, not the ones that survived.
    """
    agent = "f114-survives"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f114-survives", ["first", "second", "third"])

    with patch(TRIGGER, AsyncMock(side_effect=NO_RUNNER)):
        for _ in range(4):
            await schedule_agent("proj-test", agent)
        await app.post(
            "/api/v1/projects/proj-test/conversations/conv-f114-survives/continue",
            headers=auth_headers,
        )

    delivered = []

    async def deliver(**kwargs):
        delivered.append(kwargs["message"])
        raise TriggerAgentError(409, "stop here; the delivery is what is under test")

    with patch(TRIGGER, AsyncMock(side_effect=deliver)):
        await schedule_agent("proj-test", agent)

    assert len(delivered) == 1, "one turn"
    for content in ("first", "second", "third"):
        assert content in delivered[0], f"{content!r} reached the agent"


@pytest.mark.asyncio
async def test_an_entry_specific_refusal_still_counts_and_still_gives_up(app, auth_headers):
    """2.2a — the case round 1 of this change would have broken, found by round 2.

    A task's checkout that cannot be prepared blocks *this* entry, not the agent: the workspace is
    the task's. `schedule_agent` always builds its turn from the oldest eligible entry, so an entry
    like this sits at the head and starves every other conversation unless the Hub eventually gives
    up on it. That is F56's scenario, it is real, and this change must not touch it.
    """
    agent = "f114-entry-specific"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f114-specific", ["the poisoned one"])

    with patch(TRIGGER, AsyncMock(side_effect=BAD_CHECKOUT)):
        for _ in range(DELIVERY_ATTEMPT_LIMIT):
            await schedule_agent("proj-test", agent)

    rows = await _rows(agent)
    assert rows == [("the poisoned one", "withdrawn", DELIVERY_ATTEMPT_LIMIT)]
    async with async_session_factory() as db:
        entry = (
            await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent))
        ).scalar_one()
    assert "stopped retrying" in (entry.abandoned_reason or "")


@pytest.mark.asyncio
async def test_a_request_level_refusal_still_counts(app, auth_headers):
    """2.5 — F108's classification is a different question and this change does not read it.

    A refusal about what was asked is usually entry-specific, so it keeps counting. The one that
    is both request-level and agent-wide (`no such agent`) is marked agent-wide and does not — which
    is the point of the two flags being independent rather than one.
    """
    agent = "f114-request-level"
    await _register(app, auth_headers, agent)
    await _seed(agent, "conv-f114-request", ["review something impossible"])

    refusal = TriggerAgentError(
        409, "Task task-x is already under review by 'critic'.", request_level=True
    )
    with patch(TRIGGER, AsyncMock(side_effect=refusal)):
        await schedule_agent("proj-test", agent)

    assert await _rows(agent) == [("review something impossible", "queued", 1)]


@pytest.mark.asyncio
async def test_the_real_unbound_agent_path_carries_the_flag(app, auth_headers, bind_runner):
    """The end-to-end check the rest of this file cannot make.

    Every test above constructs `TriggerAgentError` itself, so all of them would still pass if the
    three raise sites were never marked. This one goes through the real route with a real agent
    that has no runner bound, exactly as `t_queue_attrition.py` does against a live Hub — five
    triggers, no patching of the trigger at all — and asserts nothing was destroyed.

    It is the difference between testing the gate and testing that the gate is wired to anything.
    """
    agent = "f114-real"
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    for n in range(1, 6):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": f"message {n}", "session_mode": "new"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "queued"

    rows = await _rows(agent)
    assert len(rows) == 5, rows
    assert [state for _, state, _ in rows] == [
        "queued"
    ] * 5, "before F114 the first message was withdrawn by the third trigger"
    assert {attempts for _, _, attempts in rows} == {0}, rows
