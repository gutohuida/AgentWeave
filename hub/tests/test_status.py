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


@pytest.mark.asyncio
async def test_pending_counts_mail_not_yet_delivered(app, auth_headers, add_agent):
    """F259: `pending` read `Message.read`, which nothing in the product sets, so it always equalled
    `total`. Pending mail is mail not yet delivered, which each message's inbound entry records."""
    from sqlalchemy import select

    from hub.db.engine import async_session_factory
    from hub.db.models import InboundQueueEntry

    # No runner bound, so nothing can deliver the two messages below.
    await add_agent("inbox")
    for subject in ("first", "second"):
        sent = await app.post(
            "/api/v1/projects/proj-test/messages",
            json={"to": "inbox", "subject": subject, "content": subject},
            headers=auth_headers,
        )
        assert sent.status_code in (200, 201), sent.text

    async with async_session_factory() as session:
        entries = (
            (
                await session.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == "inbox")
                )
            )
            .scalars()
            .all()
        )
        assert [e.state for e in entries] == ["queued", "queued"]
        entries[0].state = "delivered"
        await session.commit()

    counts = (await app.get("/api/v1/projects/proj-test/status", headers=auth_headers)).json()[
        "message_counts"
    ]
    assert counts == {"pending": 1, "total": 2}
