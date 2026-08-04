"""Hub runtime diagnostics visibility tests."""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_agent_trigger_reports_missing_cli_directly(app, auth_headers, bind_runner):
    """Decision 2: the trigger endpoint reports what actually happened, not a guess about
    whether some other process (the watchdog) might eventually notice a queued message.
    An agent bound to a runner whose CLI has no matching binary on PATH is refused with a
    stated reason — execution_confidence and watchdog-heartbeat staleness no longer factor
    into the response at all.
    """
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"diag-no-such-cli": {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("diag-no-such-cli", cli="claude")

    with patch("hub.launchability.shutil.which", return_value=None):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "diag-no-such-cli", "message": "hello", "session_mode": "new"},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"
    assert "not found in PATH" in resp.json()["waiting_reason"]
    assert "execution_confidence" not in resp.json()
    assert "watchdog" not in resp.json()["waiting_reason"].lower()


@pytest.mark.asyncio
async def test_log_agents_endpoint_includes_configured_and_logged_agents(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={
            "name": "minimax",
            "contact_mode": "poll",
            "config": {"runner": "claude_proxy"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200

    log_resp = await app.post(
        "/api/v1/projects/proj-test/logs",
        json={
            "event_type": "proxy_api_key_missing",
            "agent": "glm",
            "severity": "error",
            "data": {"category": "proxy", "api_key_var": "ZHIPU_API_KEY"},
        },
        headers=auth_headers,
    )
    assert log_resp.status_code == 201

    agents_resp = await app.get("/api/v1/projects/proj-test/logs/agents", headers=auth_headers)
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
        "/api/v1/projects/proj-test/jobs",
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

    run = await app.post(f"/api/v1/projects/proj-test/jobs/{job_id}/run", headers=auth_headers)
    assert run.status_code == 503

    history = await app.get(
        f"/api/v1/projects/proj-test/jobs/{job_id}/history", headers=auth_headers
    )
    assert history.status_code == 200
    runs = history.json()
    assert runs[0]["status"] == "failed"
    assert "scheduler not available" in runs[0]["error_summary"].lower()
