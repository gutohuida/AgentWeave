"""F36: an operator can declare a dependency between two tasks they created.

`TaskDependency` rows were written in exactly one place — `spec_tasks.materialise()`, reached only
when an approved document carried `depends_on` keys. `TaskUpdate` refused the field
`422 extra_forbidden` and no route reached it, so a whole subsystem — `dependency_gate`, the
Dependencies board tab, two tables, and the `prerequisites`/`dependents` fields on every task
response — was reachable only if an agent happened to author the right keys. In the sweep the agent
authored a five-task decomposition with no `depends_on` at all, so the graph came out empty and the
gate was never exercisable.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task

TASKS = "/api/v1/projects/proj-test/tasks"


async def _tasks(*ids):
    async with async_session_factory() as session:
        for task_id in ids:
            session.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title=f"Task {task_id}",
                    status="pending",
                )
            )
        await session.commit()


async def _declare(app, auth_headers, task_id, depends_on):
    return await app.post(
        f"{TASKS}/{task_id}/dependencies",
        json={"depends_on": depends_on},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_an_operator_can_declare_that_b_needs_a(app, auth_headers):
    await _tasks("task-a", "task-b")

    response = await _declare(app, auth_headers, "task-b", "task-a")

    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "added"


@pytest.mark.asyncio
async def test_the_declared_dependency_reaches_the_gate(app, auth_headers):
    """The point of the finding: the subsystem was unreachable, not absent. Once an operator can
    build the graph, everything downstream of it starts working."""
    await _tasks("task-gate-a", "task-gate-b")
    await _declare(app, auth_headers, "task-gate-b", "task-gate-a")

    moved = await app.patch(
        f"{TASKS}/task-gate-b", json={"status": "in_progress"}, headers=auth_headers
    )

    assert moved.status_code == 409, moved.text
    assert "task-gate-a" in str(moved.json()["detail"])


@pytest.mark.asyncio
async def test_the_dependency_is_visible_on_the_task(app, auth_headers):
    await _tasks("task-vis-a", "task-vis-b")
    await _declare(app, auth_headers, "task-vis-b", "task-vis-a")

    body = (await app.get(f"{TASKS}/task-vis-b", headers=auth_headers)).json()

    assert [row["id"] for row in body["prerequisites"]] == ["task-vis-a"]


@pytest.mark.asyncio
async def test_a_cycle_is_refused_and_names_it(app, auth_headers):
    """The check the document path never had either: `a -> b -> a` produced a graph on which the
    gate refused both tasks forever, each waiting on the other."""
    await _tasks("task-cyc-a", "task-cyc-b")
    await _declare(app, auth_headers, "task-cyc-b", "task-cyc-a")

    response = await _declare(app, auth_headers, "task-cyc-a", "task-cyc-b")

    assert response.status_code == 409, response.text
    assert "task-cyc-b" in response.json()["detail"]


@pytest.mark.asyncio
async def test_an_indirect_cycle_is_refused(app, auth_headers):
    """Walked, not just compared: `c -> b -> a` then `a -> c` closes a three-task loop."""
    await _tasks("task-ind-a", "task-ind-b", "task-ind-c")
    await _declare(app, auth_headers, "task-ind-b", "task-ind-a")
    await _declare(app, auth_headers, "task-ind-c", "task-ind-b")

    response = await _declare(app, auth_headers, "task-ind-a", "task-ind-c")

    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_self_dependency_is_refused(app, auth_headers):
    await _tasks("task-self")

    response = await _declare(app, auth_headers, "task-self", "task-self")

    assert response.status_code == 400, response.text
    assert "itself" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_missing_task_is_named(app, auth_headers):
    await _tasks("task-real")

    response = await _declare(app, auth_headers, "task-real", "task-imaginary")

    assert response.status_code == 404, response.text
    assert "task-imaginary" in response.json()["detail"]


@pytest.mark.asyncio
async def test_declaring_the_same_edge_twice_is_not_a_conflict(app, auth_headers):
    """An operator who clicks twice has not made a mistake."""
    await _tasks("task-dup-a", "task-dup-b")
    await _declare(app, auth_headers, "task-dup-b", "task-dup-a")

    response = await _declare(app, auth_headers, "task-dup-b", "task-dup-a")

    assert response.status_code == 201, response.text
    assert response.json()["outcome"] == "duplicate"


@pytest.mark.asyncio
async def test_a_dependency_can_be_withdrawn(app, auth_headers):
    await _tasks("task-rm-a", "task-rm-b")
    await _declare(app, auth_headers, "task-rm-b", "task-rm-a")

    removed = await app.delete(f"{TASKS}/task-rm-b/dependencies/task-rm-a", headers=auth_headers)

    assert removed.status_code == 204, removed.text
    moved = await app.patch(
        f"{TASKS}/task-rm-b", json={"status": "in_progress"}, headers=auth_headers
    )
    assert moved.status_code == 200, moved.text


@pytest.mark.asyncio
async def test_withdrawing_an_edge_that_is_not_there_says_so(app, auth_headers):
    await _tasks("task-none-a", "task-none-b")

    removed = await app.delete(
        f"{TASKS}/task-none-b/dependencies/task-none-a", headers=auth_headers
    )

    assert removed.status_code == 404, removed.text
