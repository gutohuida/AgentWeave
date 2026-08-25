"""The run→task binding: what attaches a run to work, and what that costs the task.

`test_task_transition_service.py` covers the machine. These cover the edge B1 could not see —
whether a run knows what it is doing, and whether the ledger found out.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run, Task, TaskDependency
from hub.run_task_binding import (
    DEFAULT_POLICY,
    POLICIES,
    TaskBindingError,
    bind_run_to_task,
    binding_from_entries,
    may_retry,
    resolve_task_for_project,
    run_advanced_its_task,
)
from hub.task_transition_service import RunNotBoundError, apply_transition, history_for
from hub.task_transitions import operator, run_actor


async def _make_task(session, task_id: str, status: str = "pending", project="proj-test") -> Task:
    task = Task(id=task_id, project_id=project, title=f"Task {task_id}", status=status)
    session.add(task)
    await session.flush()
    return task


def _run(run_id: str, agent: str = "worker", **kwargs) -> Run:
    return Run(id=run_id, project_id="proj-test", agent=agent, status="running", **kwargs)


# ---------------------------------------------------------------------------
# Which task a turn is about
# ---------------------------------------------------------------------------


def test_the_earliest_queued_entry_naming_a_task_wins():
    """Deterministic beats clever. A turn delivering several items must always produce the same
    binding, or the boundary check is unreproducible."""
    entries = [
        InboundQueueEntry(id="e3", sequence=3, task_id="task-c"),
        InboundQueueEntry(id="e1", sequence=1, task_id="task-a"),
        InboundQueueEntry(id="e2", sequence=2, task_id="task-b"),
    ]
    assert binding_from_entries(entries) == ("task-a", None)


def test_entries_naming_no_task_produce_no_binding():
    """Unbound is legitimate — conversation, questions and exploration are real work."""
    entries = [InboundQueueEntry(id="e1", sequence=1), InboundQueueEntry(id="e2", sequence=2)]
    assert binding_from_entries(entries) == (None, None)


def test_an_entry_naming_a_task_beats_an_earlier_one_that_does_not():
    entries = [
        InboundQueueEntry(id="e1", sequence=1),
        InboundQueueEntry(id="e2", sequence=2, task_id="task-b"),
    ]
    assert binding_from_entries(entries) == ("task-b", None)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_in_another_project_is_refused(app):
    async with async_session_factory() as session:
        await _make_task(session, "task-elsewhere", project="proj-other")
        await session.commit()

        with pytest.raises(TaskBindingError) as excinfo:
            await resolve_task_for_project(session, "task-elsewhere", "proj-test")
        assert "task-elsewhere" in excinfo.value.detail
        assert excinfo.value.http_status == 404


@pytest.mark.asyncio
async def test_a_task_that_does_not_exist_is_refused(app):
    async with async_session_factory() as session:
        with pytest.raises(TaskBindingError):
            await resolve_task_for_project(session, "task-ghost", "proj-test")


# ---------------------------------------------------------------------------
# Binding, and the move it causes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_binding_a_pending_task_starts_it_without_asking_the_agent(app):
    """Tier 1: the strongest enforcement is removing the need to remember."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-bind-pending", "pending")
        run = _run("run-bind-1")
        session.add(run)

        transition = await bind_run_to_task(session, run, task)
        await session.commit()

        assert run.task_id == "task-bind-pending"
        assert task.status == "in_progress"
        assert transition is not None
        assert transition.origin == "runtime"
        assert transition.run_id == "run-bind-1"
        assert transition.actor_agent == "worker"


