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
            "header": "Decide",
            "options": [{"label": "Yes"}, {"label": "No"}],
            "multi_select": False,
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
        json={
            "from_agent": "claude",
            "question": "Which one?",
            "blocking": True,
            "header": "Decide",
            "options": [{"label": "Yes"}, {"label": "No"}],
            "multi_select": False,
        },
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
            "header": "Database",
            "multi_select": False,
            "options": [
                {"label": "Postgres", "description": "Concurrent writes"},
                {"label": "SQLite", "description": ""},
            ],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert [o["label"] for o in resp.json()["options"]] == ["Postgres", "SQLite"]
    assert resp.json()["options"][0]["description"] == "Concurrent writes"

    listed = await app.get(
        "/api/v1/projects/proj-test/questions?answered=false", headers=auth_headers
    )
    found = next(q for q in listed.json() if q["id"] == resp.json()["id"])
    assert [o["label"] for o in found["options"]] == ["Postgres", "SQLite"]


@pytest.mark.asyncio
async def test_a_question_without_the_structure_is_refused(app, auth_headers):
    """The whole point of requiring these: an agent cannot forget them, because a call without
    them never becomes a question. Teaching it to remember is probabilistic; this is not."""
    for missing in ("header", "options", "multi_select"):
        body = {
            "from_agent": "claude",
            "question": "Anything?",
            "header": "Decide",
            "options": [{"label": "Yes"}, {"label": "No"}],
            "multi_select": False,
        }
        del body[missing]
        resp = await app.post(
            "/api/v1/projects/proj-test/questions", json=body, headers=auth_headers
        )
        assert resp.status_code == 422, f"omitting {missing} was accepted"


@pytest.mark.asyncio
async def test_a_single_option_is_refused(app, auth_headers):
    """One option is not a choice; it is a confirmation dialog wearing a choice's clothes."""
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Which?",
            "header": "Pick",
            "multi_select": False,
            "options": [{"label": "only"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_too_many_options_are_refused(app, auth_headers):
    """A wall of buttons is not a choice, and the operator is deciding under a run's timeout."""
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Pick one",
            "header": "Pick",
            "multi_select": False,
            "options": [{"label": f"option-{i}"} for i in range(9)],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_the_operator_may_answer_something_other_than_an_offered_option(app, auth_headers):
    """Options are an offer, not a constraint."""
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Which?",
            "header": "Pick",
            "multi_select": False,
            "options": [{"label": "a"}, {"label": "b"}],
        },
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


@pytest.mark.asyncio
async def test_chosen_labels_are_stored_structurally(app, auth_headers):
    """A multi-select answer stays a list rather than a string someone re-splits."""
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Which?",
            "options": [{"label": "a"}, {"label": "b"}],
            "multi_select": True,
            "header": "Pick",
        },
        headers=auth_headers,
    )
    assert resp.json()["multi_select"] is True
    assert resp.json()["header"] == "Pick"
    q_id = resp.json()["id"]

    answered = await app.patch(
        f"/api/v1/projects/proj-test/questions/{q_id}",
        json={"answer": "a, b", "labels": ["a", "b"]},
        headers=auth_headers,
    )
    assert answered.json()["answer_labels"] == ["a", "b"]
    assert answered.json()["answer"] == "a, b"


@pytest.mark.asyncio
async def test_an_option_must_have_a_label(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/questions",
        json={
            "from_agent": "claude",
            "question": "Which?",
            "header": "Pick",
            "multi_select": False,
            "options": [{"description": "x"}, {"description": "y"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 422
