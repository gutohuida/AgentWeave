"""Multi-tenant BOLA (Broken Object Level Authorization) tests.

PR 6 T5: every endpoint that returns project-scoped data must enforce isolation
so that Project B's API key cannot read Project A's resources.
"""

import pytest
import pytest_asyncio

from hub.db.engine import async_session_factory
from hub.db.models import Project


@pytest_asyncio.fixture
async def project_a(app, auth_headers):
    """First explicitly addressed project under the instance operator."""
    project_id = "proj-bola-a"
    async with async_session_factory() as session:
        session.add(Project(id=project_id, name="BOLA Project A"))
        await session.commit()
    return {
        "project_id": project_id,
        "headers": auth_headers,
    }


@pytest_asyncio.fixture
async def other_project(app, auth_headers):
    """A second explicitly addressed project under the same operator."""
    project_id = "proj-bola-other"
    async with async_session_factory() as session:
        session.add(Project(id=project_id, name="Other Project"))
        await session.commit()
    return {
        "project_id": project_id,
        "headers": auth_headers,
    }


@pytest_asyncio.fixture
async def project_a_resources(app, project_a):
    """Create a representative set of resources in Project A and return their IDs."""
    auth_headers = project_a["headers"]
    base = f"/api/v1/projects/{project_a['project_id']}"
    # Sync a configured agent so the Agent row exists for heartbeat/output endpoints.
    sync_resp = await app.post(
        f"{base}/session/sync",
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
        f"{base}/agents/register",
        json={"name": "bob", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert reg_resp.status_code == 200

    # Message
    msg_resp = await app.post(
        f"{base}/messages",
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
        f"{base}/tasks",
        json={"title": "project a task", "assignee": "alice"},
        headers=auth_headers,
    )
    assert task_resp.status_code == 201
    task_id = task_resp.json()["id"]

    # Question
    q_resp = await app.post(
        f"{base}/questions",
        json={
            "from_agent": "alice",
            "question": "project a question",
            "header": "Decide",
            "options": [{"label": "Yes"}, {"label": "No"}],
            "multi_select": False,
        },
        headers=auth_headers,
    )
    assert q_resp.status_code == 201
    question_id = q_resp.json()["id"]

    # Job
    job_resp = await app.post(
        f"{base}/jobs",
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
        f"{base}/agents/alice/heartbeat",
        json={"status": "active"},
        headers=auth_headers,
    )
    assert hb_resp.status_code == 201

    # Agent output with a session id (used by chat history)
    out_resp = await app.post(
        f"{base}/agents/alice/output",
        json={"content": "project a output", "session_id": "sess-a"},
        headers=auth_headers,
    )
    assert out_resp.status_code == 201

    # Context usage event
    ctx_resp = await app.post(
        f"{base}/agents/alice/context-usage",
        json={"percent": 50, "warning": False},
        headers=auth_headers,
    )
    assert ctx_resp.status_code == 201

    # Log event
    log_resp = await app.post(
        f"{base}/logs",
        json={"event_type": "test", "agent": "alice", "data": {"x": 1}},
        headers=auth_headers,
    )
    assert log_resp.status_code == 201

    # Instructions
    instr_resp = await app.put(
        f"{base}/project/instructions",
        json={"content": "project a instructions"},
        headers=auth_headers,
    )
    assert instr_resp.status_code == 200

    return {
        "agent": "alice",
        "session_id": "sess-a",
        "message_id": msg_id,
        "task_id": task_id,
        "question_id": question_id,
        "job_id": job_id,
    }


@pytest.mark.asyncio
async def test_cross_project_object_reads_return_404(app, other_project, project_a_resources):
    """Project B paths must not resolve Project A's individual resources."""
    b = other_project["headers"]
    ids = project_a_resources
    base = f"/api/v1/projects/{other_project['project_id']}"

    object_endpoints = [
        ("GET", f"{base}/tasks/{ids['task_id']}"),
        ("GET", f"{base}/tasks/{ids['task_id']}/history"),
        ("GET", f"{base}/questions/{ids['question_id']}"),
        ("GET", f"{base}/jobs/{ids['job_id']}"),
        ("GET", f"{base}/jobs/{ids['job_id']}/history"),
    ]

    for method, path in object_endpoints:
        resp = await app.request(method, path, headers=b)
        assert resp.status_code in (
            401,
            404,
        ), f"BOLA leak on {method} {path}: got {resp.status_code}"


@pytest.mark.asyncio
async def test_cross_project_list_reads_return_empty_data(app, other_project, project_a_resources):
    """Project B's key must see empty project-scoped lists, not Project A's data."""
    b = other_project["headers"]
    a_ids = set(project_a_resources.values())
    base = f"/api/v1/projects/{other_project['project_id']}"

    list_endpoints = [
        f"{base}/messages",
        f"{base}/tasks",
        f"{base}/questions",
        f"{base}/jobs",
        f"{base}/events/history",
        f"{base}/logs",
        f"{base}/agents",
        f"{base}/agents/alice/timeline",
        f"{base}/agents/alice/output",
    ]

    for path in list_endpoints:
        resp = await app.get(path, headers=b)
        assert resp.status_code == 200, f"{path} returned {resp.status_code}"
        data = resp.json()
        assert isinstance(data, list), f"{path} did not return a list"
        # No Project A ids should appear anywhere in the response.
        assert not any(
            item.get("id") in a_ids for item in data if isinstance(item, dict)
        ), f"{path} leaked Project A resources"

    # Agent sessions returns a dict wrapper; ensure the inner list is empty.
    sessions_resp = await app.get(f"{base}/agent/sessions/alice", headers=b)
    assert sessions_resp.status_code == 200
    assert sessions_resp.json()["sessions"] == []

    # The merged chat timeline also returns a dict wrapper (task 8.3) — both the
    # sessionless and session-scoped forms must report an empty entries list.
    recent_chat_resp = await app.get(f"{base}/agent/alice/chat", headers=b)
    assert recent_chat_resp.status_code == 200
    assert recent_chat_resp.json()["entries"] == []

    chat_resp = await app.get(
        f"{base}/agent/alice/chat/{project_a_resources['session_id']}",
        headers=b,
    )
    assert chat_resp.status_code == 404

    # Status endpoint must report Project B, not Project A.
    status_resp = await app.get(f"{base}/status", headers=b)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["project_id"] == other_project["project_id"]
    assert status["message_counts"]["total"] == 0
    assert status["task_counts"] == {}
    assert status["question_counts"]["total"] == 0

    # Configured agents for Project B should be empty.
    configured_resp = await app.get(f"{base}/agents/configured", headers=b)
    assert configured_resp.status_code == 200
    assert configured_resp.json()["agents"] == []

    session_resp = await app.get(f"{base}/session/sync", headers=b)
    assert session_resp.status_code == 200
    assert session_resp.json()["synced"] is False

    instructions_resp = await app.get(f"{base}/project/instructions", headers=b)
    assert instructions_resp.status_code == 200
    assert instructions_resp.json()["content"] == ""


@pytest.mark.asyncio
async def test_cross_project_conversation_mutations_return_404(
    app, project_a, other_project, project_a_resources
):
    """Renaming, archiving or messaging into another project's conversation must not work.

    404 rather than 403 throughout: whether a conversation id exists in some other project is
    not this caller's to learn.
    """
    a_base = f"/api/v1/projects/{project_a['project_id']}"
    listed = await app.get(f"{a_base}/agent/alice/conversations", headers=project_a["headers"])
    assert listed.status_code == 200, listed.text
    conversation_id = listed.json()[0]["id"]

    b = other_project["headers"]
    b_base = f"/api/v1/projects/{other_project['project_id']}"
    target = f"{b_base}/agent/alice/conversations/{conversation_id}"

    assert (await app.patch(target, json={"title": "Stolen"}, headers=b)).status_code == 404
    assert (await app.post(f"{target}/archive", headers=b)).status_code == 404
    assert (await app.post(f"{target}/unarchive", headers=b)).status_code == 404

    # And a message cannot be aimed into it either.
    sent = await app.post(
        f"{b_base}/messages",
        json={
            "from": "intruder",
            "to": "alice",
            "content": "Cross-project delivery",
            "conversation_id": conversation_id,
        },
        headers=b,
    )
    assert sent.status_code == 404

    # Project A's conversation is untouched by any of it.
    after = await app.get(
        f"{a_base}/agent/alice/conversations?lifecycle=all", headers=project_a["headers"]
    )
    target_row = next(row for row in after.json() if row["id"] == conversation_id)
    assert target_row["lifecycle"] == "open"
    assert target_row["title"] != "Stolen"


@pytest.mark.asyncio
async def test_project_a_can_still_read_its_own_resources(app, project_a, project_a_resources):
    """Isolation must not break the legitimate owner's access."""
    ids = project_a_resources
    a_headers = project_a["headers"]
    base = f"/api/v1/projects/{project_a['project_id']}"

    assert (await app.get(f"{base}/tasks/{ids['task_id']}", headers=a_headers)).status_code == 200
    assert (
        await app.get(f"{base}/questions/{ids['question_id']}", headers=a_headers)
    ).status_code == 200
    assert (await app.get(f"{base}/jobs/{ids['job_id']}", headers=a_headers)).status_code == 200

    agents_resp = await app.get(f"{base}/agents", headers=a_headers)
    assert agents_resp.status_code == 200
    names = {a["name"] for a in agents_resp.json()}
    assert ids["agent"] in names
