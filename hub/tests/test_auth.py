"""Tests for API key authentication."""

import pytest


@pytest.mark.asyncio
async def test_no_auth_returns_401(app):
    resp = await app.get("/api/v1/status")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bad_key_returns_401(app):
    resp = await app.get("/api/v1/status", headers={"Authorization": "Bearer aw_live_wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_key_returns_200(app, auth_headers):
    resp = await app.get("/api/v1/status", headers=auth_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_query_token_rejected_on_non_sse_endpoints(app, auth_headers):
    """S3: ?token= fallback must not work on regular REST endpoints."""
    token = "aw_live_testkey_abcdefgh"
    resp = await app.get("/api/v1/status", params={"token": token})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_old_api_key_query_rejected_for_sse(app):
    """S3: raw API keys in ?token= must not be accepted by the SSE stream."""
    import httpx

    token = "aw_live_testkey_abcdefgh"
    try:
        resp = await app.get(
            "/api/v1/events", params={"token": token}, timeout=httpx.Timeout(1.0)
        )
    except httpx.ReadTimeout:
        assert False, "SSE stream accepted raw API key and hung instead of 401"
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_sse_ticket_flow(app, auth_headers):
    """S3: /events/ticket returns a signed token that works on /events."""
    import asyncio

    ticket_resp = await app.get("/api/v1/events/ticket", headers=auth_headers)
    assert ticket_resp.status_code == 200
    token = ticket_resp.json()["token"]
    assert token.startswith("aw_ticket_")

    # The SSE endpoint intentionally never closes. If the ticket is rejected we
    # would get an immediate 401; if accepted, the connection stays open.
    try:
        await asyncio.wait_for(
            app.get("/api/v1/events", params={"token": token}),
            timeout=1.0,
        )
    except (asyncio.TimeoutError, TimeoutError):
        pass  # expected: ticket accepted and stream is held open
    else:
        assert False, "SSE stream returned immediately instead of staying open"


@pytest.mark.asyncio
async def test_oversized_request_body_rejected(app, auth_headers):
    """Bonus: requests larger than the default 1 MB body cap return 413."""
    big_content = "x" * (1_048_576 + 1)
    resp = await app.post(
        "/api/v1/messages",
        json={
            "from": "user",
            "to": "alice",
            "subject": "big",
            "content": big_content,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 413
