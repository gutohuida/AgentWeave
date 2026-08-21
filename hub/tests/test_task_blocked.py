"""A task that is waiting on a person, rather than one that was dropped.

The distinction these cover is the whole point of the status. Before it, an agent that correctly
stopped and asked was indistinguishable at the run boundary from one that walked away: the run
ended, the task had not moved, a divergence was recorded — and under `retry` the agent was started
again while still blocked on the same unanswered question.

Three rules carry it, and each has tests here:

- the runtime observes a block, an agent never asserts one (design D3);
- only an *unanswered blocking* question parks a task (R1);
- a task whose status at the run boundary is `blocked` is not divergent (D5), regardless of which
  run parked it — which is what makes multi-turn blocked work safe.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Question, Run, RunDivergence, Task
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import (
    bind_run_to_task,
    block_task_for_question,
    release_block_for_question,
)
from hub.task_transitions import STATUS_BLOCKED


async def _run_that_asked(
    session,
    run_id: str,
    task_id: str,
    *,
    blocking: bool = True,
    answered: bool = False,
    policy: str = "surface",
    asked: bool = True,
    run_status: str = "completed",
) -> tuple[Run, Task, Question | None]:
    """A run bound to a task, which asked a question and then ended without moving the task."""
    task = Task(
        id=task_id,
        project_id="proj-test",
        title=f"Task {task_id}",
        status="pending",
        divergence_policy=policy,
        assignee="worker",
    )
    session.add(task)
    run = Run(id=run_id, project_id="proj-test", agent="worker", status="running")
    session.add(run)
    await session.flush()
    await bind_run_to_task(session, run, task)

    question = None
    if asked:
        question = Question(
            id=f"q-{run_id}",
            project_id="proj-test",
            from_agent="worker",
            question="Should the retry bound be per-agent or per-task?",
            blocking=blocking,
            answered=answered,
            created_by_run_id=run_id,
        )
        session.add(question)

    run.status = run_status
    await session.commit()
    return run, task, question


async def _reload(session, task_id: str) -> Task:
    return await session.get(Task, task_id)


async def _divergence_for(session, run_id: str) -> RunDivergence | None:
    result = await session.execute(select(RunDivergence).where(RunDivergence.run_id == run_id))
    return result.scalars().first()


# ---------------------------------------------------------------------------
# The runtime observes the block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_that_ended_waiting_on_its_own_question_parks_its_task(app):
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-1", "task-blk-1")

    assert await evaluate_run_end("run-blk-1") is None

    async with async_session_factory() as session:
        task = await _reload(session, "task-blk-1")
        assert task.status == STATUS_BLOCKED
        assert "Should the retry bound" in task.blocked_reason


@pytest.mark.asyncio
async def test_the_question_records_which_task_it_parked(app):
    """So answering releases *that* task, without re-deriving it from the run's binding — a run may
    be bound to a task the question was not about (design D4)."""
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-2", "task-blk-2")

    await evaluate_run_end("run-blk-2")

    async with async_session_factory() as session:
        question = await session.get(Question, "q-run-blk-2")
        assert question.blocked_task_id == "task-blk-2"


@pytest.mark.asyncio
async def test_a_second_question_records_and_releases_an_already_blocked_task(app):
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-second-1", "task-blk-second")
    await evaluate_run_end("run-blk-second-1")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-blk-second")
        second_run = Run(
            id="run-blk-second-2",
            project_id="proj-test",
            agent="worker",
            status="completed",
        )
        second = Question(
            id="q-run-blk-second-2",
            project_id="proj-test",
            from_agent="worker",
            question="One more thing?",
            blocking=True,
            answered=False,
            created_by_run_id=second_run.id,
        )
        session.add_all([second_run, second])

        transition = await block_task_for_question(session, second_run, task, second)
        assert transition is None
        assert task.status == STATUS_BLOCKED
        assert second.blocked_task_id == task.id

        second.answered = True
        released = await release_block_for_question(session, second)
        assert released is task
        assert task.status == "in_progress"


@pytest.mark.asyncio
async def test_the_block_is_recorded_as_caused_by_the_runtime(app):
    """`origin` keeps meaning "who caused this" (design D5). The Hub saw the run end holding an
    unanswered question; the agent did not announce it."""
    from hub.db.models import TaskTransition

    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-3", "task-blk-3")

    await evaluate_run_end("run-blk-3")

    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskTransition)
            .where(TaskTransition.task_id == "task-blk-3")
            .where(TaskTransition.to_status == STATUS_BLOCKED)
        )
        transition = result.scalars().one()
        assert transition.origin == "runtime"
        assert transition.run_id == "run-blk-3"


# ---------------------------------------------------------------------------
# Only an unanswered blocking question counts (R1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_non_blocking_question_does_not_park_the_task(app):
    """`ask_user(blocking=False)` is the agent leaving a note and carrying on. A task parked on a
    note would make the status mean "an agent mentioned something" (R1).

    So this run dropped its work in the ordinary way, and is recorded as having done so.
    """
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-4", "task-blk-4", blocking=False)

    assert await evaluate_run_end("run-blk-4") is not None

    async with async_session_factory() as session:
        task = await _reload(session, "task-blk-4")
        assert task.status == "in_progress"
        assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_an_already_answered_question_does_not_park_the_task(app):
    """Nothing is being waited for. The agent got its answer and still did not move the task."""
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-5", "task-blk-5", answered=True)

    assert await evaluate_run_end("run-blk-5") is not None

    async with async_session_factory() as session:
        assert (await _reload(session, "task-blk-5")).status == "in_progress"


@pytest.mark.asyncio
async def test_another_runs_unanswered_question_does_not_park_this_runs_task(app):
    """A question someone else left open is not evidence that *this* run stopped for it."""
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-6", "task-blk-6", asked=False)
        stray = Question(
            id="q-stray",
            project_id="proj-test",
            from_agent="worker",
            question="Unrelated, and asked by nobody in particular",
            blocking=True,
            answered=False,
            created_by_run_id="run-somewhere-else",
        )
        session.add(stray)
        await session.commit()

    assert await evaluate_run_end("run-blk-6") is not None

    async with async_session_factory() as session:
        assert (await _reload(session, "task-blk-6")).status == "in_progress"


# ---------------------------------------------------------------------------
# A waiting task is not divergent (D5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_parking_a_task_records_no_divergence_and_starts_nothing(app):
    """Under `retry`, this is the exact bug the change exists to remove: before it, the agent was
    restarted while still waiting on the same unanswered question."""
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-7", "task-blk-7", policy="retry")

    assert await evaluate_run_end("run-blk-7") is None

    async with async_session_factory() as session:
        assert await _divergence_for(session, "run-blk-7") is None
        result = await session.execute(
            select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "divergence")
        )
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_a_later_run_on_an_already_blocked_task_is_not_divergent(app):
    """The exclusion is on the task's *status at the boundary*, not on which run parked it.

    This is what makes a multi-turn blocked task safe now that every turn of a bound conversation
    is checked: turn two ends, the task is still waiting on the same unanswered question, and that
    is not a second offence.
    """
    async with async_session_factory() as session:
        _, task, _ = await _run_that_asked(session, "run-blk-8", "task-blk-8")

    await evaluate_run_end("run-blk-8")

    async with async_session_factory() as session:
        task = await _reload(session, "task-blk-8")
        assert task.status == STATUS_BLOCKED
        later = Run(id="run-blk-8b", project_id="proj-test", agent="worker", status="running")
        session.add(later)
        await session.flush()
        await bind_run_to_task(session, later, task)
        later.status = "completed"
        await session.commit()

    assert await evaluate_run_end("run-blk-8b") is None

    async with async_session_factory() as session:
        assert await _divergence_for(session, "run-blk-8b") is None


@pytest.mark.asyncio
async def test_starting_a_run_on_a_blocked_task_does_not_silently_unpark_it(app):
    """`blocked -> in_progress` is a legal run edge, so binding would otherwise release the block
    merely because something started — and that run's end would then find it un-blocked and record
    a divergence. A block ends when the answer arrives or the operator says so."""
    async with async_session_factory() as session:
        _, task, _ = await _run_that_asked(session, "run-blk-9", "task-blk-9")

    await evaluate_run_end("run-blk-9")

    async with async_session_factory() as session:
        task = await _reload(session, "task-blk-9")
        run = Run(id="run-blk-9b", project_id="proj-test", agent="worker", status="running")
        session.add(run)
        await session.flush()
        assert await bind_run_to_task(session, run, task) is None
        await session.commit()
        assert (await _reload(session, "task-blk-9")).status == STATUS_BLOCKED


# ---------------------------------------------------------------------------
# The answer releases it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answering_returns_the_work_to_progress_and_drops_the_reason(app):
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-10", "task-blk-10")

    await evaluate_run_end("run-blk-10")

    async with async_session_factory() as session:
        question = await session.get(Question, "q-run-blk-10")
        question.answered = True
        released = await release_block_for_question(session, question)
        await session.commit()
        assert released is not None

        task = await _reload(session, "task-blk-10")
        assert task.status == "in_progress"
        assert task.blocked_reason is None


@pytest.mark.asyncio
async def test_an_answer_arriving_late_does_not_drag_back_a_task_that_moved_on(app):
    """The operator may have rejected or reassigned it while it sat waiting. Their decision stands
    over an answer that arrives afterwards."""
    from hub.task_transition_service import apply_transition
    from hub.task_transitions import operator

    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-11", "task-blk-11")

    await evaluate_run_end("run-blk-11")

    async with async_session_factory() as session:
        task = await _reload(session, "task-blk-11")
        await apply_transition(session, task, "rejected", operator())
        await session.commit()

    async with async_session_factory() as session:
        question = await session.get(Question, "q-run-blk-11")
        assert await release_block_for_question(session, question) is None
        assert (await _reload(session, "task-blk-11")).status == "rejected"


@pytest.mark.asyncio
async def test_a_question_that_parked_nothing_releases_nothing(app):
    async with async_session_factory() as session:
        question = Question(
            id="q-parked-nothing",
            project_id="proj-test",
            from_agent="worker",
            question="Just checking",
            blocking=True,
            answered=True,
        )
        session.add(question)
        await session.commit()
        assert await release_block_for_question(session, question) is None


# ---------------------------------------------------------------------------
# A timed-out question leaves it parked (R2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_question_nobody_answers_leaves_the_task_waiting(app):
    """Deliberately: the task *is* still waiting, so `blocked` stays truthful.

    Auto-unblocking on timeout would hand the task back to the divergence check while the agent is
    still waiting on the same unanswered question — the bug this change removes, reintroduced by
    the tidiest-looking fix. Nothing here unparks it; only an answer or the operator does.
    """
    async with async_session_factory() as session:
        await _run_that_asked(session, "run-blk-12", "task-blk-12", policy="retry")

    assert await evaluate_run_end("run-blk-12") is None
    # Asked again, as a later sweep or a second boundary evaluation would.
    assert await evaluate_run_end("run-blk-12") is None

    async with async_session_factory() as session:
        task = await _reload(session, "task-blk-12")
        assert task.status == STATUS_BLOCKED
        assert task.blocked_reason is not None
        assert await _divergence_for(session, "run-blk-12") is None
