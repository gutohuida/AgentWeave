"""F131: `continue` answered `started: true` for a turn that began in another conversation.

`POST /api/v1/projects/{project_id}/conversations/{conversation_id}/continue` is addressed to one
conversation, but the resource it starts is the *agent*. `schedule_agent` builds its turn from the
oldest eligible entry across the agent's whole queue, so the conversation in the path contributes
the agent's name and a 404 and nothing else — while `started` was derived from
`result.waiting_reason is None`, which answers "did a turn begin for this agent".

The product had already decided this question one route over. `POST /agent/trigger` compares
`scheduled.response.conversation_id` to the conversation it appended to
(`agent_trigger.py:1344-1358`) and answers *queued* when they differ, which is the shipped
requirement "A refusal is reported only to the input it is about". `continue` is the second
conversation-addressed caller and implemented neither half; the start-direction obligation the
trigger route nonetheless honours had never been written down.

**The reproduction that matters is not the one F131 filed.** F131 pressed Continue on a conversation
with *nothing* queued for it, and that path is unreachable from the shipped UI — the button renders
only when a queued entry names the conversation on screen. The reachable path is the one built here:
the addressed conversation *has* a queued entry and another conversation of the same agent has an
**older** one, so every client-side gate is satisfied and the substitution still happens. Both cases
are covered below, because they need different answers: input waiting behind other input, versus
nothing queued at all.
"""

from typing import List, Optional
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub.api.v1.agent_trigger import TriggerAgentResponse
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Project, Run
from hub.inbound_queue import deliver_entries_with_run, new_entry
from hub.utils import short_id

TRIGGER = "hub.api.v1.agent_trigger.trigger_agent_directly"


async def _register(app, auth_headers, bind_runner, agent):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(agent, cli="claude")


async def _open_conversation(agent: str, conversation_id: str) -> None:
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 6
        db.add(
            Conversation(id=conversation_id, project_id="proj-test", agent=agent, lifecycle="open")
        )
        await db.commit()


async def _queue(agent: str, conversation_id: str, content: str) -> str:
    """Append one operator entry. Insert order is arrival order — `sequence` autoincrements."""
    async with async_session_factory() as db:
        entry = new_entry(
            project_id="proj-test",
            agent=agent,
            origin_type="operator",
            content=content,
            hop_depth=0,
            conversation_id=conversation_id,
        )
        db.add(entry)
        await db.commit()
        return entry.id


def _spawning_trigger():
    """A `trigger_agent_directly` that starts a real `Run` in the conversation it is given.

    The fake has to create the row and deliver the entries, not merely return a response: the
    assertions below query `Run` by `conversation_id` and check that the *unaddressed*
    conversation's entry was consumed while the addressed one's is still queued. A mock that only
    returned a response would make both of those pass vacuously.
    """

    async def _trigger(
        *,
        project_id: str,
        agent: str,
        message: str,
        conversation_id: str,
        session,
        queue_entry_ids: Optional[List[str]] = None,
        **kwargs,
    ) -> TriggerAgentResponse:
        run = Run(
            id=f"run-{short_id()}",
            project_id=project_id,
            agent=agent,
            conversation_id=conversation_id,
            status="running",
        )
        if queue_entry_ids:
            await deliver_entries_with_run(
                session,
                project_id=project_id,
                agent=agent,
                entry_ids=queue_entry_ids,
                run=run,
            )
        else:
            session.add(run)
            await session.commit()
        return TriggerAgentResponse(
            success=True,
            message="started",
            agent=agent,
            run_id=run.id,
            status="running",
            conversation_id=conversation_id,
        )

    return AsyncMock(side_effect=_trigger)


async def _run_for(conversation_id: str) -> Optional[Run]:
    """By conversation, never by recency — a stale row must not be able to satisfy this."""
    async with async_session_factory() as db:
        result = await db.execute(select(Run).where(Run.conversation_id == conversation_id))
        return result.scalars().first()


async def _state_of(entry_id: str) -> str:
    async with async_session_factory() as db:
        row = (
            await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
        ).scalar_one()
        return row.state