@pytest.mark.asyncio
async def test_binding_an_assigned_task_also_starts_it(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-bind-assigned", "assigned")
        run = _run("run-bind-2")
        session.add(run)

        await bind_run_to_task(session, run, task)
        await session.commit()

        assert task.status == "in_progress"


@pytest.mark.asyncio
async def test_binding_a_task_already_in_progress_records_nothing(app):
    """B1's same-status no-op. A second turn on the same task must not manufacture a transition —
    "who moved this" would start returning whoever happened to resume."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-bind-running", "in_progress")
        run = _run("run-bind-3")
        session.add(run)

        transition = await bind_run_to_task(session, run, task)
        await session.commit()

        assert run.task_id == "task-bind-running"
        assert transition is None
        assert await history_for(session, "task-bind-running") == []


@pytest.mark.asyncio
async def test_a_task_with_no_legal_path_to_in_progress_still_binds(app):
    """Binding is a statement about the run, not a claim about the task's status. Refusing to bind
    would mean an operator could not point an agent at finished work to look at it."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-bind-approved", "approved")
        run = _run("run-bind-4")
        session.add(run)

        transition = await bind_run_to_task(session, run, task)
        await session.commit()

        assert run.task_id == "task-bind-approved"
        assert transition is None
        assert task.status == "approved"


@pytest.mark.asyncio
async def test_binding_revision_work_advances_it(app):
    """`revision_needed → in_progress` is a legal run edge, so re-delegating revision work starts
    it for free."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-bind-revision", "revision_needed")
        run = _run("run-bind-5")
        session.add(run)

        await bind_run_to_task(session, run, task)
        await session.commit()

        assert task.status == "in_progress"


# ---------------------------------------------------------------------------
# The dependency gate reaches the runtime move too (task-dependencies §5.8) — the "jobs" surface,
# since this is the automatic `-> in_progress` a run's own binding makes, not something a caller
# asked for by name.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_binding_a_task_with_an_unmet_dependency_leaves_it_un_started(app):
    """`bind_run_to_task` already catches `TransitionRefusedError` broadly and returns `None` — the
    same path an illegal edge would take. A gated task now takes it too: the run still binds (design
    D3 of the run-task-binding change — binding is a statement about the run, not a claim about the
    task), but the task stays wherever it was, gated the same way a manual attempt would be."""
    async with async_session_factory() as session:
        prereq = await _make_task(session, "task-bind-prereq", "pending")
        task = await _make_task(session, "task-bind-gated", "pending")
        session.add(
            TaskDependency(
                id="tdep-bind-gated",
                project_id="proj-test",
                task_id="task-bind-gated",
                depends_on_task_id="task-bind-prereq",
            )
        )
        run = _run("run-bind-gated")
        session.add(run)
        await session.commit()

        transition = await bind_run_to_task(session, run, task)
        await session.commit()

        assert run.task_id == "task-bind-gated"
        assert transition is None
        assert task.status == "pending"
        assert prereq.status == "pending"


@pytest.mark.asyncio
async def test_binding_a_task_with_an_approved_dependency_starts_it_as_usual(app):
    async with async_session_factory() as session:
        await _make_task(session, "task-bind-prereq-ok", "approved")
        task = await _make_task(session, "task-bind-unblocked", "pending")
        session.add(
            TaskDependency(
                id="tdep-bind-unblocked",
                project_id="proj-test",
                task_id="task-bind-unblocked",
                depends_on_task_id="task-bind-prereq-ok",
            )
        )
        run = _run("run-bind-unblocked")
        session.add(run)
        await session.commit()

        transition = await bind_run_to_task(session, run, task)
        await session.commit()

        assert transition is not None
        assert task.status == "in_progress"


# ---------------------------------------------------------------------------
# The boundary question
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_whose_only_transition_is_the_runtime_s_has_not_advanced_its_task(app):
    """The reason `origin` exists. Without it this returns True for every bound run and the check
    reports nothing."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-boundary-1", "pending")
        run = _run("run-boundary-1")
        session.add(run)
        await bind_run_to_task(session, run, task)
        await session.commit()

        assert await run_advanced_its_task(session, run) is False


@pytest.mark.asyncio
async def test_a_run_that_completed_its_task_has_advanced_it(app):
    async with async_session_factory() as session:
        task = await _make_task(session, "task-boundary-2", "pending")
        run = _run("run-boundary-2")
        session.add(run)
        await bind_run_to_task(session, run, task)
        await apply_transition(session, task, "completed", run_actor(run.id, run.agent))
        await session.commit()

        assert await run_advanced_its_task(session, run) is True


