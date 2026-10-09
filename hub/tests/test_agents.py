"""Tests for agent endpoints and input validation."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_agent_trigger_rejects_work_dir_with_parent_traversal(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
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
        "/api/v1/projects/proj-test/agent/trigger",
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
        "/api/v1/projects/proj-test/agent/trigger",
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
async def test_patch_agent_refuses_binding_a_charter_to_an_archived_agent(
    app, auth_headers, add_agent
):
    """F185's guard: 1.1 releases charter_id on archive, but this route is the only other way
    to write it — without a lifecycle check here, one ordinary PATCH puts an archived agent
    straight back into F185's state.
    """
    charter = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Guard Test Charter", "content": "Guard behavior"},
            headers=auth_headers,
        )
    ).json()
    await add_agent("guard-archived-agent")
    archived = await app.post(
        "/api/v1/projects/proj-test/agents/guard-archived-agent/archive", headers=auth_headers
    )
    assert archived.status_code == 200

    refused = await app.patch(
        "/api/v1/projects/proj-test/agents/guard-archived-agent",
        json={"charter_id": charter["id"]},
        headers=auth_headers,
    )
    assert refused.status_code == 409

    cleared = await app.patch(
        "/api/v1/projects/proj-test/agents/guard-archived-agent",
        json={"charter_id": None},
        headers=auth_headers,
    )
    assert cleared.status_code == 200
    assert cleared.json()["charter_id"] is None

    await add_agent("guard-open-agent")
    allowed = await app.patch(
        "/api/v1/projects/proj-test/agents/guard-open-agent",
        json={"charter_id": charter["id"]},
        headers=auth_headers,
    )
    assert allowed.status_code == 200
    assert allowed.json()["charter_id"] == charter["id"]


@pytest.mark.asyncio
async def test_recent_chat_limit_is_bounded(app, auth_headers):
    # M14: limit must be between 1 and 500
    from hub.db.engine import async_session_factory
    from hub.db.models import Agent

    async with async_session_factory() as session:  # F194: the route refuses an unknown agent
        session.add(Agent(id="agt-claude", project_id="proj-test", name="claude"))
        await session.commit()
    resp_low = await app.get(
        "/api/v1/projects/proj-test/agent/claude/chat?limit=0",
        headers=auth_headers,
    )
    assert resp_low.status_code == 422

    resp_high = await app.get(
        "/api/v1/projects/proj-test/agent/claude/chat?limit=501",
        headers=auth_headers,
    )
    assert resp_high.status_code == 422

    resp_ok = await app.get(
        "/api/v1/projects/proj-test/agent/claude/chat?limit=50",
        headers=auth_headers,
    )
    assert resp_ok.status_code == 200


@pytest.mark.asyncio
async def test_list_agents_avoids_n_plus_one(app, auth_headers):
    """M15: list_agents must not issue per-agent queries inside a loop."""
    agents = ["agent-a", "agent-b", "agent-c"]
    sync_resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "native"} for name in agents}}},
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200

    for name in agents:
        hb_resp = await app.post(
            f"/api/v1/projects/proj-test/agents/{name}/heartbeat",
            json={"status": "active"},
            headers=auth_headers,
        )
        assert hb_resp.status_code == 201
        task_resp = await app.post(
            "/api/v1/projects/proj-test/tasks",
            json={"title": f"task {name}", "assignee": name},
            headers=auth_headers,
        )
        assert task_resp.status_code == 201

    from sqlalchemy import event

    from hub.db.engine import engine

    statements: list = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == len(agents)
    assert {a["name"] for a in data} == set(agents)
    # With bulk queries the endpoint should stay well below one query per agent.
    assert (
        len(statements) <= 15
    ), f"list_agents issued {len(statements)} SQL queries for {len(agents)} agents"


@pytest.mark.asyncio
async def test_list_agents_marks_expired_running_heartbeat_as_stalled(app, auth_headers):
    from hub.db.engine import async_session_factory
    from hub.db.models import AgentHeartbeat

    sync_resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"stale-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200

    async with async_session_factory() as session:
        session.add(
            AgentHeartbeat(
                id="hb-stale-running",
                project_id="proj-test",
                agent="stale-agent",
                status="running",
                message="Responding",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=3),
            )
        )
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    stale_agent = next(agent for agent in resp.json() if agent["name"] == "stale-agent")
    assert stale_agent["status"] == "stalled"
    # The message used to tell the operator to restart the watchdog, deleted in
    # 2026-08-03-single-runtime. It now points at somewhere that exists.
    assert "watchdog" not in stale_agent["latest_status_msg"].lower()
    assert "may have stopped" in stale_agent["latest_status_msg"]


@pytest.mark.asyncio
async def test_list_agents_shows_running_for_active_direct_spawn_run(app, auth_headers):
    """A Hub direct-spawn run (agent_trigger.py) never posts a heartbeat — the
    agents list must still report "running" by consulting the Run table,
    not only AgentHeartbeat, or a live direct-spawn run is invisible in the UI."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    sync_resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"direct-spawn-agent": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync_resp.status_code == 200

    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-active-test",
                project_id="proj-test",
                agent="direct-spawn-agent",
                status="running",
            )
        )
        await session.commit()

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    agent = next(a for a in resp.json() if a["name"] == "direct-spawn-agent")
    assert agent["status"] == "running"


