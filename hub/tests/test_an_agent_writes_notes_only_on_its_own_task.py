"""F709: an agent's run wrote the notes of another agent's task.

Found in the 2026-10-18 sweep: alpha's run, bound to its own task, called `update_task` with notes
only on beta's task and got 200 — `notes: "Attempting to set description to hijacked"`. The status
guards look only at moves to in_progress/completed, and the operator-only field check covered
assignee/priority/description, not notes; notes then become the verdict's evidence text.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task

PROJECT = "proj-test"
pytestmark = pytest.mark.asyncio


async def _run(run_id: str, agent: str, task_id=None) -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent=agent,
                status="running",
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _task(task_id: str, **kwargs) -> None:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id=PROJECT,
                title="t",
                status=kwargs.pop("status", "assigned"),
                notes=kwargs.pop("notes", "original"),
                **kwargs,
            )
        )
        await session.commit()


async def _notes(task_id: str):
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).notes


async def test_a_run_cannot_write_notes_on_another_agents_task(app):
    await _task("task-own-a", assignee="alpha", status="in_progress")
    await _task("task-beta", assignee="beta")
    headers = await _run("run-alpha-1", "alpha", task_id="task-own-a")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-beta", headers=headers, json={"notes": "hijacked"}
    )
    assert response.status_code == 403, response.text
    assert "cannot write the notes" in response.text
    assert await _notes("task-beta") == "original"

    # Restating the task's current status is not a move, so it does not carry notes past the check.
    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-beta",
        headers=headers,
        json={"status": "assigned", "notes": "hijacked"},
    )
    assert response.status_code == 403, response.text
    assert await _notes("task-beta") == "original"


async def test_the_assignee_and_a_bound_run_still_write_notes(app):
    await _task("task-mine", assignee="alpha")
    headers = await _run("run-alpha-2", "alpha")
    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-mine", headers=headers, json={"notes": "progress"}
    )
    assert response.status_code == 200, response.text
    assert await _notes("task-mine") == "progress"

    # A reviewer's run is bound to the task it inspects, though another agent holds it.
    await _task("task-reviewed", assignee="author", status="under_review")
    headers = await _run("run-rev-1", "rev", task_id="task-reviewed")
    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-reviewed", headers=headers, json={"notes": "looked"}
    )
    assert response.status_code == 200, response.text
    assert await _notes("task-reviewed") == "looked"


async def test_claiming_an_unassigned_task_may_carry_notes(app):
    await _task("task-free", status="pending")
    headers = await _run("run-claim-1", "gamma")
    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-free",
        headers=headers,
        json={"status": "in_progress", "notes": "taking it"},
    )
    assert response.status_code == 200, response.text
    assert await _notes("task-free") == "taking it"


async def test_the_operator_writes_any_tasks_notes(app, auth_headers):
    await _task("task-op", assignee="beta")
    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/tasks/task-op", headers=auth_headers, json={"notes": "op"}
    )
    assert response.status_code == 200, response.text
    assert await _notes("task-op") == "op"
