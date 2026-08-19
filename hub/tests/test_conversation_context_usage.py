"""A conversation reports its own context reading, not its agent's newest.

`AgentSummary.context_usage` answers "how full is this agent's context" by taking the newest
`context_warning` row for that agent, across every thread it owns. That is a correct answer to a
different question, and the composer — which is conversation-scoped — was reading it. So every one
of an agent's conversations showed whichever one had reported most recently.

Measured on the trial Hub 2026-08-19: agent `verifier` had three conversations whose readings were
18.56%, 16.6% and 15.9%, and the API offered only 15.9%.
"""

import pytest

from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import EventLog
from hub.utils import short_id


async def _sync_agents(app, auth_headers, *names):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _conversation_with_reading(agent: str, reading: dict | None) -> str:
    """A conversation, and optionally one `context_warning` row belonging to it."""
    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent=agent, origin="operator")
        conversation.title = "Thread"
        db.add(conversation)
        if reading is not None:
            db.add(
                EventLog(
                    id=f"evt-{short_id()}",
                    project_id="proj-test",
                    event_type="context_warning",
                    agent=agent,
                    severity="info",
                    data={**reading, "conversation_id": conversation.id},
                )
            )
        await db.commit()
        return conversation.id


def _reading(percent: float, tokens: int, session_id: str = "sess-1") -> dict:
    return {
        "status": "measured",
        "source": "test",
        "basis": "provider_context",
        "context_tokens": tokens,
        "limit_tokens": 100_000,
        "percent": percent,
        "session_id": session_id,
        "observed_at": 1_786_800_000.0,
    }


async def _conversations(app, auth_headers, agent="reader"):
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/conversations", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()}


@pytest.mark.asyncio
async def test_each_conversation_reports_its_own_reading(app, auth_headers):
    """The defect, stated directly: three threads, three different numbers."""
    await _sync_agents(app, auth_headers, "reader")
    high = await _conversation_with_reading("reader", _reading(18.56, 47_970))
    middle = await _conversation_with_reading("reader", _reading(16.6, 42_884))
    low = await _conversation_with_reading("reader", _reading(15.9, 41_085))

    rows = await _conversations(app, auth_headers)

    assert rows[high]["context_usage"]["percent"] == 18.56
    assert rows[middle]["context_usage"]["percent"] == 16.6
    assert rows[low]["context_usage"]["percent"] == 15.9


@pytest.mark.asyncio
async def test_a_conversation_with_no_reading_reports_none(app, auth_headers):
    """Never a fallback to the agent's newest — that fallback is precisely the bug."""
    await _sync_agents(app, auth_headers, "reader")
    measured = await _conversation_with_reading("reader", _reading(42.0, 42_000))
    silent = await _conversation_with_reading("reader", None)

    rows = await _conversations(app, auth_headers)

    assert rows[measured]["context_usage"]["percent"] == 42.0
    assert rows[silent]["context_usage"] is None


@pytest.mark.asyncio
async def test_another_agents_reading_never_leaks_in(app, auth_headers):
    await _sync_agents(app, auth_headers, "reader", "other")
    mine = await _conversation_with_reading("reader", _reading(11.0, 11_000))
    await _conversation_with_reading("other", _reading(99.0, 99_000))

    rows = await _conversations(app, auth_headers)

    assert rows[mine]["context_usage"]["percent"] == 11.0
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_a_row_with_no_percent_does_not_hide_the_one_that_has_it(app, auth_headers):
    """The rule `usable_context_reading` exists for, applied per conversation.

    Claude's end-of-turn message reports a window with no token count, so the newest row for a
    thread routinely carries no percentage. Taking it verbatim reported nothing for 329 samples.
    """
    await _sync_agents(app, auth_headers, "reader")
    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent="reader", origin="operator")
        conversation.title = "Thread"
        db.add(conversation)
        complete = _reading(33.0, 33_000)
        complete["observed_at"] = 1_786_800_000.0
        blank = {**_reading(33.0, 33_000), "percent": None, "context_tokens": None}
        blank["observed_at"] = 1_786_800_100.0
        for index, data in enumerate((complete, blank)):
            db.add(
                EventLog(
                    id=f"evt-{short_id()}-{index}",
                    project_id="proj-test",
                    event_type="context_warning",
                    agent="reader",
                    severity="info",
                    data={**data, "conversation_id": conversation.id},
                )
            )
        await db.commit()
        conversation_id = conversation.id

    rows = await _conversations(app, auth_headers)

    assert rows[conversation_id]["context_usage"]["percent"] == 33.0


@pytest.mark.asyncio
async def test_the_project_wide_list_carries_it_too(app, auth_headers):
    """The rail reads the project-scoped list; the composer reads a conversation from it."""
    await _sync_agents(app, auth_headers, "reader")
    conversation_id = await _conversation_with_reading("reader", _reading(27.5, 27_500))

    response = await app.get("/api/v1/projects/proj-test/conversations", headers=auth_headers)
    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()["conversations"]}

    assert rows[conversation_id]["context_usage"]["percent"] == 27.5
