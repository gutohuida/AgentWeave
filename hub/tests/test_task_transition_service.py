"""The transition service — the machine meeting a row.

`test_task_transitions.py` covers the declaration. These tests cover what only a database can
answer: that the history is written, that it is read (rather than the mutable column) to decide
author/reviewer separation, and that a no-op records nothing.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskTransition
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
        transition = await apply_transition(
            session, task, "completed", run_actor("run-1", "agent-1")
        )
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
        result = await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
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
            await apply_transition(session, task, "approved", run_actor("run-1", "agent-1"))

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
        await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1", "agent-1"))
        await session.commit()

        with pytest.raises(ActorNotPermittedError) as excinfo:
            await apply_transition(session, task, "approved", run_actor("run-1", "agent-1"))

        assert task.status == "under_review"
        assert excinfo.value.http_status == 403
        assert "different actor" in excinfo.value.detail


async def test_a_different_run_may_approve(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-other", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1", "agent-1"))
        await apply_transition(session, task, "approved", run_actor("run-2", "agent-2"))
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
        await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1", "agent-1"))
        await session.commit()

        with pytest.raises(ActorNotPermittedError):
            await apply_transition(session, task, outcome, run_actor("run-1", "agent-1"))


async def test_separation_reads_the_history_not_the_mutable_column(app):
    """`updated_by_run_id` is overwritten by every write. If the rule read it, a third run touching
    the task in between would erase the completing run and let the author approve after all."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-hist", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
        # A different run moves it on, overwriting any last-writer field.
        await apply_transition(session, task, "under_review", run_actor("run-9", "agent-9"))
        task.updated_by_run_id = "run-9"
        await session.commit()

        with pytest.raises(ActorNotPermittedError):
            await apply_transition(session, task, "approved", run_actor("run-1", "agent-1"))


async def test_an_agent_cannot_approve_across_a_new_run(app):
    """The defect live use found on 2026-08-10, and the reason this rule compares agents.

    The first version compared `run_id`. An agent completed a task on one run and approved it on
    its next — different runs by construction, since every turn is a new run — and the check
    passed. It forbade nothing in practice.
    """
    async with async_session_factory() as session:
        task = await _make_task(session, "task-cross-run", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-turn-1", "claude"))
        await apply_transition(session, task, "under_review", run_actor("run-turn-2", "claude"))
        await session.commit()

        # A *different run* of the *same agent* must still be refused.
        with pytest.raises(ActorNotPermittedError) as excinfo:
            await apply_transition(session, task, "approved", run_actor("run-turn-3", "claude"))

        assert task.status == "under_review"
        assert "claude" in excinfo.value.detail


async def test_a_genuinely_different_agent_may_still_approve(app):
    """The rule separates agents, not runs — a second agent reviewing the first is the point."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-two-agents", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-a", "claude"))
        await apply_transition(session, task, "under_review", run_actor("run-b", "claude"))
        await apply_transition(session, task, "approved", run_actor("run-c", "codex"))
        await session.commit()

        assert task.status == "approved"


async def test_a_transition_records_the_agent_not_only_the_run(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-records-agent", "in_progress")
        transition = await apply_transition(
            session, task, "completed", run_actor("run-x", "claude")
        )
        await session.commit()
        assert transition.actor_agent == "claude"
        assert transition.run_id == "run-x"


async def test_a_pre_existing_transition_without_an_agent_does_not_block_anyone(app):
    """Rows written before the agent column existed carry NULL. The rule treats NULL as "not the
    same agent", so an old task stays approvable rather than becoming permanently stuck — the
    honest outcome, since who completed it was never recorded (migration 0053)."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-legacy", "under_review")
        session.add(
            TaskTransition(
                id="ttr-legacy",
                project_id="proj-test",
                task_id="task-legacy",
                from_status="in_progress",
                to_status="completed",
                actor_kind="run",
                run_id="run-old",
                actor_agent=None,
            )
        )
        await session.commit()

        await apply_transition(session, task, "approved", run_actor("run-new", "claude"))
        await session.commit()
        assert task.status == "approved"


