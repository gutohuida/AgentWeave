"""Tests for agent endpoints and input validation."""

from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_get_charter_context_rejects_path_traversal_identifier(app, auth_headers):
    # Charter lookup is DB-backed; path-shaped identifiers must never read files.
    resp = await app.get(
        "/api/v1/projects/proj-test/agents/context?charter=../../../../README",
        headers=auth_headers,
    )
    assert resp.status_code in (400, 404)
    assert "charter" in resp.text.lower() or "invalid" in resp.text.lower()


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
async def test_recent_chat_limit_is_bounded(app, auth_headers):
    # M14: limit must be between 1 and 500
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
    assert "restart the host watchdog" in stale_agent["latest_status_msg"]


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
