"""Tests for status endpoint."""

import pytest


@pytest.mark.asyncio
async def test_status_structure(app, auth_headers):
    resp = await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "project_id" in data
    assert "project_name" in data
    assert "message_counts" in data
    assert "task_counts" in data
    assert "question_counts" in data
    assert "agents_active" in data
    assert data["message_counts"]["total"] >= 0
