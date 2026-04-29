"""Hub runtime diagnostics visibility tests."""

import pytest


@pytest.mark.asyncio
async def test_agent_trigger_reports_missing_watchdog_heartbeat(app, auth_headers):
    resp = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "claude", "message": "hello", "session_mode": "new"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["execution_confidence"] == "queued_no_watchdog_heartbeat"
    assert "no watchdog heartbeat" in data["message"].lower()


@pytest.mark.asyncio
async def test_agent_trigger_reports_healthy_watchdog_heartbeat(app, auth_headers):
    hb = await app.post(
        "/api/v1/agents/claude/heartbeat",
        json={"status": "idle", "message": "ready"},
        headers=auth_headers,
    )
    assert hb.status_code == 201

    resp = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "claude", "message": "hello", "session_mode": "new"},
        headers=auth_headers,
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["execution_confidence"] == "queued_watchdog_healthy"
    assert data["watchdog_status"] == "idle"


@pytest.mark.asyncio
async def test_log_agents_endpoint_includes_configured_and_logged_agents(app, auth_headers):
    resp = await app.post(
        "/api/v1/agents/register",
        json={
            "name": "minimax",
            "contact_mode": "poll",
            "config": {"runner": "claude_proxy"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    log_resp = await app.post(
        "/api/v1/logs",
        json={
            "event_type": "proxy_api_key_missing",
            "agent": "glm",
            "severity": "error",
            "data": {"category": "proxy", "api_key_var": "ZHIPU_API_KEY"},
        },
        headers=auth_headers,
    )
    assert log_resp.status_code == 201

    agents_resp = await app.get("/api/v1/logs/agents", headers=auth_headers)
    assert agents_resp.status_code == 200
    agents = agents_resp.json()
    assert "minimax" in agents
    assert "glm" in agents
    assert "system" in agents


@pytest.mark.asyncio
async def test_manual_job_run_failure_is_persisted(app, auth_headers, monkeypatch):
    import hub.scheduler

    monkeypatch.setattr(hub.scheduler, "_scheduler_instance", None)
    create = await app.post(
        "/api/v1/jobs",
        json={
            "name": "Diagnostics job",
            "agent": "claude",
            "message": "run diagnostics",
            "cron": "0 9 * * *",
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert create.status_code == 201
    job_id = create.json()["id"]

    run = await app.post(f"/api/v1/jobs/{job_id}/run", headers=auth_headers)
    assert run.status_code == 503

    history = await app.get(f"/api/v1/jobs/{job_id}/history", headers=auth_headers)
    assert history.status_code == 200
    runs = history.json()
    assert runs[0]["status"] == "failed"
    assert "scheduler not available" in runs[0]["error_summary"].lower()
