"""F1120: an agent's `list_tasks` lists the whole ledger, spec-bound tasks included.

`list_shared_tasks` called the operator route's function without `no_spec`, so that parameter kept its
FastAPI default, a `Query(False)` object, which is truthy: the agent route answered only the tasks with
no spec, with a `total` and `has_more` true to that cut. Two menders missed a running build's tasks on
2026-11-01 because of it.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument, Task

TASKS = "/api/v1/agent-actions/tasks"


@pytest.fixture
async def ledger():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-f1120", project_id="proj-test", name="mender"))
        session.add(
            Run(
                id="run-f1120",
                project_id="proj-test",
                agent="mender",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_f1120-secret"),
            )
        )
        session.add(
            SpecDocument(
                id="doc-f1120",
                project_id="proj-test",
                path="spec/changes/f1120/spec.json",
                title="F1120",
                phase="approved",
                kind="change-spec",
            )
        )
        await session.commit()
        session.add(
            Task(
                id="task-f1120-bound",
                project_id="proj-test",
                title="bound",
                spec_document_id="doc-f1120",
            )
        )
        session.add(Task(id="task-f1120-free", project_id="proj-test", title="unbound"))
        await session.commit()
    return {"Authorization": "Bearer aw_run_f1120-secret"}


@pytest.mark.asyncio
async def test_the_agent_route_lists_bound_and_unbound_tasks(app, ledger):
    answer = (await app.get(TASKS, headers=ledger)).json()

    assert {task["id"] for task in answer["tasks"]} == {"task-f1120-bound", "task-f1120-free"}
    assert answer["total"] == 2
    assert answer["has_more"] is False


@pytest.mark.asyncio
async def test_a_page_of_the_agent_route_counts_the_bound_tasks(app, ledger):
    answer = (await app.get(TASKS, params={"limit": 1}, headers=ledger)).json()

    assert len(answer["tasks"]) == 1
    assert answer["total"] == 2
    assert answer["has_more"] is True
