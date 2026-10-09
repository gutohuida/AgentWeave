"""An agent updates a task with what its tool carries — F366,
`openspec/changes/an-agent-updates-a-task-with-what-its-tool-carries/`.

The agent plane's `PATCH /agent-actions/tasks/{id}` took the operator's own `TaskUpdate`, so an
agent reaching the route directly could write fields its tool never offered: `assignee`, `priority`,
`description`. The costly one was `assignee` — an agent could unassign another agent's work, or name
itself reviewer of its own finished task in the same request that moved it to `under_review`.

`assignee`, `priority` and `description` are now operator-only on the agent plane (403, before any
write). `requirement_ids`/`spec_document` move the other way: the route already recorded an agent's
link as the agent's, so the MCP `update_task` tool gains them, and `status` becomes optional so
linking a requirement needs no status restatement — including on a `blocked` task, where restating
`blocked` is itself refused.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecRequirement, Task, TaskRequirementLink, TaskTransition
from hub.spec_payload import SCHEMA_VERSION

PROJECT = "proj-test"
BASE = f"/api/v1/projects/{PROJECT}/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
SPEC_PATH = "spec/changes/tool-carries/spec.json"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}


async def _active_run(run_id: str, agent: str) -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(Agent(id=f"ag-{run_id}", project_id=PROJECT, name=agent))
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


async def _linked_identifiers(task_id: str) -> list[str]:
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(SpecRequirement.identifier)
                    .join(
                        TaskRequirementLink,
                        TaskRequirementLink.requirement_id == SpecRequirement.id,
                    )
                    .where(TaskRequirementLink.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)


async def _declare_requirement(app, auth_headers) -> None:
    created = await app.post(
        f"{BASE}/documents", json={"path": SPEC_PATH, "title": "Tool carries"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    run_headers = await _active_run("run-declare-fr1", "declarer")
    saved = await app.post(
        SUBMIT,
        json={
            "path": SPEC_PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Tool carries",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


@pytest.mark.asyncio
async def test_agent_cannot_reassign_another_agents_in_progress_task(app):
    headers = await _active_run("run-reassign", "reassigner")
    await _make_task("task-tc-1", status="in_progress", assignee="original-holder")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-1",
        headers=headers,
        json={"assignee": "someone-else"},
    )
    assert response.status_code == 403, response.text
    assert "who holds a task" in response.json()["detail"]

    async with async_session_factory() as session:
        task = await session.get(Task, "task-tc-1")
        assert task.assignee == "original-holder"


@pytest.mark.asyncio
async def test_agent_cannot_name_itself_reviewer_in_the_same_request_that_completes_its_task(app):
    """F366's actual bypass: bundling the review-status move with a self-assignment."""
    headers = await _active_run("run-self-review", "author")
    await _make_task("task-tc-2", status="completed", assignee="author")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-2",
        headers=headers,
        json={"status": "under_review", "assignee": "author"},
    )
    assert response.status_code == 403, response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-tc-2")
        assert task.status == "completed"
        assert task.assignee == "author"
    assert await _transition_count("task-tc-2") == 0


@pytest.mark.asyncio
async def test_agent_cannot_set_priority_or_description_and_the_detail_names_requirement_ids(app):
    headers = await _active_run("run-priority", "pusher")
    await _make_task("task-tc-3")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-3",
        headers=headers,
        json={"priority": "critical", "description": "x"},
    )
    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert "priority" in detail
    assert "description" in detail
    assert "requirement_ids" in detail

    async with async_session_factory() as session:
        task = await session.get(Task, "task-tc-3")
        assert task.priority != "critical"
        assert task.description != "x"


