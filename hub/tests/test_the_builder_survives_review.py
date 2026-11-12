"""`where-each-task-stands-is-visible-on-the-board`, FR-7: the builder is whoever holds the task as
it completes, stays through the hand-off to a reviewer, and is replaced by whoever holds it at a
later completion."""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator

pytestmark = pytest.mark.asyncio


async def _task(db, suffix: str, assignee: str) -> Task:
    task = Task(
        id=f"task-bsr{suffix}",
        project_id="proj-test",
        title="Built",
        status="in_progress",
        assignee=assignee,
    )
    db.add(task)
    await db.commit()
    return task


async def test_the_builder_is_kept_when_the_task_is_handed_to_a_reviewer(app):
    async with async_session_factory() as db:
        task = await _task(db, "keep", "DeveloperSonnet2")
        await apply_transition(db, task, "completed", operator())
        await db.commit()
        assert task.builder == "DeveloperSonnet2"

        task.assignee = "QA"
        await apply_transition(db, task, "under_review", operator())
        await db.commit()
        await db.refresh(task)

    assert task.builder == "DeveloperSonnet2"
    assert task.assignee == "QA"


async def test_a_second_completion_names_whoever_holds_it_then(app):
    async with async_session_factory() as db:
        task = await _task(db, "again", "D")
        await apply_transition(db, task, "completed", operator())
        await apply_transition(db, task, "revision_needed", operator())
        await db.commit()
        task.assignee = "E"
        await apply_transition(db, task, "in_progress", operator())
        await apply_transition(db, task, "completed", operator())
        await db.commit()
        await db.refresh(task)

    assert task.builder == "E"
