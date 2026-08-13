"""A batch of answers reaches the agent as one turn, not one turn per answer.

Change `2026-08-13-answers-arrive-together`. The tool half was already right: `ask_user` holds
until every question resolves, so a live asker receives them together. This covers the other path —
the asking run has ended, so the answers have to reach the agent as new input — where the endpoint
created a queue entry, and so a turn, per answer. The operator answered the first of three and the
agent started work on it while they were still deciding the second.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Question, Run

PROJECT = "proj-test"
BATCH_URL = "/api/v1/agent-actions/questions/batch"


async def _asking_run(run_id: str, agent: str = "asker", status: str = "running") -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                status=status,
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _end_run(run_id: str) -> None:
    """The case this change is about: nobody is holding the tool call open any more."""
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        run.status = "completed"
        await session.commit()


def _q(text: str) -> dict:
    return {
        "question": text,
        "header": "H",
        "options": [{"label": "yes"}, {"label": "no"}],
        "multi_select": False,
    }


async def _ask(app, run_headers, *texts, blocking: bool = True) -> list[str]:
    resp = await app.post(
        BATCH_URL,
        json={"questions": [_q(t) for t in texts], "blocking": blocking},
        headers=run_headers,
    )
    assert resp.status_code == 201, resp.text
    return [row["id"] for row in resp.json()["questions"]]


async def _entries() -> list[InboundQueueEntry]:
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.project_id == PROJECT)
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )


async def _answer(app, auth_headers, question_id: str, answer: str):
    return await app.patch(
        f"/api/v1/projects/{PROJECT}/questions/{question_id}",
        json={"answer": answer, "labels": [answer]},
        headers=auth_headers,
    )


async def _decline(app, auth_headers, question_id: str):
    return await app.post(
        f"/api/v1/projects/{PROJECT}/questions/{question_id}/decline",
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_a_partly_answered_batch_delivers_nothing(app, auth_headers):
    """The reported defect. Answering the first of three woke the agent immediately, so it began
    work on one decision while the operator was still making the other two."""
    run_headers = await _asking_run("run-partial")
    ids = await _ask(app, run_headers, "First?", "Second?", "Third?")
    await _end_run("run-partial")

    assert (await _answer(app, auth_headers, ids[0], "yes")).status_code == 200

    assert await _entries() == []


@pytest.mark.asyncio
async def test_the_completing_answer_delivers_the_whole_batch_in_ask_order(app, auth_headers):
    run_headers = await _asking_run("run-whole")
    ids = await _ask(app, run_headers, "First?", "Second?", "Third?")
    await _end_run("run-whole")

    await _answer(app, auth_headers, ids[0], "alpha")
    await _answer(app, auth_headers, ids[1], "beta")
    assert await _entries() == []

    await _answer(app, auth_headers, ids[2], "gamma")

    entries = await _entries()
    assert len(entries) == 1, "one delivery for the batch, not one per answer"
    content = entries[0].content
    for text in ("First?", "Second?", "Third?", "alpha", "beta", "gamma"):
        assert text in content, content
    # Ask order, which is what the tool's own return promises. The two paths carry the same
    # information to the same agent and should not disagree about something this cheap.
    assert content.index("First?") < content.index("Second?") < content.index("Third?")


@pytest.mark.asyncio
async def test_a_decline_completes_a_batch_and_is_named_as_a_decline(app, auth_headers):
    """How the operator sends what they have decided without answering the rest.

    Omitting the declined question would leave the agent unable to tell "they saw this and passed"
    from "this was never asked", and those call for opposite behaviour.
    """
    run_headers = await _asking_run("run-decline")
    ids = await _ask(app, run_headers, "First?", "Second?")
    await _end_run("run-decline")

    await _answer(app, auth_headers, ids[0], "alpha")
    assert await _entries() == []

    assert (await _decline(app, auth_headers, ids[1])).status_code == 200

    entries = await _entries()
    assert len(entries) == 1
    assert "alpha" in entries[0].content
    assert "Second?" in entries[0].content
    assert "declined" in entries[0].content.lower()


@pytest.mark.asyncio
async def test_a_batch_declined_outright_delivers_nothing(app, auth_headers):
    """A decline carries no content to act on beyond the fact itself, which is already true of a
    single declined question. A turn spent saying "nothing was decided" is a turn wasted."""
    run_headers = await _asking_run("run-all-declined")
    ids = await _ask(app, run_headers, "First?", "Second?")
    await _end_run("run-all-declined")

    await _decline(app, auth_headers, ids[0])
    await _decline(app, auth_headers, ids[1])

    assert await _entries() == []


@pytest.mark.asyncio
async def test_an_answer_the_dead_run_never_received_is_still_delivered(app, auth_headers):
    """The second defect, and the one nobody would have noticed.

    An answer given while the run was still waiting queued nothing — someone was waiting — and the
    tool call never returned, so nothing consumed it. It reached no one at all. Scoping delivery by
    batch rather than by "what happened since the run ended" includes it by construction.
    """
    run_headers = await _asking_run("run-died")
    ids = await _ask(app, run_headers, "First?", "Second?")

    # Answered while the asker is still alive: correctly queues nothing.
    await _answer(app, auth_headers, ids[0], "rescued-answer")
    assert await _entries() == []

    await _end_run("run-died")
    await _answer(app, auth_headers, ids[1], "later-answer")

    entries = await _entries()
    assert len(entries) == 1
    assert "rescued-answer" in entries[0].content, "the answer the dead run never received"
    assert "later-answer" in entries[0].content


@pytest.mark.asyncio
async def test_a_batch_of_one_is_unchanged(app, auth_headers):
    """`batch_size` 1 completes on its only answer, so it produces exactly what it always did."""
    run_headers = await _asking_run("run-single")
    ids = await _ask(app, run_headers, "Only?")
    await _end_run("run-single")

    await _answer(app, auth_headers, ids[0], "sure")

    entries = await _entries()
    assert len(entries) == 1
    assert entries[0].content == "Question: Only?\n\nAnswer: sure"


@pytest.mark.asyncio
async def test_a_question_with_no_batch_id_is_a_batch_of_one(app, auth_headers):
    """`POST /questions` leaves `batch_id` NULL, so a null id is what "asked on its own" looks like
    in the database. It must keep behaving as it did before batching existed."""
    resp = await app.post(
        f"/api/v1/projects/{PROJECT}/questions",
        json={"from_agent": "asker", "blocking": False, **_q("Standalone?")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    question_id = resp.json()["id"]
    async with async_session_factory() as db:
        assert (await db.get(Question, question_id)).batch_id is None

    await _answer(app, auth_headers, question_id, "yep")

    entries = await _entries()
    assert len(entries) == 1
    assert entries[0].content == "Question: Standalone?\n\nAnswer: yep"


@pytest.mark.asyncio
async def test_a_still_waiting_asker_is_not_sent_the_batch_as_well(app, auth_headers):
    """Measured behaviour from `2026-08-11-declining-a-question`: queuing to an agent that already
    received the answers through its tool result cost a whole extra turn, in which it restated the
    directive it had just been given. Batching must not reintroduce it."""
    run_headers = await _asking_run("run-alive")
    ids = await _ask(app, run_headers, "First?", "Second?")

    await _answer(app, auth_headers, ids[0], "alpha")
    await _answer(app, auth_headers, ids[1], "beta")

    assert await _entries() == [], "the live asker gets these through ask_user, not the queue"


@pytest.mark.asyncio
async def test_an_answer_is_recorded_before_its_batch_completes(app, auth_headers):
    """Recording is per answer; only delivery is per batch. Deferring the write as well would have
    put the operator's answers in browser memory and broken "an answer survives an interruption"."""
    run_headers = await _asking_run("run-recorded")
    ids = await _ask(app, run_headers, "First?", "Second?")
    await _end_run("run-recorded")

    await _answer(app, auth_headers, ids[0], "written-down")

    async with async_session_factory() as db:
        row = await db.get(Question, ids[0])
        assert row.answered is True
        assert row.answer == "written-down"
    assert await _entries() == [], "recorded, but not yet delivered"
