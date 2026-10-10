"""`a-tasks-prerequisites-can-be-declared-at-creation-and-in-its-drawer` (F571), task `create`.

`depends_on` on the operator's `POST /tasks`, the agent plane's `POST /agent-actions/tasks` and the
MCP `create_task`, written through `create_task_for_actor` so there is one path. Each test reads the
graph back through `GET /tasks/{id}` (`prerequisites`, `dependents`), the way the drawer does, and
the refusal cases read the table so "nothing left behind" cannot hide in a list's paging.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import Task, TaskDependency

from .test_a_document_says_how_it_will_be_built import run_headers  # noqa: F401  (a fixture)

BASE = "/api/v1/projects/proj-test"
AGENT_TASKS = "/api/v1/agent-actions/tasks"


async def _task(app, auth_headers, title, **extra):
    response = await app.post(f"{BASE}/tasks", headers=auth_headers, json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


async def _get(app, auth_headers, task_id):
    response = await app.get(f"{BASE}/tasks/{task_id}", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _count(model) -> int:
    async with async_session_factory() as session:
        return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_the_operator_creates_a_task_that_depends_on_two_others(app, auth_headers):
    a = await _task(app, auth_headers, "A")
    b = await _task(app, auth_headers, "B")

    created = await _task(app, auth_headers, "D", depends_on=[a["id"], b["id"]])

    assert {p["id"] for p in created["prerequisites"]} == {a["id"], b["id"]}
    detail = await _get(app, auth_headers, created["id"])
    assert {p["id"] for p in detail["prerequisites"]} == {a["id"], b["id"]}
    assert [d["id"] for d in (await _get(app, auth_headers, a["id"]))["dependents"]] == [
        created["id"]
    ]


@pytest.mark.asyncio
async def test_a_repeated_prerequisite_is_one_edge(app, auth_headers):
    a = await _task(app, auth_headers, "A")

    created = await _task(app, auth_headers, "D", depends_on=[a["id"], a["id"]])

    assert [p["id"] for p in created["prerequisites"]] == [a["id"]]
    assert await _count(TaskDependency) == 1


@pytest.mark.asyncio
async def test_an_unknown_prerequisite_is_refused_naming_it_and_leaves_nothing(app, auth_headers):
    a = await _task(app, auth_headers, "A")

    refused = await app.post(
        f"{BASE}/tasks",
        headers=auth_headers,
        json={"title": "D", "depends_on": [a["id"], "task-nothere"]},
    )

    assert refused.status_code == 422
    assert "task-nothere" in refused.json()["detail"]
    assert await _count(Task) == 1
    assert await _count(TaskDependency) == 0


@pytest.mark.asyncio
async def test_a_task_naming_its_own_id_is_refused_and_leaves_nothing(app, auth_headers):
    refused = await app.post(
        f"{BASE}/tasks",
        headers=auth_headers,
        json={"id": "task-mine", "title": "D", "depends_on": ["task-mine"]},
    )

    assert refused.status_code == 422
    assert "task-mine" in refused.json()["detail"]
    assert await _count(Task) == 0
    assert await _count(TaskDependency) == 0


@pytest.mark.asyncio
async def test_a_prerequisite_in_another_project_is_unknown(app, auth_headers):
    refused = await app.post(
        f"{BASE}/tasks",
        headers=auth_headers,
        json={"title": "D", "depends_on": ["task-elsewhere"]},
    )

    assert refused.status_code == 422


@pytest.mark.asyncio
async def test_an_agent_creates_a_task_that_depends_on_one(
    app, auth_headers, run_headers  # noqa: F811
):
    a = await _task(app, auth_headers, "A")

    response = await app.post(
        AGENT_TASKS, headers=run_headers, json={"title": "C", "depends_on": [a["id"]]}
    )

    assert response.status_code == 201, response.text
    assert [p["id"] for p in response.json()["prerequisites"]] == [a["id"]]
    detail = await _get(app, auth_headers, response.json()["id"])
    assert [p["id"] for p in detail["prerequisites"]] == [a["id"]]


@pytest.mark.asyncio
async def test_an_agent_naming_an_unknown_prerequisite_is_refused_and_leaves_nothing(
    app, run_headers  # noqa: F811
):
    refused = await app.post(
        AGENT_TASKS, headers=run_headers, json={"title": "C", "depends_on": ["task-nothere"]}
    )

    assert refused.status_code == 422
    assert "task-nothere" in refused.json()["detail"]
    assert await _count(Task) == 0


def test_the_mcp_tool_and_both_renderings_carry_depends_on():
    import asyncio

    from hub.api.v1.agents import _operations
    from hub.mcp_server import mcp

    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "create_task")
    assert "depends_on" in (tool.parameters or {}).get("properties", {})
    operation = next(op for op in _operations() if op.tool == "create_task")
    assert "depends_on" in operation.fields
    assert "depends_on" in operation.args
