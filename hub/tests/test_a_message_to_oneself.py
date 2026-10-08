"""F468: an agent that sends a message to itself is refused, and no turn starts.

The operator is not a message recipient, so a model asked to "send me a message" picks the nearest
name it has: its own. The Hub used to queue that as input to the sender and start a second,
autonomous turn that spent a model call acknowledging itself. Operator's answer, 2026-09-30: refuse
it with a 400 naming the reply as the way to reach the operator.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, InboundQueueEntry, Message, Run

pytestmark = pytest.mark.asyncio


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


async def _counts() -> tuple[int, int, int]:
    async with async_session_factory() as session:
        messages = (await session.execute(select(Message))).scalars().all()
        entries = (await session.execute(select(InboundQueueEntry))).scalars().all()
        runs = (await session.execute(select(Run))).scalars().all()
        return len(messages), len(entries), len(runs)


async def test_a_message_to_oneself_is_refused_naming_the_reply(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "cop-1", "peer")
    headers = await _active_run("run-self-send", "cop-1")
    before = await _counts()

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "cop-1", "subject": "Note", "content": "hello me"},
    )

    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "yourself" in detail
    assert "reply" in detail
    assert "ask_user" in detail
    # Nothing queued and no turn started: the refusal is before any Message, entry or Run exists.
    assert await _counts() == before

    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "agent_action_rejected")
                )
            )
            .scalars()
            .all()
        )
    assert [e.data.get("reason") for e in events] == ["message_to_self"]


async def test_a_message_to_a_peer_still_goes_through(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "cop-1", "peer")
    headers = await _active_run("run-peer-send", "cop-1")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "peer", "subject": "Note", "content": "hello peer"},
    )

    assert response.status_code in (200, 201), response.text


async def test_naming_its_own_current_conversation_is_still_a_message_to_oneself(
    app, auth_headers
) -> None:
    await _sync_agents(app, auth_headers, "cop-1")
    async with async_session_factory() as session:
        from hub.db.models import Conversation

        session.add(Conversation(id="conv-own", project_id="proj-test", agent="cop-1"))
        await session.commit()
    token = "aw_run_run-self-own-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-self-own",
                project_id="proj-test",
                agent="cop-1",
                status="running",
                turn_depth=0,
                conversation_id="conv-own",
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    before = await _counts()

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "recipient": "cop-1",
            "subject": "Note",
            "content": "hello me",
            "conversation_id": "conv-own",
        },
    )

    assert response.status_code == 400, response.text
    assert await _counts() == before
