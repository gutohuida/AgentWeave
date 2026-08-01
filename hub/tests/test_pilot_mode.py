"""Tests for pilot mode endpoints."""

import pytest


@pytest.mark.asyncio
async def test_trigger_rejects_pilot_mode_agent(app, auth_headers):
    """A pilot-mode agent cannot be direct-spawned — the whole point of pilot mode is that
    a human drives it manually. The trigger endpoint now refuses with a stated reason
    (Decision 2: an observable outcome, not a message quietly queued for someone else to
    notice) instead of silently creating a message as it did under the old protocol.
    """
    resp = await app.post(
        "/api/v1/agents/claude-pilot-test/register-session",
        json={"session_id": "sess-pilot-123"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["pilot"] is True

    resp = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "claude-pilot-test",
            "message": "Hello from test",
            "session_mode": "new",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "pilot mode" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_trigger_unsupported_runner_reports_501(app, auth_headers):
    """Kimi isn't wired to direct spawn yet (task 3.5 scoped to claude/codex only) — the
    endpoint must say so clearly rather than silently misbehaving or pretending to queue it.
    """
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"kimi-agent": {"runner": "kimi"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    resp = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "kimi-agent",
            "message": "Hello from test",
            "session_mode": "new",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 501
    assert "kimi" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_session_creates_agent(app, auth_headers):
    """Test that register-session endpoint creates agent if it doesn't exist."""
    resp = await app.post(
        "/api/v1/agents/new-pilot-agent/register-session",
        json={"session_id": "sess-new-agent-456"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["agent"] == "new-pilot-agent"
    assert data["session_id"] == "sess-new-agent-456"
    assert data["pilot"] is True


@pytest.mark.asyncio
async def test_register_session_upserts(app, auth_headers):
    """Test that register-session overwrites previous session ID."""
    # First registration
    resp = await app.post(
        "/api/v1/agents/upsert-test/register-session",
        json={"session_id": "sess-first"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-first"

    # Second registration - should overwrite
    resp = await app.post(
        "/api/v1/agents/upsert-test/register-session",
        json={"session_id": "sess-second"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-second"
    assert data["success"] is True


@pytest.mark.asyncio
async def test_register_session_missing_session_id(app, auth_headers):
    """Test that register-session fails without session_id."""
    resp = await app.post(
        "/api/v1/agents/missing-session-agent/register-session",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "session_id is required" in data.get("detail", "").lower()


@pytest.mark.asyncio
async def test_agents_list_includes_pilot_flag(app, auth_headers):
    """Test that agent list includes pilot and registered_session_id fields."""
    # Register an agent with pilot mode
    await app.post(
        "/api/v1/agents/pilot-list-test/register-session",
        json={"session_id": "sess-list-test"},
        headers=auth_headers,
    )

    # List agents
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()

    # Find our agent
    agent = next((a for a in agents if a["name"] == "pilot-list-test"), None)
    assert agent is not None
    assert agent["pilot"] is True
    assert agent["registered_session_id"] == "sess-list-test"


@pytest.mark.asyncio
async def test_set_pilot_mode_enable_disable(app, auth_headers):
    """Test enabling and disabling pilot mode via the pilot endpoint."""
    # Enable pilot mode
    resp = await app.post(
        "/api/v1/agents/pilot-toggle-test/pilot",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["pilot"] is True
    assert data["agent"] == "pilot-toggle-test"

    # Verify in agent list
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    agents = resp.json()
    agent = next((a for a in agents if a["name"] == "pilot-toggle-test"), None)
    assert agent is not None
    assert agent["pilot"] is True

    # Disable pilot mode
    resp = await app.post(
        "/api/v1/agents/pilot-toggle-test/pilot",
        json={"enabled": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["pilot"] is False

    # Verify in agent list
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    agents = resp.json()
    agent = next((a for a in agents if a["name"] == "pilot-toggle-test"), None)
    assert agent is not None
    assert agent["pilot"] is False