# Moved from the deleted `test_agents_self_registered.py` (`agents-no-longer-register-themselves`,
# task 2.7): what they test is the charter/agent context routes, the roster summary and PATCH, not
# registration. The agents they need are inserted with `add_agent`.


@pytest.mark.asyncio
async def test_get_agent_context_known_agent_gets_runtime_context(app, auth_headers, add_agent):
    """A Hub agent gets runtime context, with quality gates when configured.

    An agent row is the only thing that makes an agent "known" — synced session data does
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

    await add_agent("claude-known")

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
async def test_get_agent_context_never_tells_a_known_agent_to_stand_down(
    app, auth_headers, add_agent
):
    """The stand-down block is gone.

    It was applied to every Hub-native agent unconditionally, which is why agents answered a
    clear operator instruction with "the user hasn't given me any explicit task yet" and then
    tried to message a non-existent `principal`.
    """
    await add_agent("hermes-context")

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
async def test_get_agent_context_describes_the_tool_surface(app, auth_headers, add_agent):
    """Naming a tool without its accepted values is what made Codex guess `message_type="text"`,
    and the four job tools were never mentioned to agents at all."""
    await add_agent("tools-agent")

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
        "archive_job",
        "toggle_job",
        "run_job",
    ):
        assert tool in context, f"{tool} is callable but undescribed"

    # Constrained parameters carry their values, which is the actual fix.
    assert "`direct_trigger`" in context
    assert "`revision_needed`" in context
    assert "`critical`" in context


@pytest.mark.asyncio
async def test_get_agent_context_does_not_point_at_its_own_context_file(
    app, auth_headers, add_agent
):
    """That pointer produced the first permission denial of the operator's test: the agent read
    a file whose contents it had already been given."""
    await add_agent("pointer-agent")

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=pointer-agent", headers=auth_headers
    )
    context = resp.json()["context"]
    assert ".agentweave/context/" not in context


@pytest.mark.asyncio
async def test_get_agent_context_lists_the_real_roster(app, auth_headers, add_agent):
    """An agent must be told its peers' exact names, or it cannot address them."""
    for name in ("roster-one", "roster-two"):
        await add_agent(name)

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
async def test_agent_context_keeps_the_injected_tool_wording_outside_a_run(
    app, auth_headers, add_agent
):
    """A decision, not an omission — and held by a test rather than by a comment.

    `_render_hub_agent_context` grew an `access_path` parameter in
    `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` §2, defaulting to `"mcp"`. Only
    `trigger_agent_directly` passes it: the access path is a per-*run* fact settled at spawn time,
    and this route is answered under the project API key outside any run, so a path it named would
    be a prediction the next trigger is free to contradict.

    Flipping that default was mutation 9 of that section's check and failed nothing. This test
    covered two routes until `POST /agents/register` was deleted
    (`agents-no-longer-register-themselves`); `GET /agents/agent-context` is the one left.
    """
    await add_agent("default-idiom")

    fetched = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=default-idiom",
        headers=auth_headers,
    )
    assert fetched.status_code == 200

    context = fetched.json()["context"]
    assert "`send_message(to_agent" in context
    # No run and no runner means no grounds for the Claude-family full name, so the route keeps
    # the bare names under the "may" wording
    # (`2026-09-29-a-claude-run-is-told-its-agentweave-tools-by-their-full-names`, D2/R3).
    assert "a prefix such as `mcp__agentweave__`" in context
    assert "POST /api/v1/agent-actions/messages" not in context


