"""A task added to a running build gets the build's people (`added-task-people`, FR-7).

Named by acceptance criterion: `-k ac_added_task_staffed`.
"""

import pytest

from hub import builds
from hub.db.engine import async_session_factory
from hub.db.models import Build, SpecDocument, Task

P = "proj-test"
DOC = "doc-added-people"


async def _running_build(people):
    async with async_session_factory() as db:
        db.add(
            SpecDocument(
                id=DOC,
                project_id=P,
                path="spec/changes/added-people/spec.json",
                title="Added people",
                phase="approved",
                kind="change-spec",
            )
        )
        db.add(
            Build(
                id="build-added-people",
                project_id=P,
                document_id=DOC,
                state="running",
                driver="flow",
                level="reviewed",
                builders=[],
                reviewers=[],
                landing="main",
                people=people,
            )
        )
        await db.commit()


async def _joined(task: Task):
    async with async_session_factory() as db:
        await builds.join_running_build(db, task)
        db.add(task)
        await db.commit()
        marks = await builds.default_marks_by_task(db, [task])
        build = await db.get(Build, task.build_id)
        return builds.checker_of(build, task), marks[task.id]


@pytest.mark.asyncio
async def test_ac_added_task_staffed_takes_the_defaults_and_marks_them(app):
    await _running_build({"builder": "Developer", "checker": "QA", "tasks": {}})
    task = Task(id="task-added-1", project_id=P, title="t", status="pending", spec_document_id=DOC)
    checker, marks = await _joined(task)
    assert (task.build_id, task.level, task.builder) == (
        "build-added-people",
        "reviewed",
        "Developer",
    )
    assert checker == ("QA", "default")
    assert marks == {"builder": True, "checker": True}


@pytest.mark.asyncio
async def test_ac_added_task_staffed_keeps_the_people_it_names(app):
    await _running_build({"builder": "Developer", "checker": "QA", "tasks": {}})
    task = Task(
        id="task-added-2",
        project_id=P,
        title="t",
        status="pending",
        spec_document_id=DOC,
        builder="DeveloperOpus",
    )
    async with async_session_factory() as db:
        await builds.join_running_build(db, task, checker="QA2")
        db.add(task)
        await db.commit()
        build = await db.get(Build, task.build_id)
        marks = await builds.default_marks_by_task(db, [task])
    assert task.builder == "DeveloperOpus"
    assert builds.checker_of(build, task) == ("QA2", "task")
    assert marks[task.id] == {"builder": False, "checker": False}
