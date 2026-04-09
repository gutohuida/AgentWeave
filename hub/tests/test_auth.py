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
