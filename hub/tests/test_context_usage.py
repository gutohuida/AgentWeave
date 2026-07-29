"""Canonical and rolling-compatible Hub context usage tests."""

import json

import pytest

from hub.sse import sse_manager


async def _configure(app, auth_headers, agent: str) -> str:
    response = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {agent: {}}}},
        headers=auth_headers,
    )
    assert response.status_code == 200
    status = await app.get("/api/v1/status", headers=auth_headers)
    return status.json()["project_id"]


@pytest.mark.asyncio
async def test_canonical_context_round_trip_summary_and_sse(app, auth_headers):
    agent = "context-canonical"
    project_id = await _configure(app, auth_headers, agent)
    queue = sse_manager.subscribe(project_id)
    body = {
        "status": "measured",
        "source": "codex_rollout",
        "basis": "provider_context",
        "context_tokens": 250,
        "limit_tokens": 1000,
        "model": "gpt-test",
        "session_id": "sess-context",
        "observed_at": 1000,
        "breakdown": {"input_tokens": 200, "reasoning_tokens": 50},
    }
    try:
        response = await app.post(
            f"/api/v1/agents/{agent}/context-usage", json=body, headers=auth_headers
        )
        assert response.status_code == 201
        event = queue.get_nowait()
        assert event.event == "context_warning"
        projected = json.loads(event.data)
        assert projected["percent"] == 25.0

        response = await app.get("/api/v1/agents", headers=auth_headers)
        summary = next(item for item in response.json() if item["name"] == agent)
        assert summary["context_usage"] == projected
    finally:
        sse_manager.unsubscribe(project_id, queue)


@pytest.mark.asyncio
async def test_context_states_and_legacy_normalization(app, auth_headers):
    cases = [
        (
            "context-estimated",
            {
                "status": "estimated",
                "source": "stdout",
                "basis": "cumulative_delta",
                "context_tokens": 20,
                "observed_at": 10,
            },
            "estimated",
        ),
        (
            "context-token-only",
            {"tokens_used": 42, "model": "legacy", "observed_at": 11},
            "measured",
        ),
        (
            "context-unavailable",
            {"status": "unavailable", "source": "reset", "observed_at": 12},
            "unavailable",
        ),
        (
            "context-unsupported",
            {"status": "unsupported", "source": "runner", "observed_at": 13},
            "unsupported",
        ),
    ]
    for agent, body, expected in cases:
        await _configure(app, auth_headers, agent)
        response = await app.post(
            f"/api/v1/agents/{agent}/context-usage", json=body, headers=auth_headers
        )
        assert response.status_code == 201, response.text
        summaries = (await app.get("/api/v1/agents", headers=auth_headers)).json()
        sample = next(item for item in summaries if item["name"] == agent)["context_usage"]
        assert sample["status"] == expected


@pytest.mark.asyncio
async def test_context_ingress_rejects_invalid_samples(app, auth_headers):
    invalid = [
        {"status": "measured", "source": "x", "observed_at": 1},
        {
            "status": "measured",
            "source": "x",
            "basis": "provider_context",
            "context_tokens": -1,
            "observed_at": 1,
        },
        {
            "status": "measured",
            "source": "x",
            "basis": "provider_context",
            "context_tokens": 1,
            "observed_at": 1,
            "breakdown": {"messages": 1},
        },
    ]
    for body in invalid:
        response = await app.post(
            "/api/v1/agents/context-invalid/context-usage", json=body, headers=auth_headers
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_stale_or_old_session_context_cannot_replace_latest(app, auth_headers):
    agent = "context-order"
    await _configure(app, auth_headers, agent)
    endpoint = f"/api/v1/agents/{agent}/context-usage"
    newest = {
        "status": "measured",
        "source": "collector",
        "basis": "provider_context",
        "context_tokens": 90,
        "session_id": "new-session",
        "observed_at": 200,
    }
    stale = {**newest, "context_tokens": 10, "session_id": "old-session", "observed_at": 100}
    assert (await app.post(endpoint, json=newest, headers=auth_headers)).status_code == 201
    response = await app.post(endpoint, json=stale, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["status"] == "ignored"
    summaries = (await app.get("/api/v1/agents", headers=auth_headers)).json()
    sample = next(item for item in summaries if item["name"] == agent)["context_usage"]
    assert sample["session_id"] == "new-session"
    assert sample["context_tokens"] == 90