@pytest.mark.asyncio
async def test_single_agent_project_gets_no_team_section(app, auth_headers, add_agent):
    """A project with one agent is told nothing about a team (umbrella task 13.9).

    The requirement is to omit the roster *and all collaboration instruction* entirely, not to
    render a Team section stating the team is empty. The old text — "No other agents are registered
    in this project yet." — is the opposite of that, and it landed in every turn of the journey a
    first-time user actually takes.
    """
    await add_agent("solo")

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=solo", headers=auth_headers
    )
    assert resp.status_code == 200
    context = resp.json()["context"]

    assert "### Team" not in context
    assert "No other agents are registered" not in context
    assert "Address a peer" not in context
    # The tools are still described — they are still callable, and `request_agent` is how a
    # single-agent project stops being one.
    assert "request_agent" in context
    assert "You are the only agent in this project." in context


@pytest.mark.asyncio
async def test_team_section_returns_as_soon_as_there_is_a_peer(app, auth_headers, add_agent):
    """The mutation check for the test above: one more agent and the whole block is back."""
    for name in ("solo", "second"):
        await add_agent(name)

    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=solo", headers=auth_headers
    )
    context = resp.json()["context"]

    assert "### Team" in context
    assert "`solo`" in context and "`second`" in context
    assert "Address a peer by the exact name above" in context
    assert "You are the only agent in this project." not in context


@pytest.mark.asyncio
async def test_agent_summary_reports_the_bound_runner(app, auth_headers, add_agent, bind_runner):
    """A runner-bound agent reports its runner's cli and model, not "native"/"Native".

    The summary used to derive these from synced session config merged over Agent.config,
    neither of which carries the binding, so every Hub-created agent reported "Native"
    despite holding a correct runner_id.
    """
    await add_agent("bound-agent")
    await bind_runner("bound-agent", cli="codex", model="gpt-5.6-luna")

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    agent = next(a for a in resp.json() if a["name"] == "bound-agent")
    assert agent["runner"] == "codex"
    assert agent["display_model"] == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_agent_summary_reports_the_bound_runners_compaction_point(
    app, auth_headers, add_agent, bind_runner
):
    """A Copilot-bound agent reports its adapter's compaction point (80); an unbound one is null.

    `checkpoint_compaction_percent` reads `_bound_adapter.compaction_percent` — the same adapter
    the summary already resolves for `permission_mode_at_rest` — so this is the one summary field
    `checkpoint_trigger.consider` also derives from, surfaced for the operator to see.
    """
    await add_agent("copilot-bound")
    await bind_runner("copilot-bound", cli="copilot")
    await add_agent("unbound-agent-2")

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    by_name = {a["name"]: a for a in resp.json()}
    assert by_name["copilot-bound"]["checkpoint_compaction_percent"] == 80
    assert by_name["unbound-agent-2"]["checkpoint_compaction_percent"] is None


@pytest.mark.asyncio
async def test_agent_summary_keeps_stored_config_when_unbound(app, auth_headers, add_agent):
    """An agent with no bound runner still derives runner and model from its own stored config.

    `Agent.config` is PATCH-able and carries `runner`/`model` keys, so the runner override must not
    clobber them when no runner row is bound. The retired `dev_role` fields stay absent.
    """
    await add_agent(
        "unbound-agent", config={"runner": "opencode", "model": "ollama/qwen2.5-coder:7b"}
    )

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert resp.status_code == 200
    agent = next(a for a in resp.json() if a["name"] == "unbound-agent")
    assert agent["runner"] == "opencode"
    assert agent["display_model"] == "ollama/qwen2.5-coder:7b"
    assert "dev_role" not in agent
    assert "dev_roles" not in agent