@pytest.mark.asyncio
async def test_agent_status_and_notes_still_work(app):
    headers = await _active_run("run-status-notes", "worker")
    await _make_task("task-tc-4")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-4",
        headers=headers,
        json={"status": "in_progress", "notes": "started"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "in_progress"


def test_mcp_update_task_request_carries_both_status_and_requirement_ids(monkeypatch):
    """1.5: the MCP tool sends both fields to the route in one request, `test_mcp_server.py` style
    (a captured `urlopen` request rather than a real socket)."""
    from hub import mcp_server

    captured = {}

    def _fake_hub_request(method, path, body=None):
        captured["method"], captured["path"], captured["body"] = method, path, body
        return {"id": "task-x", "status": "in_progress"}

    monkeypatch.setattr(mcp_server, "_hub_request", _fake_hub_request)
    result = mcp_server.update_task("task-x", status="in_progress", requirement_ids=["FR-1"])

    assert result["status"] == "in_progress"
    assert captured["method"] == "PATCH"
    assert captured["path"] == "/tasks/task-x"
    assert captured["body"] == {"status": "in_progress", "requirement_ids": ["FR-1"]}


def test_mcp_update_task_omits_status_and_notes_when_only_linking(monkeypatch):
    """1.5a: linking a requirement needs no status restatement, so the request body carries no
    `status` and no `notes` key when only `requirement_ids` is given."""
    from hub import mcp_server

    captured = {}

    def _fake_hub_request(method, path, body=None):
        captured["method"], captured["path"], captured["body"] = method, path, body
        return {"id": "task-x"}

    monkeypatch.setattr(mcp_server, "_hub_request", _fake_hub_request)
    mcp_server.update_task("task-x", requirement_ids=["FR-1"])

    assert captured["body"] == {"requirement_ids": ["FR-1"]}
    assert "status" not in captured["body"]
    assert "notes" not in captured["body"]


@pytest.mark.asyncio
async def test_route_records_the_link_with_actor_kind_agent(app, auth_headers):
    """The route half of 1.5: what the tool sends is recorded as the agent's link, not the
    operator's — `SpecActor(kind="agent")` (`tasks.py:1456`)."""
    await _declare_requirement(app, auth_headers)
    headers = await _active_run("run-mcp-link", "linker")
    await _make_task("task-tc-5")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-5",
        headers=headers,
        json={"status": "in_progress", "requirement_ids": ["FR-1"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "in_progress"
    assert response.json()["requirement_ids"] == ["FR-1"]

    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(TaskRequirementLink).where(TaskRequirementLink.task_id == "task-tc-5")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].actor_kind == "agent"


@pytest.mark.asyncio
async def test_linking_a_requirement_on_a_blocked_task_leaves_it_blocked(app, auth_headers):
    """The route side of 1.5a: an agent whose task is `blocked` cannot restate `blocked` (403), so
    linking must not require it to. `status` absent from the body must not disturb the status or
    the reason."""
    await _declare_requirement(app, auth_headers)
    headers = await _active_run("run-link-blocked", "waiter")
    await _make_task("task-tc-6", status="blocked", blocked_reason="waiting on the operator")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-6",
        headers=headers,
        json={"requirement_ids": ["FR-1"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blocked"

    async with async_session_factory() as session:
        task = await session.get(Task, "task-tc-6")
        assert task.status == "blocked"
        assert task.blocked_reason == "waiting on the operator"
    assert await _linked_identifiers("task-tc-6") == ["FR-1"]


@pytest.mark.asyncio
async def test_operator_can_still_set_assignee_priority_and_description(app, auth_headers):
    await _make_task("task-tc-7")

    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/tasks/task-tc-7",
        headers=auth_headers,
        json={"assignee": "someone", "priority": "high", "description": "operator's words"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["assignee"] == "someone"
    assert response.json()["priority"] == "high"
    assert response.json()["description"] == "operator's words"


@pytest.mark.asyncio
async def test_existing_named_refusals_keep_their_sentences(app):
    """divergence_policy, escalation_agent and the blocked-status refusals are unchanged by this
    change — a regression guard alongside `test_agent_actions_coordination.py`'s own coverage."""
    headers = await _active_run("run-existing-refusals", "guarded")
    await _make_task("task-tc-8", divergence_policy="retry")

    response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-8",
        headers=headers,
        json={"divergence_policy": "surface"},
    )
    assert response.status_code == 403, response.text
    assert "divergence policy" in response.json()["detail"]

    block_response = await app.patch(
        "/api/v1/agent-actions/tasks/task-tc-8",
        headers=headers,
        json={"status": "blocked", "blocked_reason": "waiting"},
    )
    assert block_response.status_code == 403, block_response.text
    assert "ask_user" in block_response.json()["detail"]
