"""Tests for the three-tier session lookup in hub.api.v1.agent_chat.

The /api/v1/agent/{agent}/chat/{session_id} endpoint merges:
  1. Messages with msg.session_id == session_id  (post-migration column)
  2. Messages with [Session: {session_id}] in content  (pre-migration tag)
  3. Untagged messages (session_id=NULL) inside the session's time window,
     excluding any that belong to a closer previous session.

This is the second-most-recent refactor in the Hub and the 2026-04-01
PR 11 session spent 60+ lines of HANDOFF on the bug-class. These 10
tests pin the three tiers so a regression is caught at the test layer
rather than the UI blinking.

Approach: insert Message + AgentOutput rows directly via
async_session_factory, then call the endpoint and assert.

Important: the Hub's DB engine is a module-level singleton, so in-memory
SQLite data persists across tests in the same pytest run. Each test
therefore uses a UNIQUE agent name (agent_t1, agent_t2, etc.) so the
"other sessions" lookup in Tier 3 doesn't pick up leftover data from
sibling tests and incorrectly exclude in-window messages.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _project_id(app, auth_headers) -> str:
    """Fetch the current project id from the /status endpoint."""
    resp = await app.get("/api/v1/status", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()["project_id"]


async def _add_message(
    project_id: str,
    *,
    msg_id: str,
    recipient: str,
    content: str,
    session_id: str | None = None,
    timestamp: datetime | None = None,
) -> None:
    """Insert a Message row directly into the DB.

    sender is hard-coded to "user" (the agent_chat query only fetches
    user→agent messages).
    """
    async with async_session_factory() as session:
        session.add(
            Message(
                id=msg_id,
                project_id=project_id,
                sender="user",
                recipient=recipient,
                content=content,
                type="message",
                session_id=session_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _add_output(
    project_id: str,
    *,
    out_id: str,
    agent: str,
    content: str,
    session_id: str,
    timestamp: datetime | None = None,
) -> None:
    """Insert an AgentOutput row directly into the DB."""
    async with async_session_factory() as session:
        session.add(
            AgentOutput(
                id=out_id,
                project_id=project_id,
                agent=agent,
                content=content,
                session_id=session_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Tier 1: exact match on msg.session_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier1_exact_session_id_match(app, auth_headers):
    """A message with msg.session_id == session_id shows up in the chat."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t1"
    await _add_message(
        project_id,
        msg_id="m-tier1",
        recipient=agent,
        session_id="sess-A",
        content="tier1 content",
    )
    await _add_output(
        project_id,
        out_id="o-tier1",
        agent=agent,
        content="tier1 reply",
        session_id="sess-A",
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-A", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    ids = [m["id"] for m in data["messages"]]
    assert "m-tier1" in ids
    assert "o-tier1" in ids


# ---------------------------------------------------------------------------
# Tier 2: content-tag fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier2_content_tag_fallback(app, auth_headers):
    """A pre-migration message with [Session: sess-B] in content shows up."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t2"
    await _add_message(
        project_id,
        msg_id="m-tier2",
        recipient=agent,
        session_id=None,
        content="pre-migration body\n\n[Session: sess-B]",
    )
    await _add_output(
        project_id,
        out_id="o-tier2",
        agent=agent,
        content="tier2 reply",
        session_id="sess-B",
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-B", headers=auth_headers)
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["messages"]]
    assert "m-tier2" in ids
    # And the tag is stripped from the displayed content.
    msg = next(m for m in resp.json()["messages"] if m["id"] == "m-tier2")
    assert "[Session:" not in msg["content"]
    assert msg["content"].startswith("pre-migration body")


# ---------------------------------------------------------------------------
# Tier 3: untagged message inside the time window
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tier3_untagged_message_in_time_window(app, auth_headers):
    """An untagged message (session_id=None) that falls inside the agent-output
    time window is included via the heuristic."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t3a"
    now = datetime.now(timezone.utc)
    # Output at 'now' anchors the session window [now, now].
    await _add_output(
        project_id,
        out_id="o-anchor",
        agent=agent,
        content="anchor",
        session_id="sess-C",
        timestamp=now,
    )
    # Untagged message 1 minute BEFORE the anchor — inside the 5-min buffer.
    await _add_message(
        project_id,
        msg_id="m-tier3",
        recipient=agent,
        session_id=None,
        content="tier3 untagged",
        timestamp=now - timedelta(minutes=1),
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-C", headers=auth_headers)
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["messages"]]
    assert "m-tier3" in ids


@pytest.mark.asyncio
async def test_tier3_untagged_outside_time_window_excluded(app, auth_headers):
    """An untagged message 10 minutes BEFORE the first output is excluded
    (outside the 5-minute pre-buffer)."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t3b"
    now = datetime.now(timezone.utc)
    await _add_output(
        project_id,
        out_id="o-anchor2",
        agent=agent,
        content="anchor",
        session_id="sess-D",
        timestamp=now,
    )
    await _add_message(
        project_id,
        msg_id="m-too-old",
        recipient=agent,
        session_id=None,
        content="too old",
        timestamp=now - timedelta(minutes=10),
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-D", headers=auth_headers)
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["messages"]]
    assert "m-too-old" not in ids


@pytest.mark.asyncio
async def test_tier3_closer_session_excludes_untagged(app, auth_headers):
    """If another session started between the untagged message and the
    current session, the untagged message is excluded from the current
    session (it belongs to the closer previous one)."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t3c"
    now = datetime.now(timezone.utc)
    # Previous session starts 30s ago, current session starts now.
    await _add_output(
        project_id,
        out_id="o-prev",
        agent=agent,
        content="previous",
        session_id="sess-prev",
        timestamp=now - timedelta(seconds=30),
    )
    await _add_output(
        project_id,
        out_id="o-curr",
        agent=agent,
        content="current",
        session_id="sess-curr",
        timestamp=now,
    )
    # Untagged message 1 minute ago — closer to sess-prev than to sess-curr.
    await _add_message(
        project_id,
        msg_id="m-untagged",
        recipient=agent,
        session_id=None,
        content="closer to prev",
        timestamp=now - timedelta(minutes=1),
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-curr", headers=auth_headers)
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["messages"]]
    assert "m-untagged" not in ids, "untagged msg should belong to sess-prev, not sess-curr"


# ---------------------------------------------------------------------------
# Cross-tier / structural invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_output_always_included(app, auth_headers):
    """An agent output with session_id=requested is always in the response."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t4"
    await _add_output(
        project_id,
        out_id="o-only",
        agent=agent,
        content="only output",
        session_id="sess-only",
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-only", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert any(m["id"] == "o-only" and m["role"] == "agent" for m in data["messages"])


@pytest.mark.asyncio
async def test_message_with_session_tag_strips_tag_from_displayed_content(app, auth_headers):
    """A Tier-2 message's content is split on the \\n\\n[Session: tag and only
    the prefix is returned to the client."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t5"
    await _add_message(
        project_id,
        msg_id="m-strip",
        recipient=agent,
        session_id=None,
        content="user-visible\n\n[Session: sess-strip]",
    )
    # Anchor the session so the Tier-2 message is eligible.
    await _add_output(
        project_id,
        out_id="o-strip",
        agent=agent,
        content="x",
        session_id="sess-strip",
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-strip", headers=auth_headers)
    assert resp.status_code == 200
    msg = next(
        m for m in resp.json()["messages"] if m["id"] == "m-strip"
    )
    assert msg["content"] == "user-visible"


@pytest.mark.asyncio
async def test_empty_session_returns_empty_messages(app, auth_headers):
    """A session with no outputs and no qualifying messages returns [ ]."""
    agent = "agent_t6"
    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-empty", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-empty"
    assert data["agent"] == agent
    assert data["messages"] == []


@pytest.mark.asyncio
async def test_other_session_messages_excluded(app, auth_headers):
    """A message tagged with a DIFFERENT session_id is not in the response
    for the current session."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t7"
    now = datetime.now(timezone.utc)
    # Add an output for sess-X to anchor the window.
    await _add_output(
        project_id,
        out_id="o-anchor-x",
        agent=agent,
        content="x-anchor",
        session_id="sess-X",
        timestamp=now,
    )
    # Message tied to a different session.
    await _add_message(
        project_id,
        msg_id="m-other",
        recipient=agent,
        session_id="sess-OTHER",
        content="belongs to OTHER",
    )

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-X", headers=auth_headers)
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["messages"]]
    assert "m-other" not in ids


@pytest.mark.asyncio
async def test_messages_sorted_by_timestamp(app, auth_headers):
    """The final response is sorted by message.timestamp (agent output + user
    messages interleaved correctly)."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t8"
    now = datetime.now(timezone.utc)
    # 3 outputs and 2 messages, interleaved.
    await _add_output(project_id, out_id="o1", agent=agent, content="first", session_id="sess-Z", timestamp=now - timedelta(seconds=10))
    await _add_message(project_id, msg_id="m1", recipient=agent, session_id="sess-Z", content="second", timestamp=now - timedelta(seconds=9))
    await _add_output(project_id, out_id="o2", agent=agent, content="third", session_id="sess-Z", timestamp=now - timedelta(seconds=8))
    await _add_message(project_id, msg_id="m2", recipient=agent, session_id="sess-Z", content="fourth", timestamp=now - timedelta(seconds=7))
    await _add_output(project_id, out_id="o3", agent=agent, content="fifth", session_id="sess-Z", timestamp=now - timedelta(seconds=6))

    resp = await app.get(f"/api/v1/agent/{agent}/chat/sess-Z", headers=auth_headers)
    assert resp.status_code == 200
    msgs = resp.json()["messages"]
    # Must be ascending timestamp order.
    ts = [m["timestamp"] for m in msgs]
    assert ts == sorted(ts), f"messages not sorted ascending: {ts!r}"
    assert len(msgs) == 5
