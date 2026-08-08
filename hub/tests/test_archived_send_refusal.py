"""An agent sending into an archived conversation is refused, and told how to recover.

The failure carries three parts, and the third is the point: restating the submitted content
means the retry is mechanical rather than a reconstruction from a context the agent may have
already moved past.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Message

CONTENT = "Please re-run the migration against the staging snapshot and report the diff."


async def _sync_agents(app, auth_headers, *names):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _archived_conversation(app, auth_headers, drain_conversation) -> str:
    """A conversation belonging to `recipient`, archived and quiet."""
    await _sync_agents(app, auth_headers, "sender", "recipient")
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "recipient", "message": "First thread"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]
    await drain_conversation(conversation_id)
    archived = await app.post(
        f"/api/v1/projects/proj-test/agent/recipient/conversations/{conversation_id}/archive",
        headers=auth_headers,
    )
    assert archived.status_code == 200, archived.text
    return conversation_id


def _assert_carries_all_three(detail: str, conversation_id: str) -> None:
    assert conversation_id in detail
    assert "archived" in detail.lower()
    assert "new conversation" in detail.lower()
    assert CONTENT in detail


@pytest.mark.asyncio
async def test_the_http_send_is_refused_with_cause_instruction_and_content(
    app, auth_headers, drain_conversation
) -> None:
    conversation_id = await _archived_conversation(app, auth_headers, drain_conversation)

    refused = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "sender",
            "to": "recipient",
            "content": CONTENT,
            "conversation_id": conversation_id,
        },
        headers=auth_headers,
    )

    assert refused.status_code == 409
    _assert_carries_all_three(refused.json()["detail"], conversation_id)


@pytest.mark.asyncio
async def test_nothing_is_written_to_the_archived_conversation(
    app, auth_headers, drain_conversation
) -> None:
    conversation_id = await _archived_conversation(app, auth_headers, drain_conversation)
    async with async_session_factory() as session:
        entries_before = len(
            (
                await session.execute(
                    select(InboundQueueEntry.id).where(
                        InboundQueueEntry.conversation_id == conversation_id
                    )
                )
            )
            .scalars()
            .all()
        )

    await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "sender",
            "to": "recipient",
            "content": CONTENT,
            "conversation_id": conversation_id,
        },
        headers=auth_headers,
    )

    async with async_session_factory() as session:
        entries_after = (
            (
                await session.execute(
                    select(InboundQueueEntry.id).where(
                        InboundQueueEntry.conversation_id == conversation_id
                    )
                )
            )
            .scalars()
            .all()
        )
        messages = (
            (await session.execute(select(Message.id).where(Message.content == CONTENT)))
            .scalars()
            .all()
        )

    assert len(entries_after) == entries_before
    assert messages == [], "the refused message must not exist anywhere"


@pytest.mark.asyncio
async def test_the_message_is_not_silently_rehomed(
    app, auth_headers, drain_conversation
) -> None:
    """The agent decides where its message goes. A refusal that quietly picked another
    conversation would be worse than the stranding it was meant to prevent."""
    conversation_id = await _archived_conversation(app, auth_headers, drain_conversation)

    await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "sender",
            "to": "recipient",
            "content": CONTENT,
            "conversation_id": conversation_id,
        },
        headers=auth_headers,
    )

    listed = await app.get(
        "/api/v1/projects/proj-test/agent/recipient/conversations?lifecycle=all",
        headers=auth_headers,
    )
    assert [row["id"] for row in listed.json()] == [conversation_id]


@pytest.mark.asyncio
async def test_omitting_the_conversation_id_opens_a_new_one(
    app, auth_headers, drain_conversation
) -> None:
    """The recovery the refusal instructs actually works."""
    conversation_id = await _archived_conversation(app, auth_headers, drain_conversation)

    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"from": "sender", "to": "recipient", "content": CONTENT},
        headers=auth_headers,
    )
    assert sent.status_code == 201, sent.text

    listed = await app.get(
        "/api/v1/projects/proj-test/agent/recipient/conversations", headers=auth_headers
    )
    open_ids = [row["id"] for row in listed.json()]
    assert conversation_id not in open_ids
    assert len(open_ids) == 1
    assert listed.json()[0]["origin"] == "peer"


@pytest.mark.asyncio
async def test_an_open_conversation_id_is_honoured(
    app, auth_headers, drain_conversation
) -> None:
    """Targeting is not archive-only: naming an open conversation sends into that one."""
    await _sync_agents(app, auth_headers, "sender", "recipient")
    first = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "recipient", "message": "First thread"},
        headers=auth_headers,
    )
    second = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "recipient", "message": "Second thread"},
        headers=auth_headers,
    )
    target = first.json()["conversation_id"]
    assert target != second.json()["conversation_id"]

    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "sender",
            "to": "recipient",
            "content": CONTENT,
            "conversation_id": target,
        },
        headers=auth_headers,
    )
    assert sent.status_code == 201, sent.text

    async with async_session_factory() as session:
        conversation_ids = (
            (
                await session.execute(
                    select(InboundQueueEntry.conversation_id).where(
                        InboundQueueEntry.content == CONTENT
                    )
                )
            )
            .scalars()
            .all()
        )
    assert conversation_ids == [target]


@pytest.mark.asyncio
async def test_a_conversation_belonging_to_another_agent_is_not_found(
    app, auth_headers
) -> None:
    await _sync_agents(app, auth_headers, "sender", "recipient", "bystander")
    other = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "bystander", "message": "Not yours"},
        headers=auth_headers,
    )

    refused = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "sender",
            "to": "recipient",
            "content": CONTENT,
            "conversation_id": other.json()["conversation_id"],
        },
        headers=auth_headers,
    )
    assert refused.status_code == 404


@pytest.mark.asyncio
async def test_the_mcp_adapter_carries_the_same_three_parts(
    app, auth_headers, drain_conversation, monkeypatch
) -> None:
    """`HubAPIError` puts the Hub's detail in its message, so what the HTTP caller is told is
    what the agent is told.

    This does **not** exercise the route `send_message` posts to — it stubs `_hub_request` and
    manufactures the error from the operator route. An earlier version of this docstring claimed
    it "reaches the same route", which is how `conversation_id` came to be accepted by
    `MessageCreate` and rejected by `AgentMessageCreate` with the whole suite green. The real
    join lives in `test_mcp_body_contract.py` and `test_agent_message_routing.py`."""
    import hub.mcp_server as mcp_server

    conversation_id = await _archived_conversation(app, auth_headers, drain_conversation)

    async def _post(method, path, payload=None):
        response = await app.post(
            f"/api/v1/projects/proj-test{path}", json=payload, headers=auth_headers
        )
        if response.status_code >= 400:
            raise mcp_server.HubAPIError(
                response.status_code, response.json()["detail"], method, path
            )
        return response.json()

    captured = {}

    def _fake_hub_request(method, path, payload=None):
        captured["payload"] = payload
        raise captured["error"]

    try:
        await _post(
            "POST",
            "/messages",
            {
                "from": "sender",
                "recipient": "recipient",
                "content": CONTENT,
                "conversation_id": conversation_id,
            },
        )
    except mcp_server.HubAPIError as exc:
        captured["error"] = exc

    monkeypatch.setattr(mcp_server, "_hub_request", _fake_hub_request)
    with pytest.raises(mcp_server.HubAPIError) as excinfo:
        mcp_server.send_message(
            to_agent="recipient",
            subject="Migration",
            content=CONTENT,
            conversation_id=conversation_id,
        )

    # The tool forwards the target it was given...
    assert captured["payload"]["conversation_id"] == conversation_id
    # ...and the agent sees the cause, the instruction, and its own content.
    _assert_carries_all_three(str(excinfo.value), conversation_id)
