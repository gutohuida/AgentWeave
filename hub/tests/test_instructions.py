"""Tests for project-wide instructions endpoints."""

import pytest


@pytest.mark.asyncio
async def test_get_instructions_empty(app, auth_headers):
    """Test GET returns empty string when no instructions are set."""
    resp = await app.get("/api/v1/projects/proj-test/project/instructions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == ""


@pytest.mark.asyncio
async def test_put_and_get_instructions(app, auth_headers):
    """Test PUT sets instructions and GET returns them."""
    # Set instructions
    resp = await app.put(
        "/api/v1/projects/proj-test/project/instructions",
        json={"content": "# Project Rules\n\nAlways write tests."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "# Project Rules\n\nAlways write tests."

    # Retrieve instructions
    resp = await app.get("/api/v1/projects/proj-test/project/instructions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["content"] == "# Project Rules\n\nAlways write tests."


@pytest.mark.asyncio
async def test_put_overwrites_instructions(app, auth_headers):
    """Test PUT upserts instructions (overwrites existing)."""
    # First PUT
    resp = await app.put(
        "/api/v1/projects/proj-test/project/instructions",
        json={"content": "First version"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Second PUT
    resp = await app.put(
        "/api/v1/projects/proj-test/project/instructions",
        json={"content": "Second version"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # Verify overwritten
    resp = await app.get("/api/v1/projects/proj-test/project/instructions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["content"] == "Second version"


@pytest.mark.asyncio
async def test_get_agent_context_places_instructions_before_charter(app, auth_headers, add_agent):
    """Full agent context layers project instructions ahead of charter guidance."""
    # Set project instructions
    resp = await app.put(
        "/api/v1/projects/proj-test/project/instructions",
        json={"content": "# Global Rule\n\nBe concise."},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    charter = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Instruction Test", "content": "Charter guidance"},
            headers=auth_headers,
        )
    ).json()
    await add_agent("instruction-agent")
    await app.patch(
        "/api/v1/projects/proj-test/agents/instruction-agent",
        json={"charter_id": charter["id"]},
        headers=auth_headers,
    )
    resp = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=instruction-agent",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    content = resp.json()["context"]

    assert "# Global Rule\n\nBe concise." in content
    assert content.index("# Global Rule") < content.index("Charter guidance")


@pytest.mark.asyncio
async def test_an_empty_body_is_refused_and_clearing_takes_an_explicit_empty_string(
    app, auth_headers
):
    """F647: `{}` used to clear the instructions without a word, bypassing the app's confirmation.
    An omitted `content` is now refused and changes nothing; `{"content": ""}` still clears."""
    url = "/api/v1/projects/proj-test/project/instructions"
    put = await app.put(url, json={"content": "Keep me."}, headers=auth_headers)
    assert put.status_code == 200, put.text

    empty = await app.put(url, json={}, headers=auth_headers)

    assert empty.status_code == 422, empty.text
    assert "content" in empty.text
    assert (await app.get(url, headers=auth_headers)).json()["content"] == "Keep me."
    cleared = await app.put(url, json={"content": ""}, headers=auth_headers)
    assert cleared.status_code == 200 and cleared.json()["content"] == ""
