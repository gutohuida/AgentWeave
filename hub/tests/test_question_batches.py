"""Several questions asked in one call become rows sharing one batch identity."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Question, Run

PROJECT = "proj-test"
BATCH_URL = "/api/v1/agent-actions/questions/batch"


async def active_run(run_id: str = "run-batch", agent: str = "asker") -> dict[str, str]:
    """Headers for a running agent, which is the only identity that may ask."""
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def q(text: str, *, header="H", multi_select=False, labels=("a", "b")) -> dict:
    return {
        "question": text,
        "header": header,
        "options": [{"label": label} for label in labels],
        "multi_select": multi_select,
    }


async def _rows() -> list[Question]:
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(Question)
                    .where(Question.project_id == PROJECT)
                    .order_by(Question.batch_index)
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.asyncio
async def test_a_batch_creates_one_row_per_question_sharing_a_batch_id(app):
    resp = await app.post(
        BATCH_URL,
        headers=await active_run(),
        json={"questions": [q("Which database?"), q("Which package manager?"), q("Write tests?")]},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["questions"]) == 3

    rows = await _rows()
    assert [row.batch_index for row in rows] == [0, 1, 2]
    assert {row.batch_size for row in rows} == {3}
    assert len({row.batch_id for row in rows}) == 1
    assert rows[0].batch_id == body["batch_id"]
    assert [row.question for row in rows] == [
        "Which database?",
        "Which package manager?",
        "Write tests?",
    ]


@pytest.mark.asyncio
async def test_the_returned_order_is_the_order_asked(app):
    """The tool pairs answers back to questions by position, so this ordering is load-bearing."""
    resp = await app.post(
        BATCH_URL,
        headers=await active_run(),
        json={"questions": [q("first?"), q("second?")]},
    )
    assert [entry["question"] for entry in resp.json()["questions"]] == ["first?", "second?"]
    assert [entry["batch_index"] for entry in resp.json()["questions"]] == [0, 1]


@pytest.mark.asyncio
async def test_a_batch_of_one_is_an_ordinary_question(app):
    resp = await app.post(
        BATCH_URL,
        headers=await active_run(),
        json={"questions": [q("Only one?")]},
    )
    assert resp.status_code == 201
    row = (await _rows())[0]
    assert row.batch_size == 1
    assert row.batch_index == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 5])
async def test_a_batch_outside_one_to_four_is_refused(app, count):
    """Past a handful, stepping through stops feeling like being asked and starts feeling like
    filling in a form."""
    resp = await app.post(
        BATCH_URL,
        headers=await active_run(),
        json={"questions": [q(f"q{i}?") for i in range(count)]},
    )
    assert resp.status_code == 422
    assert await _rows() == []


@pytest.mark.asyncio
async def test_one_malformed_entry_rejects_the_whole_batch(app):
    """A half-created batch would leave the operator a partial prompt and the agent waiting on
    questions that were never asked."""
    resp = await app.post(
        BATCH_URL,
        headers=await active_run(),
        json={
            "questions": [
                q("fine?"),
                {"question": "no options?", "header": "H", "multi_select": False},
            ]
        },
    )
    assert resp.status_code == 422
    assert await _rows() == []


@pytest.mark.asyncio
async def test_a_single_option_is_still_refused_inside_a_batch(app):
    """One option is a confirmation dialog wearing a choice's clothes — the rule does not relax
    just because the question arrived with company."""
    resp = await app.post(
        BATCH_URL,
        headers=await active_run(),
        json={"questions": [q("only one option?", labels=("a",))]},
    )
    assert resp.status_code == 422
    assert await _rows() == []


@pytest.mark.asyncio
async def test_batched_questions_are_bound_to_the_asking_run(app):
    """The unasked-question backstop keys off `created_by_run_id`; a batch must set it the same
    way a lone question does, or asking three things would look like asking none."""
    await app.post(
        BATCH_URL,
        headers=await active_run(),
        json={"questions": [q("first?"), q("second?")]},
    )
    rows = await _rows()
    assert all(row.created_by_run_id for row in rows)
    assert len({row.created_by_run_id for row in rows}) == 1
