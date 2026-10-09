"""Charter-backed agent context tests for phase 2.3."""

import pytest


async def _create_agent_and_charter(
    app, auth_headers, add_agent, *, content: str = "Custom charter"
):
    charter = (
        await app.post(
            "/api/v1/projects/proj-test/charters",
            json={"name": "Custom Charter", "content": content},
            headers=auth_headers,
        )
    ).json()
    await add_agent("chartered")
    bound = await app.patch(
        "/api/v1/projects/proj-test/agents/chartered",
        json={"charter_id": charter["id"]},
        headers=auth_headers,
    )
    assert bound.status_code == 200
    return charter


@pytest.mark.asyncio
async def test_agent_context_includes_bound_charter(app, auth_headers, add_agent):
    charter = await _create_agent_and_charter(
        app, auth_headers, add_agent, content="# Custom Charter\n\nHonor the release checklist."
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
async def test_agent_context_uses_edited_charter_content(app, auth_headers, add_agent):
    charter = await _create_agent_and_charter(app, auth_headers, add_agent, content="Old behavior")
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
async def test_agent_without_charter_gets_instructions_and_notice(app, auth_headers, add_agent):
    instructions = await app.put(
        "/api/v1/projects/proj-test/project/instructions",
        json={"content": "# Project Rules\n\nKeep changes focused."},
        headers=auth_headers,
    )
    assert instructions.status_code == 200
    await add_agent("unchartered")

    response = await app.get(
        "/api/v1/projects/proj-test/agents/agent-context?agent=unchartered", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["charter_id"] is None
    assert "# Project Rules" in data["context"]
    assert "No charter is assigned" in data["context"]


@pytest.mark.asyncio
async def test_bind_agent_to_unknown_charter_is_refused(app, auth_headers, add_agent):
    await add_agent("unknown-charter")
    response = await app.patch(
        "/api/v1/projects/proj-test/agents/unknown-charter",
        json={"charter_id": "charter-does-not-exist"},
        headers=auth_headers,
    )
    # The charter's 404, not the agent's: when the fixture was the deleted register route this
    # passed without the agent existing at all.
    assert response.status_code == 404
    assert "Charter 'charter-does-not-exist' not found" in response.json()["detail"]
