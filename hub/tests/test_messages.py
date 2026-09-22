"""Tests for message endpoints."""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import EventLog


async def _sync_agent(app, auth_headers, *agent_names):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {} for name in agent_names}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _queued(app, auth_headers, agent):
    resp = await app.get(f"/api/v1/projects/proj-test/queue/{agent}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _event_types(project_id="proj-test"):
    async with async_session_factory() as session:
        rows = await session.execute(
            select(EventLog.event_type).where(EventLog.project_id == project_id)
        )
        return [row[0] for row in rows]


@pytest.mark.asyncio
async def test_create_and_list_message(app, auth_headers):
    await _sync_agent(app, auth_headers, "kimi")

    # Create a message
    resp = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "to": "kimi",
            "subject": "Hello",
            "content": "Hi there",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("msg-")
    assert data["from"] == "operator"
    assert data["to"] == "kimi"

    # List messages for kimi
    resp2 = await app.get("/api/v1/projects/proj-test/messages?agent=kimi", headers=auth_headers)
    assert resp2.status_code == 200
    messages = resp2.json()
    assert len(messages) >= 1
    assert messages[0]["to"] == "kimi"


@pytest.mark.asyncio
async def test_mark_message_read(app, auth_headers):
    await _sync_agent(app, auth_headers, "kimi")

    # Create
    resp = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"to": "kimi", "content": "Test"},
        headers=auth_headers,
    )
    msg_id = resp.json()["id"]

    # Mark read
    resp2 = await app.patch(
        f"/api/v1/projects/proj-test/messages/{msg_id}/read", headers=auth_headers
    )
    assert resp2.status_code == 200

    # Should no longer appear in unread list
    resp3 = await app.get("/api/v1/projects/proj-test/messages?agent=kimi", headers=auth_headers)
    ids = [m["id"] for m in resp3.json()]
    assert msg_id not in ids


# The four refusals below send no `from`: with `"from": "claude"` and no run they would be refused
# for the sender (F261) and pass whatever the field under test did.


@pytest.mark.asyncio
async def test_create_message_rejects_client_supplied_id(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"to": "kimi", "content": "Hi", "id": "msg-custom-id"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "id" in resp.text


@pytest.mark.asyncio
async def test_create_message_rejects_client_supplied_timestamp(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"to": "kimi", "content": "Hi", "timestamp": "2026-01-01T00:00:00+00:00"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "timestamp" in resp.text


@pytest.mark.asyncio
async def test_create_message_rejects_overlong_subject(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"to": "kimi", "subject": "x" * 257, "content": "Hi"},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "subject" in resp.text


@pytest.mark.asyncio
async def test_create_message_rejects_overlong_content(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"to": "kimi", "content": "x" * 10001},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "content" in resp.text


# F258 + F395 — an operator's message starts a chain; it does not arrive spent.


@pytest.mark.asyncio
async def test_an_operator_message_is_queued_at_depth_zero_as_the_operators(app, auth_headers):
    """It used to be born at `hop_budget + 1`, labelled `origin_type="agent"`, and held as
    "hop budget exhausted" until someone released it by hand."""
    await _sync_agent(app, auth_headers, "bravo")

    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"to": "bravo", "content": "Look at the build"},
        headers=auth_headers,
    )
    assert sent.status_code == 201, sent.text

    [entry] = await _queued(app, auth_headers, "bravo")
    assert entry["hop_depth"] == 0
    assert entry["origin_type"] == "operator"
    assert entry["origin_agent"] is None
    assert "queue_chain_suspended" not in await _event_types()
    status = await app.get("/api/v1/projects/proj-test/queue/bravo/status", headers=auth_headers)
    assert status.json()["waiting_reason"] != "hop budget exhausted"


@pytest.mark.asyncio
async def test_an_operator_message_opens_an_operator_conversation(app, auth_headers):
    await _sync_agent(app, auth_headers, "bravo")

    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"from": "operator", "to": "bravo", "content": "Look at the build"},
        headers=auth_headers,
    )
    assert sent.status_code == 201, sent.text

    listed = await app.get(
        "/api/v1/projects/proj-test/agent/bravo/conversations", headers=auth_headers
    )
    [conversation] = listed.json()
    assert conversation["origin"] == "operator"


