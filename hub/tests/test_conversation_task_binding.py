"""The binding that outlives one run.

Before this, only the *first* run of a conversation was bound. Starting work from a board card sent
a task id; a follow-up typed into the composer did not, and nothing carried the binding across
turns. So a five-turn piece of work was checked once, at the end of turn one — when an agent is most
legitimately unfinished, and so where a divergence is least informative — and was silent for the
turn where it actually stopped, which is where "did this ever reach the ledger?" is the right
question.

These cover the three rules that fix it: a turn naming a task rebinds the thread, a turn naming none
inherits, and a binding is released only by an explicit act or a terminal status — never by
inference about what the thread seems to be about (design D6, D7).
"""

import pytest
from sqlalchemy import select

from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Run, Task
from hub.run_task_binding import (
    TERMINAL_FOR_BINDING,
    bind_run_to_task,
    binding_for_conversation,
    rebind_conversation,
    release_conversations_bound_to,
)


async def _conversation(session, conv_id: str, *, task_id: str | None = None) -> Conversation:
    conversation = Conversation(
        id=conv_id,
        project_id="proj-test",
        agent="worker",
        lifecycle="open",
        origin="operator",
        task_id=task_id,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def _task(session, task_id: str, *, status: str = "pending") -> Task:
    task = Task(id=task_id, project_id="proj-test", title=f"Task {task_id}", status=status)
    session.add(task)
    await session.flush()
    return task


# ---------------------------------------------------------------------------
# Inheritance — the hole this closes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_thread_already_about_a_task_lends_it_to_the_next_turn(app):
    """The composer sends no task id, so without this every turn after the first went unchecked."""
    async with async_session_factory() as session:
        await _task(session, "task-conv-1")
        conversation = await _conversation(session, "conv-1", task_id="task-conv-1")
        await session.commit()

        inherited = await binding_for_conversation(session, conversation, "proj-test")
        assert inherited is not None
        assert inherited.id == "task-conv-1"


@pytest.mark.asyncio
async def test_an_unbound_thread_stays_unbound(app):
    """Nothing is inferred. A conversation nobody bound is a conversation whose runs are not
    checked, which is the pre-existing behaviour and must stay available."""
    async with async_session_factory() as session:
        conversation = await _conversation(session, "conv-2")
        await session.commit()
        assert await binding_for_conversation(session, conversation, "proj-test") is None


@pytest.mark.asyncio
async def test_a_deleted_task_unbinds_rather_than_failing_the_turn(app):
    """Removing a row must not cancel work the operator asked for. The turn runs, unbound."""
    async with async_session_factory() as session:
        conversation = await _conversation(session, "conv-3", task_id="task-gone")
        await session.commit()
        assert await binding_for_conversation(session, conversation, "proj-test") is None


@pytest.mark.asyncio
async def test_a_thread_cannot_inherit_another_projects_task(app):
    async with async_session_factory() as session:
        session.add(Task(id="task-other", project_id="proj-other", title="Elsewhere"))
        conversation = await _conversation(session, "conv-4", task_id="task-other")
        await session.commit()
        assert await binding_for_conversation(session, conversation, "proj-test") is None


# ---------------------------------------------------------------------------
# A turn that names a task wins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_naming_a_different_task_rebinds_the_thread(app):
    """The more specific statement wins, so the operator does not have to release an old binding
    before starting something else in the same thread (design D6)."""
    async with async_session_factory() as session:
        await _task(session, "task-conv-5a")
        second = await _task(session, "task-conv-5b")
        conversation = await _conversation(session, "conv-5", task_id="task-conv-5a")

        rebind_conversation(conversation, second)
        await session.commit()

        assert conversation.task_id == "task-conv-5b"
        inherited = await binding_for_conversation(session, conversation, "proj-test")
        assert inherited.id == "task-conv-5b"


@pytest.mark.asyncio
async def test_the_run_still_records_its_own_task(app):
    """`Run.task_id` stays (design D6). Transitions and divergences are attributed to a run, and a
    record that had to join through a conversation to say which task it concerned would be weaker
    for it."""
    async with async_session_factory() as session:
        task = await _task(session, "task-conv-6")
        conversation = await _conversation(session, "conv-6", task_id="task-conv-6")
        run = Run(
            id="run-conv-6",
            project_id="proj-test",
            agent="worker",
            status="running",
            conversation_id=conversation.id,
        )
        session.add(run)
        await session.flush()

        inherited = await binding_for_conversation(session, conversation, "proj-test")
        await bind_run_to_task(session, run, inherited)
        await session.commit()

        assert run.task_id == "task-conv-6"
        assert task.status == "in_progress"


# ---------------------------------------------------------------------------
# Releasing (design D7)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finishing_the_task_releases_every_thread_bound_to_it(app):
    """Otherwise a thread keeps attributing turns to work the operator already decided about, and
    puts stalled markers on something they approved."""
    async with async_session_factory() as session:
        task = await _task(session, "task-conv-7", status="in_progress")
        await _conversation(session, "conv-7a", task_id="task-conv-7")
        await _conversation(session, "conv-7b", task_id="task-conv-7")
        await _conversation(session, "conv-7c", task_id="task-elsewhere")
        await session.commit()

        assert await release_conversations_bound_to(session, task) == 2
        await session.commit()

        result = await session.execute(select(Conversation).where(Conversation.task_id.isnot(None)))
        still_bound = {row.id for row in result.scalars().all()}
        assert still_bound == {"conv-7c"}


@pytest.mark.asyncio
async def test_review_does_not_release_the_binding(app):
    """Work under review comes back often. Releasing there would unbind precisely the thread that
    is about to do the revisions."""
    assert "under_review" not in TERMINAL_FOR_BINDING
    assert "completed" not in TERMINAL_FOR_BINDING
    assert set(TERMINAL_FOR_BINDING) == {"approved", "rejected"}


@pytest.mark.asyncio
async def test_approving_a_task_releases_the_thread_through_the_route(app, auth_headers):
    async with async_session_factory() as session:
        await _task(session, "task-conv-8", status="under_review")
        await _conversation(session, "conv-8", task_id="task-conv-8")
        await session.commit()

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-conv-8",
        headers=auth_headers,
        json={"status": "approved"},
    )
    assert response.status_code == 200, response.text

    async with async_session_factory() as session:
        conversation = await get_conversation_by_id(session, "conv-8")
        assert conversation.task_id is None


