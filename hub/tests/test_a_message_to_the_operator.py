"""F77: send_message to a reserved name is told where the operator actually reads, not just that
the recipient doesn't exist.

`Operator`/`operator`/`USER` can never be an agent row (`worktrees._RESERVED_AGENT_NAMES`), so the
plain "Unknown recipient" 404 an agent got for a real typo was also what it got for this — a true
but useless answer that sends the agent guessing another name. The fix is a refusal on the same
branch, naming what already works: the agent's own reply, `update_task`'s notes, and `ask_user`.
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


async def _counts() -> tuple[int, int]:
    async with async_session_factory() as session:
        messages = (await session.execute(select(Message))).scalars().all()
        entries = (await session.execute(select(InboundQueueEntry))).scalars().all()
        return len(messages), len(entries)


@pytest.mark.parametrize("recipient", ["Operator", "operator", "USER"])
async def test_an_agent_sending_to_the_operator_is_told_where_the_operator_reads(
    app, auth_headers, recipient
) -> None:
    await _sync_agents(app, auth_headers, "author")
    headers = await _active_run(f"run-operator-{recipient}", "author")
    before_messages, before_entries = await _counts()

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": recipient, "subject": "Result", "content": "done"},
    )

    assert response.status_code == 404, response.text
    detail = response.json()["detail"]
    assert "not a message recipient" in detail
    assert "update_task" in detail
    assert "ask_user" in detail

    after_messages, after_entries = await _counts()
    assert after_messages == before_messages
    assert after_entries == before_entries


async def test_a_send_to_a_ghost_peer_still_answers_unknown_recipient(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "author")
    headers = await _active_run("run-ghost-peer", "author")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "ghost", "subject": "Hi", "content": "hello"},
    )

    assert response.status_code == 404, response.text
    assert "Unknown recipient 'ghost'" in response.json()["detail"]


async def test_the_operators_own_send_to_operator_keeps_todays_answer(app, auth_headers) -> None:
    response = await app.post(
        "/api/v1/projects/proj-test/messages",
        headers=auth_headers,
        json={"to": "operator", "content": "hello"},
    )

    assert response.status_code == 404, response.text
    assert "Unknown recipient 'operator'" in response.json()["detail"]
    assert "not a message recipient" not in response.json()["detail"]


async def test_the_rejection_event_names_the_reason(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "author")
    headers = await _active_run("run-operator-event", "author")

    response = await app.post(
        "/api/v1/agent-actions/messages",
        headers=headers,
        json={"recipient": "operator", "subject": "Result", "content": "done"},
    )
    assert response.status_code == 404, response.text

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
    matching = [e for e in events if e.data.get("reason") == "operator_not_a_recipient"]
    assert matching, [e.data for e in events]
