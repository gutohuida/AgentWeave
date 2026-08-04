"""Charter-backed agent context tests for phase 2.3."""

import pytest


async def _create_agent_and_charter(app, auth_headers, *, content: str = "Custom charter"):
    charter = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Custom Charter", "content": content},
            headers=auth_headers,
        )
    ).json()
    registered = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "chartered", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert registered.status_code == 200
    bound = await app.patch(
        "/api/v1/projects/proj-test/agents/chartered",
        json={"charter_id": charter["id"]},
        headers=auth_headers,
    )
    assert bound.status_code == 200
    return charter


@pytest.mark.asyncio
async def test_agent_context_includes_bound_charter(app, auth_headers):
    charter = await _create_agent_and_charter(
        app, auth_headers, content="# Custom Charter\n\nHonor the release checklist."
    )

    response = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=chartered", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["charter_id"] == charter["id"]
    assert "## Charter: Custom Charter" in data["context"]
    assert "Honor the release checklist." in data["context"]


@pytest.mark.asyncio
async def test_agent_context_uses_edited_charter_content(app, auth_headers):
    charter = await _create_agent_and_charter(app, auth_headers, content="Old behavior")
    updated = await app.patch(
        f"/api/v1/projects/proj-test/charters/{charter['id']}",
        json={"content": "New behavior after edit"},
        headers=auth_headers,
    )
    assert updated.status_code == 200

    response = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=chartered", headers=auth_headers
    )
    assert "New behavior after edit" in response.json()["context"]
    assert "Old behavior" not in response.json()["context"]


@pytest.mark.asyncio
async def test_agent_without_charter_gets_instructions_and_notice(app, auth_headers):
    instructions = await app.put(
        "/api/v1/projects/proj-test/project/instructions",
        json={"content": "# Project Rules\n\nKeep changes focused."},
        headers=auth_headers,
    )
    assert instructions.status_code == 200
    registered = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "unchartered", "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert registered.status_code == 200

    response = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=unchartered", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["charter_id"] is None
    assert "# Project Rules" in data["context"]
    assert "No charter is assigned" in data["context"]


@pytest.mark.asyncio
async def test_direct_charter_lookup_returns_content_and_richer_context_hint(app, auth_headers):
    charter = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Lookup", "content": "Direct charter content"},
            headers=auth_headers,
        )
    ).json()

    response = await app.get(
        f"/api/v1/projects/proj-test/agents/context?charter={charter['id']}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["content"] == "Direct charter content"
    assert "get_agent_context" in response.json()["hint"]


@pytest.mark.asyncio
async def test_direct_charter_lookup_rejects_unknown_id(app, auth_headers):
    response = await app.get(
        "/api/v1/projects/proj-test/agents/context?charter=charter-does-not-exist",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bind_agent_to_unknown_charter_is_refused(app, auth_headers):
    await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "unknown-charter", "contact_mode": "poll"},
        headers=auth_headers,
    )
    response = await app.patch(
        "/api/v1/projects/proj-test/agents/unknown-charter",
        json={"charter_id": "charter-does-not-exist"},
        headers=auth_headers,
    )
    assert response.status_code == 404
