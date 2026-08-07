"""Archiving is how a conversation leaves the rail without leaving the record.

Governance is a product pillar and runs carry cost and usage data, so nothing here deletes.
`Conversation.lifecycle` has accepted `archived` since 0017; until now nothing ever wrote it.
"""

import pytest


async def _sync_agent(app, auth_headers, name="offline"):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _conversations(app, auth_headers, agent="offline", lifecycle=None):
    suffix = f"?lifecycle={lifecycle}" if lifecycle else ""
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/conversations{suffix}", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _open_conversation(app, auth_headers, drain_conversation, message="Check the build"):
    await _sync_agent(app, auth_headers)
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": message},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    conversation_id = created.json()["conversation_id"]
    await drain_conversation(conversation_id)
    return conversation_id


@pytest.mark.asyncio
async def test_archive_and_unarchive_round_trip(
    app, auth_headers, drain_conversation
) -> None:
    conversation_id = await _open_conversation(app, auth_headers, drain_conversation)
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"

    archived = await app.post(f"{base}/archive", headers=auth_headers)
    assert archived.status_code == 200, archived.text
    assert archived.json()["lifecycle"] == "archived"
    assert archived.json()["archived_at"] is not None

    unarchived = await app.post(f"{base}/unarchive", headers=auth_headers)
    assert unarchived.status_code == 200, unarchived.text
    assert unarchived.json()["lifecycle"] == "open"
    assert unarchived.json()["archived_at"] is None


@pytest.mark.asyncio
async def test_the_listing_hides_archived_by_default(
    app, auth_headers, drain_conversation
) -> None:
    conversation_id = await _open_conversation(app, auth_headers, drain_conversation)
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"
    await app.post(f"{base}/archive", headers=auth_headers)

    assert await _conversations(app, auth_headers) == []

    archived = await _conversations(app, auth_headers, lifecycle="archived")
    assert [row["id"] for row in archived] == [conversation_id]

    everything = await _conversations(app, auth_headers, lifecycle="all")
    assert [row["id"] for row in everything] == [conversation_id]


@pytest.mark.asyncio
async def test_an_archived_conversation_is_still_readable(
    app, auth_headers, drain_conversation
) -> None:
    """Archiving removes it from the rail. It does not remove the history."""
    conversation_id = await _open_conversation(
        app, auth_headers, drain_conversation, message="Investigate the flaky checkout test"
    )
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"
    await app.post(f"{base}/archive", headers=auth_headers)

    history = await app.get(
        f"/api/v1/projects/proj-test/agent/offline/chat/{conversation_id}", headers=auth_headers
    )
    assert history.status_code == 200, history.text
    assert any(
        "Investigate the flaky checkout test" in entry["content"]
        for entry in history.json()["entries"]
    )


@pytest.mark.asyncio
async def test_unarchiving_returns_it_to_the_default_listing(
    app, auth_headers, drain_conversation
) -> None:
    conversation_id = await _open_conversation(app, auth_headers, drain_conversation)
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"

    await app.post(f"{base}/archive", headers=auth_headers)
    await app.post(f"{base}/unarchive", headers=auth_headers)

    assert [row["id"] for row in await _conversations(app, auth_headers)] == [conversation_id]
    assert await _conversations(app, auth_headers, lifecycle="archived") == []


@pytest.mark.asyncio
async def test_archiving_an_already_archived_conversation_is_idempotent(
    app, auth_headers, drain_conversation
) -> None:
    conversation_id = await _open_conversation(app, auth_headers, drain_conversation)
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"

    first = await app.post(f"{base}/archive", headers=auth_headers)
    second = await app.post(f"{base}/archive", headers=auth_headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["lifecycle"] == "archived"


@pytest.mark.asyncio
async def test_archiving_an_unknown_conversation_is_not_found(app, auth_headers) -> None:
    await _sync_agent(app, auth_headers)
    response = await app.post(
        "/api/v1/projects/proj-test/agent/offline/conversations/conv-nope/archive",
        headers=auth_headers,
    )
    assert response.status_code == 404
