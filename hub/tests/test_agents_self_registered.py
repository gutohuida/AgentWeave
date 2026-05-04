"""Tests for self-registered agents endpoint."""

import pytest


@pytest.mark.asyncio
async def test_agents_list_includes_self_registered_with_liveness(app, auth_headers):
    """Test that GET /api/v1/agents returns self-registered agents with liveness."""
    # Register a self-registered agent
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "hermes-test",
            "contact_mode": "poll",
            "role_request": "backend_dev",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "backend_dev"

    # Post a heartbeat for the agent
    resp = await app.post(
        "/api/v1/agents/hermes-test/heartbeat",
        json={"status": "active"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # List agents
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()

    hermes = next((a for a in agents if a["name"] == "hermes-test"), None)
    assert hermes is not None
    assert hermes["self_registered"] is True
    assert hermes["liveness"] == "online"


@pytest.mark.asyncio
async def test_register_agent_rejects_configured_agent_name(app, auth_headers):
    """Test that registering with a configured agent name is rejected."""
    # First push a session with configured agents
    resp = await app.put(
        "/api/v1/agents/roles/config",
        json={},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Push session config so 'claude' appears as configured
    resp = await app.post(
        "/api/v1/session/sync",
        json={
            "data": {
                "id": "sess-test",
                "name": "Test Session",
                "mode": "hierarchical",
                "principal": "claude",
                "agents": {
                    "claude": {"runner": "claude"},
                    "kimi": {"runner": "kimi"},
                },
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Try to register as 'claude'
    resp = await app.post(
        "/api/v1/agents/register",
        json={"name": "claude", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "reserved for a configured agent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_agent_invalid_contact_mode(app, auth_headers):
    """Test that invalid contact_mode is rejected."""
    resp = await app.post(
        "/api/v1/agents/register",
        json={"name": "bad-agent", "contact_mode": "invalid"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Invalid contact_mode" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_context_returns_role_content(app, auth_headers):
    """Test that GET /api/v1/agents/context returns role guide content."""
    resp = await app.get(
        "/api/v1/agents/context?role=backend_dev",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert "get_agent_context" in data["hint"]


@pytest.mark.asyncio
async def test_get_context_unknown_role(app, auth_headers):
    """Test that GET /api/v1/agents/context returns 404 for unknown role."""
    resp = await app.get(
        "/api/v1/agents/context?role=nonexistent_role_xyz",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_context_declared_agent(app, auth_headers):
    resp = await app.put(
        "/api/v1/agents/roles/config",
        json={
            "agent_roles": {"claude": ["tech_lead"]},
            "roles": {"tech_lead": {"label": "Tech Lead", "file": "roles/tech_lead.md"}},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.post(
        "/api/v1/session/sync",
        json={
            "data": {
                "id": "sess-test",
                "name": "Test Session",
                "mode": "hierarchical",
                "principal": "claude",
                "quality": {
                    "review_required": True,
                    "docs_threshold": "non_trivial",
                    "echo_chamber_guard": "enforce",
                },
                "agents": {
                    "claude": {"runner": "claude", "model": "sonnet", "role": "principal"},
                    "kimi": {"runner": "kimi"},
                },
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.get("/api/v1/agents/agent-context?agent=claude", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "claude"
    assert data["declared"] is True
    assert data["registered"] is True
    assert data["provisional"] is False
    assert data["roles"] == ["tech_lead"]
    assert "Project Operating Profile" in data["context"]
    assert "review_required: `true`" in data["context"]


@pytest.mark.asyncio
async def test_get_agent_context_registered_undeclared_agent(app, auth_headers):
    resp = await app.post(
        "/api/v1/agents/register",
        json={"name": "hermes-context", "contact_mode": "poll", "role_request": "backend_dev"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.get(
        "/api/v1/agents/agent-context?agent=hermes-context",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["declared"] is False
    assert data["registered"] is True
    assert data["provisional"] is True
    assert data["roles"] == ["backend_dev"]
    assert "do not modify files" in data["context"]


@pytest.mark.asyncio
async def test_get_agent_context_unknown_agent(app, auth_headers):
    resp = await app.get("/api/v1/agents/agent-context?agent=unknown-agent", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["known"] is False
    assert data["registered"] is False
    assert "register_agent" in data["context"]


@pytest.mark.asyncio
async def test_get_agent_context_invalid_agent_name(app, auth_headers):
    resp = await app.get("/api/v1/agents/agent-context?agent=bad%20name", headers=auth_headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_agent_with_config(app, auth_headers):
    """Test that register_agent stores the full config dict."""
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "hermes-config",
            "contact_mode": "poll",
            "config": {
                "runner": "kimi",
                "model": "kimi-k2",
                "yolo": True,
                "roles": ["backend_dev", "code_reviewer"],
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "backend_dev"


@pytest.mark.asyncio
async def test_register_agent_role_request_becomes_config_roles(app, auth_headers):
    """Test that role_request populates config['roles'] when config.roles is empty."""
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "hermes-role-only",
            "contact_mode": "poll",
            "role_request": "architect",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # List agents and verify the role appears in dev_roles
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()
    hermes = next((a for a in agents if a["name"] == "hermes-role-only"), None)
    assert hermes is not None
    assert hermes["dev_roles"] == ["architect"]
    assert hermes["dev_role"] == "architect"


@pytest.mark.asyncio
async def test_list_agents_shows_config_for_self_registered(app, auth_headers):
    """Test that list_agents populates runner, model, yolo, and roles from stored config."""
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "hermes-full",
            "contact_mode": "poll",
            "config": {
                "runner": "claude_proxy",
                "model": "MiniMax-Text-01",
                "yolo": True,
                "roles": ["backend_dev"],
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # List agents
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()

    hermes = next((a for a in agents if a["name"] == "hermes-full"), None)
    assert hermes is not None
    assert hermes["runner"] == "claude_proxy"
    assert hermes["display_model"] == "MiniMax-Text-01"
    assert hermes["yolo"] is True
    assert hermes["dev_role"] == "backend_dev"
    assert hermes["dev_roles"] == ["backend_dev"]
    assert hermes["self_registered"] is True


@pytest.mark.asyncio
async def test_re_register_updates_config(app, auth_headers):
    """Test that re-registering updates the stored config."""
    # First registration
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "hermes-update",
            "contact_mode": "poll",
            "config": {"runner": "kimi", "roles": ["backend_dev"]},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Re-register with different config
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "hermes-update",
            "contact_mode": "mcp-push",
            "config": {"runner": "glm", "model": "glm-5", "roles": ["frontend_dev"]},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Verify updated
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()
    hermes = next((a for a in agents if a["name"] == "hermes-update"), None)
    assert hermes is not None
    assert hermes["runner"] == "glm"
    assert hermes["display_model"] == "glm-5"
    assert hermes["dev_role"] == "frontend_dev"


@pytest.mark.asyncio
async def test_patch_agent_config(app, auth_headers):
    """Test PATCH merges config without touching other fields."""
    # Register agent with initial config
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "hermes-patch",
            "contact_mode": "poll",
            "config": {"runner": "kimi", "model": "kimi-k2", "yolo": False},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Patch just yolo and model
    resp = await app.patch(
        "/api/v1/agents/hermes-patch",
        json={"config": {"model": "kimi-k3", "yolo": True}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["runner"] == "kimi"  # preserved
    assert data["config"]["model"] == "kimi-k3"  # updated
    assert data["config"]["yolo"] is True  # updated

    # Verify via list
    resp = await app.get("/api/v1/agents", headers=auth_headers)
    assert resp.status_code == 200
    hermes = next((a for a in resp.json() if a["name"] == "hermes-patch"), None)
    assert hermes is not None
    assert hermes["runner"] == "kimi"
    assert hermes["display_model"] == "kimi-k3"
    assert hermes["yolo"] is True


@pytest.mark.asyncio
async def test_patch_agent_contact_mode(app, auth_headers):
    """Test PATCH can update top-level contact_mode."""
    resp = await app.post(
        "/api/v1/agents/register",
        json={"name": "hermes-patch-cm", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.patch(
        "/api/v1/agents/hermes-patch-cm",
        json={"contact_mode": "mcp-push"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["contact_mode"] == "mcp-push"


@pytest.mark.asyncio
async def test_patch_agent_unknown(app, auth_headers):
    """Test PATCH returns 404 for non-existent agent."""
    resp = await app.patch(
        "/api/v1/agents/nonexistent-agent",
        json={"config": {"yolo": True}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_agent_configured_agent_rejected(app, auth_headers):
    """Test PATCH returns 409 for configured agents."""
    # Push session config so 'claude' is configured
    resp = await app.post(
        "/api/v1/session/sync",
        json={
            "data": {
                "id": "sess-patch",
                "name": "Test Session",
                "mode": "hierarchical",
                "principal": "claude",
                "agents": {"claude": {"runner": "claude"}},
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.patch(
        "/api/v1/agents/claude",
        json={"config": {"yolo": True}},
        headers=auth_headers,
    )
    assert resp.status_code == 409