async def test_the_most_recent_completion_is_the_one_that_counts(app):
    """After a revision cycle, the run that completed it *this* time is the author."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-cycle", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
        await apply_transition(session, task, "under_review", run_actor("run-2", "agent-2"))
        await apply_transition(session, task, "revision_needed", run_actor("run-2", "agent-2"))
        await apply_transition(session, task, "in_progress", run_actor("run-3", "agent-3"))
        await apply_transition(session, task, "completed", run_actor("run-3", "agent-3"))
        await apply_transition(session, task, "under_review", run_actor("run-3", "agent-3"))
        await session.commit()

        # run-3 completed most recently, so run-3 may not approve.
        with pytest.raises(ActorNotPermittedError):
            await apply_transition(session, task, "approved", run_actor("run-3", "agent-3"))

        # run-1 completed an earlier cycle and is no longer the author.
        await apply_transition(session, task, "approved", run_actor("run-1", "agent-1"))
        await session.commit()
        assert task.status == "approved"


async def test_an_agent_cannot_reopen_a_decided_task(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-reopen-agent", "approved")
        with pytest.raises(IllegalTransitionError):
            await apply_transition(session, task, "revision_needed", run_actor("run-1", "agent-1"))


async def test_the_operator_can_reopen_and_the_earlier_history_survives(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-reopen-op", "in_progress")
        await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
        await apply_transition(session, task, "under_review", run_actor("run-1", "agent-1"))
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

        await apply_transition(session, task, "completed", run_actor("run-1", "agent-1"))
        await session.commit()

        history = await history_for(session, "task-old")
        assert len(history) == 1
        assert history[0].from_status == "in_progress"


async def test_refusals_share_a_base_so_routes_can_catch_one_type(app):
    assert issubclass(IllegalTransitionError, TransitionRefusedError)
    assert issubclass(ActorNotPermittedError, TransitionRefusedError)
    assert issubclass(InvalidEntryStatusError, TransitionRefusedError)


# ---------------------------------------------------------------------------
# The transition origin (run-task-binding, design D5)
# ---------------------------------------------------------------------------


async def test_a_transition_defaults_to_actor_caused(app):
    """`actor` is the default because it is what almost every caller is, and because a default of
    `runtime` would let a forgotten argument quietly exempt a real transition from the divergence
    check."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-origin-default", "pending")
        transition = await apply_transition(session, task, "in_progress", operator())
        await session.commit()

        assert transition is not None
        assert transition.origin == "actor"


async def test_a_runtime_transition_records_its_cause_and_still_names_the_run(app):
    """The system acts *as* the run, not instead of it: the run and agent are still recorded, and
    only the cause differs. That is what lets author/reviewer separation keep working unchanged
    while the divergence check can still tell the two apart."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-origin-runtime", "pending")
        transition = await apply_transition(
            session, task, "in_progress", run_actor("run-bind", "worker"), origin="runtime"
        )
        await session.commit()

        assert transition is not None
        assert transition.origin == "runtime"
        assert transition.run_id == "run-bind"
        assert transition.actor_agent == "worker"
        assert transition.actor_kind == "run"


async def test_the_runtime_cannot_make_a_move_the_run_could_not(app):
    """A `runtime` transition is the same call with the same `Actor`, so it meets the same map.
    An automatic move that is not an edge available to the run does not happen."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-origin-illegal", "in_progress")

        with pytest.raises(IllegalTransitionError):
            await apply_transition(
                session, task, "approved", run_actor("run-bind", "worker"), origin="runtime"
            )
        assert task.status == "in_progress"


async def test_an_unknown_origin_is_refused(app):
    """There is no CHECK constraint behind this column — it sits on an existing table, and a
    table-level CHECK naming a column makes that column undroppable in SQLite — so this is where a
    bad value is caught."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-origin-bad", "pending")

        with pytest.raises(ValueError, match="origin must be one of"):
            await apply_transition(session, task, "in_progress", operator(), origin="magic")


async def test_a_runtime_transition_still_binds_author_reviewer_separation(app):
    """The agent recorded on an automatic move is the run's agent, so later review of that task is
    judged against it exactly as if the agent had asked."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-origin-separation", "in_progress")
        await apply_transition(
            session, task, "completed", run_actor("run-a", "worker"), origin="runtime"
        )
        await apply_transition(session, task, "under_review", run_actor("run-b", "worker"))
        await session.commit()

        with pytest.raises(ActorNotPermittedError):
            await apply_transition(session, task, "approved", run_actor("run-c", "worker"))
