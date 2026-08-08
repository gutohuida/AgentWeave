"""Tests for self-registered agents endpoint."""

import pytest


@pytest.mark.asyncio
async def test_agents_list_includes_self_registered_with_liveness(app, auth_headers):
    """Test that GET /api/v1/projects/proj-test/agents returns self-registered agents with liveness."""
    # Register a self-registered agent
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "hermes-test",
            "contact_mode": "poll",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["charter_id"] is None
    assert "No charter is assigned" in data["context"]

    # Post a heartbeat for the agent
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/hermes-test/heartbeat",
        json={"status": "active"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    # List agents
    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
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
    # Push session config so 'claude' appears as configured
    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
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
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "claude", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 409
    assert "reserved for a configured agent" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_register_agent_invalid_contact_mode(app, auth_headers):
    """Test that invalid contact_mode is rejected."""
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "bad-agent", "contact_mode": "invalid"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert "Invalid contact_mode" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_context_returns_charter_content(app, auth_headers):
    """The direct compatibility lookup resolves a stable charter ID."""
    charters = (await app.get("/api/v1/projects/proj-test/charters", headers=auth_headers)).json()
    charter = next(item for item in charters if item["name"] == "Backend Developer")
    resp = await app.get(
        f"/api/v1/projects/proj-test/agents/context?charter={charter['id']}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert "get_agent_context" in data["hint"]


@pytest.mark.asyncio
async def test_get_context_unknown_charter(app, auth_headers):
    """Unknown charter identifiers return 404."""
    resp = await app.get(
        "/api/v1/projects/proj-test/agents/context?charter=charter-nonexistent",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_context_known_agent_gets_runtime_context(app, auth_headers):
    """A Hub-registered agent gets runtime context, with quality gates when configured.

    Hub registration is the only thing that makes an agent "known" — synced session data does
    not, since nothing has written that table since 2026-08-03-single-runtime.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "id": "sess-test",
                "name": "Test Session",
                "quality": {
                    "review_required": True,
                    "docs_threshold": "non_trivial",
                    "echo_chamber_guard": "enforce",
                },
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "claude-known", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=claude-known", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["agent"] == "claude-known"
    assert data["known"] is True
    assert data["registered"] is True
    assert data["provisional"] is False
    assert "roles" not in data
    assert "AgentWeave Runtime Context" in data["context"]
    assert "Project Operating Profile" in data["context"]
    assert "review_required: `true`" in data["context"]


@pytest.mark.asyncio
async def test_get_agent_context_never_tells_a_known_agent_to_stand_down(app, auth_headers):
    """The stand-down block is gone.

    It was applied to every Hub-native agent unconditionally, which is why agents answered a
    clear operator instruction with "the user hasn't given me any explicit task yet" and then
    tried to message a non-existent `principal`.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "hermes-context", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=hermes-context",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["registered"] is True
    assert data["provisional"] is False
    assert "roles" not in data

    context = data["context"]
    for forbidden in (
        "External Agent Rules",
        "do not modify files",
        "do not claim tasks",
        "principal",
        "agentweave.yml",
    ):
        assert forbidden not in context, f"context still contains {forbidden!r}"


@pytest.mark.asyncio
async def test_get_agent_context_describes_the_tool_surface(app, auth_headers):
    """Naming a tool without its accepted values is what made Codex guess `message_type="text"`,
    and the four job tools were never mentioned to agents at all."""
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "tools-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=tools-agent", headers=auth_headers
    )
    context = resp.json()["context"]

    assert "## Your tools" in context
    # Every callable tool is described, including the ones agents could not previously see.
    for tool in (
        "send_message",
        "create_task",
        "list_tasks",
        "get_task",
        "update_task",
        "ask_user",
        "get_answer",
        "request_agent",
        "create_job",
        "delete_job",
        "toggle_job",
        "run_job",
    ):
        assert tool in context, f"{tool} is callable but undescribed"

    # Constrained parameters carry their values, which is the actual fix.
    assert "`direct_trigger`" in context
    assert "`revision_needed`" in context
    assert "`critical`" in context


@pytest.mark.asyncio
async def test_get_agent_context_does_not_point_at_its_own_context_file(app, auth_headers):
    """That pointer produced the first permission denial of the operator's test: the agent read
    a file whose contents it had already been given."""
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "pointer-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=pointer-agent", headers=auth_headers
    )
    context = resp.json()["context"]
    assert ".agentweave/context/" not in context


@pytest.mark.asyncio
async def test_get_agent_context_lists_the_real_roster(app, auth_headers):
    """An agent must be told its peers' exact names, or it cannot address them."""
    for name in ("roster-one", "roster-two"):
        resp = await app.post(
            "/api/v1/projects/proj-test/agents/register",
            json={"name": name, "contact_mode": "poll"},
            headers=auth_headers,
        )
        assert resp.status_code == 200

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=roster-one", headers=auth_headers
    )
    assert resp.status_code == 200
    context = resp.json()["context"]

    assert "### Team" in context
    assert "`roster-one`" in context
    assert "`roster-two`" in context
    # The reading agent is marked, and only the reading agent.
    assert "`roster-one`: runner=native <- you" in context
    assert "`roster-two`: runner=native\n" in context


