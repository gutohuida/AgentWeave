"""Where an agent's message lands, exercised through the route agents actually use.

`test_archived_send_refusal.py` covers this over `/api/v1/projects/{id}/messages` — the operator
route. `mcp_server.send_message` posts to `/api/v1/agent-actions/messages`, which has its own
schema, and that difference is what let `conversation_id` be accepted on one and rejected on the
other while every test passed.

The behaviour these lock down is the one an agent relies on most: a sending agent usually has no
idea what conversation ids the recipient owns, so omitting the id has to route somewhere sensible
rather than fail.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Message, Run

CONTENT = "Please pick this thread back up."


async def _active_run(run_id: str, agent: str) -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _sync_agents(app, auth_headers, *names: str) -> None:
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _conversation_of(message_id: str) -> str | None:
    """Which conversation the recipient's queued entry landed in."""
    async with async_session_factory() as session:
        message = await session.get(Message, message_id)
        entry = (
            await session.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.message_id == message.id)
            )
        ).scalars().first()
        return entry.conversation_id if entry else None


async def _open_conversation(agent: str, conversation_id: str) -> None:
    async with async_session_factory() as session:
        session.add(
            Conversation(
                id=conversation_id,
                project_id="proj-test",
                agent=agent,
                lifecycle="open",
                origin="operator",
                title=conversation_id,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_send_with_no_conversation_id_is_accepted(app, auth_headers) -> None:
    """The regression: `mcp_server.send_message` puts `conversation_id` in every body it builds,
    null included, and `extra: "forbid"` rejects a forbidden key whatever its value. Every
    agent-to-agent message failed 422 — not only the ones naming a conversation."""
    await _sync_agents(app, auth_headers, "codex-2")
    headers = await _active_run("run-route-1", "codex-1")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={
            "recipient": "codex-2",
            "subject": "Handover",
            "content": CONTENT,
            "type": "message",
            "task_id": None,
            "conversation_id": None,
        },
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_no_conversation_id_lands_in_the_recipients_newest_open_one(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "codex-2")
    await _open_conversation("codex-2", "conv-older")
    await _open_conversation("codex-2", "conv-newest")
    headers = await _active_run("run-route-2", "codex-1")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT, "conversation_id": None},
    )
    assert response.status_code == 201, response.text
    assert await _conversation_of(response.json()["id"]) == "conv-newest"


@pytest.mark.asyncio
async def test_no_conversation_id_opens_one_when_the_recipient_has_none(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "codex-2")
    headers = await _active_run("run-route-3", "codex-1")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    assert response.status_code == 201, response.text

    landed = await _conversation_of(response.json()["id"])
    assert landed is not None
    async with async_session_factory() as session:
        conversation = await session.get(Conversation, landed)
        assert conversation.agent == "codex-2"
        assert conversation.lifecycle == "open"
        assert conversation.origin == "peer"


@pytest.mark.asyncio
async def test_a_named_conversation_is_honoured_over_the_newest(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "codex-2")
    await _open_conversation("codex-2", "conv-target")
    await _open_conversation("codex-2", "conv-newest")
    headers = await _active_run("run-route-4", "codex-1")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT, "conversation_id": "conv-target"},
    )
    assert response.status_code == 201, response.text
    assert await _conversation_of(response.json()["id"]) == "conv-target"


@pytest.mark.asyncio
async def test_a_conversation_belonging_to_someone_else_is_not_found(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "codex-2", "haiku-1")
    await _open_conversation("haiku-1", "conv-not-yours")
    headers = await _active_run("run-route-5", "codex-1")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT, "conversation_id": "conv-not-yours"},
    )
    assert response.status_code == 404
    assert "conv-not-yours" in response.json()["detail"]


@pytest.mark.asyncio
async def test_an_archived_conversation_is_refused_with_all_three_parts(app, auth_headers) -> None:
    """Same refusal the operator route gives, over the route an agent actually reaches."""
    await _sync_agents(app, auth_headers, "codex-2")
    await _open_conversation("codex-2", "conv-archived")
    async with async_session_factory() as session:
        conversation = await session.get(Conversation, "conv-archived")
        conversation.lifecycle = "archived"
        await session.commit()
    headers = await _active_run("run-route-6", "codex-1")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT, "conversation_id": "conv-archived"},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "archived" in detail                      # the cause
    assert "omitting conversation_id" in detail      # the way out
    assert CONTENT in detail                         # the agent's own words back
