"""A task waits while its run waits — F14 (the wait is invisible) and F60 (it ends in silence).

Group 1 of `openspec/changes/a-task-waits-while-its-run-waits/` is written here first, as
reproductions that **pass against unmodified code**. A reproduction that does not pass first is not
a reproduction: it is a test of the fix, and it cannot tell you whether the defect was ever real.

Each reproduction is inverted in place by the group that fixes it, so the file reads as one story
rather than as a pair of files disagreeing about what the product does.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Question, Run, Task
from hub.task_transition_service import history_for

AUTH = {"Authorization": "Bearer aw_live_testkey_abcdefgh"}


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


# ---------------------------------------------------------------------------
# 4. The wait's deadline, recorded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_ask_records_the_deadline_of_the_wait_it_starts(app):
    """4.3a. Stamped Hub-side, in the same write as the park, for blocking questions only.

    `test_question_wait_resolution.py` covers which number is chosen and that the tool agrees; this
    covers that it is written at all, and that the ask carries nothing that could influence it.
    """
    await make_agent(question_timeout_seconds=90)
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    before = datetime.now(timezone.utc)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question = await question_row(asked.json()["id"])

    assert question.wait_expires_at is not None
    recorded = question.wait_expires_at
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=timezone.utc)
    # 90s from the agent's own column, not the 240s default.
    assert timedelta(seconds=85) <= recorded - before <= timedelta(seconds=95)
    assert question.wait_ended_at is None


@pytest.mark.asyncio
async def test_a_note_starts_no_wait_and_records_no_deadline(app):
    """A non-blocking ask is the agent carrying on. There is no wait, so there is no deadline —
    and a question with no deadline can never be reported as expired."""
    await make_agent()
    headers = await make_run()

    asked = await app.post(
        "/api/v1/agent-actions/questions", headers=headers, json=one(blocking=False)
    )
    assert (await question_row(asked.json()["id"])).wait_expires_at is None


@pytest.mark.asyncio
async def test_an_unbound_runs_wait_is_recorded_even_though_nothing_parks(app):
    """The deadline is about the run's wait, not about a task. A conversation turn that asks and
    waits has a real deadline and must be able to report its expiry."""
    await make_agent()
    headers = await make_run(run_id="run-chat")

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    assert (await question_row(asked.json()["id"])).wait_expires_at is not None


def test_the_ask_schema_carries_no_wait_seconds():
    """4.3, design D3. Round 3 removed it deliberately: `wait_seconds` would arrive over the run's
    own credential, so the refusal that keeps an expiry a report of a fact rather than a lever
    would compare the report against a number the reporting party chose."""
    from hub.api.v1.agent_actions import AgentQuestionBatchCreate, AgentQuestionCreate

    assert "wait_seconds" not in AgentQuestionCreate.model_fields
    assert "wait_seconds" not in AgentQuestionBatchCreate.model_fields


def test_the_tools_ask_is_unchanged_by_this_change():
    """4.4. Round 3 deleted the task that would have changed it. The only edit this change makes
    to `mcp_server.py` is the expiry report `ask_user` sends after its wait loop (5.5)."""
    import inspect

    from hub import mcp_server

    assert "wait_seconds" not in inspect.signature(mcp_server.ask_user).parameters


# ---------------------------------------------------------------------------
# 5. The end of the wait
# ---------------------------------------------------------------------------


async def expire_the_wait(question_id: str) -> None:
    """Move the recorded deadline into the past, which is the only thing time would have done."""
    async with async_session_factory() as session:
        question = await session.get(Question, question_id)
        question.wait_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()


@pytest.mark.asyncio
async def test_reporting_an_expired_wait_releases_the_task_and_lets_the_work_land(app):
    """5.6, and the completion of 1.2. The whole path, end to end.

    The history assertion is the requirement this exists for: no history may state that a task was
    completed while it was waiting on a person who never answered. `blocked -> completed` does not
    exist, so the work passes back through `in_progress` and the record says the block ended before
    the work did.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    assert (await task_row(task_id)).status == "blocked"
    await expire_the_wait(question_id)

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    assert reported.status_code == 200, reported.text
    assert reported.json()["accepted"] == [question_id]

    question = await question_row(question_id)
    assert question.wait_ended_at is not None
    assert question.answered is False

    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None

    completed = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "completed"}
    )
    assert completed.status_code == 200, completed.text

    async with async_session_factory() as session:
        history = await history_for(session, task_id)
    assert [row.to_status for row in history] == ["blocked", "in_progress", "completed"]
    assert [row.origin for row in history[:2]] == ["runtime", "runtime"]