@pytest.mark.asyncio
async def test_agent_summary_reports_the_bound_runner(app, auth_headers, bind_runner):
    """A runner-bound agent reports its runner's cli and model, not "native"/"Native".

    The summary used to derive these from synced session config merged over Agent.config,
    neither of which carries the binding, so every Hub-created agent reported "Native"
    despite holding a correct runner_id.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "bound-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    await bind_runner("bound-agent", cli="codex", model="gpt-5.4-mini")

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    agent = next(a for a in resp.json() if a["name"] == "bound-agent")
    assert agent["runner"] == "codex"
    assert agent["display_model"] == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_agent_summary_keeps_stored_config_when_unbound(app, auth_headers):
    """An agent with no bound runner still derives from its own stored config.

    That path is real for self-registered agents launched outside the Hub's spawn path,
    so the runner override must not clobber it.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "unbound-agent",
            "contact_mode": "poll",
            "config": {"runner": "opencode", "model": "ollama/qwen2.5-coder:7b"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    agent = next(a for a in resp.json() if a["name"] == "unbound-agent")
    assert agent["runner"] == "opencode"
    assert agent["display_model"] == "ollama/qwen2.5-coder:7b"


@pytest.mark.asyncio
async def test_get_agent_context_unknown_agent(app, auth_headers):
    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=unknown-agent", headers=auth_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["known"] is False
    assert data["registered"] is False
    assert "Ask the operator to register or configure this agent" in data["context"]


@pytest.mark.asyncio
async def test_get_agent_context_invalid_agent_name(app, auth_headers):
    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=bad%20name", headers=auth_headers
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_register_agent_with_config(app, auth_headers):
    """Test that register_agent stores the full config dict."""
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "hermes-config",
            "contact_mode": "poll",
            "config": {
                "runner": "kimi",
                "model": "kimi-k2",
                "yolo": True,
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["charter_id"] is None


@pytest.mark.asyncio
async def test_list_agents_shows_config_for_self_registered(app, auth_headers):
    """Test that list_agents populates runner and model from stored config.

    `yolo` stays in the stored config — it drives the spawn (`runner_commands`) and Codex's
    approval policy — but it is deliberately not surfaced on the summary. See
    openspec/changes/2026-08-08-agent-configuration-page tasks 1.2/1.5.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "hermes-full",
            "contact_mode": "poll",
            "config": {
                "runner": "claude_proxy",
                "model": "MiniMax-Text-01",
                "yolo": True,
            },
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # List agents
    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()

    hermes = next((a for a in agents if a["name"] == "hermes-full"), None)
    assert hermes is not None
    assert hermes["runner"] == "claude_proxy"
    assert hermes["display_model"] == "MiniMax-Text-01"
    assert "dev_role" not in hermes
    assert "dev_roles" not in hermes
    assert hermes["self_registered"] is True


@pytest.mark.asyncio
async def test_agent_summary_carries_no_role_or_yolo(app, auth_headers):
    """The summary exposes neither `role` nor `yolo`, even when both sit in stored config.

    `role` is the deleted multi-role subsystem's last remnant: nothing in the Hub reads it.
    `yolo` is different — it is live in `Agent.config`, where `runner_commands` and
    `codex_appserver` read it — but it is not an operator-facing summary field, and the
    read-only badge that rendered it is gone. Asserting absence here is what stops either
    returning unnoticed. Tasks 1.2/1.5 of 2026-08-08-agent-configuration-page.
    """
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "hermes-legacy-fields",
            "contact_mode": "poll",
            "config": {"runner": "claude", "model": "sonnet", "role": "principal", "yolo": True},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # The config store keeps both — removal is of the response field, not of the setting.
    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/hermes-legacy-fields",
        json={"config": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["yolo"] is True
    assert resp.json()["config"]["role"] == "principal"

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    hermes = next((a for a in resp.json() if a["name"] == "hermes-legacy-fields"), None)
    assert hermes is not None
    assert "role" not in hermes
    assert "yolo" not in hermes


@pytest.mark.asyncio
async def test_re_register_updates_config(app, auth_headers):
    """Test that re-registering updates the stored config."""
    # First registration
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "hermes-update",
            "contact_mode": "poll",
            "config": {"runner": "kimi"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Re-register with different config
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "hermes-update",
            "contact_mode": "mcp-push",
            "config": {"runner": "glm", "model": "glm-5"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Verify updated
    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    agents = resp.json()
    hermes = next((a for a in agents if a["name"] == "hermes-update"), None)
    assert hermes is not None
    assert hermes["runner"] == "glm"
    assert hermes["display_model"] == "glm-5"
    assert "dev_role" not in hermes


@pytest.mark.asyncio
async def test_patch_agent_config(app, auth_headers):
    """Test PATCH merges config without touching other fields."""
    # Register agent with initial config
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
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
        "/api/v1/projects/proj-test/agents/hermes-patch",
        json={"config": {"model": "kimi-k3", "yolo": True}},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["config"]["runner"] == "kimi"  # preserved
    assert data["config"]["model"] == "kimi-k3"  # updated
    assert data["config"]["yolo"] is True  # updated

    # Verify via list
    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    hermes = next((a for a in resp.json() if a["name"] == "hermes-patch"), None)
    assert hermes is not None
    assert hermes["runner"] == "kimi"
    assert hermes["display_model"] == "kimi-k3"


@pytest.mark.asyncio
async def test_patch_agent_contact_mode(app, auth_headers):
    """Test PATCH can update top-level contact_mode."""
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "hermes-patch-cm", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/hermes-patch-cm",
        json={"contact_mode": "mcp-push"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["contact_mode"] == "mcp-push"


@pytest.mark.asyncio
async def test_patch_agent_unknown(app, auth_headers):
    """Test PATCH returns 404 for non-existent agent."""
    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/nonexistent-agent",
        json={"config": {"yolo": True}},
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_agent_configured_agent_rejected(app, auth_headers):
    """Test PATCH returns 409 for configured agents."""
    # Push session config so 'claude' is configured
    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
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
        "/api/v1/projects/proj-test/agents/claude",
        json={"config": {"yolo": True}},
        headers=auth_headers,
    )
    assert resp.status_code == 409
