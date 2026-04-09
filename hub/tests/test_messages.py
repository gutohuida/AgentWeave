"""Tests for message endpoints."""

import pytest


@pytest.mark.asyncio
async def test_create_and_list_message(app, auth_headers):
    # Create a message
    resp = await app.post(
        "/api/v1/messages",
        json={
            "from": "claude",
            "to": "kimi",
            "subject": "Hello",
            "content": "Hi there",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("msg-")
    assert data["from"] == "claude"
    assert data["to"] == "kimi"

    # List messages for kimi
    resp2 = await app.get("/api/v1/messages?agent=kimi", headers=auth_headers)
    assert resp2.status_code == 200
    messages = resp2.json()
    assert len(messages) >= 1
    assert messages[0]["to"] == "kimi"


@pytest.mark.asyncio
async def test_mark_message_read(app, auth_headers):
    # Create
    resp = await app.post(
        "/api/v1/messages",
        json={"from": "claude", "to": "kimi", "content": "Test"},
        headers=auth_headers,
    )
    msg_id = resp.json()["id"]

    # Mark read
    resp2 = await app.patch(f"/api/v1/messages/{msg_id}/read", headers=auth_headers)
    assert resp2.status_code == 200

    # Should no longer appear in unread list
    resp3 = await app.get("/api/v1/messages?agent=kimi", headers=auth_headers)
    ids = [m["id"] for m in resp3.json()]
    assert msg_id not in ids