@pytest.mark.asyncio
async def test_a_report_before_the_deadline_is_refused(app):
    """5.7, and the refusal the whole design turns on. The report must describe a fact, not create
    one — and it is only checkable because the deadline is the Hub's own (design D3)."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [asked.json()["id"]]},
    )
    assert reported.status_code == 200
    assert reported.json()["accepted"] == []
    assert (await task_row(task_id)).status == "blocked"


@pytest.mark.asyncio
async def test_a_run_cannot_report_another_runs_wait(app):
    """5.7. You may only report your own wait. Otherwise one agent could release another's task by
    naming its question id."""
    await make_agent()
    task_id = await make_task()
    asker = await make_run(run_id="run-asker", task_id=task_id)
    stranger = await make_run(run_id="run-stranger", agent="other")

    asked = await app.post("/api/v1/agent-actions/questions", headers=asker, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=stranger,
        json={"question_ids": [question_id]},
    )
    assert reported.json()["accepted"] == []
    assert (await question_row(question_id)).wait_ended_at is None
    assert (await task_row(task_id)).status == "blocked"


@pytest.mark.asyncio
async def test_an_answered_question_never_expired(app, auth_headers):
    """5.7. Nothing expired, so nothing is recorded — which is what keeps the permanent statement
    in group 8 from appearing on work the operator actually decided."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)

    await app.patch(
        f"/api/v1/projects/proj-test/questions/{question_id}",
        headers=auth_headers,
        json={"answer": "blue"},
    )

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    assert reported.json()["accepted"] == []
    assert (await question_row(question_id)).wait_ended_at is None


@pytest.mark.asyncio
async def test_a_declined_question_never_expired(app, auth_headers):
    """5.7, and design D7's reason it must not be marked: the tool returns early on a decline
    rather than waiting out the deadline, so a decline is a decision handed back, not silence."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)

    await app.post(
        f"/api/v1/projects/proj-test/questions/{question_id}/decline", headers=auth_headers, json={}
    )

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    assert reported.json()["accepted"] == []
    assert (await question_row(question_id)).wait_ended_at is None


@pytest.mark.asyncio
async def test_a_question_with_no_recorded_deadline_cannot_be_reported(app):
    """5.7. A non-blocking note starts no wait, so there is nothing to have ended."""
    await make_agent()
    headers = await make_run()
    asked = await app.post(
        "/api/v1/agent-actions/questions", headers=headers, json=one(blocking=False)
    )

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [asked.json()["id"]]},
    )
    assert reported.json()["accepted"] == []


@pytest.mark.asyncio
async def test_reporting_twice_is_accepted_and_changes_nothing(app):
    """5.4's idempotence, from the outside. `expire_permission_request`'s own docstring names
    arriving second as the normal case for a report-plus-sweep pair, not an error."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)

    first = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    recorded = (await question_row(question_id)).wait_ended_at
    second = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )

    assert first.json()["accepted"] == second.json()["accepted"] == [question_id]
    assert (await question_row(question_id)).wait_ended_at == recorded

    async with async_session_factory() as session:
        history = await history_for(session, task_id)
    assert [row.to_status for row in history] == ["blocked", "in_progress"]


@pytest.mark.asyncio
async def test_a_batch_reports_only_the_waits_that_expired(app, auth_headers):
    """5.3. Refused per question, silently skipped rather than erroring the batch — because a
    batch where one was answered and the rest expired is the ordinary case."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post(
        "/api/v1/agent-actions/questions/batch",
        headers=headers,
        json={"questions": [one("first?"), one("second?")]},
    )
    first_id, second_id = [row["id"] for row in asked.json()["questions"]]
    await expire_the_wait(first_id)
    await expire_the_wait(second_id)
    await app.patch(
        f"/api/v1/projects/proj-test/questions/{first_id}",
        headers=auth_headers,
        json={"answer": "blue"},
    )

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [first_id, second_id]},
    )
    assert reported.json()["accepted"] == [second_id]
    assert (await question_row(first_id)).wait_ended_at is None
    assert (await question_row(second_id)).wait_ended_at is not None


@pytest.mark.asyncio
async def test_a_wait_that_is_never_reported_leaves_the_task_waiting(app):
    """5.7's unreported case, before the run ends. The task is still `blocked`, which is correct
    while the run is still there — group 5a is what answers the run's *end*."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    await expire_the_wait(asked.json()["id"])

    assert (await task_row(task_id)).status == "blocked"
    assert (await question_row(asked.json()["id"])).wait_ended_at is None


