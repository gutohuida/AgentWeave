"""Tests for the merged conversation timeline in hub.api.v1.agent_chat (task 8.3).

`GET /api/v1/projects/proj-test/agent/{agent}/chat/{session_id}` (and the sessionless
`/chat?limit=`) merge four record types into one chronological, typed
timeline:

  - operator_input / inbound_peer — delivered `InboundQueueEntry` rows,
    placed by their `Run.session_id` (recorded association, never a
    timestamp window)
  - agent_output — `AgentOutput` rows, filtered by their own `session_id`
  - outbound_peer — `Message` rows the agent sent, filtered by their own
    `session_id` (set at send time from the sender's live Run)

Still-queued (undelivered) entries for the agent are appended regardless of
which session was requested, since they have no session yet.

Important: the Hub's DB engine is a module-level singleton, so in-memory
SQLite data persists across tests in the same pytest run. Each test
therefore uses a UNIQUE agent name so sibling tests' rows can't leak in.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Conversation, InboundQueueEntry, Message, Project

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _project_id(app, auth_headers) -> str:
    resp = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    assert resp.status_code == 200
    return resp.json()["project_id"]


async def _add_run(project_id: str, *, run_id: str, agent: str, session_id: str) -> None:
    from hub.db.models import Run

    async with async_session_factory() as session:
        session.add(
            Conversation(
                id=session_id,
                project_id=project_id,
                agent=agent,
                provider_session_id=session_id,
                lifecycle="open",
            )
        )
        session.add(
            Run(
                id=run_id,
                project_id=project_id,
                agent=agent,
                session_id=session_id,
                conversation_id=session_id,
                status="completed",
                started_at=datetime.now(timezone.utc),
                turn_depth=0,
            )
        )
        await session.commit()


async def _add_queue_entry(
    project_id: str,
    *,
    entry_id: str,
    agent: str,
    origin_type: str,
    content: str,
    origin_agent: str | None = None,
    hop_depth: int = 0,
    run_id: str | None = None,
    conversation_id: str | None = None,
    timestamp: datetime | None = None,
) -> None:
    async with async_session_factory() as session:
        if run_id:
            from hub.db.models import Run

            run = await session.get(Run, run_id)
            conversation_id = run.conversation_id
        elif conversation_id is None:
            conversation_id = f"conv-{agent}"
        if await get_conversation_by_id(session, conversation_id) is None:
            session.add(
                Conversation(
                    id=conversation_id,
                    project_id=project_id,
                    agent=agent,
                    lifecycle="open",
                )
            )
        session.add(
            InboundQueueEntry(
                id=entry_id,
                project_id=project_id,
                agent=agent,
                origin_type=origin_type,
                origin_agent=origin_agent,
                content=content,
                arrived_at=timestamp or datetime.now(timezone.utc),
                hop_depth=hop_depth,
                state="delivered" if run_id else "queued",
                delivered_in_run_id=run_id,
                delivered_at=(timestamp or datetime.now(timezone.utc)) if run_id else None,
                conversation_id=conversation_id,
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
    async with async_session_factory() as session:
        if await get_conversation_by_id(session, session_id) is None:
            session.add(
                Conversation(
                    id=session_id,
                    project_id=project_id,
                    agent=agent,
                    provider_session_id=session_id,
                    lifecycle="open",
                )
            )
        session.add(
            AgentOutput(
                id=out_id,
                project_id=project_id,
                agent=agent,
                content=content,
                session_id=session_id,
                conversation_id=session_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _add_outbound_message(
    project_id: str,
    *,
    msg_id: str,
    sender: str,
    recipient: str,
    content: str,
    session_id: str | None,
    timestamp: datetime | None = None,
) -> None:
    async with async_session_factory() as session:
        if session_id and await get_conversation_by_id(session, session_id) is None:
            session.add(
                Conversation(
                    id=session_id,
                    project_id=project_id,
                    agent=sender,
                    provider_session_id=session_id,
                    lifecycle="open",
                )
            )
        session.add(
            Message(
                id=msg_id,
                project_id=project_id,
                sender=sender,
                recipient=recipient,
                content=content,
                type="message",
                session_id=session_id,
                conversation_id=session_id,
                timestamp=timestamp or datetime.now(timezone.utc),
            )
        )
        await session.commit()


def _by_id(entries: list[dict], entry_id: str) -> dict:
    return next(e for e in entries if e["id"] == entry_id)


# ---------------------------------------------------------------------------
# Recorded association, not inferred
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delivered_operator_input_placed_by_its_run(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t1"
    await _add_run(project_id, run_id="run-t1", agent=agent, session_id="sess-A")
    await _add_queue_entry(
        project_id,
        entry_id="entry-t1",
        agent=agent,
        origin_type="operator",
        content="hello",
        run_id="run-t1",
    )
    await _add_output(project_id, out_id="o-t1", agent=agent, content="reply", session_id="sess-A")

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-A", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    entries = data["entries"]
    op = _by_id(entries, "entry-t1")
    assert op["kind"] == "operator_input"
    assert op["delivery_state"] == "delivered"
    out = _by_id(entries, "o-t1")
    assert out["kind"] == "agent_output"


@pytest.mark.asyncio
async def test_untagged_entry_from_a_different_session_is_never_inferred_in(app, auth_headers):
    """An entry delivered into a DIFFERENT session's run must never leak into this
    session, no matter how close its timestamp is (no timestamp-window fallback)."""
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t2"
    now = datetime.now(timezone.utc)
    await _add_run(project_id, run_id="run-prev", agent=agent, session_id="sess-prev")
    await _add_queue_entry(
        project_id,
        entry_id="entry-prev",
        agent=agent,
        origin_type="operator",
        content="belongs to prev session",
        run_id="run-prev",
        timestamp=now - timedelta(seconds=1),
    )
    await _add_output(
        project_id,
        out_id="o-curr",
        agent=agent,
        content="current",
        session_id="sess-curr",
        timestamp=now,
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-curr", headers=auth_headers
    )
    assert resp.status_code == 200
    ids = [e["id"] for e in resp.json()["entries"]]
    assert "entry-prev" not in ids
    assert "o-curr" in ids


@pytest.mark.asyncio
async def test_concurrent_sessions_do_not_cross_contaminate(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t3"
    await _add_run(project_id, run_id="run-a", agent=agent, session_id="sess-a")
    await _add_run(project_id, run_id="run-b", agent=agent, session_id="sess-b")
    await _add_queue_entry(
        project_id,
        entry_id="entry-a",
        agent=agent,
        origin_type="operator",
        content="a",
        run_id="run-a",
    )
    await _add_queue_entry(
        project_id,
        entry_id="entry-b",
        agent=agent,
        origin_type="operator",
        content="b",
        run_id="run-b",
    )
    await _add_output(project_id, out_id="o-a", agent=agent, content="a-out", session_id="sess-a")
    await _add_output(project_id, out_id="o-b", agent=agent, content="b-out", session_id="sess-b")

    resp_a = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-a", headers=auth_headers
    )
    resp_b = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-b", headers=auth_headers
    )
    ids_a = {e["id"] for e in resp_a.json()["entries"] if e["delivery_state"] == "delivered"}
    ids_b = {e["id"] for e in resp_b.json()["entries"] if e["delivery_state"] == "delivered"}
    assert ids_a == {"entry-a", "o-a"}
    assert ids_b == {"entry-b", "o-b"}


# ---------------------------------------------------------------------------
# Peer traffic in both directions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inbound_peer_message_tinted_with_sender(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t4"
    await _add_run(project_id, run_id="run-t4", agent=agent, session_id="sess-t4")
    await _add_queue_entry(
        project_id,
        entry_id="entry-t4",
        agent=agent,
        origin_type="agent",
        origin_agent="sender_agent",
        content="hi from sender_agent",
        run_id="run-t4",
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-t4", headers=auth_headers
    )
    entry = _by_id(resp.json()["entries"], "entry-t4")
    assert entry["kind"] == "inbound_peer"
    assert entry["participant"] == "sender_agent"
    assert entry["delivery_state"] == "delivered"


@pytest.mark.asyncio
async def test_outbound_peer_message_placed_by_its_own_session_id(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t5"
    await _add_outbound_message(
        project_id,
        msg_id="msg-t5",
        sender=agent,
        recipient="other_agent",
        content="delegating to other_agent",
        session_id="sess-t5",
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-t5", headers=auth_headers
    )
    entry = _by_id(resp.json()["entries"], "msg-t5")
    assert entry["kind"] == "outbound_peer"
    assert entry["participant"] == "other_agent"

    # And it must NOT appear under an unrelated session for the same agent.
    other_resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-other", headers=auth_headers
    )
    assert other_resp.status_code == 404


# ---------------------------------------------------------------------------
# Undelivered entries and hop-budget suspension
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_queued_entry_appears_in_its_conversation(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t6"
    await _add_queue_entry(
        project_id,
        entry_id="entry-t6-queued",
        agent=agent,
        origin_type="operator",
        content="not delivered yet",
        conversation_id="sess-anything",
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-anything", headers=auth_headers
    )
    entry = _by_id(resp.json()["entries"], "entry-t6-queued")
    assert entry["delivery_state"] == "queued"
    assert entry["hop_budget_exceeded"] is False


@pytest.mark.asyncio
async def test_queued_agent_origin_entry_over_hop_budget_is_flagged_suspended(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t7"

    async with async_session_factory() as session:
        project = await session.get(Project, project_id)
        hop_budget = project.hop_budget
        await session.commit()

    await _add_queue_entry(
        project_id,
        entry_id="entry-t7-suspended",
        agent=agent,
        origin_type="agent",
        origin_agent="chain_source",
        content="over budget",
        hop_depth=hop_budget + 1,
    )

    resp = await app.get(f"/api/v1/projects/proj-test/agent/{agent}/chat", headers=auth_headers)
    entry = _by_id(resp.json()["entries"], "entry-t7-suspended")
    assert entry["delivery_state"] == "queued"
    assert entry["hop_budget_exceeded"] is True


@pytest.mark.asyncio
async def test_delivered_entries_never_carry_hop_budget_exceeded(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t8"
    await _add_run(project_id, run_id="run-t8", agent=agent, session_id="sess-t8")
    await _add_queue_entry(
        project_id,
        entry_id="entry-t8",
        agent=agent,
        origin_type="operator",
        content="delivered",
        run_id="run-t8",
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-t8", headers=auth_headers
    )
    entry = _by_id(resp.json()["entries"], "entry-t8")
    assert entry["hop_budget_exceeded"] is None


# ---------------------------------------------------------------------------
# Structural invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_session_returns_empty_entries(app, auth_headers):
    agent = "agent_t9"
    project_id = await _project_id(app, auth_headers)
    async with async_session_factory() as session:
        session.add(
            Conversation(
                id="sess-empty",
                project_id=project_id,
                agent=agent,
                provider_session_id=None,
                lifecycle="open",
            )
        )
        await session.commit()
    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-empty", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["conversation_id"] == "sess-empty"
    assert data["session_id"] is None
    assert data["agent"] == agent
    assert data["entries"] == []


@pytest.mark.asyncio
async def test_entries_sorted_by_timestamp_with_queue_appended_last(app, auth_headers):
    project_id = await _project_id(app, auth_headers)
    agent = "agent_t10"
    now = datetime.now(timezone.utc)
    await _add_run(project_id, run_id="run-t10", agent=agent, session_id="sess-t10")
    await _add_queue_entry(
        project_id,
        entry_id="entry-t10-1",
        agent=agent,
        origin_type="operator",
        content="first",
        run_id="run-t10",
        timestamp=now - timedelta(seconds=10),
    )
    await _add_output(
        project_id,
        out_id="o-t10-1",
        agent=agent,
        content="second",
        session_id="sess-t10",
        timestamp=now - timedelta(seconds=9),
    )
    await _add_outbound_message(
        project_id,
        msg_id="msg-t10-1",
        sender=agent,
        recipient="peer",
        content="third",
        session_id="sess-t10",
        timestamp=now - timedelta(seconds=8),
    )
    await _add_queue_entry(
        project_id,
        entry_id="entry-t10-pending",
        agent=agent,
        origin_type="operator",
        content="pending",
        conversation_id="sess-t10",
    )

    resp = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/chat/sess-t10", headers=auth_headers
    )
    entries = resp.json()["entries"]
    delivered = [e for e in entries if e["delivery_state"] == "delivered"]
    ts = [e["timestamp"] for e in delivered]
    assert ts == sorted(ts)
    assert [e["id"] for e in delivered] == ["entry-t10-1", "o-t10-1", "msg-t10-1"]
    # Queued entries are appended after every delivered one.
    assert entries[-1]["id"] == "entry-t10-pending"
    assert entries[-1]["delivery_state"] == "queued"
