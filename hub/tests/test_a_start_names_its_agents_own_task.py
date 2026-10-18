"""F687: the operator could start one agent working another agent's task.

Found 2026-10-18: a task assigned to `board`, then `POST /agent/trigger {"agent": "alpha",
"task_id": ...}` -> 200; alpha's run took it `pending -> in_progress -> completed` and the task
ended completed with assignee `board`, which the board credits.

Over HTTP, because the route queues an entry and the binding happens later, out of the
operator's sight: only the request proves the refusal is reachable.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Task

pytestmark = pytest.mark.asyncio

TRIGGER = "/api/v1/projects/proj-test/agent/trigger"


async def _task(task_id: str, *, status: str = "assigned", assignee=None) -> None:
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
        await session.commit()


async def _entries() -> list:
    async with async_session_factory() as session:
        return (await session.execute(select(InboundQueueEntry))).scalars().all()


async def test_starting_an_agent_on_another_agents_task_is_refused(app, auth_headers, add_agent):
    await add_agent("alpha")
    await _task("task-f687-board", assignee="board")

    response = await app.post(
        TRIGGER,
        json={"agent": "alpha", "message": "work", "task_id": "task-f687-board"},
        headers=auth_headers,
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "'board'" in detail and "reassign" in detail
    assert await _entries() == [], "nothing is queued for a start that was refused"


async def test_the_author_still_starts_on_its_task_while_a_reviewer_holds_it(
    app, auth_headers, add_agent
):
    """Under review the assignee is the staffed reviewer, so the holder rule does not apply: the
    author's revision turn is deliberately not refused (F79's band boundary)."""
    await add_agent("author")
    await _task("task-f687-review", status="under_review", assignee="rev")

    response = await app.post(
        TRIGGER,
        json={"agent": "author", "message": "fix", "task_id": "task-f687-review"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("assignee", [None, "alpha"])
async def test_an_agent_still_starts_on_its_own_or_an_unassigned_task(
    app, auth_headers, add_agent, assignee
):
    await add_agent("alpha")
    await _task("task-f687-ok", assignee=assignee)

    response = await app.post(
        TRIGGER,
        json={"agent": "alpha", "message": "work", "task_id": "task-f687-ok"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert [e.task_id for e in await _entries()] == ["task-f687-ok"]
