"""Only the builder profile completes (`a-two-profile-build-cannot-deadlock-and-a-stall-says-so`,
FR-5, FR-6; task builder-only-completes).

A move to `completed` by a run whose agent is not the task's builder profile, as named at the time
of the move, is refused naming the builder (D3). Any thread of the builder profile may complete; so
may a run the operator started themselves (AW-101) and the Hub's mender (task-e5c9147da336).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import stalls
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Build, Conversation, Run, Task, TaskTransition
from hub.task_transition_service import (
    ActorNotPermittedError,
    apply_transition,
    completion_refusal,
)
from hub.task_transitions import Actor as TransitionActor

pytestmark = pytest.mark.asyncio

P = "proj-test"
TASK = "task-1"


@pytest.fixture(autouse=True)
def _database(app):
    """The `app` fixture creates the test database."""
    return app


async def _add(*rows) -> None:
    async with async_session_factory() as db:
        for row in rows:
            db.add(row)
        await db.commit()


async def _task(*, builder: str | None = "Developer", **columns) -> None:
    await _add(
        Task(
            id=TASK,
            project_id=P,
            readable_id="TPBCD-9",
            title="A task",
            status="in_progress",
            assignee=builder,
            builder=builder,
            **columns,
        )
    )


async def _run(agent: str, conversation: str, *, initiator: str = "autonomous") -> str:
    """A run of *agent* in its own conversation, bound to the task (it holds it)."""
    run_id = f"run-{conversation}"
    await _add(
        Conversation(
            id=conversation, project_id=P, agent=agent, origin="job", lineage_id=conversation
        ),
        Run(
            id=run_id,
            project_id=P,
            agent=agent,
            status="running",
            conversation_id=conversation,
            initiator=initiator,
            task_id=TASK,
        ),
    )
    return run_id


async def _complete(agent: str, run_id: str) -> None:
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        await apply_transition(db, task, "completed", TransitionActor("run", run_id, agent))
        await db.commit()


async def _status() -> str:
    async with async_session_factory() as db:
        return (await db.get(Task, TASK)).status


async def _completers() -> list:
    async with async_session_factory() as db:
        rows = await db.execute(
            select(TaskTransition.actor_agent)
            .where(TaskTransition.task_id == TASK, TaskTransition.to_status == "completed")
            .order_by(TaskTransition.sequence)
        )
        return [agent for (agent,) in rows.all()]


async def test_checker_completion_refused():
    """checker-completion-refused: QA, a run the operator did not start, is refused naming
    Developer as the builder; the task stays in_progress (as run-4dcfa9265fd8 was on 11-21)."""
    await _task()
    qa = await _run("QA", "conv-qa")
    with pytest.raises(ActorNotPermittedError) as refused:
        await _complete("QA", qa)
    message = str(refused.value)
    assert "Developer is this task's builder" in message
    assert "only its builder completes it" in message
    assert "run-" not in message and "conv-" not in message
    assert await _status() == "in_progress"
    assert await _completers() == []


async def test_completion_refusal_reads_the_same_rule():
    """The read-only probe the fast checks consult refuses too, so no checks run for QA's move."""
    await _task()
    qa = await _run("QA", "conv-qa")
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        refusal = await completion_refusal(db, task, TransitionActor("run", qa, "QA"))
    assert isinstance(refusal, ActorNotPermittedError)
    assert "Developer is this task's builder" in str(refusal)


async def test_another_builder_thread_completes():
    """another-builder-thread-completes: the build started in Developer thread A; a run in thread B
    completes it."""
    await _task()
    await _run("Developer", "conv-dev-a")
    b = await _run("Developer", "conv-dev-b")
    await _complete("Developer", b)
    assert await _status() == "completed"
    assert await _completers() == ["Developer"]


async def test_reassigned_builder_completes():
    """reassigned-builder-completes: built by DeveloperOpus2, reassigned to DeveloperOpus (as
    task-ef2c024ea80c was on 11-14). DeveloperOpus2 is refused naming DeveloperOpus; DeveloperOpus
    completes."""
    await _task(builder="DeveloperOpus2")
    old = await _run("DeveloperOpus2", "conv-old")
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        task.builder = "DeveloperOpus"
        task.assignee = "DeveloperOpus"
        await db.commit()
    with pytest.raises(ActorNotPermittedError) as refused:
        await _complete("DeveloperOpus2", old)
    assert "DeveloperOpus is this task's builder" in str(refused.value)
    new = await _run("DeveloperOpus", "conv-new")
    await _complete("DeveloperOpus", new)
    assert await _completers() == ["DeveloperOpus"]
    # And afterwards: the earlier builder may not complete it again once it is reopened.
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        task.status = "in_progress"
        await db.commit()
    with pytest.raises(ActorNotPermittedError) as again:
        await _complete("DeveloperOpus2", old)
    assert "DeveloperOpus is this task's builder" in str(again.value)


async def test_builder_named_by_the_build_when_the_task_names_none():
    """With no builder on the task, the build's default builder is the builder."""
    await _add(
        Build(
            id="build-1",
            project_id=P,
            document_id="spdoc-x",
            state="running",
            driver="flow",
            level="reviewed",
            people={"builder": "Developer", "checker": "QA"},
        )
    )
    await _task(builder=None, build_id="build-1")
    qa = await _run("QA", "conv-qa")
    with pytest.raises(ActorNotPermittedError) as refused:
        await _complete("QA", qa)
    assert "Developer is this task's builder" in str(refused.value)


async def test_a_folded_name_counts_as_the_builder():
    """A name folded into the builder profile completes as that profile."""
    await _add(
        Agent(id="agt-dev", project_id=P, name="Developer", lifecycle="open"),
        Agent(
            id="agt-dev2",
            project_id=P,
            name="DeveloperOld",
            lifecycle="archived",
            folded_into="Developer",
        ),
    )
    await _task()
    run = await _run("DeveloperOld", "conv-old")
    await _complete("DeveloperOld", run)
    assert await _status() == "completed"


async def test_no_builder_determinable_permits():
    """No builder on the task, no build, no recorded start: permit to act."""
    await _task(builder=None)
    qa = await _run("QA", "conv-qa")
    await _complete("QA", qa)
    assert await _status() == "completed"


async def test_operator_started_architect_completes():
    """operator-started-architect-completes: built by CodexSol; an Architect run the operator
    started (initiator operator), as in AW-101, completes it."""
    await _task(builder="CodexSol")
    architect = await _run("Architect", "conv-arch", initiator="operator")
    await _complete("Architect", architect)
    assert await _status() == "completed"
    assert await _completers() == ["Architect"]


async def test_mender_completes():
    """mender-completes: built by Developer; a run of the Hub's mender completes it, as on
    task-e5c9147da336."""
    await _add(
        Agent(
            id="agt-mender",
            project_id=P,
            name="mender",
            lifecycle="open",
            config={"hub_role": stalls.HUB_ROLE},
        )
    )
    await _task()
    run = await _run("mender", "conv-mender")
    await _complete("mender", run)
    assert await _status() == "completed"
    assert await _completers() == ["mender"]


async def test_the_operator_completes():
    """The operator is not a run and is never refused by this guard."""
    await _task()
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        await apply_transition(db, task, "completed", TransitionActor("operator"))
        await db.commit()
    assert await _status() == "completed"
