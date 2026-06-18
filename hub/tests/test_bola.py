"""Multi-tenant BOLA (Broken Object Level Authorization) tests.

PR 6 T5: every endpoint that returns project-scoped data must enforce isolation
so that Project B's API key cannot read Project A's resources.
"""

import secrets

import pytest
import pytest_asyncio

from hub.db.engine import async_session_factory
from hub.db.models import ApiKey, Project


@pytest_asyncio.fixture
async def project_a(app):
    """First BOLA tenant with its own API key."""
    project_id = f"proj-bola-a-{secrets.token_hex(4)}"
    api_key = f"aw_live_{secrets.token_hex(16)}"
    async with async_session_factory() as session:
        session.add(Project(id=project_id, name="BOLA Project A"))
        session.add(ApiKey(id=api_key, project_id=project_id, revoked=False))
        await session.commit()
    return {
        "project_id": project_id,
        "api_key": api_key,
        "headers": {"Authorization": f"Bearer {api_key}"},
    }


@pytest_asyncio.fixture
async def other_project(app):
    """A second project with its own API key."""
    project_id = f"proj-bola-other-{secrets.token_hex(4)}"
    api_key = f"aw_live_{secrets.token_hex(16)}"
    async with async_session_factory() as session:
        session.add(Project(id=project_id, name="Other Project"))
        session.add(ApiKey(id=api_key, project_id=project_id, revoked=False))
        await session.commit()
    return {
        "project_id": project_id,
        "api_key": api_key,
        "headers": {"Authorization": f"Bearer {api_key}"},
    }


