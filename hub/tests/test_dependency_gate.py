"""The gate: `task-dependencies` section 5 — a task may not start while a prerequisite it depends
on is not `approved`.

`dependency_gate.py` covers the pure evaluation over a set of `TaskDependency` rows.
`test_task_transition_service.py` covers the machine `apply_transition` walks; these tests cover
the third guard wired into it — placement (`-> in_progress` only, including the `blocked ->
in_progress` resume edge), what "met" means (D2), and the permanent-vs-temporary refusal shape
(D1/D2). `test_task_transitions_api.py` and `test_run_task_binding.py` carry the HTTP and
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
# 5.2/5.3 — gated on `-> in_progress` only, including the `blocked` resume edge
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


async def test_the_blocked_resume_edge_is_gated_the_same_way(app):
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-prereq-for-resume", "pending")
        task = await _make_task(session, "task-blocked-resume", "blocked")
        await _depend(session, task.id, prereq.id)
        await session.commit()

        with pytest.raises(DependencyUnmetError):
            await apply_transition(session, task, "in_progress", operator())
        assert task.status == "blocked"


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