@pytest.mark.asyncio
async def test_an_unbound_run_has_nothing_to_have_neglected(app):
    async with async_session_factory() as session:
        run = _run("run-boundary-3")
        session.add(run)
        await session.commit()

        assert await run_advanced_its_task(session, run) is True


@pytest.mark.asyncio
async def test_another_run_moving_the_task_does_not_absolve_this_one(app):
    """The question is about this run, not about the task. A second agent tidying up afterwards
    does not make the first run's turn clean."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-boundary-4", "pending")
        run = _run("run-boundary-4")
        session.add(run)
        await bind_run_to_task(session, run, task)
        await apply_transition(session, task, "completed", run_actor("run-other", "reviewer"))
        await session.commit()

        assert await run_advanced_its_task(session, run) is False


# ---------------------------------------------------------------------------
# The retry bound
# ---------------------------------------------------------------------------


def test_an_ordinary_run_may_be_retried():
    assert may_retry(_run("run-plain")) is True


def test_a_run_started_in_answer_to_a_divergence_may_not_retry_again():
    """The whole bound (design D8). `A diverges → B` can only be followed by escalation or
    surfacing, so no counter exists to misconfigure and no loop is expressible."""
    assert may_retry(_run("run-response", divergence_source_run_id="run-plain")) is False


# ---------------------------------------------------------------------------
# The policy vocabulary agrees with the column it is stored in
# ---------------------------------------------------------------------------


def test_the_default_policy_matches_the_column_default():
    """`surface` being the default is what makes this capability safe to ship onto a board of
    existing tasks. Two declarations of it must not drift."""
    column = Task.__table__.columns["divergence_policy"]
    assert column.default.arg == DEFAULT_POLICY
    assert column.server_default.arg == DEFAULT_POLICY
    assert DEFAULT_POLICY in POLICIES


# ---------------------------------------------------------------------------
# Who is doing it (F6/F18)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_binding_names_the_agent_doing_the_work(app):
    """The board reported `in_progress / assignee: null / assignee_status: idle` about a live run.

    Two paths reach `in_progress`: the loop's claim, which sets `assignee`, and a direct `task_id`
    trigger, which went through here and set nothing. Since `assignee_status` is derived from that
    null, an agent that was at that moment running read as idle (`scripts/drive/FINDINGS.md`, F6
    and F18).
    """
    async with async_session_factory() as session:
        task = await _make_task(session, "task-bind-assignee", "pending")
        run = _run("run-bind-assignee", agent="builder")
        session.add(run)

        await bind_run_to_task(session, run, task)
        await session.commit()

        assert task.status == "in_progress"
        assert task.assignee == "builder"


@pytest.mark.asyncio
async def test_binding_does_not_take_a_task_someone_else_holds(app):
    """An operator's assignment, or a loop's claim for one agent, is a statement. A run merely
    starting is not grounds to overwrite it."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-bind-held", "assigned")
        task.assignee = "reviewer"
        run = _run("run-bind-held", agent="builder")
        session.add(run)

        await bind_run_to_task(session, run, task)
        await session.commit()

        assert task.assignee == "reviewer"


@pytest.mark.asyncio
async def test_a_task_that_binds_without_starting_still_names_its_agent(app):
    """A gated task stays `pending` and the run stays bound to it. It is still being worked on by
    somebody, and the card saying who is the only thing that distinguishes it from an abandoned
    one."""
    async with async_session_factory() as session:
        await _make_task(session, "task-bind-assignee-prereq", "pending")
        task = await _make_task(session, "task-bind-assignee-gated", "pending")
        session.add(
            TaskDependency(
                id="tdep-bind-assignee-gated",
                project_id="proj-test",
                task_id="task-bind-assignee-gated",
                depends_on_task_id="task-bind-assignee-prereq",
            )
        )
        run = _run("run-bind-assignee-gated", agent="builder")
        session.add(run)
        await session.commit()

        transition = await bind_run_to_task(session, run, task)
        await session.commit()

        assert transition is None
        assert task.status == "pending"
        assert task.assignee == "builder"


