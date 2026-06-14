"""Tests for agent endpoints and input validation."""

import pytest


@pytest.mark.asyncio
async def test_get_role_context_rejects_path_traversal_role(app, auth_headers):
    # Before S1 fix this reads project-root README.md via ../ traversal and returns 200.
    resp = await app.get(
        "/api/v1/agents/context?role=../../../../README",
        headers=auth_headers,
    )
    assert resp.status_code in (400, 404)
    assert "role" in resp.text.lower() or "invalid" in resp.text.lower()


@pytest.mark.asyncio
async def test_register_session_rejects_configured_agent_collision(app, auth_headers):
    # Mark an agent as configured via session sync
    sync_resp = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {}}}},
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200

    # M16: registering a session for a configured agent must be rejected
    resp = await app.post(
        "/api/v1/agents/claude/register-session",
        json={"session_id": "sess-abc123"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "reserved for a configured agent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_session_allows_unconfigured_agent(app, auth_headers):
    resp = await app.post(
        "/api/v1/agents/kimi/register-session",
        json={"session_id": "sess-xyz789"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["session_id"] == "sess-xyz789"


@pytest.mark.asyncio
async def test_agent_trigger_rejects_work_dir_with_parent_traversal(app, auth_headers):
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "claude",
            "message": "Hello",
            "work_dir": "/tmp/.. /etc",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "work_dir" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_agent_trigger_rejects_work_dir_with_tilde(app, auth_headers):
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "claude",
            "message": "Hello",
            "work_dir": "~/projects/secret",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "work_dir" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_agent_trigger_rejects_work_dir_with_non_printable_chars(app, auth_headers):
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "claude",
            "message": "Hello",
            "work_dir": "/tmp/\x00secret",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "work_dir" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_recent_chat_limit_is_bounded(app, auth_headers):
    # M14: limit must be between 1 and 500
    resp_low = await app.get(
        "/api/v1/agent/claude/chat?limit=0",
        headers=auth_headers,
    )
    assert resp_low.status_code == 422

    resp_high = await app.get(
        "/api/v1/agent/claude/chat?limit=501",
        headers=auth_headers,
    )
    assert resp_high.status_code == 422

    resp_ok = await app.get(
        "/api/v1/agent/claude/chat?limit=50",
        headers=auth_headers,
    )
    assert resp_ok.status_code == 200
