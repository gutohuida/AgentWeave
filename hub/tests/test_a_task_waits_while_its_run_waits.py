"""A task waits while its run waits — F14 (the wait is invisible) and F60 (it ends in silence).

Group 1 of `openspec/changes/a-task-waits-while-its-run-waits/` is written here first, as
reproductions that **pass against unmodified code**. A reproduction that does not pass first is not
a reproduction: it is a test of the fix, and it cannot tell you whether the defect was ever real.

Each reproduction is inverted in place by the group that fixes it, so the file reads as one story
rather than as a pair of files disagreeing about what the product does.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Question, Run, Task


async def make_run(
    run_id: str = "run-waiter",
    *,
    agent: str = "worker",
    task_id: str | None = None,
    status: str = "running",
) -> dict[str, str]:
    """A run with a minted credential, in the shape the agent-facing router resolves."""
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status=status,
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def make_task(
    task_id: str = "task-waiting",
    *,
    status: str = "in_progress",
    assignee: str | None = "worker",
) -> str:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title="The work being done while somebody is asked about it",
                status=status,
                assignee=assignee,
            )
        )
        await session.commit()
    return task_id


async def make_agent(name: str = "worker", **columns) -> None:
    async with async_session_factory() as session:
        session.add(Agent(id=f"ag-{name}", project_id="proj-test", name=name, **columns))
        await session.commit()


async def read_task(app, headers, task_id: str) -> dict:
    response = await app.get(f"/api/v1/agent-actions/tasks/{task_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def question_row(question_id: str) -> Question:
    async with async_session_factory() as session:
        return (
            await session.execute(select(Question).where(Question.id == question_id))
        ).scalar_one()


async def task_row(task_id: str) -> Task:
    async with async_session_factory() as session:
        return await session.get(Task, task_id)


def one(question: str = "which colour?", *, blocking: bool = True) -> dict:
    """One well-formed question.

    `blocking` is stated rather than defaulted: `AgentQuestionCreate.blocking` is `False` on the
    single-question route and `True` on the batch body, and every reproduction here is about a run
    that stopped, so leaving it to the schema would silently test the wrong thing on one route.
    """
    return {
        "blocking": blocking,
        "question": question,
        "header": "A decision only you can make",
        "options": [{"label": "blue"}, {"label": "green"}],
        "multi_select": False,
    }


# ---------------------------------------------------------------------------
# 1. The two defects, reproduced against unmodified code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asking_a_blocking_question_parks_the_bound_task(app):
    """1.1 → 2.7. F14: for the whole wait the board says the work is progressing.

    Reproduction (unmodified code): the task stays `in_progress`, carries no `blocked_reason`, and
    the question does not know which task it stopped. Only `awaiting_answer_reason` — the secondary
    field F14 already added — mentions the wait at all, beside a status that contradicts it.

    After group 2 this is inverted: the task parks at ask time, the reason names the question, and
    the transition is attributed to the run with `origin='runtime'`.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    assert asked.status_code == 201, asked.text
    question_id = asked.json()["id"]

    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None
    assert (await question_row(question_id)).blocked_task_id is None

    # The board reports the wait, and only this: `awaiting_answer_reason` is the secondary field
    # F14 already added, and the status beside it still says the work is progressing.
    body = await read_task(app, headers, task_id)
    assert body["status"] == "in_progress"
    assert body["blocked_reason"] is None
    assert body["awaiting_answer_reason"] == "Waiting on your answer: which colour?"


@pytest.mark.asyncio
async def test_a_wait_that_ends_without_an_answer_leaves_no_record(app):
    """1.2. F60: the run waits out its deadline, decides for itself, and completes the task.

    Measured live: the question stays unanswered and undeclined, the task reads `completed`, and
    nothing anywhere says a decision was taken without the operator. Group 5 reports the expiry and
    group 8 puts the statement on the task; until then this is what the product does.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]

    # The wait ends unanswered and the agent carries on — which today it can, straight to
    # `completed`, because nothing ever parked the task.
    completed = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert completed.status_code == 200, completed.text

    task = await task_row(task_id)
    assert task.status == "completed"
    assert task.blocked_reason is None

    question = await question_row(question_id)
    assert question.answered is False
    assert question.declined is False
    assert question.blocked_task_id is None

    # Nothing on the task response says a decision was made without the operator. This is the
    # assertion group 8 inverts, and the reason that field has to be permanent.
    body = await read_task(app, headers, task_id)
    assert "proceeded_without_answer_reason" not in body
    # And what the board *does* say is the opposite of a record: the completed task reports that
    # it is still waiting, because the run is still running and still bound to it. A live wait
    # reported on finished work — the secondary field standing in for a status, which is exactly
    # what the rejected alternative "render `awaiting_answer_reason` more prominently" would have
    # shipped.
    assert body["awaiting_answer_reason"] == "Waiting on your answer: which colour?"


@pytest.mark.asyncio
async def test_a_batch_parks_once_and_every_question_knows_the_task(app):
    """1.3 → 2.7. A batch is one wait, not four.

    Reproduction (unmodified code): neither question records `blocked_task_id` and the task does
    not move. After group 2, `block_task_for_question`'s already-blocked branch makes the batch
    park once and record twice without a line of batch-specific logic.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post(
        "/api/v1/agent-actions/questions/batch",
        headers=headers,
        json={"questions": [one("first?"), one("second?")]},
    )
    assert asked.status_code == 201, asked.text
    ids = [row["id"] for row in asked.json()["questions"]]

    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None
    for question_id in ids:
        assert (await question_row(question_id)).blocked_task_id is None
