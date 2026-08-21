"""A reply continues the conversation it is replying to (design.md D1/D2, conversations-continue
phase 3).

`test_agent_message_routing.py` locks down the forward lookup — a sender's own line of work always
reaches the same recipient thread. This covers the direction that lookup cannot answer: a reply,
sent with no `conversation_id`, from a thread the recipient already opened for the sender. Before
this phase every reply of that shape minted a fresh thread, which is why three messages that read as
one exchange landed in three unrelated conversations.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Message, Run

CONTENT = "Please pick this thread back up."


async def _active_run(
    run_id: str, agent: str, conversation_id: str | None = None
) -> dict[str, str]:
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
    lineage_id: str | None = None,
    lifecycle: str = "open",
) -> None:
    async with async_session_factory() as session:
        session.add(
            Conversation(
                id=conversation_id,
                project_id="proj-test",
                agent=agent,
                lifecycle=lifecycle,
                origin=origin,
                title=conversation_id,
                bound_sender_conversation_id=bound_sender_conversation_id,
                lineage_id=lineage_id or conversation_id,
            )
        )
        await session.commit()


async def _send(app, headers, recipient: str, content: str = CONTENT):
    return await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": recipient, "content": content},
    )


@pytest.mark.asyncio
async def test_a_reply_reaches_the_thread_it_answers(app, auth_headers) -> None:
    """B, replying from `convB1` (already bound to A's `conv-a1`), reaches `conv-a1` — the
    conversation the forward lookup on this send cannot find, because the binding it wrote points
    the other way."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-a1", origin="operator")
    await _open_conversation(
        "haiku-1", "conv-b1", origin="peer", bound_sender_conversation_id="conv-a1"
    )
    headers = await _active_run("run-reply-1", "haiku-1", conversation_id="conv-b1")

    response = await _send(app, headers, "codex-1")
    assert response.status_code == 201, response.text
    assert await _conversation_of(response.json()["id"]) == "conv-a1"


@pytest.mark.asyncio
async def test_an_exchange_settles_into_exactly_two_conversations(app, auth_headers) -> None:
    """A -> B mints `conv-b`. B -> A resolves back to `conv-a` via the reverse rule. A -> B again
    resolves forward to `conv-b`. Three sends, two conversations total."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-a", origin="operator")
    a_to_b = await _active_run("run-exch-1", "codex-1", conversation_id="conv-a")

    first = await _send(app, a_to_b, "haiku-1")
    assert first.status_code == 201, first.text
    conv_b = await _conversation_of(first.json()["id"])
    assert conv_b is not None and conv_b != "conv-a"

    b_to_a = await _active_run("run-exch-2", "haiku-1", conversation_id=conv_b)
    second = await _send(app, b_to_a, "codex-1")
    assert second.status_code == 201, second.text
    assert await _conversation_of(second.json()["id"]) == "conv-a"

    third = await _send(app, a_to_b, "haiku-1")
    assert third.status_code == 201, third.text
    assert await _conversation_of(third.json()["id"]) == conv_b


@pytest.mark.asyncio
async def test_a_message_to_a_third_agent_does_not_continue_an_unrelated_thread(
    app, auth_headers
) -> None:
    """B's thread is bound back to A. A message from that same thread to C — not A — must not
    resolve onto A's conversation just because B's binding names *someone*."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1", "solo")
    await _open_conversation(
        "haiku-1", "conv-b1", origin="peer", bound_sender_conversation_id="conv-a1"
    )
    headers = await _active_run("run-reply-3rd", "haiku-1", conversation_id="conv-b1")

    response = await _send(app, headers, "solo")
    assert response.status_code == 201, response.text
    landed = await _conversation_of(response.json()["id"])
    assert landed not in {"conv-a1", "conv-b1"}
    async with async_session_factory() as session:
        conversation = await get_conversation_by_id(session, landed)
        assert conversation.agent == "solo"
        assert conversation.bound_sender_conversation_id == "conv-b1"


