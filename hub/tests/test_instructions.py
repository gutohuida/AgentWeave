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
async def test_get_agent_context_places_instructions_before_charter(app, auth_headers):
    """Full agent context layers project instructions ahead of charter guidance."""
    # Set project instructions
    resp = await app.put(
        "/api/v1/project/instructions",
        json={"content": "# Global Rule\n\nBe concise."},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    charter = (
        await app.post(
            "/api/v1/charters",
            json={"name": "Instruction Test", "content": "Charter guidance"},
            headers=auth_headers,
        )
    ).json()
    await app.post(
        "/api/v1/agents/register",
        json={"name": "instruction-agent", "contact_mode": "poll"},
        headers=auth_headers,
    )
    await app.patch(
        "/api/v1/agents/instruction-agent",
        json={"charter_id": charter["id"]},
        headers=auth_headers,
    )
    resp = await app.get(
        "/api/v1/agents/agent-context?agent=instruction-agent", headers=auth_headers
    )
    assert resp.status_code == 200
    content = resp.json()["context"]

    assert "# Global Rule\n\nBe concise." in content
    assert content.index("# Global Rule") < content.index("Charter guidance")

    direct = await app.get(
        f"/api/v1/agents/context?charter={charter['id']}", headers=auth_headers
    )
    assert direct.status_code == 200
    assert direct.json()["content"] == "# Global Rule\n\nBe concise.\n\n---\n\nCharter guidance"


@pytest.mark.asyncio
async def test_direct_charter_context_without_instructions_is_unchanged(app, auth_headers):
    """With no project instructions, direct lookup returns the charter unchanged."""
    # Ensure no instructions are set (clean up from prior tests)
    await app.put(
        "/api/v1/project/instructions",
        json={"content": ""},
        headers=auth_headers,
    )

    charter = (
        await app.post(
            "/api/v1/charters",
            json={"name": "Direct", "content": "Direct guidance"},
            headers=auth_headers,
        )
    ).json()
    resp = await app.get(f"/api/v1/agents/context?charter={charter['id']}", headers=auth_headers)
    assert resp.status_code == 200
    content = resp.json()["content"]

    assert content == "Direct guidance"
