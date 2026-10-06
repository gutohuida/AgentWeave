"""F519: a reviewer is told what the task under review builds on, and where that work already is.

On the trial Hub `:8010` the F510 slice's fix task depended on its acceptance-test task, already
merged. The reviewer judged the fix's diff alone, found no tests in it, and sent correct work back:
the seven tests were on the main branch and passed on the fix's branch.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskDependency, TaskIntegration
from hub.review_turn import verdict_evidence_sentence

PROJECT = "proj-test"


async def _tasks(*, merged: bool):
    async with async_session_factory() as session:
        session.add(
            Task(
                id="task-tests",
                project_id=PROJECT,
                title="Failing acceptance tests",
                description="",
                status="approved" if merged else "in_progress",
            )
        )
        session.add(
            Task(
                id="task-fix",
                project_id=PROJECT,
                title="The fix",
                description="",
                status="under_review",
            )
        )
        await session.flush()
        session.add(
            TaskDependency(
                id="dep-1", project_id=PROJECT, task_id="task-fix", depends_on_task_id="task-tests"
            )
        )
        if merged:
            session.add(
                TaskIntegration(
                    id="tint-1",
                    project_id=PROJECT,
                    task_id="task-tests",
                    commit_sha="252076c33a60bcd2",
                    outcome="merged",
                    actor_kind="operator",
                )
            )
        await session.commit()


async def _sentence(task_id="task-fix"):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        return await verdict_evidence_sentence(session, task, may_decide=False) or ""


@pytest.mark.asyncio
async def test_a_merged_prerequisite_is_named_with_its_commit(app):
    await _tasks(merged=True)
    sentence = await _sentence()
    assert "task-tests" in sentence and "Failing acceptance tests" in sentence
    assert "252076c33a60" in sentence
    assert "not in this task's diff" in sentence


@pytest.mark.asyncio
async def test_an_unmerged_prerequisite_is_named_with_its_status(app):
    await _tasks(merged=False)
    sentence = await _sentence()
    assert "task-tests" in sentence and "in_progress" in sentence


@pytest.mark.asyncio
async def test_a_task_with_no_prerequisites_is_told_nothing_new(app):
    await _tasks(merged=True)
    assert "builds on" not in await _sentence("task-tests")
