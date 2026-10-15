"""`a-run-claims-only-its-agents-or-nobodys-work` (F450) -- spec/changes, trial Hub document
`spdoc-02d1259eea94`.

The 2026-09-25 sweep's row 7: a task assigned to `alpha` and never started was claimed and
completed by a real turn of idle `beta`, both moves 200, while `tasks.assignee` kept saying `alpha`.
`_guard_run_holds_the_task` bound a run holding nothing to any task it claimed and never compared
the run's agent with the assignee.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import Run, Task, TaskTransition
from hub.task_transition_service import RunNotBoundError, apply_transition
from hub.task_transitions import operator, run_actor

pytestmark = pytest.mark.asyncio


async def _setup(task_id, *, status="assigned", assignee="alpha", run_agent="beta"):
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=f"Task {task_id}",
                status=status,
                assignee=assignee,
            )
        )
        session.add(
            Run(id=f"run-{task_id}", project_id="proj-test", agent=run_agent, status="running")
        )
        await session.commit()


async def _state(task_id):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        run = await session.get(Run, f"run-{task_id}")
        count = await session.scalar(
            select(func.count())
            .select_from(TaskTransition)
            .where(TaskTransition.task_id == task_id)
        )
        return task.status, task.assignee, run.task_id, count


async def test_a_run_cannot_claim_a_task_assigned_to_another_agent(app):
    await _setup("task-f450-refused")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f450-refused")
        with pytest.raises(RunNotBoundError) as excinfo:
            await apply_transition(
                session, task, "in_progress", run_actor("run-task-f450-refused", "beta")
            )

    assert excinfo.value.http_status == 403
    assert "alpha" in str(excinfo.value)
    assert "operator" in str(excinfo.value)
    assert await _state("task-f450-refused") == ("assigned", "alpha", None, 0)


async def test_completing_it_afterwards_is_refused_too(app):
    await _setup("task-f450-complete", status="in_progress")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f450-complete")
        with pytest.raises(RunNotBoundError):
            await apply_transition(
                session, task, "completed", run_actor("run-task-f450-complete", "beta")
            )

    assert (await _state("task-f450-complete"))[:2] == ("in_progress", "alpha")


async def test_claiming_an_unassigned_task_makes_the_run_its_assignee(app):
    await _setup("task-f450-open", status="pending", assignee=None)

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f450-open")
        await apply_transition(
            session, task, "in_progress", run_actor("run-task-f450-open", "beta")
        )
        await session.commit()

    status, assignee, bound, _ = await _state("task-f450-open")
    assert (status, assignee, bound) == ("in_progress", "beta", "task-f450-open")


async def test_a_run_claims_its_own_agents_task_as_before(app):
    await _setup("task-f450-own", assignee="beta")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f450-own")
        await apply_transition(session, task, "in_progress", run_actor("run-task-f450-own", "beta"))
        await session.commit()

    status, assignee, bound, _ = await _state("task-f450-own")
    assert (status, assignee, bound) == ("in_progress", "beta", "task-f450-own")


async def test_the_operator_moves_another_agents_task_as_before(app):
    await _setup("task-f450-operator")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f450-operator")
        await apply_transition(session, task, "in_progress", operator())
        await session.commit()

    assert (await _state("task-f450-operator"))[:2] == ("in_progress", "alpha")


async def test_a_reviewer_cannot_take_back_its_own_send_back(app):
    """F606: in one turn the tester sent dev1's task back, then moved it to in_progress and to
    completed itself, becoming its recorded completer, after which the flow refused to review it.
    A run that gave the verdict may not then work the task; only its assignee does."""
    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-f606",
                project_id="proj-test",
                title="dev1's work",
                status="under_review",
                assignee="dev1",
            )
        )
        session.add(
            Run(
                id="run-f606",
                project_id="proj-test",
                agent="tester",
                status="running",
                task_id="task-f606",
            )
        )
        await session.commit()

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f606")
        await apply_transition(session, task, "revision_needed", run_actor("run-f606", "tester"))
        await session.commit()

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f606")
        with pytest.raises(RunNotBoundError) as excinfo:
            await apply_transition(session, task, "in_progress", run_actor("run-f606", "tester"))
    assert "dev1" in str(excinfo.value)

    # And from in_progress (as if dev1 had picked it up), the tester's run still cannot complete it.
    async with async_session_factory() as session:
        task = await session.get(Task, "task-f606")
        task.status = "in_progress"
        await session.commit()
    async with async_session_factory() as session:
        task = await session.get(Task, "task-f606")
        with pytest.raises(RunNotBoundError):
            await apply_transition(session, task, "completed", run_actor("run-f606", "tester"))
        task.status = "revision_needed"
        await session.commit()

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f606")
        movers = (
            await session.execute(
                select(TaskTransition.actor_agent, TaskTransition.to_status).where(
                    TaskTransition.task_id == "task-f606"
                )
            )
        ).all()
    assert task.status == "revision_needed" and task.assignee == "dev1"
    assert movers == [("tester", "revision_needed")]


async def test_the_assignee_works_the_task_after_a_send_back(app):
    """The control: dev1's own run takes the task back up as before."""
    await _setup("task-f606-ok", status="revision_needed", assignee="dev1", run_agent="dev1")
    async with async_session_factory() as session:
        task = await session.get(Task, "task-f606-ok")
        await apply_transition(session, task, "in_progress", run_actor("run-task-f606-ok", "dev1"))
        await session.commit()
    assert (await _state("task-f606-ok"))[0] == "in_progress"
