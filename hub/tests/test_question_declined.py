"""Closing a question without answering it.

Found by the operator on 2026-08-11: an agent asked, they did not answer, it gave up and asked
again, they answered — and the first question was still there. A question had no exit but an answer,
and the queue was strictly oldest-first, so a dead question stood in front of a live one.

Three rules carry the fix, and each has tests here:

- declining is terminal and distinct from answering (D1), and is the operator's alone;
- a declined question neither parks a task nor keeps one parked (D3, D4);
- "is anyone waiting on this?" is derived from the asking run and defaults to yes (D5).
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Question, Run, RunDivergence, Task
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import bind_run_to_task
from hub.task_transitions import STATUS_BLOCKED

QUESTIONS = "/api/v1/projects/proj-test/questions"


async def _question(session, question_id: str, **kwargs) -> Question:
    question = Question(
        id=question_id,
        project_id="proj-test",
        from_agent="worker",
        question=kwargs.pop("text", "Which way?"),
        blocking=kwargs.pop("blocking", True),
        answered=kwargs.pop("answered", False),
        **kwargs,
    )
    session.add(question)
    await session.flush()
    return question


async def _run_that_asked(session, run_id: str, task_id: str, *, run_status: str = "completed"):
    """A run bound to a task, which asked a blocking question and ended without moving the task."""
    task = Task(
        id=task_id,
        project_id="proj-test",
        title=f"Task {task_id}",
        status="pending",
        divergence_policy="retry",
        assignee="worker",
    )
    session.add(task)
    run = Run(id=run_id, project_id="proj-test", agent="worker", status="running")
    session.add(run)
    await session.flush()
    await bind_run_to_task(session, run, task)
    question = await _question(
        session, f"q-{run_id}", text="Per-agent or per-task?", created_by_run_id=run_id
    )
    run.status = run_status
    await session.commit()
    return run, task, question


# ---------------------------------------------------------------------------
# Declining is terminal, and is not an answer (D1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_declining_closes_a_question_without_answering_it(app, auth_headers):
    async with async_session_factory() as session:
        await _question(session, "q-decline-1")
        await session.commit()

    response = await app.post(f"{QUESTIONS}/q-decline-1/decline", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["declined"] is True
    assert body["answered"] is False
    assert body["answer"] is None


@pytest.mark.asyncio
async def test_the_record_of_having_been_asked_survives(app, auth_headers):
    """Kept, not deleted. That the operator was asked and chose not to answer is exactly the kind
    of thing the record exists to hold."""
    async with async_session_factory() as session:
        await _question(session, "q-decline-2", text="Something worth remembering")
        await session.commit()

    await app.post(f"{QUESTIONS}/q-decline-2/decline", headers=auth_headers)

    async with async_session_factory() as session:
        row = await session.get(Question, "q-decline-2")
        assert row is not None
        assert row.question == "Something worth remembering"
        assert row.declined_at is not None


@pytest.mark.asyncio
async def test_an_answered_question_cannot_be_declined(app, auth_headers):
    """Declining it would discard a decision that was already made."""
    async with async_session_factory() as session:
        await _question(session, "q-decline-3", answered=True, answer="the real answer")
        await session.commit()

    response = await app.post(f"{QUESTIONS}/q-decline-3/decline", headers=auth_headers)
    assert response.status_code == 409, response.text

    async with async_session_factory() as session:
        row = await session.get(Question, "q-decline-3")
        assert row.declined is False
        assert row.answer == "the real answer"


@pytest.mark.asyncio
async def test_declining_twice_is_the_state_the_caller_asked_for(app, auth_headers):
    async with async_session_factory() as session:
        await _question(session, "q-decline-4")
        await session.commit()

    first = await app.post(f"{QUESTIONS}/q-decline-4/decline", headers=auth_headers)
    second = await app.post(f"{QUESTIONS}/q-decline-4/decline", headers=auth_headers)
    assert first.status_code == 200
    assert second.status_code == 200, second.text
    assert second.json()["declined"] is True


@pytest.mark.asyncio
async def test_a_question_in_another_project_is_not_found(app, auth_headers):
    async with async_session_factory() as session:
        session.add(
            Question(
                id="q-elsewhere",
                project_id="proj-other",
                from_agent="worker",
                question="Not yours",
            )
        )
        await session.commit()

    response = await app.post(f"{QUESTIONS}/q-elsewhere/decline", headers=auth_headers)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# A declined question does not hold a task (D3, D4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_declining_releases_a_task_the_question_parked(app, auth_headers):
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-dq-1", "task-dq-1")

    await evaluate_run_end("run-dq-1")

    async with async_session_factory() as session:
        assert (await session.get(Task, "task-dq-1")).status == STATUS_BLOCKED

    response = await app.post(f"{QUESTIONS}/q-run-dq-1/decline", headers=auth_headers)
    assert response.status_code == 200, response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-dq-1")
        assert task.status == "in_progress"
        assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_a_declined_question_does_not_park_a_task_at_the_boundary(app, auth_headers):
    """Without this the release is undone by the mechanism it was meant to satisfy: the operator
    closes the question, the run ends, and the boundary check parks the task on it again."""
    async with async_session_factory() as session:
        _, _, question = await _run_that_asked(session, "run-dq-2", "task-dq-2")
        question.declined = True
        await session.commit()

    # Declined, so this is an ordinary dropped task rather than one waiting on a person.
    assert await evaluate_run_end("run-dq-2") is not None

    async with async_session_factory() as session:
        task = await session.get(Task, "task-dq-2")
        assert task.status != STATUS_BLOCKED
        assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_the_boundary_check_applies_again_after_a_decline(app, auth_headers):
    """Work no longer waiting on a person is work that can be dropped in the ordinary way."""
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-dq-3", "task-dq-3")

    await evaluate_run_end("run-dq-3")
    await app.post(f"{QUESTIONS}/q-run-dq-3/decline", headers=auth_headers)

    async with async_session_factory() as session:
        task = await session.get(Task, "task-dq-3")
        later = Run(id="run-dq-3b", project_id="proj-test", agent="worker", status="running")
        session.add(later)
        await session.flush()
        await bind_run_to_task(session, later, task)
        later.status = "completed"
        await session.commit()

    assert await evaluate_run_end("run-dq-3b") is not None

    async with async_session_factory() as session:
        result = await session.execute(
            select(RunDivergence).where(RunDivergence.run_id == "run-dq-3b")
        )
        assert result.scalars().first() is not None


@pytest.mark.asyncio
async def test_declining_a_question_that_parked_nothing_changes_no_task(app, auth_headers):
    async with async_session_factory() as session:
        session.add(
            Task(id="task-dq-4", project_id="proj-test", title="Untouched", status="in_progress")
        )
        await _question(session, "q-decline-5")
        await session.commit()

    response = await app.post(f"{QUESTIONS}/q-decline-5/decline", headers=auth_headers)
    assert response.status_code == 200

    async with async_session_factory() as session:
        assert (await session.get(Task, "task-dq-4")).status == "in_progress"


# ---------------------------------------------------------------------------
# Is anyone waiting? (D5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_question_whose_run_has_ended_reports_nobody_waiting(app, auth_headers):
    async with async_session_factory() as session:
        session.add(Run(id="run-ended", project_id="proj-test", agent="worker", status="completed"))
        await _question(session, "q-stale", created_by_run_id="run-ended")
        await session.commit()

    response = await app.get(f"{QUESTIONS}?answered=false", headers=auth_headers)
    rows = {row["id"]: row for row in response.json()}
    assert rows["q-stale"]["asker_waiting"] is False


@pytest.mark.asyncio
async def test_a_question_whose_run_is_alive_reports_someone_waiting(app, auth_headers):
    async with async_session_factory() as session:
        session.add(Run(id="run-alive", project_id="proj-test", agent="worker", status="running"))
        await _question(session, "q-live", created_by_run_id="run-alive")
        await session.commit()

    response = await app.get(f"{QUESTIONS}?answered=false", headers=auth_headers)
    rows = {row["id"]: row for row in response.json()}
    assert rows["q-live"]["asker_waiting"] is True


@pytest.mark.asyncio
async def test_an_unrecorded_asker_is_presumed_to_be_waiting(app, auth_headers):
    """Guessing the other way would mark a live question inert and sort it behind dead ones, which
    is the worse error of the two (design D5)."""
    async with async_session_factory() as session:
        await _question(session, "q-no-run")
        await session.commit()

    response = await app.get(f"{QUESTIONS}?answered=false", headers=auth_headers)
    rows = {row["id"]: row for row in response.json()}
    assert rows["q-no-run"]["asker_waiting"] is True
