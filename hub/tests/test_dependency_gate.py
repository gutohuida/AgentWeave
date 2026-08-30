"""The gate: `task-dependencies` section 5 — a task may not start while a prerequisite it depends
on is not `approved`.

`dependency_gate.py` covers the pure evaluation over a set of `TaskDependency` rows.
`test_task_transition_service.py` covers the machine `apply_transition` walks; these tests cover
the third guard wired into it — placement (the edges that *begin* work, which since
`a-task-waits-while-its-run-waits` excludes the `blocked -> in_progress` resume edge), what "met"
means (D2), and the permanent-vs-temporary refusal shape (D1/D2). `test_task_transitions_api.py` and `test_run_task_binding.py` carry the HTTP and
runtime-surface halves of task 5.8's "test every surface" requirement — this file is the direct
`apply_transition` half, which every one of those surfaces funnels through.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskDependency
from hub.dependency_gate import evaluate
from hub.task_transition_service import (
    DependencyUnmetError,
    TransitionRefusedError,
    apply_transition,
)
from hub.task_transitions import operator

pytestmark = pytest.mark.asyncio


async def _make_task(
    session, task_id: str, status: str = "pending", project: str = "proj-test"
) -> Task:
    task = Task(id=task_id, project_id=project, title=f"Task {task_id}", status=status)
    session.add(task)
    await session.flush()
    return task


async def _depend(session, task_id: str, on_task_id: str) -> None:
    session.add(
        TaskDependency(
            id=f"tdep-{task_id}-{on_task_id}",
            project_id="proj-test",
            task_id=task_id,
            depends_on_task_id=on_task_id,
        )
    )


# ---------------------------------------------------------------------------
# 5.9 — a task with no dependencies transitions exactly as before this gate
# ---------------------------------------------------------------------------


async def test_a_task_with_no_dependencies_starts_exactly_as_before(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-no-deps", "pending")
        transition = await apply_transition(session, task, "in_progress", operator())
        await session.commit()
        assert transition is not None
        assert task.status == "in_progress"


async def test_evaluate_refuses_nothing_for_a_task_with_no_rows(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-no-deps-eval", "pending")
        refusal = await evaluate(session, task)
        assert not refusal.refuses


# ---------------------------------------------------------------------------
# 5.4 — met means `approved`. Nothing earlier.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prerequisite_status",
    ["pending", "assigned", "in_progress", "completed", "under_review", "revision_needed"],
)
async def test_a_prerequisite_short_of_approved_gates_the_move(app, prerequisite_status):
    async with async_session_factory() as session:
        prereq = await _make_task(
            session, f"task-prereq-{prerequisite_status}", prerequisite_status
        )
        task = await _make_task(session, f"task-gated-{prerequisite_status}", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        with pytest.raises(DependencyUnmetError) as excinfo:
            await apply_transition(session, task, "in_progress", operator())

        assert task.status == "pending"
        assert prereq.title in excinfo.value.detail
        assert excinfo.value.http_status == 409


async def test_an_approved_prerequisite_lets_the_task_start(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-approved", "approved")
        task = await _make_task(session, "task-unblocked", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        transition = await apply_transition(session, task, "in_progress", operator())
        await session.commit()
        assert transition is not None
        assert task.status == "in_progress"


async def test_completed_is_not_enough_only_approved_is(app):
    """D2's stricter reading — the one section 5 exists to enforce. A dependency's own approval
    still needs a second agent to review it (author/reviewer separation), so this is also what
    stops a dependency chain advancing with a single agent."""
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-completed", "completed")
        task = await _make_task(session, "task-waits-on-review", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        with pytest.raises(DependencyUnmetError):
            await apply_transition(session, task, "in_progress", operator())


# ---------------------------------------------------------------------------
# 5.6 — a rejected prerequisite gates permanently, and says so differently
# ---------------------------------------------------------------------------


async def test_a_rejected_prerequisite_gates_permanently_with_a_different_message(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-rejected", "rejected")
        task = await _make_task(session, "task-gated-forever", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        refusal = await evaluate(session, task)
        assert refusal.refuses
        assert len(refusal.rejected) == 1
        assert not refusal.unmet
        assert "rejected" in refusal.detail()
        assert "not yet approved" not in refusal.detail()


async def test_an_unmet_but_not_rejected_prerequisite_says_not_yet_approved(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-pending-msg", "pending")
        task = await _make_task(session, "task-gated-msg", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        refusal = await evaluate(session, task)
        assert refusal.unmet and not refusal.rejected
        assert "not yet approved" in refusal.detail()


# ---------------------------------------------------------------------------
# 5.2/5.3 — gated on the edges that begin work, and not on the `blocked` resume edge
# ---------------------------------------------------------------------------


async def test_assigning_a_gated_task_is_not_gated(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-for-assign", "pending")
        task = await _make_task(session, "task-assign-through-gate", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        transition = await apply_transition(session, task, "assigned", operator())
        await session.commit()
        assert transition is not None
        assert task.status == "assigned"


async def test_rejecting_a_gated_task_is_not_gated(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-for-reject", "pending")
        task = await _make_task(session, "task-reject-through-gate", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        transition = await apply_transition(session, task, "rejected", operator())
        await session.commit()
        assert transition is not None
        assert task.status == "rejected"


async def test_the_blocked_resume_edge_is_not_gated(app):
    """Overturned by `a-task-waits-while-its-run-waits` (design D5). This test used to assert the
    opposite, under the name `test_the_blocked_resume_edge_is_gated_the_same_way`, and it is
    inverted here rather than worked around because the rule it asserted is the rule that changed.

    Three facts carry the reversal. The gate asks whether work may *start* and `blocked` is
    reachable only from `in_progress`, so this work started. Every refusal at this edge is
    therefore a change that happened *after* the start, which the shipped *A dependency that
    regresses after a dependent has started does not halt it* already governs — so gating here
    breached that requirement and the exemption restores it. And `scheduler.candidate_is_startable`
    had already exempted `blocked` from this same call in its own words, so the board and the gate
    contradicted each other at exactly one edge.

    The concrete cost of leaving it gated was measured by F60's shape: a run whose wait expired
    could not resume its own task, so its `update_task(completed)` came back refused for work it
    had genuinely finished, with no action available to it.
    """
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-for-resume", "pending")
        task = await _make_task(session, "task-blocked-resume", "blocked")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        transition = await apply_transition(session, task, "in_progress", operator())
        await session.commit()
        assert transition is not None
        assert task.status == "in_progress"


async def test_starting_work_that_has_not_started_is_still_gated(app):
    """7.4. The exemption is not a general weakening: both edges that *begin* work still refuse.

    Asserted beside the inverted test above, so a reader sees at once that one edge moved and the
    others did not.
    """
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-for-start", "pending")
        pending = await _make_task(session, "task-pending-start", "pending")
        assigned = await _make_task(session, "task-assigned-start", "assigned")
        await _depend(session, pending.id, prereq.id)
        await _depend(session, assigned.id, prereq.id)
        await session.commit()

        with pytest.raises(DependencyUnmetError):
            await apply_transition(session, pending, "in_progress", operator())
        with pytest.raises(DependencyUnmetError):
            await apply_transition(session, assigned, "in_progress", operator())
        assert (pending.status, assigned.status) == ("pending", "assigned")


async def test_a_dependency_declared_while_a_task_waits_no_longer_stops_it_resuming(app):
    """7.6. The honest cost of the ungating, with a test rather than only a paragraph.

    `task-dependencies` says of a dependency declared on a task that has already started that "the
    existing gate SHALL apply to B unchanged". At this one edge it no longer does — and it is
    small, because the work is already under way, so the gate could not have prevented it, only the
    record of it. The record is what `dependency_state` carries instead.
    """
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-declared-late", "pending")
        task = await _make_task(session, "task-waiting-then-depended-on", "blocked")
        await session.commit()

        # Declared *while* it waits, which is the only way this edge can meet an unmet prerequisite
        # it did not already clear on the way in.
        await _depend(session, task.id, prereq.id)
        await session.commit()

        transition = await apply_transition(session, task, "in_progress", operator())
        await session.commit()
        assert transition is not None
        assert task.status == "in_progress"


async def test_the_blocked_resume_edge_succeeds_once_the_prerequisite_is_approved(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-for-resume-ok", "approved")
        task = await _make_task(session, "task-blocked-resume-ok", "blocked")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        transition = await apply_transition(session, task, "in_progress", operator())
        await session.commit()
        assert transition is not None
        assert task.status == "in_progress"


# ---------------------------------------------------------------------------
# Several prerequisites at once
# ---------------------------------------------------------------------------


async def test_every_unmet_prerequisite_is_named_not_just_the_first(app):
    async with async_session_factory() as session:
        prereq_a = await _make_task(session, "task-prereq-a", "pending")
        prereq_b = await _make_task(session, "task-prereq-b", "in_progress")
        task = await _make_task(session, "task-multi-gated", "pending")
        await _depend(session, task.id, prereq_a.id)
        await _depend(session, task.id, prereq_b.id)
        await session.commit()

        with pytest.raises(DependencyUnmetError) as excinfo:
            await apply_transition(session, task, "in_progress", operator())
        assert prereq_a.title in excinfo.value.detail
        assert prereq_b.title in excinfo.value.detail


async def test_one_approved_and_one_unmet_prerequisite_still_gates(app):
    async with async_session_factory() as session:
        prereq_ok = await _make_task(session, "task-prereq-ok", "approved")
        prereq_bad = await _make_task(session, "task-prereq-bad", "pending")
        task = await _make_task(session, "task-partial-gated", "pending")
        await _depend(session, task.id, prereq_ok.id)
        await _depend(session, task.id, prereq_bad.id)
        await session.commit()

        with pytest.raises(DependencyUnmetError) as excinfo:
            await apply_transition(session, task, "in_progress", operator())
        assert prereq_ok.title not in excinfo.value.detail
        assert prereq_bad.title in excinfo.value.detail


# ---------------------------------------------------------------------------
# Refusal shape
# ---------------------------------------------------------------------------


async def test_the_refusal_shares_the_base_so_routes_catch_one_type(app):
    assert issubclass(DependencyUnmetError, TransitionRefusedError)


async def test_the_structured_refusal_round_trips_through_to_dict(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-dict", "rejected")
        task = await _make_task(session, "task-gated-dict", "pending")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        with pytest.raises(DependencyUnmetError) as excinfo:
            await apply_transition(session, task, "in_progress", operator())
        payload = excinfo.value.refusal.to_dict()
        assert payload["code"] == "dependency_unmet"
        assert payload["rejected"][0]["id"] == prereq.id
        assert payload["unmet"] == []