def test_the_wait_ended_report_is_not_in_the_agents_capability_surface():
    """5.2, design D4. It is not a capability, so no model can be prompted into calling it —
    `ask_user` calls it directly over the credential it already holds."""
    from hub import mcp_server

    exported = {name for name in dir(mcp_server) if not name.startswith("_")}
    assert "report_wait_ended" not in exported
    assert "wait_ended" not in exported


def test_the_tool_reports_the_expired_waits_and_not_the_declined_ones(monkeypatch):
    """5.5. `expired`, not `unanswered`. A decline left the wait early and is a decision the
    operator made and handed back; reporting one as an expiry would mark the task as
    proceeded-without-an-answer when an answer was in fact given."""
    from hub import mcp_server

    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    monkeypatch.setattr(mcp_server, "QUESTION_ANSWER_TIMEOUT", 0.05)
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    reported: list = []

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST" and path == "/questions/batch":
            return {"batch_id": "qb-1", "questions": [{"id": "q-declined"}, {"id": "q-expired"}]}
        if method == "POST" and path == "/questions/wait-ended":
            reported.append(body)
            return {"accepted": (body or {}).get("question_ids", [])}
        if path == "/questions/q-declined":
            return {"answered": False, "declined": True, "question": "a?"}
        return {"answered": False, "declined": False, "question": "b?"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user(
        [
            {"question": "a?", "header": "H", "options": [{"label": "x"}, {"label": "y"}]},
            {"question": "b?", "header": "H", "options": [{"label": "x"}, {"label": "y"}]},
        ]
    )

    assert reported == [{"question_ids": ["q-expired"]}]
    assert result["answered"] is False


def test_a_failed_report_still_returns_the_agent_its_answers(monkeypatch):
    """5.5. The agent is owed its answers whatever the Hub does with the report, and a turn dying
    because a report did not land would be worse than the report being lost. This is also the case
    that makes the run-end sweep required rather than optional (group 5a)."""
    from hub import mcp_server

    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    monkeypatch.setattr(mcp_server, "QUESTION_ANSWER_TIMEOUT", 0.05)
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)

    def hub(method, path, *_a, **_k):
        if path == "/questions/wait-ended":
            raise RuntimeError("the Hub was not reachable")
        if method == "POST":
            return {"batch_id": "qb-1", "questions": [{"id": "q-1"}]}
        return {"answered": False, "declined": False, "question": "a?"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user(
        [{"question": "a?", "header": "H", "options": [{"label": "x"}, {"label": "y"}]}]
    )

    assert result["success"] is True
    assert "went unanswered" in result["note"]


# ---------------------------------------------------------------------------
# 5a. The report is not the only signal (design D4)
#
# Rounds 1 and 2 merged "the report was never sent" with "the report was sent and did not land"
# and concluded that a missing report means nobody proceeded. Task 5.5 requires the second to be
# swallowed, so in that case somebody did — and the task would sit `blocked` with its own agent
# unable to record the work. The shipped analogue in the same router already has both halves:
# `expire_permission_request` — "The run reports and the run's end sweeps."
# ---------------------------------------------------------------------------


async def end_the_run(run_id: str = "run-waiter") -> None:
    """The run boundary, reached the way the trigger path reaches it."""
    from hub.run_divergence import evaluate_run_end

    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        run.status = "completed"
        await session.commit()
    await evaluate_run_end(run_id)


@pytest.mark.asyncio
async def test_a_run_that_ends_after_a_lost_report_does_not_strand_its_task(app, monkeypatch):
    """5a.1 → 5a.2. The honest reproduction: the report is sent and fails.

    With group 2b in place the agent has no way out at all — `blocked -> completed` does not exist
    and `blocked -> in_progress` is refused — which is the correct behaviour and exactly why this
    sweep is required rather than optional.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)

    # The report never lands. The agent proceeds anyway, as `ask_user` tells it to, and is refused.
    refused = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "completed"}
    )
    assert refused.status_code == 409
    assert (await task_row(task_id)).status == "blocked"

    await end_the_run()

    question = await question_row(question_id)
    assert question.wait_ended_at is not None
    assert question.answered is False
    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_the_sweep_never_fires_early(app):
    """5a.4. A run that ends while its recorded deadline is still in the future leaves the task
    waiting and sets nothing.

    This is the guard against turning the sweep into the Hub-side timer design D4 rejected: a
    sweep that fired on a clock would release a task while the tool was still waiting, because its
    own deadline had not passed.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())

    await end_the_run()

    assert (await question_row(asked.json()["id"])).wait_ended_at is None
    assert (await task_row(task_id)).status == "blocked"