@pytest.mark.asyncio
async def test_the_operator_can_release_a_binding_explicitly(app, auth_headers):
    async with async_session_factory() as session:
        await _task(session, "task-conv-9")
        await _conversation(session, "conv-9", task_id="task-conv-9")
        await session.commit()

    response = await app.delete(
        "/api/v1/projects/proj-test/agent/worker/conversations/conv-9/task",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["task_id"] is None

    async with async_session_factory() as session:
        assert (await get_conversation_by_id(session, "conv-9")).task_id is None


@pytest.mark.asyncio
async def test_releasing_an_unbound_thread_is_not_an_error(app, auth_headers):
    """Idempotent: it is the state the caller asked for."""
    async with async_session_factory() as session:
        await _conversation(session, "conv-10")
        await session.commit()

    response = await app.delete(
        "/api/v1/projects/proj-test/agent/worker/conversations/conv-10/task",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["task_id"] is None


@pytest.mark.asyncio
async def test_nothing_infers_a_release_from_what_the_thread_is_about(app):
    """Design D7, asserted as a source scan rather than a behaviour, because the failure it guards
    against is a *new* caller quietly clearing a binding.

    A wrong guess silently stops checking a run, and a mechanism that stops enforcing without
    saying so is worse than one that never started. Only the explicit route and the terminal-status
    release may clear it.
    """
    from pathlib import Path

    hub_package = Path(__file__).resolve().parents[1] / "hub"
    permitted = {"run_task_binding.py", "agent_chat.py", "agent_trigger.py"}
    offenders = []
    for path in hub_package.rglob("*.py"):
        if path.name in permitted:
            continue
        source = path.read_text(encoding="utf-8")
        if "conversation.task_id = " in source or "conversation.task_id=" in source:
            offenders.append(path.name)
    assert (
        offenders == []
    ), f"only the declared release paths may clear a binding, found: {offenders}"
