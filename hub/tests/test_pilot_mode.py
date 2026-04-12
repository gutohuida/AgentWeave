"""Tests for pilot mode endpoints."""

import pytest


@pytest.mark.asyncio
async def test_trigger_returns_pilot_mode_response(app, auth_headers):
    """Test that trigger endpoint returns pilot-mode response without executing."""
    # First register an agent with pilot mode
    resp = await app.post(
        "/api/v1/agents/claude/register-session",
        json={"session_id": "sess-pilot-123"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["pilot"] is True

    # Now trigger the agent - should return pilot mode response
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "claude",
            "message": "Hello from test",
            "session_mode": "new",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "pilot mode" in data["message"].lower()
    assert data["agent"] == "claude"
    assert data["message_id"].startswith("msg-")


@pytest.mark.asyncio
async def test_trigger_non_pilot_agent(app, auth_headers):
    """Test that trigger works normally for non-pilot agents."""
    # Trigger an agent that is NOT in pilot mode
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "kimi",
            "message": "Hello from test",
            "session_mode": "new",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # Should NOT mention pilot mode
    assert "pilot mode" not in data["message"].lower()
    assert "watchdog" in data["message"].lower()


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
        "/api/v1/agents/claude/register-session",
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