@pytest.mark.asyncio
async def test_the_sweep_is_idempotent_when_the_report_already_arrived(app):
    """5a.3. Arriving second is the normal case for a report-plus-sweep pair, not an error — and
    after 6.1 the sweep will not even see the question again, because its wait has ended."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    recorded = (await question_row(question_id)).wait_ended_at

    await end_the_run()

    assert (await question_row(question_id)).wait_ended_at == recorded
    async with async_session_factory() as session:
        history = await history_for(session, task_id)
    assert [row.to_status for row in history] == ["blocked", "in_progress"]


@pytest.mark.asyncio
async def test_a_swept_task_carries_the_same_record_as_a_reported_one(app):
    """5a.5. A wait that ended is a wait that ended; how the Hub found out must not change the
    record."""
    await make_agent()
    reported_task = await make_task("task-reported")
    reporter = await make_run(run_id="run-reporter", task_id=reported_task)
    first = await app.post("/api/v1/agent-actions/questions", headers=reporter, json=one())
    await expire_the_wait(first.json()["id"])
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=reporter,
        json={"question_ids": [first.json()["id"]]},
    )

    swept_task = await make_task("task-swept")
    sweeper = await make_run(run_id="run-sweeper", agent="other", task_id=swept_task)
    second = await app.post("/api/v1/agent-actions/questions", headers=sweeper, json=one())
    await expire_the_wait(second.json()["id"])
    await end_the_run("run-sweeper")

    reported_row = await question_row(first.json()["id"])
    swept_row = await question_row(second.json()["id"])
    assert (reported_row.wait_ended_at is not None) == (swept_row.wait_ended_at is not None) is True
    assert (await task_row(reported_task)).status == (await task_row(swept_task)).status


# ---------------------------------------------------------------------------
# 6. An expired wait is not an open one (design D6)
#
# `wait_ended_at` introduces a state that did not exist: a question that is unanswered, undeclined,
# and nobody is waiting on. Rounds 1 and 2 fixed the two queries this change happens to touch;
# round 3 asked what *else* derives "somebody is waiting" from `answered = False` and found three
# more, two of them governed by shipped requirements in other capabilities. The decision is not one
# answer — two are excluded and the third is kept and marked.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_that_reported_its_expiry_and_then_dropped_the_work_is_divergent(app):
    """6.3, and the case 6.1 exists for.

    Without the `wait_ended_at IS NULL` exclusion the boundary would park the task on a wait that
    had already ended, and suppress a divergence that is real: the agent proceeded, then dropped
    the work, and the record would say it was waiting on somebody.
    """
    from hub.db.models import RunDivergence

    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    assert (await task_row(task_id)).status == "in_progress"

    await end_the_run()

    task = await task_row(task_id)
    assert task.status == "in_progress"
    assert task.blocked_reason is None
    async with async_session_factory() as session:
        divergences = list(
            (
                await session.execute(
                    select(RunDivergence).where(RunDivergence.run_id == "run-waiter")
                )
            ).scalars()
        )
    assert len(divergences) == 1


@pytest.mark.asyncio
async def test_the_board_stops_reporting_a_wait_that_ended(app):
    """6.2. `_attach_awaiting_answer` inherits the same exclusion as the predicate it matches."""
    await make_agent()
    task_id = await make_task("task-review", status="under_review")
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    assert (await read_task(app, headers, task_id))["awaiting_answer_reason"] is not None

    await expire_the_wait(question_id)
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )

    assert (await read_task(app, headers, task_id))["awaiting_answer_reason"] is None


@pytest.mark.asyncio
async def test_three_surfaces_read_the_same_ended_wait_and_two_stop_saying_someone_waits(app):
    """6.7. One run, one expired wait, three readers — and the decision is different per reader.

    The conversation rail and the loop's open-question count are read by the **operator**: a
    "waiting on you" that outranks `running`, and a count they read as "these still need me".
    Neither may include a wait nobody is in. The checkpoint's question list is read by the
    successor **agent**, which needs to know the question was asked and decided without anybody —
    so it keeps the entry and says the wait ended.
    """
    from hub.checkpoints import _open_questions_for
    from hub.conversations import conversation_attention
    from hub.db.models import AIJob, Conversation, JobRun, Loop

    await make_agent()
    task_id = await make_task()

    async with async_session_factory() as session:
        session.add(Conversation(id="conv-wait", project_id="proj-test", agent="worker"))
        session.add(
            AIJob(
                id="job-wait",
                project_id="proj-test",
                name="the loop",
                agent="worker",
                message="keep going",
                cron="0 9 * * *",
            )
        )
        session.add(
            Loop(id="loop-wait", project_id="proj-test", job_id="job-wait", purpose="keep going")
        )
        session.add(
            JobRun(
                id="jr-wait",
                job_id="job-wait",
                project_id="proj-test",
                conversation_id="conv-wait",
            )
        )
        await session.commit()

    headers = await make_run(task_id=task_id)
    async with async_session_factory() as session:
        run = await session.get(Run, "run-waiter")
        run.conversation_id = "conv-wait"
        await session.commit()

    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]

    async def read_all():
        async with async_session_factory() as session:
            rail = await conversation_attention(session, ["conv-wait"])
            checkpoint = await _open_questions_for(session, "conv-wait")
        loops = await app.get("/api/v1/projects/proj-test/jobs", headers=AUTH)
        job = next(row for row in loops.json() if row["id"] == "job-wait")
        return rail["conv-wait"], job["loop"]["open_questions"], checkpoint

    rail, open_questions, checkpoint = await read_all()
    assert rail == "waiting"
    assert open_questions == 1
    assert [entry["wait_ended"] for entry in checkpoint] == [False]

    await expire_the_wait(question_id)
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )

    rail, open_questions, checkpoint = await read_all()
    # The rail's own shipped rationale is the consumed timeout, and it is spent. `running` again,
    # which is what the run is actually doing.
    assert rail == "running"
    assert open_questions == 0
    # Kept, and marked. Dropping it would lose the most useful thing on the successor's list — and
    # it is the stated cover for the task `LIVE_STATUSES` omits during a wait.
    assert [entry["question"] for entry in checkpoint] == ["which colour?"]
    assert [entry["wait_ended"] for entry in checkpoint] == [True]


def test_the_loops_stop_reason_is_deliberately_out_of_scope():
    """6.8. `scheduler._pending_loop_request` is a fifth reader of the same family and a real
    defect — it has no `declined` exclusion at all — but it is about a loop's *stop reason*, not
    about who is waiting, and folding it in would put an unrelated fix inside a reproduction that
    cannot cover it. Recorded here so the omission is deliberate rather than forgotten.
    """
    import inspect

    from hub import scheduler

    source = inspect.getsource(scheduler._pending_loop_request)
    assert "declined" not in source
    assert "wait_ended_at" not in source


# ---------------------------------------------------------------------------
# 7 + 3.5. Ungating the resume, and the board that has to agree with it
#
# Coupled in both directions (design D5). Teaching the board to read a waiting task as "flagged,
# not stopped" while the gate could still stop it permanently would make the board state something
# false; ungating without the board fix leaves a resumable task rendered `gated`. Neither ships
# alone, so they are tested together.
# ---------------------------------------------------------------------------


async def regress_a_prerequisite(task_id: str, prereq_id: str = "task-prereq") -> None:
    """A prerequisite that was approved when the task started, and is not any more.

    This is the only shape in which the resume edge can meet an unmet prerequisite at all: the way
    *into* `in_progress` is the gated edge, so a waiting task cleared the gate on the way in.
    """
    from hub.db.models import TaskDependency

    async with async_session_factory() as session:
        session.add(
            Task(
                id=prereq_id,
                project_id="proj-test",
                title="the thing this depends on",
                status="revision_needed",
            )
        )
        session.add(
            TaskDependency(
                id=f"dep-{prereq_id}",
                project_id="proj-test",
                task_id=task_id,
                depends_on_task_id=prereq_id,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_an_answer_releases_a_waiting_task_whose_prerequisite_regressed(app, auth_headers):
    """7.3, first of three. Before the ungating `release_block_for_question` swallowed the refusal,
    so an answer could silently fail to release the task it settled."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    await regress_a_prerequisite(task_id)

    await app.patch(
        f"/api/v1/projects/proj-test/questions/{asked.json()['id']}",
        headers=auth_headers,
        json={"answer": "blue"},
    )

    assert (await task_row(task_id)).status == "in_progress"