@pytest.mark.asyncio
async def test_agent_summary_carries_no_role_or_yolo(app, auth_headers, add_agent):
    """The summary exposes neither `role` nor `yolo`, even when both sit in stored config.

    `role` is the deleted multi-role subsystem's last remnant: nothing in the Hub reads it.
    `yolo` is different — it is live in `Agent.config`, where `runner_commands` and
    `codex_appserver` read it — but it is not an operator-facing summary field, and the
    read-only badge that rendered it is gone. Asserting absence here is what stops either
    returning unnoticed. Tasks 1.2/1.5 of 2026-08-08-agent-configuration-page.
    """
    await add_agent(
        "hermes-legacy-fields",
        config={"runner": "claude", "model": "sonnet", "role": "principal", "yolo": True},
    )

    # The config store keeps both — removal is of the response field, not of the setting. A
    # merge of an unchanged key reads the config back (`{}` is refused since F243).
    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/hermes-legacy-fields",
        json={"config": {"model": "sonnet"}},
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
async def test_patch_agent_config(app, auth_headers, add_agent):
    """Test PATCH merges config without touching other fields."""
    await add_agent("hermes-patch", config={"runner": "kimi", "model": "kimi-k2", "yolo": False})

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


@pytest.mark.asyncio
async def test_agent_description_round_trips_and_normalizes_blank(app, auth_headers, add_agent):
    """A description is set, read back on the summary, and cleared.

    Blank is not a description. It collapses to null on write, so "cleared" and "never written"
    are the same state and no consumer has to test for both. Task 3.1 of
    2026-08-08-agent-configuration-page.
    """
    await add_agent("hermes-described")

    # Absent until written — not "".
    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    hermes = next(a for a in resp.json() if a["name"] == "hermes-described")
    assert hermes["description"] is None

    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/hermes-described",
        json={"description": "  Reviews migrations before they ship.  "},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Reviews migrations before they ship."

    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    hermes = next(a for a in resp.json() if a["name"] == "hermes-described")
    assert hermes["description"] == "Reviews migrations before they ship."

    # Whitespace-only clears rather than storing a blank.
    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/hermes-described",
        json={"description": "   "},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] is None


@pytest.mark.asyncio
async def test_agent_description_refuses_overlong_and_non_text(app, auth_headers, add_agent):
    """Bounded at the API, not only in the input box.

    The column is String(256); a longer value would be truncated or rejected by the backend
    depending on the database, which is not a behaviour worth having two of.
    """
    await add_agent("hermes-desc-bounds")

    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/hermes-desc-bounds",
        json={"description": "x" * 257},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/hermes-desc-bounds",
        json={"description": 42},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # Neither attempt stored anything.
    resp = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    hermes = next(a for a in resp.json() if a["name"] == "hermes-desc-bounds")
    assert hermes["description"] is None


@pytest.mark.asyncio
async def test_a_configured_agent_can_be_described(app, auth_headers, add_agent):
    """A description is not a session-config field, so the configured-agent guard must not claim it.

    An agent does not stop being describable because of how it was declared — the same reasoning
    that made the waiting settings and the runner/charter bindings unrestricted.
    """
    await add_agent("claude")

    resp = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "id": "sess-describe",
                "name": "Test Session",
                "mode": "hierarchical",
                "principal": "claude",
                "agents": {"claude": {"runner": "claude"}},
            }
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # The guard still holds for the field it owns (`config`; `contact_mode` was the other,
    # dropped with self-registration).
    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/claude",
        json={"config": {"yolo": True}},
        headers=auth_headers,
    )
    assert resp.status_code == 409

    resp = await app.patch(
        "/api/v1/projects/proj-test/agents/claude",
        json={"description": "The one the session config declared."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "The one the session config declared."
