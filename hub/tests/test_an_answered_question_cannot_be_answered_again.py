"""F594: the answer route refuses a question that already has an answer.

`decline_question` refuses an answered question; the answer route had no mirror refusal. Its
conditional UPDATE guarded `declined == False` only, so a double submit, a second tab or a stale
page overwrote the first answer, and after the asker's run had ended it queued the second one as a
new operator entry and spent a turn on it.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Question

QUESTIONS = "/api/v1/projects/proj-test/questions"


@pytest.mark.asyncio
async def test_a_second_answer_is_refused_and_the_first_is_kept(app, auth_headers):
    async with async_session_factory() as session:
        session.add(
            Question(
                id="q-twice-1",
                project_id="proj-test",
                from_agent="worker",
                question="Pick a colour",
                blocking=False,
            )
        )
        await session.commit()

    first = await app.patch(f"{QUESTIONS}/q-twice-1", json={"answer": "blue"}, headers=auth_headers)
    assert first.status_code == 200, first.text

    async with async_session_factory() as session:
        queued_before = len(
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.project_id == "proj-test")
                )
            )
            .scalars()
            .all()
        )

    second = await app.patch(f"{QUESTIONS}/q-twice-1", json={"answer": "red"}, headers=auth_headers)
    assert second.status_code == 409, second.text
    assert "already been answered" in second.json()["detail"]

    async with async_session_factory() as session:
        row = await session.get(Question, "q-twice-1")
        assert row is not None
        assert row.answer == "blue"
        queued_after = len(
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.project_id == "proj-test")
                )
            )
            .scalars()
            .all()
        )
    assert queued_after == queued_before, "a refused answer must queue nothing"
