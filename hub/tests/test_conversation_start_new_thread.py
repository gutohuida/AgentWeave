"""Starting a thread deliberately (design.md D4, conversations-continue phase 4).

`start_new_thread` bypasses both the forward (`peer_bound_conversation`) and reverse
(`reply_bound_conversation`) lookups on purpose, minting a fresh recipient conversation even when
a binding already exists. No new state is needed to make it the active thread afterwards — the
forward lookup already takes the *newest* open binding, so the new thread simply wins the next
ordinary send (task 4.4).
"""

import pytest
from sqlalchemy import select

from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Message

CONTENT = "Starting fresh on this one."


async def _active_run(run_id: str, agent: str, conversation_id: str | None = None) -> dict:
    from hub.agent_auth import hash_run_token
    from hub.db.models import Run

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
    async with async_session_factory() as session:
        message = await session.get(Message, message_id)
        entry = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.message_id == message.id)
                )
            )
            .scalars()
            .first()
        )
        return entry.conversation_id if entry else None


async def _open_conversation(
    agent: str,
    conversation_id: str,
    *,
    origin: str = "operator",
    bound_sender_conversation_id: str | None = None,
) -> None:
    async with async_session_factory() as session:
        session.add(
            Conversation(
                id=conversation_id,
                project_id="proj-test",
                agent=agent,
                lifecycle="open",
                origin=origin,
                title=conversation_id,
                bound_sender_conversation_id=bound_sender_conversation_id,
                lineage_id=conversation_id,
            )
        )
        await session.commit()


async def _send(app, headers, recipient: str, **extra):
    payload = {"recipient": recipient, "content": CONTENT, **extra}
    return await app.post("/api/v1/agent-actions/messages", headers=headers, json=payload)


@pytest.mark.asyncio
async def test_explicit_request_creates_a_thread_even_when_a_binding_exists(
    app, auth_headers
) -> None:
    """A already has a binding to a `haiku-1` thread. Asking for `start_new_thread` mints a
    second one instead of reusing it — the forward lookup would otherwise have found it."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-a1", origin="operator")
    a_headers = await _active_run("run-snt-1", "codex-1", conversation_id="conv-a1")

    first = await _send(app, a_headers, "haiku-1")
    assert first.status_code == 201, first.text
    existing_thread = await _conversation_of(first.json()["id"])
    assert existing_thread is not None

    second = await _send(app, a_headers, "haiku-1", start_new_thread=True)
    assert second.status_code == 201, second.text
    new_thread = await _conversation_of(second.json()["id"])
    assert new_thread is not None
    assert new_thread != existing_thread

    async with async_session_factory() as session:
        conversation = await get_conversation_by_id(session, new_thread)
        assert conversation.bound_sender_conversation_id == "conv-a1"


@pytest.mark.asyncio
async def test_the_new_thread_becomes_the_bound_one_for_later_messages(app, auth_headers) -> None:
    """After a deliberate branch, an ordinary follow-up (no flag) resolves to the *new* thread,
    not the one that existed before it — the newest binding wins the forward lookup, so no extra
    state was needed to make the branch the active one (task 4.4)."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-a1", origin="operator")
    a_headers = await _active_run("run-snt-2", "codex-1", conversation_id="conv-a1")

    first = await _send(app, a_headers, "haiku-1")
    old_thread = await _conversation_of(first.json()["id"])

    branched = await _send(app, a_headers, "haiku-1", start_new_thread=True)
    new_thread = await _conversation_of(branched.json()["id"])
    assert new_thread != old_thread

    follow_up = await _send(app, a_headers, "haiku-1")
    assert follow_up.status_code == 201, follow_up.text
    assert await _conversation_of(follow_up.json()["id"]) == new_thread


@pytest.mark.asyncio
async def test_omitting_the_flag_continues_as_today(app, auth_headers) -> None:
    """`start_new_thread` defaults to False, and an ordinary send with the field left out behaves
    exactly like the forward-lookup binding it always has."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-a1", origin="operator")
    a_headers = await _active_run("run-snt-3", "codex-1", conversation_id="conv-a1")

    first = await _send(app, a_headers, "haiku-1")
    thread = await _conversation_of(first.json()["id"])

    second = await _send(app, a_headers, "haiku-1")
    assert await _conversation_of(second.json()["id"]) == thread


@pytest.mark.asyncio
async def test_naming_a_conversation_and_asking_for_a_new_thread_is_refused(
    app, auth_headers
) -> None:
    """Naming a thread and asking for a new one are contradictory (D4) — refused with nothing
    created and nothing delivered, mirroring the archived-conversation refusal's shape."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-a1", origin="operator")
    await _open_conversation(
        "haiku-1", "conv-b1", origin="peer", bound_sender_conversation_id="conv-a1"
    )
    a_headers = await _active_run("run-snt-4", "codex-1", conversation_id="conv-a1")

    async with async_session_factory() as session:
        before_messages = (await session.execute(select(Message))).scalars().all()
        before_ids = {m.id for m in before_messages}
        before_conversations = (await session.execute(select(Conversation))).scalars().all()
        before_conv_ids = {c.id for c in before_conversations}

    response = await _send(
        app, a_headers, "haiku-1", conversation_id="conv-b1", start_new_thread=True
    )
    assert response.status_code == 409, response.text
    assert CONTENT in response.json()["detail"]

    async with async_session_factory() as session:
        after_messages = (await session.execute(select(Message))).scalars().all()
        after_ids = {m.id for m in after_messages}
        after_conversations = (await session.execute(select(Conversation))).scalars().all()
        after_conv_ids = {c.id for c in after_conversations}
    assert after_ids == before_ids
    assert after_conv_ids == before_conv_ids