@pytest.mark.asyncio
async def test_a_reply_continues_into_an_operator_origin_conversation(app, auth_headers) -> None:
    """A delegation begun in the operator's own thread returns to it (D5): the reply is not
    refused or diverted just because the thread it continues was never `origin: peer`."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-operator-1", origin="operator")
    headers = await _active_run("run-op-origin-1", "codex-1", conversation_id="conv-operator-1")
    delegated = await _send(app, headers, "haiku-1", content="Please look into this.")
    assert delegated.status_code == 201, delegated.text
    conv_haiku = await _conversation_of(delegated.json()["id"])

    reply_headers = await _active_run("run-op-origin-2", "haiku-1", conversation_id=conv_haiku)
    reply = await _send(app, reply_headers, "codex-1", content="Done — here is what I found.")
    assert reply.status_code == 201, reply.text
    assert await _conversation_of(reply.json()["id"]) == "conv-operator-1"

    message_id = reply.json()["id"]
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
        assert entry.origin_agent == "haiku-1"


@pytest.mark.asyncio
async def test_continuation_survives_the_replying_sides_cutover(app, auth_headers) -> None:
    """B's own thread (`conv-b1`, bound back to A's `conv-a1`) is cut over to a successor
    `conv-b2` sharing its lineage. Replying from the successor still resolves to `conv-a1` — the
    reverse lookup follows the *sender's* row, not the sender's original id."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-a1", origin="operator")
    await _open_conversation(
        "haiku-1", "conv-b1", origin="peer", bound_sender_conversation_id="conv-a1"
    )
    async with async_session_factory() as session:
        conversation = await get_conversation_by_id(session, "conv-b1")
        conversation.lifecycle = "archived"
        await session.commit()
    await _open_conversation(
        "haiku-1",
        "conv-b2",
        origin="peer",
        bound_sender_conversation_id="conv-a1",
        lineage_id="conv-b1",
    )

    headers = await _active_run("run-cutover-reply", "haiku-1", conversation_id="conv-b2")
    response = await _send(app, headers, "codex-1")
    assert response.status_code == 201, response.text
    assert await _conversation_of(response.json()["id"]) == "conv-a1"


@pytest.mark.asyncio
async def test_an_archived_line_with_no_open_successor_falls_through_to_minting(
    app, auth_headers
) -> None:
    """The named conversation's whole lineage is archived — no open conversation to resolve to.
    Reverse resolution fails cleanly and delivery falls through to the mint, same as a forward
    miss with no binding at all."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation(
        "haiku-1", "conv-b1", origin="peer", bound_sender_conversation_id="conv-a1"
    )
    # conv-a1 exists but has been cut over with no open successor in its lineage — the whole
    # line of work is archived, unlike the cutover test above where a successor picks it up.
    await _open_conversation("codex-1", "conv-a1", origin="peer", lifecycle="archived")

    headers = await _active_run("run-dead-lineage", "haiku-1", conversation_id="conv-b1")
    response = await _send(app, headers, "codex-1")
    assert response.status_code == 201, response.text
    landed = await _conversation_of(response.json()["id"])
    assert landed != "conv-a1"
    async with async_session_factory() as session:
        conversation = await get_conversation_by_id(session, landed)
        assert conversation.lifecycle == "open"
        assert conversation.bound_sender_conversation_id == "conv-b1"


@pytest.mark.asyncio
async def test_three_messages_alternating_produce_two_conversations_not_three(
    app, auth_headers
) -> None:
    """The measured defect (design.md Context), reproduced directly: A -> B, B -> A, A -> B."""
    await _sync_agents(app, auth_headers, "codex-1", "haiku-1")
    await _open_conversation("codex-1", "conv-alt-a", origin="operator")

    a_to_b_1 = await _active_run("run-alt-1", "codex-1", conversation_id="conv-alt-a")
    first = await _send(app, a_to_b_1, "haiku-1")
    assert first.status_code == 201, first.text
    conv_b = await _conversation_of(first.json()["id"])

    b_to_a = await _active_run("run-alt-2", "haiku-1", conversation_id=conv_b)
    second = await _send(app, b_to_a, "codex-1")
    assert second.status_code == 201, second.text
    conv_a = await _conversation_of(second.json()["id"])
    assert conv_a == "conv-alt-a"

    a_to_b_2 = await _active_run("run-alt-3", "codex-1", conversation_id="conv-alt-a")
    third = await _send(app, a_to_b_2, "haiku-1")
    assert third.status_code == 201, third.text

    landed = {conv_b, conv_a, await _conversation_of(third.json()["id"])}
    assert landed == {conv_b, conv_a}
    assert len(landed) == 2