@pytest.mark.asyncio
async def test_a_decline_releases_a_waiting_task_whose_prerequisite_regressed(app, auth_headers):
    """7.3, second. The reasoning does not distinguish the three releases, so leaving two of them
    gated would be an inconsistency nobody could explain later."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    await regress_a_prerequisite(task_id)

    await app.post(
        f"/api/v1/projects/proj-test/questions/{asked.json()['id']}/decline",
        headers=auth_headers,
        json={},
    )

    assert (await task_row(task_id)).status == "in_progress"


@pytest.mark.asyncio
async def test_an_expiry_releases_a_waiting_task_whose_prerequisite_regressed(app):
    """7.3, third, and the one that would otherwise leave an agent unable to complete finished
    work: refused the resume, its `update_task(completed)` comes back from `blocked` for work it
    has genuinely done, with no action available to it."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await regress_a_prerequisite(task_id)
    await expire_the_wait(question_id)

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    assert reported.json()["accepted"] == [question_id]
    assert (await task_row(task_id)).status == "in_progress"

    completed = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "completed"}
    )
    assert completed.status_code == 200, completed.text


@pytest.mark.asyncio
async def test_a_waiting_task_with_a_regressed_prerequisite_reads_flagged_not_stopped(app):
    """3.5. The board half of the same decision.

    `dependency_state` derived `running_on_regressed` from `status == "in_progress"` alone, so a
    `blocked` task with a regressed prerequisite rendered `gated` — "this has not started". It has:
    `blocked` is reachable only from `in_progress`. Wrong before ask-time parking, for the moments
    between a run ending and the operator answering, and only widened by it to the whole wait.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    await regress_a_prerequisite(task_id)

    body = await read_task(app, headers, task_id)
    assert body["status"] == "blocked"
    assert body["dependency_state"] == "running_on_regressed"


@pytest.mark.asyncio
async def test_a_task_that_never_started_still_reads_gated(app, auth_headers):
    """The other side of 3.5: the board's `gated` still means what it says. A widened read that
    called everything `running_on_regressed` would be the same defect pointing the other way."""
    await make_agent()
    task_id = await make_task("task-not-started", status="pending", assignee=None)
    await regress_a_prerequisite(task_id, "task-prereq-unstarted")

    response = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}", headers=auth_headers)
    assert response.json()["dependency_state"] == "gated"


# ---------------------------------------------------------------------------
# 8. Say it on the task, permanently (design D7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_completed_task_says_the_decision_was_taken_without_an_answer(app):
    """8.6, and the inversion of 1.2. F60's whole point in one assertion."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "completed"}
    )

    body = await read_task(app, headers, task_id)
    assert body["status"] == "completed"
    assert body["proceeded_without_answer_reason"] == (
        "Proceeded without your answer: which colour?"
    )