async def _continue(app, auth_headers, conversation_id: str):
    resp = await app.post(
        f"/api/v1/projects/proj-test/conversations/{conversation_id}/continue",
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_continue_reports_the_start_against_the_conversation_it_names(
    app, auth_headers, bind_runner
):
    """1.1-1.4 — the reachable reproduction: both conversations have input, the other one's is older.

    Every client-side gate is satisfied here: the addressed conversation really does have an
    undelivered entry, so the Continue button renders exactly as designed. The older entry belongs
    to a conversation the operator is not looking at, and it is the one the scheduler takes.
    """
    agent = "f131-two-conversations"
    await _register(app, auth_headers, bind_runner, agent)
    conv_a, conv_b = "conv-f131-addressed", "conv-f131-older"
    await _open_conversation(agent, conv_b)
    await _open_conversation(agent, conv_a)
    entry_b = await _queue(agent, conv_b, "arrived first, in the conversation nobody pressed")
    entry_a = await _queue(agent, conv_a, "arrived second, in the conversation the operator sees")

    with patch(TRIGGER, _spawning_trigger()):
        body = await _continue(app, auth_headers, conv_a)

    started_elsewhere = await _run_for(conv_b)
    assert started_elsewhere is not None, "the older entry's conversation is the one that ran"
    assert await _run_for(conv_a) is None, "no run began in the conversation that was addressed"
    assert await _state_of(entry_b) == "delivered"
    assert (
        await _state_of(entry_a) == "queued"
    ), "the addressed conversation's input is still waiting"

    assert body["conversation_id"] == conv_a
    assert body["started"] is False, (
        f"answered started against {conv_a}, but the turn that began was in "
        f"{started_elsewhere.conversation_id}"
    )
    assert body["started_conversation_id"] == conv_b
    assert body["waiting_reason"] == "this conversation's input is waiting behind other input"


@pytest.mark.asyncio
async def test_the_addressed_conversation_is_the_one_that_starts(app, auth_headers, bind_runner):
    """3.3 — the equal case. Built with a second conversation present so it cannot pass vacuously.

    The addressed conversation holds the **older** entry here, which is the only difference from
    the test above: same two conversations, same two entries, opposite arrival order.
    """
    agent = "f131-equal"
    await _register(app, auth_headers, bind_runner, agent)
    conv_a, conv_b = "conv-f131-equal-a", "conv-f131-equal-b"
    await _open_conversation(agent, conv_a)
    await _open_conversation(agent, conv_b)
    entry_a = await _queue(agent, conv_a, "arrived first, in the conversation the operator sees")
    entry_b = await _queue(agent, conv_b, "arrived second, elsewhere")

    with patch(TRIGGER, _spawning_trigger()):
        body = await _continue(app, auth_headers, conv_a)

    assert await _run_for(conv_a) is not None
    assert await _run_for(conv_b) is None
    assert await _state_of(entry_a) == "delivered"
    assert await _state_of(entry_b) == "queued"

    assert body["started"] is True
    assert body["conversation_id"] == conv_a
    assert body["started_conversation_id"] == conv_a
    assert body["waiting_reason"] is None


@pytest.mark.asyncio
async def test_nothing_started_names_no_conversation(app, auth_headers, bind_runner):
    """3.4 — no turn began at all: the reason stands, and nothing is identified as started."""
    agent = "f131-nothing"
    await _register(app, auth_headers, bind_runner, agent)
    conv = "conv-f131-nothing"
    await _open_conversation(agent, conv)

    with patch(TRIGGER, _spawning_trigger()) as trigger:
        body = await _continue(app, auth_headers, conv)

    trigger.assert_not_awaited()
    assert body["started"] is False
    assert body["started_conversation_id"] is None
    assert body["waiting_reason"] == "queue is empty"


@pytest.mark.asyncio
async def test_a_conversation_that_queued_nothing_is_not_told_it_is_waiting(
    app, auth_headers, bind_runner
):
    """3.5 — F131's own reproduction, and the case rounds 1 and 2 collapsed into the one above.

    Nothing is queued for the addressed conversation, and another conversation's entry starts.
    "Waiting behind other input" would report a queue position that does not exist and tell the
    caller to wait for a delivery that will never arrive. Reachable by API; the shipped Continue
    button gates it out, which is why it is not the reproduction that matters — but it is a
    different question and it gets a different answer.
    """
    agent = "f131-nothing-queued"
    await _register(app, auth_headers, bind_runner, agent)
    conv_a, conv_b = "conv-f131-silent", "conv-f131-busy"
    await _open_conversation(agent, conv_a)
    await _open_conversation(agent, conv_b)
    entry_b = await _queue(agent, conv_b, "the only input this agent holds")

    with patch(TRIGGER, _spawning_trigger()):
        body = await _continue(app, auth_headers, conv_a)

    assert await _run_for(conv_b) is not None
    assert await _run_for(conv_a) is None
    assert await _state_of(entry_b) == "delivered"

    assert body["started"] is False
    assert body["conversation_id"] == conv_a
    assert body["started_conversation_id"] == conv_b
    assert body["waiting_reason"] == "this conversation had nothing queued"
    assert "waiting behind" not in body["waiting_reason"]


@pytest.mark.asyncio
async def test_trigger_reports_the_start_against_the_conversation_it_appended_to(
    app, auth_headers, bind_runner
):
    """2.4 — the other conversation-addressed route, pinned so the two cannot drift apart again.

    `POST /agent/trigger` has satisfied this rule since F108's change and says so in a comment
    (`agent_trigger.py:1344-1358`). Nothing asserted it against the *start* direction, which is
    why `continue` could be written without it. This is the test that would have caught F131.
    """
    agent = "f131-trigger"
    await _register(app, auth_headers, bind_runner, agent)
    conv_b = "conv-f131-trigger-older"
    await _open_conversation(agent, conv_b)
    entry_b = await _queue(agent, conv_b, "arrived first, in another conversation")

    with patch(TRIGGER, _spawning_trigger()):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "start my own work"},
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["status"] == "queued", "the turn that began carried another conversation's input"
    assert body["conversation_id"] != conv_b
    assert await _run_for(conv_b) is not None
    assert await _run_for(body["conversation_id"]) is None
    assert await _state_of(entry_b) == "delivered"
    assert await _state_of(body["queue_entry_id"]) == "queued"