@pytest.mark.asyncio
async def test_an_agent_send_with_its_run_keeps_the_agents_origin_and_depth(
    app, auth_headers, start_run
):
    """The other half: a `run_id` still makes the send the agent's, one hop past its run."""
    await _sync_agent(app, auth_headers, "alpha", "bravo")

    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "alpha",
            "run_id": await start_run("alpha", turn_depth=2),
            "to": "bravo",
            "content": "Your turn",
        },
        headers=auth_headers,
    )
    assert sent.status_code == 201, sent.text

    [entry] = await _queued(app, auth_headers, "bravo")
    assert (entry["origin_type"], entry["origin_agent"], entry["hop_depth"]) == (
        "agent",
        "alpha",
        3,
    )


# F261 — without a run, `from` cannot name an agent, registered or not.


@pytest.mark.asyncio
async def test_a_sender_without_a_run_must_be_the_operator(app, auth_headers):
    await _sync_agent(app, auth_headers, "bravo")

    refused = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"from": "ghost-140008", "to": "bravo", "content": "hello"},
        headers=auth_headers,
    )
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert "ghost-140008" in detail and "run_id" in detail and "send_message" in detail
    assert await _queued(app, auth_headers, "bravo") == []

    roster = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert "ghost-140008" not in {agent["name"] for agent in roster.json()}


@pytest.mark.asyncio
async def test_the_operators_mail_does_not_list_the_operator_as_an_agent(app, auth_headers):
    """The roster falls back to message senders when no session config names agents; the
    operator sends mail and is not an agent."""
    await _sync_agent(app, auth_headers, "bravo")
    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"to": "bravo", "content": "hello"},
        headers=auth_headers,
    )
    assert sent.status_code == 201, sent.text

    roster = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert "operator" not in {agent["name"] for agent in roster.json()}
    status = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    assert "operator" not in status.json()["agents_active"]


# F262, F263 — a filter the route cannot honour is refused, not dropped.


@pytest.mark.asyncio
@pytest.mark.parametrize("conversation", ["conv-cfb1ab8dd65b", "zzz", "alpha:", ":bravo"])
async def test_a_conversation_that_is_not_an_agent_pair_is_refused(app, auth_headers, conversation):
    resp = await app.get(
        "/api/v1/projects/proj-test/messages",
        params={"history": "true", "conversation": conversation},
        headers=auth_headers,
    )
    assert resp.status_code == 422
    assert "<agent>:<agent>" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_an_agent_pair_filters_to_their_messages(app, auth_headers, start_run):
    await _sync_agent(app, auth_headers, "alpha", "bravo", "charlie")
    for sender, recipient in [("alpha", "bravo"), ("bravo", "alpha"), ("alpha", "charlie")]:
        sent = await app.post(
            "/api/v1/projects/proj-test/messages",
            json={
                "from": sender,
                "run_id": await start_run(sender),
                "to": recipient,
                "content": f"{sender} to {recipient}",
            },
            headers=auth_headers,
        )
        assert sent.status_code == 201, sent.text

    resp = await app.get(
        "/api/v1/projects/proj-test/messages",
        params={"history": "true", "conversation": "alpha:bravo"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert sorted(m["content"] for m in resp.json()) == ["alpha to bravo", "bravo to alpha"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", ["DESC", "descending", "newest", "()"])
async def test_a_sort_other_than_asc_or_desc_is_refused(app, auth_headers, sort):
    resp = await app.get(
        "/api/v1/projects/proj-test/messages",
        params={"history": "true", "sort": sort},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_desc_answers_newest_first(app, auth_headers):
    await _sync_agent(app, auth_headers, "bravo")
    for content in ["first", "second"]:
        sent = await app.post(
            "/api/v1/projects/proj-test/messages",
            json={"to": "bravo", "content": content},
            headers=auth_headers,
        )
        assert sent.status_code == 201, sent.text

    params = {"history": "true", "sort": "desc"}
    resp = await app.get("/api/v1/projects/proj-test/messages", params=params, headers=auth_headers)
    assert [m["content"] for m in resp.json()] == ["second", "first"]