@pytest.mark.asyncio
async def test_the_statement_survives_review_and_approval(app, auth_headers):
    """8.6. It describes how the work was done, so it must outlive the statuses the work passes
    through afterwards."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "completed"}
    )

    # Cleared first: `_guard_reviewer_is_not_the_author` refuses `-> under_review` while the task
    # still names the agent that completed it, which is unrelated to this assertion.
    for status, extra in (("under_review", {"assignee": None}), ("approved", {})):
        moved = await app.patch(
            f"/api/v1/projects/proj-test/tasks/{task_id}",
            headers=auth_headers,
            json={"status": status, **extra},
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["proceeded_without_answer_reason"] is not None


@pytest.mark.asyncio
async def test_the_statement_is_still_there_after_the_operator_answers(app, auth_headers):
    """8.6, and the assertion this requirement exists for.

    F60 measured the operator answering five minutes after the run ended, choosing the option the
    agent did *not* ship. If an answer cleared this, the record of the unilateral call would
    disappear at the exact moment it became most misleading — the question would read answered, the
    task would read clean, and the code would carry a decision neither of them names.
    """
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)
    await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}", headers=headers, json={"status": "completed"}
    )

    answered = await app.patch(
        f"/api/v1/projects/proj-test/questions/{question_id}",
        headers=auth_headers,
        json={"answer": "green"},
    )
    assert answered.status_code == 200, answered.text

    body = await read_task(app, headers, task_id)
    assert body["proceeded_without_answer_reason"] is not None


@pytest.mark.asyncio
async def test_a_task_that_never_parked_still_carries_the_statement(app):
    """8.3a. The second arm on its own — round 3's widening.

    A run bound to a task in `under_review` asks, waits out the full deadline, decides for itself
    and carries on. `block_task_for_question` correctly never parked it, so `blocked_task_id` is
    null, and keying the derivation on that alone would leave this task carrying nothing. It is
    F60's own shape with a different starting status.
    """
    await make_agent()
    task_id = await make_task("task-in-review", status="under_review")
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    question_id = asked.json()["id"]
    await expire_the_wait(question_id)

    reported = await app.post(
        "/api/v1/agent-actions/questions/wait-ended",
        headers=headers,
        json={"question_ids": [question_id]},
    )
    assert reported.json()["accepted"] == [question_id]

    assert (await question_row(question_id)).blocked_task_id is None
    body = await read_task(app, headers, task_id)
    assert body["status"] == "under_review"
    assert body["proceeded_without_answer_reason"] is not None


@pytest.mark.asyncio
async def test_an_answered_wait_leaves_no_statement(app, auth_headers):
    """The statement must mean something. A task whose question the operator answered inside the
    deadline carries nothing — `wait_ended_at` was never set."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    await app.patch(
        f"/api/v1/projects/proj-test/questions/{asked.json()['id']}",
        headers=auth_headers,
        json={"answer": "blue"},
    )

    assert (await read_task(app, headers, task_id))["proceeded_without_answer_reason"] is None


