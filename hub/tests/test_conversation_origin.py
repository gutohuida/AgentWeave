"""Where a conversation came from is recorded at creation and never changes.

Peer-created conversations are real rows today. Without `origin` they appear in the rail
indistinguishable from ones the operator started, which is the whole reason the column exists.
"""

import pytest

from hub.conversations import new_conversation


async def _sync_agents(app, auth_headers, *names):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _conversations(app, auth_headers, agent, lifecycle=None):
    suffix = f"?lifecycle={lifecycle}" if lifecycle else ""
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/conversations{suffix}", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_helper_refuses_an_origin_outside_the_closed_set() -> None:
    with pytest.raises(ValueError) as excinfo:
        new_conversation(project_id="proj-x", agent="a", origin="invented")
    assert "origin must be one of" in str(excinfo.value)


@pytest.mark.parametrize("origin", ["operator", "peer", "handoff", "spec", "job"])
def test_every_accepted_origin_is_constructible(origin: str) -> None:
    """`handoff` and `spec` have no producer yet. They are accepted anyway, deliberately, so
    that adding one later does not leave every conversation predating it mis-recorded."""
    assert new_conversation(project_id="proj-x", agent="a", origin=origin).origin == origin


@pytest.mark.asyncio
async def test_an_operator_started_conversation_records_operator(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "offline")
    await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Look at the build"},
        headers=auth_headers,
    )

    assert (await _conversations(app, auth_headers, "offline"))[0]["origin"] == "operator"


@pytest.mark.asyncio
async def test_a_peer_created_conversation_records_peer(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "sender", "recipient")

    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"from": "sender", "to": "recipient", "content": "Please review the migration"},
        headers=auth_headers,
    )
    assert sent.status_code == 201, sent.text

    conversations = await _conversations(app, auth_headers, "recipient")
    assert len(conversations) == 1
    assert conversations[0]["origin"] == "peer"
    # It is named by the message that opened it, like any other conversation.
    assert conversations[0]["title"] == "Please review the migration"


@pytest.mark.asyncio
async def test_origin_survives_rename_and_archive(
    app, auth_headers, drain_conversation
) -> None:
    await _sync_agents(app, auth_headers, "sender", "recipient")
    await app.post(
        "/api/v1/projects/proj-test/messages",
        json={"from": "sender", "to": "recipient", "content": "Please review the migration"},
        headers=auth_headers,
    )
    conversation_id = (await _conversations(app, auth_headers, "recipient"))[0]["id"]
    await drain_conversation(conversation_id)
    base = f"/api/v1/projects/proj-test/agent/recipient/conversations/{conversation_id}"

    renamed = await app.patch(base, json={"title": "Migration review"}, headers=auth_headers)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["origin"] == "peer"

    archived = await app.post(f"{base}/archive", headers=auth_headers)
    assert archived.status_code == 200, archived.text
    assert archived.json()["origin"] == "peer"

    unarchived = await app.post(f"{base}/unarchive", headers=auth_headers)
    assert unarchived.status_code == 200, unarchived.text
    assert unarchived.json()["origin"] == "peer"
