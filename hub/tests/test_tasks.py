"""Tests for task endpoints."""

import pytest


@pytest.mark.asyncio
async def test_create_and_list_task(app, auth_headers):
    resp = await app.post(
        "/api/v1/tasks",
        json={"title": "Build feature X", "assignee": "kimi", "priority": "high"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("task-")
    assert data["assignee"] == "kimi"
    assert data["status"] == "pending"

    resp2 = await app.get("/api/v1/tasks?agent=kimi", headers=auth_headers)
    assert resp2.status_code == 200
    tasks = resp2.json()
    assert any(t["id"] == data["id"] for t in tasks)


@pytest.mark.asyncio
async def test_update_task_status(app, auth_headers):
    resp = await app.post(
        "/api/v1/tasks",
        json={"title": "Update test task"},
        headers=auth_headers,
    )
    task_id = resp.json()["id"]

    resp2 = await app.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_get_task_by_id(app, auth_headers):
    resp = await app.post(
        "/api/v1/tasks",
        json={"title": "Get test task", "description": "Full description"},
        headers=auth_headers,
    )
    task_id = resp.json()["id"]

    resp2 = await app.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["description"] == "Full description"


@pytest.mark.asyncio
async def test_task_responses_include_assignee_runtime_status(app, auth_headers):
    heartbeat = await app.post(
        "/api/v1/agents/kimi/heartbeat",
        json={"status": "running", "message": "Working on task"},
        headers=auth_headers,
    )
    assert heartbeat.status_code == 201

    resp = await app.post(
        "/api/v1/tasks",
        json={"title": "Runtime status task", "assignee": "kimi"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["assignee_status"] == "running"
    assert data["assignee_status_msg"] == "Working on task"
    assert data["assignee_last_seen"] is not None

    task_id = data["id"]
    resp2 = await app.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["assignee_status"] == "running"

    resp3 = await app.get("/api/v1/tasks?agent=kimi", headers=auth_headers)
    assert resp3.status_code == 200
    task = next(t for t in resp3.json() if t["id"] == task_id)
    assert task["assignee_status"] == "running"


@pytest.mark.asyncio
async def test_assigned_task_without_heartbeat_reports_idle(app, auth_headers):
    resp = await app.post(
        "/api/v1/tasks",
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
        "/api/v1/tasks",
        json={"title": "Fallback agent task", "assignee": "codex-backend"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee"] == "codex-backend"

    agents_resp = await app.get("/api/v1/agents", headers=auth_headers)
    assert agents_resp.status_code == 200
    agents = agents_resp.json()
    codex = next((agent for agent in agents if agent["name"] == "codex-backend"), None)
    assert codex is not None
    assert codex["active_task_count"] == 1


@pytest.mark.asyncio
async def test_create_task_accepts_assigned_to_alias(app, auth_headers):
    resp = await app.post(
        "/api/v1/tasks",
        json={"title": "Alias assignment task", "assigned_to": "kimi"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["assignee"] == "kimi"
