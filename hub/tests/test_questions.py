"""Tests for question endpoints."""

import pytest
from sqlalchemy import select

from hub.db.models import InboundQueueEntry, Message


@pytest.mark.asyncio
async def test_ask_and_answer_question(app, auth_headers):
    # Ask a question
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Which approach should I use?",
            "blocking": True,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("q-")
    assert data["answered"] is False
    assert data["blocking"] is True

    q_id = data["id"]

    # List unanswered
    resp2 = await app.get(
        "/api/v1/projects/proj-test/questions?answered=false", headers=auth_headers
    )
    assert any(q["id"] == q_id for q in resp2.json())

    # Answer it
    resp3 = await app.patch(
        f"/api/v1/projects/proj-test/questions/{q_id}",
        json={"answer": "Use approach A"},
        headers=auth_headers,
    )
    assert resp3.status_code == 200
    assert resp3.json()["answered"] is True
    assert resp3.json()["answer"] == "Use approach A"

    from hub.db.engine import async_session_factory

    async with async_session_factory() as session:
        entry = (
            await session.execute(
                select(InboundQueueEntry).where(
                    InboundQueueEntry.project_id == "proj-test",
                    InboundQueueEntry.agent == "claude",
                    InboundQueueEntry.content.contains("Use approach A"),
                )
            )
        ).scalar_one()
        assert entry.origin_type == "operator"
        assert entry.hop_depth == 0
        magic_user_messages = (
            (
                await session.execute(
                    select(Message).where(
                        Message.sender == "user",
                        Message.recipient == "claude",
                        Message.content.contains("Use approach A"),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert magic_user_messages == []

    # Should no longer appear in unanswered
    resp4 = await app.get(
        "/api/v1/projects/proj-test/questions?answered=false", headers=auth_headers
    )
    assert not any(q["id"] == q_id for q in resp4.json())
