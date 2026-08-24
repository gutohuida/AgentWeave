"""What a run that dropped its work costs.

`test_run_task_binding.py` covers whether the run advanced its task. These cover what happens when
it did not: the record, the per-task policy, and the bound that stops a chain of automatic runs
from being able to run forever.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent, InboundQueueEntry, Run, RunDivergence, Task
from hub.run_divergence import evaluate_run_end, record_response_run
from hub.run_task_binding import bind_run_to_task
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator, run_actor


async def _agent(session, name: str) -> Agent:
    agent = Agent(id=f"agt-{name}", project_id="proj-test", name=name)
    session.add(agent)
    await session.flush()
    return agent


async def _bound_run(
    session,
    run_id: str,
    task_id: str,
    *,
    agent: str = "worker",
    policy: str = "surface",
    escalation_agent: str | None = None,
    assignee: str | None = None,
    divergence_source_run_id: str | None = None,
    status: str = "completed",
) -> tuple[Run, Task]:
    """A run that bound a pending task, started it, and then ended having done nothing else."""
    task = Task(
        id=task_id,
        project_id="proj-test",
        title=f"Task {task_id}",
        status="pending",
        divergence_policy=policy,
        escalation_agent=escalation_agent,
        assignee=assignee,
    )
    session.add(task)
    run = Run(
        id=run_id,
        project_id="proj-test",
        agent=agent,
        status="running",
        divergence_source_run_id=divergence_source_run_id,
    )
    session.add(run)
    await session.flush()
    await bind_run_to_task(session, run, task)
    run.status = status
    await session.commit()
    return run, task


async def _divergence_for(session, run_id: str) -> RunDivergence | None:
    result = await session.execute(select(RunDivergence).where(RunDivergence.run_id == run_id))
    return result.scalars().first()


async def _queued_for(session, agent: str) -> list[InboundQueueEntry]:
    result = await session.execute(
        select(InboundQueueEntry)
        .where(InboundQueueEntry.agent == agent)
        .where(InboundQueueEntry.origin_type == "divergence")
        .order_by(InboundQueueEntry.sequence)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_that_ended_without_moving_its_task_is_recorded(app):
    async with async_session_factory() as session:
        run, task = await _bound_run(session, "run-div-1", "task-div-1")

    assert await evaluate_run_end("run-div-1") is not None

    async with async_session_factory() as session:
        divergence = await _divergence_for(session, "run-div-1")
        assert divergence is not None
        assert divergence.task_id == "task-div-1"
        assert divergence.agent == "worker"
        assert divergence.task_status_at_end == "in_progress"
        assert divergence.run_exit_status == "completed"
        assert divergence.policy_applied == "surface"
        assert divergence.outcome == "surfaced"
        assert divergence.resolved_at is None


@pytest.mark.asyncio
async def test_a_run_that_completed_its_task_is_not_divergent(app):
    async with async_session_factory() as session:
        run, task = await _bound_run(session, "run-div-2", "task-div-2")
        await apply_transition(session, task, "completed", run_actor(run.id, run.agent))
        await session.commit()

    assert await evaluate_run_end("run-div-2") is None


@pytest.mark.asyncio
async def test_an_unbound_run_is_never_divergent(app):
    async with async_session_factory() as session:
        session.add(Run(id="run-div-3", project_id="proj-test", agent="chatty", status="completed"))
        await session.commit()

    assert await evaluate_run_end("run-div-3") is None


@pytest.mark.asyncio
async def test_a_crashed_run_is_checked_and_names_its_exit_status(app):
    """Exit status is not a condition of the check, but it is on the record — a crash and a
    completed run that forgot deserve different reactions from a reader."""
    async with async_session_factory() as session:
        await _bound_run(session, "run-div-4", "task-div-4", status="interrupted")

    assert await evaluate_run_end("run-div-4") is not None

    async with async_session_factory() as session:
        divergence = await _divergence_for(session, "run-div-4")
        assert divergence.run_exit_status == "interrupted"


@pytest.mark.asyncio
async def test_a_run_whose_input_went_back_to_the_queue_is_not_divergent(app):
    """The work is about to be handed to a new run that will bind to the same task, so nothing has
    been dropped. Recording one here would also, under `retry`, race the redelivery."""
    async with async_session_factory() as session:
        await _bound_run(session, "run-div-5", "task-div-5")

    assert await evaluate_run_end("run-div-5", input_returned=True) is None

    async with async_session_factory() as session:
        assert await _divergence_for(session, "run-div-5") is None


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_work_reaching_the_ledger_closes_an_open_divergence(app):
    """A divergence is an open condition, not a verdict. This is what keeps long work spanning
    several turns from reading as an accusation."""
    async with async_session_factory() as session:
        run, task = await _bound_run(session, "run-div-6", "task-div-6")
    await evaluate_run_end("run-div-6")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-div-6")
        await apply_transition(session, task, "completed", run_actor("run-later", "worker"))
        await session.commit()

        divergence = await _divergence_for(session, "run-div-6")
        assert divergence.resolved_at is not None


@pytest.mark.asyncio
async def test_the_record_survives_its_own_resolution(app):
    async with async_session_factory() as session:
        await _bound_run(session, "run-div-7", "task-div-7")
    await evaluate_run_end("run-div-7")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-div-7")
        await apply_transition(session, task, "completed", operator())
        await session.commit()

        divergence = await _divergence_for(session, "run-div-7")
        assert divergence is not None
        assert divergence.outcome == "surfaced"


@pytest.mark.asyncio
async def test_the_runtime_s_own_move_does_not_close_a_divergence(app):
    """Only an actor transition counts. Binding a second run to the same task is the runtime
    talking to itself, and must not clear a record of work being dropped."""
    async with async_session_factory() as session:
        await _bound_run(session, "run-div-8", "task-div-8")
    await evaluate_run_end("run-div-8")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-div-8")
        task.status = "assigned"
        second = Run(id="run-div-8b", project_id="proj-test", agent="worker", status="running")
        session.add(second)
        await session.flush()
        await bind_run_to_task(session, second, task)
        await session.commit()

        divergence = await _divergence_for(session, "run-div-8")
        assert divergence.resolved_at is None


# ---------------------------------------------------------------------------
# The policies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_default_policy_starts_nothing(app):
    """What every task already on a board gets. Shipping this must not begin spending tokens."""
    async with async_session_factory() as session:
        await _bound_run(session, "run-pol-1", "task-pol-1")
    await evaluate_run_end("run-pol-1")

    async with async_session_factory() as session:
        assert await _queued_for(session, "worker") == []


@pytest.mark.asyncio
async def test_retry_queues_one_run_of_the_same_agent(app):
    async with async_session_factory() as session:
        await _bound_run(session, "run-pol-2", "task-pol-2", policy="retry")
    await evaluate_run_end("run-pol-2")

    async with async_session_factory() as session:
        queued = await _queued_for(session, "worker")
        assert len(queued) == 1
        assert queued[0].task_id == "task-pol-2"
        assert queued[0].divergence_source_run_id == "run-pol-2"
        # Told what the task is and what it may do, not merely that it forgot.
        assert "task-pol-2" in queued[0].content
        assert "in_progress" in queued[0].content

        divergence = await _divergence_for(session, "run-pol-2")
        assert divergence.outcome == "retried"


@pytest.mark.asyncio
async def test_escalation_reassigns_the_task_and_runs_the_stronger_agent(app):
    async with async_session_factory() as session:
        await _agent(session, "reviewer")
        await _bound_run(
            session,
            "run-pol-3",
            "task-pol-3",
            policy="escalate",
            escalation_agent="reviewer",
            assignee="worker",
        )
    await evaluate_run_end("run-pol-3")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-pol-3")
        assert task.assignee == "reviewer"

        queued = await _queued_for(session, "reviewer")
        assert len(queued) == 1
        assert queued[0].task_id == "task-pol-3"

        divergence = await _divergence_for(session, "run-pol-3")
        assert divergence.outcome == "escalated"
        # Reversible: the board changed under the operator, and the record says what it was.
        assert divergence.previous_assignee == "worker"


@pytest.mark.asyncio
async def test_escalation_naming_no_agent_surfaces(app):
    async with async_session_factory() as session:
        await _bound_run(session, "run-pol-4", "task-pol-4", policy="escalate")
    await evaluate_run_end("run-pol-4")

    async with async_session_factory() as session:
        divergence = await _divergence_for(session, "run-pol-4")
        assert divergence.policy_applied == "escalate"
        assert divergence.outcome == "surfaced"


@pytest.mark.asyncio
async def test_escalation_to_an_agent_that_does_not_exist_surfaces(app):
    """Escalating into a name nobody answers to would leave the work stalled behind a record
    claiming it moved."""
    async with async_session_factory() as session:
        await _bound_run(
            session, "run-pol-5", "task-pol-5", policy="escalate", escalation_agent="ghost"
        )
    await evaluate_run_end("run-pol-5")

    async with async_session_factory() as session:
        divergence = await _divergence_for(session, "run-pol-5")
        assert divergence.outcome == "surfaced"
        assert await _queued_for(session, "ghost") == []
        task = await session.get(Task, "task-pol-5")
        # The claim is that the task did not move to a name nobody answers to. It used to be
        # written `is None`, which held only because binding a run named nobody at all; since
        # 2026-08-24 a bound run puts its own agent on the task (F6/F18), so the assertion has to
        # say what it actually means — still with the agent that ran it, never with the ghost.
        assert task.assignee == "worker"


# ---------------------------------------------------------------------------
# The bound — the reason no chain can run forever
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_retry_that_also_diverges_does_not_retry_again(app):
    async with async_session_factory() as session:
        await _bound_run(session, "run-chain-1", "task-chain-1", policy="retry")
    await evaluate_run_end("run-chain-1")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-chain-1")
        task.status = "assigned"
        response = Run(
            id="run-chain-1b",
            project_id="proj-test",
            agent="worker",
            status="running",
            divergence_source_run_id="run-chain-1",
        )
        session.add(response)
        await session.flush()
        await bind_run_to_task(session, response, task)
        response.status = "completed"
        await session.commit()

    await evaluate_run_end("run-chain-1b")

    async with async_session_factory() as session:
        assert len(await _queued_for(session, "worker")) == 1
        divergence = await _divergence_for(session, "run-chain-1b")
        assert divergence.outcome == "surfaced"


@pytest.mark.asyncio
async def test_a_retry_that_diverges_escalates_when_the_task_names_an_agent(app):
    async with async_session_factory() as session:
        await _agent(session, "senior")
        await _bound_run(
            session,
            "run-chain-2",
            "task-chain-2",
            policy="retry",
            escalation_agent="senior",
        )
    await evaluate_run_end("run-chain-2")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-chain-2")
        task.status = "assigned"
        response = Run(
            id="run-chain-2b",
            project_id="proj-test",
            agent="worker",
            status="running",
            divergence_source_run_id="run-chain-2",
        )
        session.add(response)
        await session.flush()
        await bind_run_to_task(session, response, task)
        response.status = "completed"
        await session.commit()

    await evaluate_run_end("run-chain-2b")

    async with async_session_factory() as session:
        divergence = await _divergence_for(session, "run-chain-2b")
        assert divergence.outcome == "escalated"
        assert len(await _queued_for(session, "senior")) == 1


@pytest.mark.asyncio
async def test_an_escalation_that_diverges_does_not_escalate_again(app):
    """Without this the escalation path loops: the same policy and the same escalation agent are
    still on the task, so it would escalate to the same agent forever."""
    async with async_session_factory() as session:
        await _agent(session, "senior2")
        await _bound_run(
            session,
            "run-chain-3",
            "task-chain-3",
            policy="escalate",
            escalation_agent="senior2",
        )
    await evaluate_run_end("run-chain-3")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-chain-3")
        task.status = "assigned"
        response = Run(
            id="run-chain-3b",
            project_id="proj-test",
            agent="senior2",
            status="running",
            divergence_source_run_id="run-chain-3",
        )
        session.add(response)
        await session.flush()
        await bind_run_to_task(session, response, task)
        response.status = "completed"
        await session.commit()

    await evaluate_run_end("run-chain-3b")

    async with async_session_factory() as session:
        divergence = await _divergence_for(session, "run-chain-3b")
        assert divergence.outcome == "surfaced"
        # Still exactly the one queued by the first escalation.
        assert len(await _queued_for(session, "senior2")) == 1


@pytest.mark.asyncio
async def test_progress_resets_the_chain(app):
    """The bound exists to stop a stuck agent burning tokens, not to ration a task's whole life."""
    async with async_session_factory() as session:
        await _bound_run(session, "run-chain-4", "task-chain-4", policy="retry")
    await evaluate_run_end("run-chain-4")

    async with async_session_factory() as session:
        task = await session.get(Task, "task-chain-4")
        response = Run(
            id="run-chain-4b",
            project_id="proj-test",
            agent="worker",
            status="running",
            divergence_source_run_id="run-chain-4",
        )
        session.add(response)
        await session.flush()
        await bind_run_to_task(session, response, task)
        # This one did the work.
        await apply_transition(session, task, "completed", run_actor(response.id, response.agent))
        response.status = "completed"
        await session.commit()

    assert await evaluate_run_end("run-chain-4b") is None

    # A later independent run — no source — gets the full policy again.
    async with async_session_factory() as session:
        task = await session.get(Task, "task-chain-4")
        task.status = "assigned"
        third = Run(id="run-chain-4c", project_id="proj-test", agent="worker", status="running")
        session.add(third)
        await session.flush()
        await bind_run_to_task(session, third, task)
        third.status = "completed"
        await session.commit()

    await evaluate_run_end("run-chain-4c")

    async with async_session_factory() as session:
        divergence = await _divergence_for(session, "run-chain-4c")
        assert divergence.outcome == "retried"


# ---------------------------------------------------------------------------
# The record names its answer once the answer exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_response_run_is_stamped_onto_the_divergence(app):
    """It could not be named when the row was written — the answer was queued, and becomes a run
    only when the agent is next free."""
    async with async_session_factory() as session:
        await _bound_run(session, "run-resp-1", "task-resp-1", policy="retry")
    await evaluate_run_end("run-resp-1")

    async with async_session_factory() as session:
        await record_response_run(session, "run-resp-1", "run-resp-1b")
        await session.commit()

        divergence = await _divergence_for(session, "run-resp-1")
        assert divergence.response_run_id == "run-resp-1b"
