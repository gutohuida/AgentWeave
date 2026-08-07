"""Tests for question endpoints."""

import pytest
from sqlalchemy import select

from hub.db.models import InboundQueueEntry, Message


@pytest.mark.asyncio
async def test_ask_and_answer_question(app, auth_headers):
    """The non-blocking path: nothing is waiting, so the answer is queued to wake the agent."""
    # Ask a question
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Which approach should I use?",
            "blocking": False,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("q-")
    assert data["answered"] is False
    assert data["blocking"] is False

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


@pytest.mark.asyncio
async def test_answering_a_blocking_question_does_not_also_queue_it(app, auth_headers):
    """`ask_user` waits and returns the answer as its own tool result, so the asking agent
    already has it. Queuing as well told it twice and cost a whole extra turn — measured live,
    the agent answered and then woke again to restate the same directive."""
    from hub.db.engine import async_session_factory

    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={"from_agent": "claude", "question": "Which one?", "blocking": True},
        headers=auth_headers,
    )
    q_id = resp.json()["id"]

    answered = await app.patch(
        f"/api/v1/projects/proj-test/questions/{q_id}",
        json={"answer": "the blocking answer"},
        headers=auth_headers,
    )
    assert answered.status_code == 200
    assert answered.json()["answer"] == "the blocking answer"

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.project_id == "proj-test",
                        InboundQueueEntry.content.contains("the blocking answer"),
                    )
                )
            )
            .scalars()
            .all()
        )
    assert entries == []


@pytest.mark.asyncio
async def test_a_question_can_offer_options_and_they_survive_the_round_trip(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Which database?",
            "blocking": True,
            "options": ["Postgres", "SQLite"],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["options"] == ["Postgres", "SQLite"]

    listed = await app.get(
        "/api/v1/projects/proj-test/questions?answered=false", headers=auth_headers
    )
    found = next(q for q in listed.json() if q["id"] == resp.json()["id"])
    assert found["options"] == ["Postgres", "SQLite"]


@pytest.mark.asyncio
async def test_an_open_question_reports_no_options(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={"from_agent": "claude", "question": "Anything?"},
        headers=auth_headers,
    )
    assert resp.json()["options"] == []


@pytest.mark.asyncio
async def test_too_many_options_are_refused(app, auth_headers):
    """A wall of buttons is not a choice, and the operator is deciding under a run's timeout."""
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Pick one",
            "options": [f"option-{i}" for i in range(9)],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_the_operator_may_answer_something_other_than_an_offered_option(app, auth_headers):
    """Options are an offer, not a constraint."""
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={"from_agent": "claude", "question": "Which?", "options": ["a", "b"]},
        headers=auth_headers,
    )
    q_id = resp.json()["id"]
    answered = await app.patch(
        f"/api/v1/projects/proj-test/questions/{q_id}",
        json={"answer": "neither, use c"},
        headers=auth_headers,
    )
    assert answered.status_code == 200
    assert answered.json()["answer"] == "neither, use c"
