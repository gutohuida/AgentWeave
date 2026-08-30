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
from hub.task_transition_service import history_for


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

    Reproduced first against unmodified code, where the task stayed `in_progress` with no
    `blocked_reason` and the question did not know what it had stopped — only
    `awaiting_answer_reason` mentioned the wait, beside a status that contradicted it.

    Inverted by group 2: the task parks at ask time, the reason names the question, and the
    transition is attributed to the run with `origin='runtime'` — observed by the runtime, not
    asserted by the agent.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    assert asked.status_code == 201, asked.text
    question_id = asked.json()["id"]

    task = await task_row(task_id)
    assert task.status == "blocked"
    assert task.blocked_reason == "Waiting on your answer: which colour?"
    assert (await question_row(question_id)).blocked_task_id == task_id

    async with async_session_factory() as session:
        history = await history_for(session, task_id)
    latest = history[-1]
    assert (latest.from_status, latest.to_status) == ("in_progress", "blocked")
    assert latest.origin == "runtime"
    assert latest.run_id == "run-waiter"

    body = await read_task(app, headers, task_id)
    assert body["status"] == "blocked"
    assert body["blocked_reason"] == "Waiting on your answer: which colour?"


@pytest.mark.asyncio
async def test_a_wait_that_ends_without_an_answer_leaves_no_record(app):
    """1.2 → 5.6. F60: the run waits out its deadline, decides for itself, and finishes the work.

    Reproduced first against unmodified code, where the ask parked nothing, the completion
    succeeded, and the question stayed unanswered and undeclined with nothing anywhere recording
    that a decision had been taken without the operator.

    Group 2 changes only where the silence is. The task now parks, so the agent that waited out its
    deadline is refused `blocked -> completed` — the edge `task_transitions` deliberately withholds
    — and its finished work has nowhere to go. That stranding is why group 5 exists, and this test
    grows into the whole path there.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]

    # The wait ends unanswered and the agent carries on, exactly as `ask_user` tells it to.
    completed = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert completed.status_code == 409, completed.text
    assert "blocked" in completed.json()["detail"]

    task = await task_row(task_id)
    assert task.status == "blocked"

    question = await question_row(question_id)
    assert question.answered is False
    assert question.declined is False

    # Nothing on the task response says a decision was made without the operator. Group 8 inverts
    # this, and F60 is what measured the need for it to be permanent.
    body = await read_task(app, headers, task_id)
    assert body.get("proceeded_without_answer_reason") is None


@pytest.mark.asyncio
async def test_a_batch_parks_once_and_every_question_knows_the_task(app):
    """1.3 → 2.7. A batch is one wait, not four.

    Reproduced first against unmodified code, where neither question recorded `blocked_task_id`
    and the task did not move. After group 2, `block_task_for_question`'s already-blocked branch
    makes the batch park once and record twice without a line of batch-specific logic: the first
    question transitions, the second takes the branch that records and changes nothing.
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
    assert task.status == "blocked"
    assert task.blocked_reason == "Waiting on your answer: first?"
    for question_id in ids:
        assert (await question_row(question_id)).blocked_task_id == task_id

    async with async_session_factory() as session:
        history = await history_for(session, task_id)
    assert [row.to_status for row in history].count("blocked") == 1


# ---------------------------------------------------------------------------
# 2. What the park refuses, and what it survives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_that_cannot_park_reports_the_wait_instead(app):
    """2.8. A run bound to a task in `under_review` asks. Nothing moves, and nothing is recorded.

    `block_task_for_question` records `blocked_task_id` on its non-transitioning branch **only**
    when the task is already `blocked` — `run-task-binding:663` is scoped to a question asked about
    a task that is *already waiting*, and `under_review` is not waiting, it is finished work in
    front of a reviewer.

    So this is the case `awaiting_answer_reason` still exists for, which is why D9 keeps it. The run
    is genuinely waiting and only that field says so.
    """
    await make_agent()
    task_id = await make_task("task-in-review", status="under_review")
    headers = await make_run(task_id=task_id)

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    assert asked.status_code == 201, asked.text
    question_id = asked.json()["id"]

    task = await task_row(task_id)
    assert task.status == "under_review"
    assert task.blocked_reason is None
    assert (await question_row(question_id)).blocked_task_id is None

    body = await read_task(app, headers, task_id)
    assert body["awaiting_answer_reason"] == "Waiting on your answer: which colour?"