# ---------------------------------------------------------------------------
# F27: a run may claim work it does not hold, but may only finish work it does
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unbound_run_cannot_complete_a_task_it_never_took():
    """The F27 reproduction, reduced.

    `run-fba9bbc08b8d` was a concurrency probe — entire prompt *"reply CONC-1 only"*, `task_id`
    NULL — and it moved four unrelated tasks to `completed`. Nothing it did was individually
    illegal; nothing asked whether it was the run that took them.
    """
    async with async_session_factory() as session:
        task = await _make_task(session, "task-f27-unheld", "in_progress")
        run = _run("run-f27-probe")
        session.add(run)
        await session.commit()

        with pytest.raises(RunNotBoundError) as excinfo:
            await apply_transition(session, task, "completed", run_actor(run.id, "worker"))

    assert "not working any task" in str(excinfo.value)
    assert task.status == "in_progress"


@pytest.mark.asyncio
async def test_a_run_cannot_complete_a_peers_task():
    """One run, one task. Holding A is not authority over B."""
    async with async_session_factory() as session:
        mine = await _make_task(session, "task-f27-mine", "in_progress")
        theirs = await _make_task(session, "task-f27-theirs", "in_progress")
        run = _run("run-f27-holder", task_id=mine.id)
        session.add(run)
        await session.commit()

        with pytest.raises(RunNotBoundError) as excinfo:
            await apply_transition(session, theirs, "completed", run_actor(run.id, "worker"))

    assert mine.id in str(excinfo.value)
    assert theirs.status == "in_progress"


@pytest.mark.asyncio
async def test_claiming_an_unheld_task_binds_the_run_to_it():
    """The charter tells agents to go and find waiting work. Doing so is a claim, not a glance."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-f27-claimed", "pending")
        run = _run("run-f27-claimer")
        session.add(run)
        await session.commit()

        transition = await apply_transition(
            session, task, "in_progress", run_actor(run.id, "worker")
        )
        await session.commit()

        assert transition is not None
        assert run.task_id == task.id
        assert task.status == "in_progress"


@pytest.mark.asyncio
async def test_a_run_holding_one_task_cannot_claim_another():
    """`run-task-binding`'s existing invariant: a run carries at most one binding."""
    async with async_session_factory() as session:
        held = await _make_task(session, "task-f27-held", "in_progress")
        other = await _make_task(session, "task-f27-other", "pending")
        run = _run("run-f27-greedy", task_id=held.id)
        session.add(run)
        await session.commit()

        with pytest.raises(RunNotBoundError):
            await apply_transition(session, other, "in_progress", run_actor(run.id, "worker"))

        assert other.status == "pending"
        assert run.task_id == held.id


@pytest.mark.asyncio
async def test_a_run_that_claimed_the_work_can_finish_it():
    """The whole legitimate path, end to end: find, claim, do, complete."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-f27-endtoend", "pending")
        run = _run("run-f27-worker")
        session.add(run)
        await session.commit()

        actor = run_actor(run.id, "worker")
        await apply_transition(session, task, "in_progress", actor)
        await apply_transition(session, task, "completed", actor)
        await session.commit()

        assert task.status == "completed"
        assert run.task_id == task.id


@pytest.mark.asyncio
async def test_the_operator_needs_no_binding_to_complete_a_task():
    """An operator marking a card done is a statement by a person."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-f27-operator", "in_progress")
        await session.commit()

        await apply_transition(session, task, "completed", operator())
        await session.commit()

        assert task.status == "completed"


@pytest.mark.asyncio
async def test_the_runtime_binding_path_arrives_already_bound():
    """`bind_run_to_task` sets `task_id` before transitioning, so the guard is a no-op for it."""
    async with async_session_factory() as session:
        task = await _make_task(session, "task-f27-runtime", "pending")
        run = _run("run-f27-runtime")
        session.add(run)
        await session.commit()

        transition = await bind_run_to_task(session, run, task)
        await session.commit()

        assert transition is not None
        assert task.status == "in_progress"
        assert run.task_id == task.id
