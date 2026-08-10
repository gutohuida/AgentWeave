"""The transition service — the machine meeting a row.

`test_task_transitions.py` covers the declaration. These tests cover what only a database can
answer: that the history is written, that it is read (rather than the mutable column) to decide
author/reviewer separation, and that a no-op records nothing.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task
from hub.task_transition_service import (
    ActorNotPermittedError,
    IllegalTransitionError,
    InvalidEntryStatusError,
    TransitionRefusedError,
    apply_transition,
    guard_entry_status,
    history_for,
)
from hub.task_transitions import operator, run_actor

pytestmark = pytest.mark.asyncio


async def _make_task(session, task_id: str, status: str = "pending") -> Task:
    task = Task(id=task_id, project_id="proj-test", title=f"Task {task_id}", status=status)
    session.add(task)
    await session.flush()
    return task


# ---------------------------------------------------------------------------
# Accepted moves are recorded
# ---------------------------------------------------------------------------


async def test_a_legal_move_changes_the_status_and_records_it(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-legal", "in_progress")
        transition = await apply_transition(session, task, "completed", run_actor("run-1"))
        await session.commit()

        assert task.status == "completed"
        assert transition is not None
        assert (transition.from_status, transition.to_status) == ("in_progress", "completed")
        assert transition.actor_kind == "run"
        assert transition.run_id == "run-1"


async def test_an_operator_move_is_recorded_without_a_run(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-op", "pending")
        transition = await apply_transition(session, task, "rejected", operator())
        await session.commit()

        assert task.status == "rejected"
        assert transition.actor_kind == "operator"
        assert transition.run_id is None


async def test_restating_the_current_status_records_nothing(app):
    """D7. An agent-plane retry must not manufacture a transition that never happened."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-noop", "completed")
        result = await apply_transition(session, task, "completed", run_actor("run-1"))
        await session.commit()

        assert result is None
        assert task.status == "completed"
        assert await history_for(session, "task-noop") == []


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


async def test_an_illegal_move_is_refused_and_changes_nothing(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-illegal", "in_progress")

        with pytest.raises(IllegalTransitionError) as excinfo:
            await apply_transition(session, task, "approved", run_actor("run-1"))

        assert task.status == "in_progress"
        assert await history_for(session, "task-illegal") == []
        # The detail must let the caller correct itself, not just say no.
        assert "in_progress" in excinfo.value.detail
        assert "completed" in excinfo.value.detail
        assert excinfo.value.http_status == 409


async def test_an_agent_cannot_approve_the_work_its_own_run_completed(app):
    """The hole this change exists to close."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-self", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1"))
        await session.commit()

        with pytest.raises(ActorNotPermittedError) as excinfo:
            await apply_transition(session, task, "approved", run_actor("run-1"))

        assert task.status == "under_review"
        assert excinfo.value.http_status == 403
        assert "different actor" in excinfo.value.detail


async def test_a_different_run_may_approve(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-other", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1"))
        await apply_transition(session, task, "approved", run_actor("run-2"))
        await session.commit()

        assert task.status == "approved"


async def test_the_operator_may_approve_work_they_completed_themselves(app):
    """A single-operator project would otherwise be unable to approve anything (D9)."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-solo", "in_progress")
        await apply_transition(session, task, "completed", operator())
        await apply_transition(session, task, "under_review", operator())
        await apply_transition(session, task, "approved", operator())
        await session.commit()

        assert task.status == "approved"


@pytest.mark.parametrize("outcome", ["rejected", "revision_needed"])
async def test_rejection_and_revision_carry_the_same_separation(app, outcome):
    async with async_session_factory() as session:
        task = await _make_task(session, f"task-sep-{outcome}", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1"))
        await session.commit()

        with pytest.raises(ActorNotPermittedError):
            await apply_transition(session, task, outcome, run_actor("run-1"))


async def test_separation_reads_the_history_not_the_mutable_column(app):
    """`updated_by_run_id` is overwritten by every write. If the rule read it, a third run touching
    the task in between would erase the completing run and let the author approve after all."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-hist", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1"))
        # A different run moves it on, overwriting any last-writer field.
        await apply_transition(session, task, "under_review", run_actor("run-9"))
        task.updated_by_run_id = "run-9"
        await session.commit()

        with pytest.raises(ActorNotPermittedError):
            await apply_transition(session, task, "approved", run_actor("run-1"))


async def test_the_most_recent_completion_is_the_one_that_counts(app):
    """After a revision cycle, the run that completed it *this* time is the author."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-cycle", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1"))
        await apply_transition(session, task, "under_review", run_actor("run-2"))
        await apply_transition(session, task, "revision_needed", run_actor("run-2"))
        await apply_transition(session, task, "in_progress", run_actor("run-3"))
        await apply_transition(session, task, "completed", run_actor("run-3"))
        await apply_transition(session, task, "under_review", run_actor("run-3"))
        await session.commit()

        # run-3 completed most recently, so run-3 may not approve.
        with pytest.raises(ActorNotPermittedError):
            await apply_transition(session, task, "approved", run_actor("run-3"))

        # run-1 completed an earlier cycle and is no longer the author.
        await apply_transition(session, task, "approved", run_actor("run-1"))
        await session.commit()
        assert task.status == "approved"


async def test_an_agent_cannot_reopen_a_decided_task(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-reopen-agent", "approved")
        with pytest.raises(IllegalTransitionError):
            await apply_transition(session, task, "revision_needed", run_actor("run-1"))


async def test_the_operator_can_reopen_and_the_earlier_history_survives(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-reopen-op", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1"))
        await apply_transition(session, task, "approved", operator())
        await apply_transition(session, task, "revision_needed", operator())
        await session.commit()

        history = await history_for(session, "task-reopen-op")
        moves = [(t.from_status, t.to_status) for t in history]
        assert moves == [
            ("in_progress", "completed"),
            ("completed", "under_review"),
            ("under_review", "approved"),
            ("approved", "revision_needed"),
        ]
        # The approval is still there, not replaced by the reopening.
        assert ("under_review", "approved") in moves


# ---------------------------------------------------------------------------
# Entry statuses (D10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["pending", "assigned"])
async def test_entry_statuses_are_allowed_at_creation(app, status):
    guard_entry_status(status)  # does not raise


@pytest.mark.parametrize(
    "status",
    ["in_progress", "completed", "under_review", "revision_needed", "approved", "rejected"],
)
async def test_creation_outside_an_entry_status_is_refused(app, status):
    with pytest.raises(InvalidEntryStatusError) as excinfo:
        guard_entry_status(status)
    assert "pending" in excinfo.value.detail
    assert excinfo.value.http_status == 409


# ---------------------------------------------------------------------------
# Append-only (D4)
# ---------------------------------------------------------------------------


async def test_history_is_never_backfilled_for_a_pre_existing_task(app):
    """D8. A task that predates the table starts its history at its next move — nothing is invented
    for the period before the capability existed."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-old", "in_progress")
        await session.commit()
        assert await history_for(session, "task-old") == []

        await apply_transition(session, task, "completed", run_actor("run-1"))
        await session.commit()

        history = await history_for(session, "task-old")
        assert len(history) == 1
        assert history[0].from_status == "in_progress"


async def test_refusals_share_a_base_so_routes_can_catch_one_type(app):
    assert issubclass(IllegalTransitionError, TransitionRefusedError)
    assert issubclass(ActorNotPermittedError, TransitionRefusedError)
    assert issubclass(InvalidEntryStatusError, TransitionRefusedError)