@pytest.mark.asyncio
async def test_a_declined_question_leaves_no_statement(app, auth_headers):
    """Design D7. A decline is a decision the operator made and handed back, not silence — and the
    tool returns early on one rather than waiting out the deadline, so `wait_ended_at` is never
    set."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    await app.post(
        f"/api/v1/projects/proj-test/questions/{asked.json()['id']}/decline",
        headers=auth_headers,
        json={},
    )

    assert (await read_task(app, headers, task_id))["proceeded_without_answer_reason"] is None


@pytest.mark.asyncio
async def test_a_swept_wait_produces_the_same_statement_as_a_reported_one(app):
    """5a.5's other half, asserted on the statement itself: how the Hub found out must not change
    the record."""
    await make_agent()
    task_id = await make_task()
    headers = await make_run(task_id=task_id)
    asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=one())
    await expire_the_wait(asked.json()["id"])

    await end_the_run()

    # Read as the operator, because the run's credential is spent once the run has ended — which is
    # the whole situation this record exists for: the agent is gone and the task has to say what
    # happened on its own.
    response = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}", headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["proceeded_without_answer_reason"] == (
        "Proceeded without your answer: which colour?"
    )


def test_the_two_statements_are_spelled_by_one_module():
    """8.1. The wait and its ending are the same question read at two moments. Two spellings would
    read as two different situations, which is the defect `reason_from_question` was made public
    to prevent in the first place."""
    from hub.run_task_binding import _REASON_LIMIT, proceeded_without_answer_reason

    long_question = Question(id="q-long", project_id="proj-test", question="x" * 400)
    text = proceeded_without_answer_reason(long_question)
    assert text.startswith("Proceeded without your answer: ")
    assert text.endswith("…")
    assert len(text) <= len("Proceeded without your answer: ") + _REASON_LIMIT

    empty = Question(id="q-empty", project_id="proj-test", question="")
    assert proceeded_without_answer_reason(empty) == "Proceeded without your answer."