@pytest_asyncio.fixture
async def project_a_resources(app, project_a):
    """Create a representative set of resources in Project A and return their IDs."""
    auth_headers = project_a["headers"]
    # Sync a configured agent so the Agent row exists for heartbeat/output endpoints.
    sync_resp = await app.post(
        "/api/v1/session/sync",
        json={
            "data": {
                "name": "Project A",
                "agents": {
                    "alice": {"runner": "native"},
                },
            }
        },
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200

    # Self-register another agent
    reg_resp = await app.post(
        "/api/v1/agents/register",
        json={"name": "bob", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert reg_resp.status_code == 200

    # Message
    msg_resp = await app.post(
        "/api/v1/messages",
        json={
            "from": "user",
            "to": "alice",
            "subject": "hello",
            "content": "project a message",
        },
        headers=auth_headers,
    )
    assert msg_resp.status_code == 201
    msg_id = msg_resp.json()["id"]

    # Task
    task_resp = await app.post(
        "/api/v1/tasks",
        json={"title": "project a task", "assignee": "alice"},
        headers=auth_headers,
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    # Question
    q_resp = await app.post(
        "/api/v1/questions",
        json={"from_agent": "alice", "question": "project a question"},
        headers=auth_headers,
    )
    assert q_resp.status_code == 201
    question_id = q_resp.json()["id"]

    # Job
    job_resp = await app.post(
        "/api/v1/jobs",
        json={
            "name": "project a job",
            "agent": "alice",
            "message": "run",
            "cron": "0 0 * * *",
        },
        headers=auth_headers,
    )
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]

    # Heartbeat
    hb_resp = await app.post(
        "/api/v1/agents/alice/heartbeat",
        json={"status": "active"},
        headers=auth_headers,
    )
    assert hb_resp.status_code == 201

    # Agent output with a session id (used by chat history)
    out_resp = await app.post(
        "/api/v1/agents/alice/output",
        json={"content": "project a output", "session_id": "sess-a"},
        headers=auth_headers,
    )
    assert out_resp.status_code == 201

    # Context usage event
    ctx_resp = await app.post(
        "/api/v1/agents/alice/context-usage",
        json={"percent": 50, "warning": False},
        headers=auth_headers,
    )
    assert ctx_resp.status_code == 201

    # Log event
    log_resp = await app.post(
        "/api/v1/logs",
        json={"event_type": "test", "agent": "alice", "data": {"x": 1}},
        headers=auth_headers,
    )
    assert log_resp.status_code == 201

    # Instructions
    instr_resp = await app.put(
        "/api/v1/project/instructions",
        json={"content": "project a instructions"},
        headers=auth_headers,
    )
    assert instr_resp.status_code == 200

    # Roles config
    roles_resp = await app.put(
        "/api/v1/agents/roles/config",
        json={"roles": {"backend_dev": {"label": "Backend"}}},
        headers=auth_headers,
    )
    assert roles_resp.status_code == 200

    return {
        "agent": "alice",
        "session_id": "sess-a",
        "message_id": msg_id,
        "task_id": task_id,
        "question_id": question_id,
        "job_id": job_id,
    }


@pytest.mark.asyncio
async def test_cross_project_object_reads_return_404(
    app, other_project, project_a_resources
):
    """Project B's key must not be able to read Project A's individual resources."""
    b = other_project["headers"]
    ids = project_a_resources

    object_endpoints = [
        ("GET", f"/api/v1/tasks/{ids['task_id']}"),
        ("GET", f"/api/v1/tasks/{ids['task_id']}/history"),
        ("GET", f"/api/v1/questions/{ids['question_id']}"),
        ("GET", f"/api/v1/jobs/{ids['job_id']}"),
        ("GET", f"/api/v1/jobs/{ids['job_id']}/history"),
    ]

    for method, path in object_endpoints:
        resp = await app.request(method, path, headers=b)
        assert resp.status_code in (401, 404), (
            f"BOLA leak on {method} {path}: got {resp.status_code}"
        )


@pytest.mark.asyncio
async def test_cross_project_list_reads_return_empty_data(
    app, other_project, project_a_resources
):
    """Project B's key must see empty project-scoped lists, not Project A's data."""
    b = other_project["headers"]
    a_ids = set(project_a_resources.values())

    list_endpoints = [
        "/api/v1/messages",
        "/api/v1/tasks",
        "/api/v1/questions",
        "/api/v1/jobs",
        "/api/v1/events/history",
        "/api/v1/logs",
        "/api/v1/agents",
        "/api/v1/agents/alice/timeline",
        "/api/v1/agents/alice/output",
        "/api/v1/agent/alice/chat",
    ]

    for path in list_endpoints:
        resp = await app.get(path, headers=b)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), f"{path} did not return a list"
        # No Project A ids should appear anywhere in the response.
        assert not any(item.get("id") in a_ids for item in data if isinstance(item, dict)), (
            f"{path} leaked Project A resources"
        )

    # Agent sessions returns a dict wrapper; ensure the inner list is empty.
    sessions_resp = await app.get("/api/v1/agent/sessions/alice", headers=b)
    assert sessions_resp.status_code == 200
    assert sessions_resp.json()["sessions"] == []

    # Chat history for a specific session must also be empty.
    chat_resp = await app.get(
        f"/api/v1/agent/alice/chat/{project_a_resources['session_id']}",
        headers=b,
    )
    assert chat_resp.status_code == 200
    assert chat_resp.json()["messages"] == []

    # Status endpoint must report Project B, not Project A.
    status_resp = await app.get("/api/v1/status", headers=b)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["project_id"] == other_project["project_id"]
    assert status["message_counts"]["total"] == 0
    assert status["task_counts"] == {}
    assert status["question_counts"]["total"] == 0

    # Configured agents and roles config for Project B should be empty.
    configured_resp = await app.get("/api/v1/agents/configured", headers=b)
    assert configured_resp.status_code == 200
    assert configured_resp.json()["agents"] == []

    roles_resp = await app.get("/api/v1/agents/roles/config", headers=b)
    assert roles_resp.status_code == 200
    assert roles_resp.json() == {}

    session_resp = await app.get("/api/v1/session/sync", headers=b)
    assert session_resp.status_code == 200
    assert session_resp.json()["synced"] is False

    instructions_resp = await app.get("/api/v1/project/instructions", headers=b)
    assert instructions_resp.status_code == 200
    assert instructions_resp.json()["content"] == ""


@pytest.mark.asyncio
async def test_project_a_can_still_read_its_own_resources(
    app, project_a, project_a_resources
):
    """Isolation must not break the legitimate owner's access."""
    ids = project_a_resources
    a_headers = project_a["headers"]

    assert (await app.get(f"/api/v1/tasks/{ids['task_id']}", headers=a_headers)).status_code == 200
    assert (
        await app.get(f"/api/v1/questions/{ids['question_id']}", headers=a_headers)
    ).status_code == 200
    assert (await app.get(f"/api/v1/jobs/{ids['job_id']}", headers=a_headers)).status_code == 200

    agents_resp = await app.get("/api/v1/agents", headers=a_headers)
    assert agents_resp.status_code == 200
    names = {a["name"] for a in agents_resp.json()}
    assert ids["agent"] in names
