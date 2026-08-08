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


async def _active_run(
    run_id: str, agent: str, conversation_id: str | None = None
) -> dict[str, str]:
    """A running turn the sender can act from.

    `conversation_id` is what the send binds on: a real turn always has one, and leaving it None
    models the senderless case (the Hub, the scheduler) that keys on identity instead.
    """
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                conversation_id=conversation_id,
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
async def test_no_conversation_id_does_not_land_on_whatever_was_touched_last(
    app, auth_headers
) -> None:
    """Delivery is bound to the sender's conversation, not to the recipient's recency.

    This asserted the opposite until 2026-08-08: a send with no id went to the recipient's newest
    open thread. That is what scattered one exchange across three unrelated threads — the
    recipient's ordering has nothing to do with which line of work a message belongs to.
    """
    await _sync_agents(app, auth_headers, "codex-2")
    await _open_conversation("codex-2", "conv-older")
    await _open_conversation("codex-2", "conv-newest")
    headers = await _active_run("run-route-2", "codex-1", conversation_id="conv-sender-a")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT, "conversation_id": None},
    )
    assert response.status_code == 201, response.text
    landed = await _conversation_of(response.json()["id"])
    assert landed not in {"conv-older", "conv-newest"}
    async with async_session_factory() as session:
        conversation = await session.get(Conversation, landed)
        assert conversation.bound_sender_conversation_id == "conv-sender-a"
        assert conversation.origin == "peer"


@pytest.mark.asyncio
async def test_one_senders_separate_conversations_reach_separate_threads(app, auth_headers) -> None:
    """The conversation-level precision the participation graph needs: two lines of work from the
    same sender are two exchanges, and collapsing them into one recipient thread loses that."""
    await _sync_agents(app, auth_headers, "codex-2")
    first = await _active_run("run-split-1", "codex-1", conversation_id="conv-work-a")
    second = await _active_run("run-split-2", "codex-1", conversation_id="conv-work-b")

    a = await app.post(
        "/api/v1/agent-actions/messages",
        headers=first,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    b = await app.post(
        "/api/v1/agent-actions/messages",
        headers=second,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    assert a.status_code == 201 and b.status_code == 201
    assert await _conversation_of(a.json()["id"]) != await _conversation_of(b.json()["id"])


@pytest.mark.asyncio
async def test_three_messages_on_one_line_of_work_land_in_one_thread(app, auth_headers) -> None:
    """The observed defect, reproduced: three `codex-1 → haiku-1` messages — one exchange by any
    human reading — were delivered into three unrelated `haiku-1` threads."""
    await _sync_agents(app, auth_headers, "haiku-1")
    # Threads the recipient touches between sends, which is what recency routing followed.
    await _open_conversation("haiku-1", "conv-noise-1")

    landed = []
    for index in range(3):
        headers = await _active_run(f"run-three-{index}", "codex-1", conversation_id="conv-one")
        response = await app.post(
            "/api/v1/agent-actions/messages",
            headers=headers,
            json={"recipient": "haiku-1", "content": CONTENT},
        )
        assert response.status_code == 201, response.text
        landed.append(await _conversation_of(response.json()["id"]))
        await _open_conversation("haiku-1", f"conv-noise-newer-{index}")

    assert len(set(landed)) == 1, landed
    assert "conv-noise-1" not in landed


@pytest.mark.asyncio
async def test_senderless_traffic_gets_one_stable_thread_per_sender(app, auth_headers) -> None:
    """The Hub and the scheduler have no source conversation. Keying on identity is what keeps
    recency routing from surviving in that corner."""
    await _sync_agents(app, auth_headers, "codex-2")
    first = await _active_run("run-sysless-1", "codex-1")
    second = await _active_run("run-sysless-2", "codex-1")

    a = await app.post(
        "/api/v1/agent-actions/messages",
        headers=first,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    await _open_conversation("codex-2", "conv-touched-since")
    b = await app.post(
        "/api/v1/agent-actions/messages",
        headers=second,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    assert a.status_code == 201 and b.status_code == 201
    landed = await _conversation_of(a.json()["id"])
    assert landed == await _conversation_of(b.json()["id"])
    assert landed != "conv-touched-since"
    async with async_session_factory() as session:
        conversation = await session.get(Conversation, landed)
        assert conversation.bound_sender_agent == "codex-1"
        assert conversation.bound_sender_conversation_id is None


@pytest.mark.asyncio
async def test_a_binding_the_operator_archived_gets_a_successor_not_a_refusal(
    app, auth_headers
) -> None:
    """The archive split. A sender that *named* an archived conversation is refused, because it
    chose one. A binding the operator archived is not the sender's doing, so it gets a successor
    bound to the same sender rather than an error about a decision it did not make."""
    await _sync_agents(app, auth_headers, "codex-2")
    headers = await _active_run("run-arch-1", "codex-1", conversation_id="conv-bound")
    first = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    assert first.status_code == 201
    original = await _conversation_of(first.json()["id"])

    async with async_session_factory() as session:
        conversation = await session.get(Conversation, original)
        conversation.lifecycle = "archived"
        await session.commit()

    headers = await _active_run("run-arch-2", "codex-1", conversation_id="conv-bound")
    second = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    assert second.status_code == 201, second.text
    successor = await _conversation_of(second.json()["id"])
    assert successor != original
    async with async_session_factory() as session:
        conversation = await session.get(Conversation, successor)
        assert conversation.bound_sender_conversation_id == "conv-bound"
        assert conversation.origin == "peer"
        assert conversation.lifecycle == "open"


@pytest.mark.asyncio
async def test_historical_conversations_are_never_resolved_by_a_binding(app, auth_headers) -> None:
    """No backfill: existing threads carry no binding, so nothing claims them. Backfilling would
    have meant guessing which of three conversations an `ack` really belonged to."""
    await _sync_agents(app, auth_headers, "codex-2")
    await _open_conversation("codex-2", "conv-historical")
    headers = await _active_run("run-hist-1", "codex-1", conversation_id="conv-historical")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "codex-2", "content": CONTENT},
    )
    assert response.status_code == 201
    assert await _conversation_of(response.json()["id"]) != "conv-historical"


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
