"""Tests for project-wide instructions endpoints."""

import pytest


@pytest.mark.asyncio
async def test_get_instructions_empty(app, auth_headers):
    """Test GET returns empty string when no instructions are set."""
    resp = await app.get("/api/v1/project/instructions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == ""


@pytest.mark.asyncio
async def test_put_and_get_instructions(app, auth_headers):
    """Test PUT sets instructions and GET returns them."""
    # Set instructions
    resp = await app.put(
        "/api/v1/project/instructions",
        json={"content": "# Project Rules\n\nAlways write tests."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "# Project Rules\n\nAlways write tests."

    # Retrieve instructions
    resp = await app.get("/api/v1/project/instructions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "# Project Rules\n\nAlways write tests."


@pytest.mark.asyncio
async def test_put_overwrites_instructions(app, auth_headers):
    """Test PUT upserts instructions (overwrites existing)."""
    # First PUT
    resp = await app.put(
        "/api/v1/project/instructions",
        json={"content": "First version"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Second PUT
    resp = await app.put(
        "/api/v1/project/instructions",
        json={"content": "Second version"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Verify overwritten
    resp = await app.get("/api/v1/project/instructions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["content"] == "Second version"


@pytest.mark.asyncio
async def test_get_context_prepends_instructions(app, auth_headers):
    """Test that role context prepends project instructions when set."""
    # Set project instructions
    resp = await app.put(
        "/api/v1/project/instructions",
        json={"content": "# Global Rule\n\nBe concise."},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Get context for a known role
    resp = await app.get("/api/v1/agents/context?role=backend_dev", headers=auth_headers)
    assert resp.status_code == 200
    content = resp.json()["content"]

    assert content.startswith("# Global Rule\n\nBe concise.")
    assert "\n\n---\n\n" in content


@pytest.mark.asyncio
async def test_get_context_without_instructions(app, auth_headers):
    """Test that role context does not prepend separator when no instructions."""
    # Ensure no instructions are set (clean up from prior tests)
    await app.put(
        "/api/v1/project/instructions",
        json={"content": ""},
        headers=auth_headers,
    )

    resp = await app.get("/api/v1/agents/context?role=backend_dev", headers=auth_headers)
    assert resp.status_code == 200
    content = resp.json()["content"]

    assert not content.startswith("\n\n---\n\n")
    assert "\n\n---\n\n" not in content