@pytest.mark.asyncio
async def test_a_non_blocking_note_parks_nothing(app):
    """2.3. `ask_user(blocking=False)` is the agent leaving a note and carrying on.

    A task parked on one would make `blocked` mean "an agent mentioned something", which is the
    rule `unanswered_blocking_question` already states of itself.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post(
        "/api/v1/agent-actions/questions", headers=headers, json=one(blocking=False)
    )
    assert asked.status_code == 201, asked.text

    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_a_question_asked_by_an_unbound_run_parks_nothing(app):
    """A conversation turn holding no task has nothing to park, and must not be an error."""
    await make_agent()
    headers = await make_run(run_id="run-unbound")

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    assert asked.status_code == 201, asked.text


@pytest.mark.asyncio
async def test_a_park_that_raises_does_not_cost_the_agent_its_question(app, monkeypatch):
    """2.2. The question is already committed and the run is about to start waiting on it.

    A park that raises must not turn a successful ask into a failed one — the agent would lose both
    the question and the wait. `run_divergence.evaluate_run_end` still parks at the run boundary,
    and after this change that fallback's real remaining job is exactly this case.
    """
    from hub.api.v1 import agent_actions

    async def explode(*_args, **_kwargs):
        raise RuntimeError("the transition machine fell over")

    monkeypatch.setattr(agent_actions, "block_task_for_question", explode)

    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    assert asked.status_code == 201, asked.text
    assert (await question_row(asked.json()["id"])).blocking is True

    task = await task_row(task_id)
    assert task.status == "in_progress"


@pytest.mark.asyncio
async def test_the_park_announces_once_for_a_batch(app):
    """2.5. Announced when — and only when — the transition actually happened.

    `info`, not `warn`: this is the mechanism working, and warning about it would train the
    operator to read the one signal meaning "someone did the right thing" as a problem.
    """
    from hub.db.models import EventLog

    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    await app.post(
        "/api/v1/agent-actions/questions/batch",
        headers=headers,
        json={"questions": [one("first?"), one("second?")]},
    )

    async with async_session_factory() as session:
        events = list(
            (
                await session.execute(select(EventLog).where(EventLog.event_type == "task_blocked"))
            ).scalars()
        )
    assert len(events) == 1
    assert events[0].severity == "info"
    assert events[0].data["task_id"] == task_id


# ---------------------------------------------------------------------------
# 2b. The way out that needs no report (design D10)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_cannot_assert_its_own_task_out_of_the_waiting_status(app):
    """2b.1 → 2b.5. `task-lifecycle-governance:445` forbids leaving the waiting status by
    assertion as well as entering it. Only entering was enforced.

    Reproduced first against group 2 and unmodified `tasks.py`, where both calls below succeeded:
    the agent that waits out its deadline is refused `blocked -> completed`, sees `in_progress` in
    its own tool surface, moves itself there and completes — reproducing F60 through the door
    ask-time parking opens, with `wait_ended_at` never set and no statement on the task.

    Latent before this change because `blocked` implied the asking run had already ended. Ask-time
    parking removes exactly that protection, which is why the guard ships here rather than
    separately.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    assert (await task_row(task_id)).status == "blocked"

    refused = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "in_progress"}
    )
    assert refused.status_code == 403, refused.text
    # The message must name what actually ends a wait, or the agent is left guessing at a 403.
    detail = refused.json()["detail"]
    assert "answer" in detail and "decline" in detail

    # And the illegal edge stays illegal, distinguishably: 409 is the map refusing a move that does
    # not exist, 403 is this guard refusing one that does.
    illegal = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "completed"}
    )
    assert illegal.status_code == 409, illegal.text

    assert (await task_row(task_id)).status == "blocked"


@pytest.mark.asyncio
async def test_the_operator_still_releases_a_waiting_task_by_hand(app, auth_headers):
    """2b.4. Exempt by `actor.is_operator`, which is the whole shape of the entering guard read
    the other way. Nothing legitimate is refused, because no legitimate agent-asserted release
    exists."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())

    released = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{task_id}",
        headers=auth_headers,
        json={"status": "in_progress"},
    )
    assert released.status_code == 200, released.text
    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_an_answer_releases_the_task_without_going_through_the_route(app, auth_headers):
    """2b.4. `release_block_for_question` uses `operator()` and does not touch the PATCH route at
    all, so the guard cannot reach it. Asserted by actor rather than by inspection."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]

    answered = await app.patch(
        f"/api/v1/projects/proj-test/questions/{question_id}",
        headers=auth_headers,
        json={"answer": "blue"},
    )
    assert answered.status_code == 200, answered.text

    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_a_decline_releases_the_task_too(app, auth_headers):
    """2b.4, third path. Settled means answered *or* declined — a block released one way but not
    the other is the bug `2026-08-11-declining-a-question` D3 guards."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]

    declined = await app.post(
        f"/api/v1/projects/proj-test/questions/{question_id}/decline", headers=auth_headers, json={}
    )
    assert declined.status_code == 200, declined.text
    assert (await task_row(task_id)).status == "in_progress"


@pytest.mark.asyncio
async def test_the_operators_transition_map_still_offers_the_release(app, auth_headers):
    """2b.6. `GET /tasks/transitions/allowed` is hardcoded to `ACTOR_OPERATOR` — the operator's own
    view of the map — and the operator is exactly who this guard exempts.

    Asserted rather than assumed, because a guard that made the operator's own status control offer
    a move that then fails would be a worse defect than the one it fixes.
    """
    response = await app.get(
        "/api/v1/projects/proj-test/tasks/transitions/allowed", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["transitions"]["blocked"] == ["assigned", "in_progress", "rejected"]


def test_the_tool_surface_still_withholds_blocked_and_still_offers_in_progress():
    """2b.7. `mcp_server` needs no change and must not get one.

    `TaskStatus` already withholds `blocked` — the second layer behind the entering guard — and
    `in_progress` must stay in it, because it is the ordinary claim. The refusal belongs at the
    route, which is where the entering one is and for the reason its docstring gives.
    """
    from hub import mcp_server

    statuses = set(mcp_server.TaskStatus.__args__)  # type: ignore[attr-defined]
    assert "blocked" not in statuses
    assert "in_progress" in statuses
