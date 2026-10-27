"""The mender's questions are notes the operator answers later
(`the-mender-wakes-only-for-real-stalls`, task 3).

On :8000, 2026-10-26/27, the mender asked 27 blocking questions, each a four-minute wait that ran
out because the operator was asleep. Every question the Hub's mender asks is now recorded as a note
(non-blocking, no wait, no parked task) whatever it passes; its brief says to leave the note, not
act, and end the stall `gave_up` naming it; and the operator's answer, whenever it comes, wakes the
mender in the conversation it was asked in, not in another stall's thread.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import stalls
from hub.agent_auth import hash_run_token
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import Agent, InboundQueueEntry, Question, Run, Stall, Task

pytestmark = pytest.mark.asyncio

BATCH = "/api/v1/agent-actions/questions/batch"
SINGLE = "/api/v1/agent-actions/questions"
PROJECT = "proj-test"


def _one(text="Touch the operator's half-written notes.txt?"):
    return {
        "question": text,
        "header": "Dirty checkout",
        "options": [{"label": "Leave it"}, {"label": "Stash it"}],
        "multi_select": False,
    }


async def _agent_with_run(
    name, *, run_id, task_id, hub_role=False, status="running", conversation_id=None
):
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Agent(
                id=f"ag-{name}",
                project_id=PROJECT,
                name=name,
                config={"hub_role": stalls.HUB_ROLE} if hub_role else None,
            )
        )
        session.add(
            Task(
                id=task_id,
                project_id=PROJECT,
                title=f"{name}'s work",
                status="in_progress",
                assignee=name,
            )
        )
        await session.commit()
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=name,
                status=status,
                turn_depth=0,
                task_id=task_id,
                conversation_id=conversation_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _questions(from_agent):
    async with async_session_factory() as session:
        return (
            (
                await session.execute(
                    select(Question)
                    .where(Question.from_agent == from_agent)
                    .order_by(Question.batch_index)
                )
            )
            .scalars()
            .all()
        )


# ---------------------------------------------------------------------------
# mender-questions-are-notes
# ---------------------------------------------------------------------------


async def test_a_menders_blocking_question_is_a_note_and_a_builders_still_waits(app):
    mender = await _agent_with_run(
        stalls.MENDER, run_id="run-n-mender", task_id="task-n-mender", hub_role=True
    )
    builder = await _agent_with_run("builder", run_id="run-n-builder", task_id="task-n-builder")

    for headers in (mender, builder):
        asked = await app.post(
            BATCH, headers=headers, json={"questions": [_one(), _one("Second?")], "blocking": True}
        )
        assert asked.status_code == 201, asked.text
        # The response tells the caller what the Hub recorded.
        expected = headers is builder
        assert [row["blocking"] for row in asked.json()["questions"]] == [expected, expected]

    rows = await _questions(stalls.MENDER)
    assert [(q.blocking, q.wait_expires_at) for q in rows] == [(False, None)] * 2
    builder_rows = await _questions("builder")
    assert all(q.blocking and q.wait_expires_at is not None for q in builder_rows)
    async with async_session_factory() as session:
        assert (await session.get(Task, "task-n-mender")).status == "in_progress"
        assert (await session.get(Task, "task-n-builder")).status == "blocked"


async def test_the_single_question_route_records_the_menders_note_too(app):
    mender = await _agent_with_run(
        stalls.MENDER, run_id="run-n-mender1", task_id="task-n-mender1", hub_role=True
    )

    asked = await app.post(SINGLE, headers=mender, json={**_one(), "blocking": True})

    assert asked.status_code == 201, asked.text
    assert asked.json()["blocking"] is False
    [row] = await _questions(stalls.MENDER)
    assert (row.blocking, row.wait_expires_at) == (False, None)


# ---------------------------------------------------------------------------
# mender-leaves-the-note-and-does-not-act
# ---------------------------------------------------------------------------


async def test_the_brief_says_to_leave_a_note_not_to_wait_or_act(app):
    stall = Stall(
        id="stall-n-brief",
        project_id=PROJECT,
        cause="loop_stalled",
        key="loop_stalled:loop-x",
        reason="loop queue is stalled: 1 still awaiting a prerequisite's approval",
        task_id=None,
        loop_id=None,
    )
    async with async_session_factory() as session:
        brief = await stalls.brief(session, stall)

    lowered = brief.lower()
    assert "wait for the answer" not in lowered
    assert "and wait" not in lowered
    assert "ask_user" in brief
    assert "leave" in lowered and "note" in lowered
    assert "do not take the action" in lowered
    assert 'mend_end_stall(stall_id, "gave_up", summary)' in brief
    assert "names the note" in lowered


# ---------------------------------------------------------------------------
# answer-reaches-the-thread-it-was-asked-in
# ---------------------------------------------------------------------------


async def _two_threads_and_a_note(app, *, question_id):
    """The mender with open conversations C1 (older, where the note was asked) and C2 (updated
    later), and the run that asked in C1 over."""
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        session.add(
            Agent(
                id="ag-n-mender",
                project_id=PROJECT,
                name=stalls.MENDER,
                config={"hub_role": stalls.HUB_ROLE},
            )
        )
        await session.commit()
        for conversation_id, age in (("conv-n-c1", 60), ("conv-n-c2", 1)):
            conversation = new_conversation(
                project_id=PROJECT, agent=stalls.MENDER, origin="mender"
            )
            conversation.id = conversation_id
            conversation.updated_at = now - timedelta(minutes=age)
            session.add(conversation)
        session.add(
            Run(
                id="run-n-asked",
                project_id=PROJECT,
                agent=stalls.MENDER,
                status="completed",
                turn_depth=0,
                conversation_id="conv-n-c1",
            )
        )
        await session.commit()
        session.add(
            Question(
                id=question_id,
                project_id=PROJECT,
                from_agent=stalls.MENDER,
                question="Touch notes.txt?",
                header="Dirty checkout",
                options=[{"label": "Leave it"}, {"label": "Stash it"}],
                multi_select=False,
                blocking=False,
                created_by_run_id="run-n-asked",
                conversation_id="conv-n-c1",
            )
        )
        await session.commit()


async def _answer(app, auth_headers, question_id):
    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()):
        answered = await app.patch(
            f"/api/v1/projects/{PROJECT}/questions/{question_id}",
            headers=auth_headers,
            json={"answer": "Leave it", "labels": ["Leave it"]},
        )
    assert answered.status_code == 200, answered.text


async def _mender_entries():
    async with async_session_factory() as session:
        return (
            (
                await session.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == stalls.MENDER)
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )


async def test_an_answer_wakes_the_mender_in_the_thread_the_note_was_asked_in(app, auth_headers):
    await _two_threads_and_a_note(app, question_id="q-n-note")

    await _answer(app, auth_headers, "q-n-note")

    [entry] = await _mender_entries()
    assert entry.conversation_id == "conv-n-c1"


async def test_an_answer_falls_back_to_the_latest_open_thread_once_its_own_is_archived(
    app, auth_headers
):
    await _two_threads_and_a_note(app, question_id="q-n-note2")
    async with async_session_factory() as session:
        from hub.db.models import Conversation

        thread = (
            await session.execute(select(Conversation).where(Conversation.id == "conv-n-c1"))
        ).scalar_one()
        thread.lifecycle = "archived"
        await session.commit()

    await _answer(app, auth_headers, "q-n-note2")

    [entry] = await _mender_entries()
    assert entry.conversation_id == "conv-n-c2"
