"""Tests for task endpoints."""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocument, Task


@pytest.mark.asyncio
async def test_create_and_list_task(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Build feature X", "assignee": "kimi", "priority": "high"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("task-")
    assert data["assignee"] == "kimi"
    assert data["status"] == "pending"

    resp2 = await app.get("/api/v1/projects/proj-test/tasks?agent=kimi", headers=auth_headers)
    assert resp2.status_code == 200
    tasks = resp2.json()
    assert any(t["id"] == data["id"] for t in tasks)


@pytest.mark.asyncio
async def test_update_task_status(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Update test task"},
        headers=auth_headers,
    )
    task_id = resp.json()["id"]

    resp2 = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{task_id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_get_task_by_id(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Get test task", "description": "Full description"},
        headers=auth_headers,
    )
    task_id = resp.json()["id"]

    resp2 = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["description"] == "Full description"


@pytest.mark.asyncio
async def test_task_responses_include_assignee_runtime_status(app, auth_headers):
    heartbeat = await app.post(
        "/api/v1/projects/proj-test/agents/kimi/heartbeat",
        json={"status": "running", "message": "Working on task"},
        headers=auth_headers,
    )
    assert heartbeat.status_code == 201

    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Runtime status task", "assignee": "kimi"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["assignee_status"] == "running"
    assert data["assignee_status_msg"] == "Working on task"
    assert data["assignee_last_seen"] is not None

    task_id = data["id"]
    resp2 = await app.get(f"/api/v1/projects/proj-test/tasks/{task_id}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["assignee_status"] == "running"

    resp3 = await app.get("/api/v1/projects/proj-test/tasks?agent=kimi", headers=auth_headers)
    assert resp3.status_code == 200
    task = next(t for t in resp3.json() if t["id"] == task_id)
    assert task["assignee_status"] == "running"


@pytest.mark.asyncio
async def test_assigned_task_without_heartbeat_reports_idle(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "No heartbeat task", "assignee": "claude"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee_status"] == "idle"
    assert resp.json()["assignee_status_msg"] is None
    assert resp.json()["assignee_last_seen"] is None


@pytest.mark.asyncio
async def test_agent_list_counts_task_assignees_without_session_sync(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Fallback agent task", "assignee": "codex-backend"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee"] == "codex-backend"

    agents_resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert agents_resp.status_code == 200
    agents = agents_resp.json()
    codex = next((agent for agent in agents if agent["name"] == "codex-backend"), None)
    assert codex is not None
    assert codex["active_task_count"] == 1


@pytest.mark.asyncio
async def test_create_task_accepts_assigned_to_alias(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Alias assignment task", "assigned_to": "kimi"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee"] == "kimi"


@pytest.mark.asyncio
async def test_create_task_honors_client_supplied_id(app, auth_headers):
    """When the client supplies a valid id, the Hub uses it and returns it
    in the response. This lets the MCP `create_task` tool return the same id
    the Hub stored, so subsequent get_task / update_task calls by id succeed.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Custom id", "id": "task-custom1234"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == "task-custom1234"

    # Subsequent get by that id must succeed.
    resp = await app.get("/api/v1/projects/proj-test/tasks/task-custom1234", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == "task-custom1234"


@pytest.mark.asyncio
async def test_create_task_generates_id_when_omitted(app, auth_headers):
    """When the client omits id, the Hub still generates one."""
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks", json={"title": "No id"}, headers=auth_headers
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"].startswith("task-")
    assert len(body["id"]) == len("task-") + 8  # short_id() = 8 hex chars


@pytest.mark.asyncio
async def test_create_task_rejects_malformed_id(app, auth_headers):
    """An id with characters outside [A-Za-z0-9_-] or with leading digit
    is rejected — protects against path traversal and entity-type spoofing."""
    for bad in [
        "../etc/passwd",  # path traversal
        "task bad space",  # whitespace
        "1task-leading-digit",  # leading digit
        "",  # empty
    ]:
        resp = await app.post(
            "/api/v1/projects/proj-test/tasks",
            json={"title": "Bad id", "id": bad},
            headers=auth_headers,
        )
        assert resp.status_code == 422, f"expected 422 for id={bad!r}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_create_task_rejects_client_supplied_created_at(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Bad date", "created_at": "2026-01-01T00:00:00+00:00"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_task_rejects_overlong_title(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "x" * 257},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_task_rejects_overlong_description(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Big description", "description": "x" * 10001},
        headers=auth_headers,
    )
    assert resp.status_code == 422


async def _make_document(doc_id: str, phase: str) -> None:
    async with async_session_factory() as session:
        session.add(
            SpecDocument(id=doc_id, project_id="proj-test", path=f"spec/{doc_id}.md", phase=phase)
        )
        await session.commit()


async def _make_task(
    task_id: str, status: str, spec_document_id: str | None, loop_id: str | None = None
) -> None:
    async with async_session_factory() as session:
        session.add(
            Task(
                id=task_id,
                project_id="proj-test",
                title=task_id,
                status=status,
                spec_document_id=spec_document_id,
                loop_id=loop_id,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_spec_document_id_scopes_to_exactly_that_document_hiding_nothing(app, auth_headers):
    await _make_document("spdoc-scale-a", "archived")
    await _make_document("spdoc-scale-b", "approved")
    await _make_task("task-scale-1", "approved", "spdoc-scale-a")
    await _make_task("task-scale-2", "in_progress", "spdoc-scale-a")
    await _make_task("task-scale-3", "pending", "spdoc-scale-b")

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks?spec_document_id=spdoc-scale-a", headers=auth_headers
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert ids == {"task-scale-1", "task-scale-2"}


@pytest.mark.asyncio
async def test_exclude_archived_completed_hides_only_terminal_tasks_from_archived_documents(
    app, auth_headers
):
    await _make_document("spdoc-exc-archived", "archived")
    await _make_document("spdoc-exc-live", "approved")
    # Terminal + archived: excluded.
    await _make_task("task-exc-1", "approved", "spdoc-exc-archived")
    await _make_task("task-exc-2", "rejected", "spdoc-exc-archived")
    # Open work from an archived document: never excluded.
    await _make_task("task-exc-3", "in_progress", "spdoc-exc-archived")
    await _make_task("task-exc-4", "blocked", "spdoc-exc-archived")
    # Terminal, but the declaring document is not archived: not excluded.
    await _make_task("task-exc-5", "approved", "spdoc-exc-live")
    # No declaring document at all: never excluded, regardless of status.
    await _make_task("task-exc-6", "approved", None)

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks?exclude_archived_completed=true", headers=auth_headers
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert "task-exc-1" not in ids
    assert "task-exc-2" not in ids
    assert {"task-exc-3", "task-exc-4", "task-exc-5", "task-exc-6"} <= ids


@pytest.mark.asyncio
async def test_scoping_wins_over_the_exclusion_when_both_are_given(app, auth_headers):
    await _make_document("spdoc-both", "archived")
    await _make_task("task-both-1", "approved", "spdoc-both")

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks"
        "?spec_document_id=spdoc-both&exclude_archived_completed=true",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert "task-both-1" in ids


@pytest.mark.asyncio
async def test_neither_parameter_returns_the_unfiltered_default(app, auth_headers):
    await _make_document("spdoc-default", "archived")
    await _make_task("task-default-1", "approved", "spdoc-default")

    resp = await app.get("/api/v1/projects/proj-test/tasks", headers=auth_headers)
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert "task-default-1" in ids


@pytest.mark.asyncio
async def test_loop_id_scopes_to_exactly_that_loops_tasks_regardless_of_status(app, auth_headers):
    await _make_task("task-loop-1", "approved", None, loop_id="loop-scale-a")
    await _make_task("task-loop-2", "pending", None, loop_id="loop-scale-a")
    await _make_task("task-loop-3", "pending", None, loop_id="loop-scale-b")
    await _make_task("task-loop-4", "pending", None, loop_id=None)

    resp = await app.get(
        "/api/v1/projects/proj-test/tasks?loop_id=loop-scale-a", headers=auth_headers
    )
    assert resp.status_code == 200
    ids = {t["id"] for t in resp.json()}
    assert ids == {"task-loop-1", "task-loop-2"}

    # The agent-actions router's own list_tasks call site must still return 200 and must not
    # inherit loop scoping it was never asked for (the D7-regression shape this change's own
    # tasks.md names: a direct-call site silently defaulting a new parameter differently from
    # the router it wraps).
    token = "aw_run_task-loop-actor-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-task-loop-actor",
                project_id="proj-test",
                agent="loop-scoper",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    shared_resp = await app.get(
        "/api/v1/agent-actions/tasks", headers={"Authorization": f"Bearer {token}"}
    )
    assert shared_resp.status_code == 200
    shared_ids = {t["id"] for t in shared_resp.json()}
    assert "task-loop-3" in shared_ids
