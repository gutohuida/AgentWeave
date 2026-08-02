"""Stable AgentWeave conversation identity contract."""

from unittest.mock import MagicMock, patch

import pytest

import hub.api.v1.agent_trigger as agent_trigger


async def _await_background_runs() -> None:
    while agent_trigger._background_runs:
        for task in list(agent_trigger._background_runs):
            await task


def _fake_pty(lines, exit_code=0):
    session = MagicMock()
    session.pid = 4242
    session.read.side_effect = [*lines, ""]
    session.wait.return_value = exit_code
    return MagicMock(return_value=session)


@pytest.mark.asyncio
async def test_new_trigger_returns_conversation_before_provider_binding(app, auth_headers):
    sync = await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"offline": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200

    response = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "offline", "message": "first"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["conversation_id"].startswith("conv-")
    assert body["queue_entry_id"].startswith("entry-")
    assert body["provider_session_id"] is None

    conversations = await app.get(
        "/api/v1/agent/offline/conversations", headers=auth_headers
    )
    assert conversations.status_code == 200
    assert conversations.json()[0]["id"] == body["conversation_id"]


@pytest.mark.asyncio
async def test_follow_up_uses_returned_conversation_while_unbound(app, auth_headers):
    await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"offline": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    first = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "offline", "message": "first"},
        headers=auth_headers,
    )
    conversation_id = first.json()["conversation_id"]

    second = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "offline",
            "message": "follow-up",
            "conversation_id": conversation_id,
        },
        headers=auth_headers,
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id
    history = await app.get(
        f"/api/v1/agent/offline/chat/{conversation_id}", headers=auth_headers
    )
    assert [entry["content"] for entry in history.json()["entries"]] == [
        "first",
        "follow-up",
    ]


@pytest.mark.asyncio
async def test_conversation_cannot_be_used_for_another_agent(app, auth_headers):
    await app.post(
        "/api/v1/session/sync",
        json={
            "data": {
                "agents": {
                    "one": {"runner": "manual"},
                    "two": {"runner": "manual"},
                }
            }
        },
        headers=auth_headers,
    )
    first = await app.post(
        "/api/v1/agent/trigger",
        json={"agent": "one", "message": "first"},
        headers=auth_headers,
    )

    response = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "two",
            "message": "wrong target",
            "conversation_id": first.json()["conversation_id"],
        },
        headers=auth_headers,
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_provider_binding_updates_conversation_without_changing_identity(app, auth_headers):
    await app.post(
        "/api/v1/session/sync",
        json={"data": {"agents": {"claude": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"provider-1"}\n']
    )

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/agent/trigger",
                json={"agent": "claude", "message": "first"},
                headers=auth_headers,
            )
            conversation_id = response.json()["conversation_id"]
            await _await_background_runs()

    conversations = await app.get(
        "/api/v1/agent/claude/conversations", headers=auth_headers
    )
    row = next(item for item in conversations.json() if item["id"] == conversation_id)
    assert row["provider_session_id"] == "provider-1"

    follow_up = await app.post(
        "/api/v1/agent/trigger",
        json={
            "agent": "claude",
            "message": "second",
            "conversation_id": conversation_id,
        },
        headers=auth_headers,
    )
    assert follow_up.json()["conversation_id"] == conversation_id
