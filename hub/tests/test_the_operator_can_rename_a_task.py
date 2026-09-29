"""The operator can rename a task — F125, `openspec/changes/the-operator-can-rename-a-task/`.

A task's title was written once, at creation, and nobody could change it afterwards: the operator's
own `PATCH /projects/{p}/tasks/{id}` answered `422 extra_forbidden` for a `title` key, because
`TaskUpdate` never declared the field. The title is the line the board and the drawer show, and it
goes stale exactly when work moves.

The operator may rename; an agent may not (design D1/D2). A rename is not a transition (D3): no new
`task_transitions` row. Blank and explicit `null` are both refused as "a task cannot have no title";
an omitted `title` leaves it alone.
"""

import inspect

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task, TaskTransition

PROJECT = "proj-test"


async def _active_run(run_id: str, agent: str) -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _make_task(task_id: str, **kwargs) -> None:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id=PROJECT,
                title=kwargs.pop("title", "Original title"),
                status=kwargs.pop("status", "pending"),
                **kwargs,
            )
        )
        await session.commit()


async def _transition_count(task_id: str) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskTransition).where(TaskTransition.task_id == task_id)
        )
        return len(result.scalars().all())


@pytest.mark.asyncio
async def test_operator_rename_trims_and_writes_no_transition(app, auth_headers):
    await _make_task("task-rename-1")

    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/tasks/task-rename-1",
        headers=auth_headers,
        json={"title": "  New name  "},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "New name"

    async with async_session_factory() as session:
        task = await session.get(Task, "task-rename-1")
        assert task.title == "New name"
    assert await _transition_count("task-rename-1") == 0


@pytest.mark.asyncio
async def test_operator_rename_to_blank_is_refused(app, auth_headers):
    await _make_task("task-rename-2")

    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/tasks/task-rename-2",
        headers=auth_headers,
        json={"title": "   "},
    )
    assert response.status_code == 422, response.text
    assert "cannot be blank" in response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-rename-2")
        assert task.title == "Original title"


@pytest.mark.asyncio
async def test_operator_rename_to_null_is_refused_and_omitted_title_leaves_it_alone(
    app, auth_headers
):
    await _make_task("task-rename-3")

    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/tasks/task-rename-3",
        headers=auth_headers,
        json={"title": None},
    )
    assert response.status_code == 422, response.text
    assert "cannot be blank" in response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-rename-3")
        assert task.title == "Original title"

    # Control: a PATCH that omits `title` entirely leaves it untouched.
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/tasks/task-rename-3",
        headers=auth_headers,
        json={"priority": "high"},
    )
    assert response.status_code == 200, response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-rename-3")
        assert task.title == "Original title"
        assert task.priority == "high"


@pytest.mark.asyncio
async def test_agent_rename_is_refused(app):
    headers = await _active_run("run-rename-1", "renamer")
    await _make_task("task-rename-4")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-rename-4",
        headers=headers,
        json={"title": "x"},
    )
    assert response.status_code == 403, response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-rename-4")
        assert task.title == "Original title"


@pytest.mark.asyncio
async def test_agent_rename_bundled_with_a_status_move_is_refused_before_any_write(app):
    """The refusal is a pre-write check, not one after the transition: bundling `title` with a
    legal `status` move must not let either field through, and must leave no transition row —
    proof the check runs before `apply_transition`, not after it."""
    headers = await _active_run("run-rename-2", "renamer2")
    await _make_task("task-rename-5", status="assigned", assignee="renamer2")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-rename-5",
        headers=headers,
        json={"status": "in_progress", "title": "x"},
    )
    assert response.status_code == 403, response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-rename-5")
        assert task.status == "assigned"
        assert task.title == "Original title"
    assert await _transition_count("task-rename-5") == 0


def test_title_refusal_precedes_the_transition_and_assignee_write_in_source():
    """Source-order proof, since a refusal placed after the transition would also leave the DB
    unchanged (the uncommitted session is discarded) and so could not be told apart by behaviour
    alone (design D2)."""
    from hub.api.v1.tasks import update_task_for_actor

    source = inspect.getsource(update_task_for_actor)
    title_refusal_pos = source.index('"title" in body.model_fields_set and not actor.is_operator')
    transition_pos = source.index("apply_transition(")
    assignee_write_pos = source.index("task.assignee = body.assignee")
    assert title_refusal_pos < transition_pos
    assert title_refusal_pos < assignee_write_pos
