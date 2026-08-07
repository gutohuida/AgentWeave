"""Archiving refuses rather than resolves.

Two obstructions, and they are refused for different reasons. Stopping a live run from a row
menu destroys work with no undo. An undelivered queue entry is not a preference at all:
`latest_open_conversation` filters on `open`, so archiving would strand the entry permanently —
the next peer message opens a fresh conversation and nothing ever delivers the old one.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run
from hub.utils import short_id


async def _sync_agents(app, auth_headers, *names):
    response = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "manual"} for name in names}}},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _conversation(app, auth_headers, agent="offline", lifecycle=None):
    suffix = f"?lifecycle={lifecycle}" if lifecycle else ""
    response = await app.get(
        f"/api/v1/projects/proj-test/agent/{agent}/conversations{suffix}", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _start_run(conversation_id: str, agent: str = "offline") -> str:
    """A run in flight against this conversation, without spawning a real process."""
    run_id = f"run-{short_id()}"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                conversation_id=conversation_id,
                status="running",
            )
        )
        await session.commit()
    return run_id


async def _finish_run(run_id: str) -> None:
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        run.status = "completed"
        await session.commit()


@pytest.mark.asyncio
async def test_a_live_run_refuses_the_archive(app, auth_headers, drain_conversation) -> None:
    await _sync_agents(app, auth_headers, "offline")
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Check the build"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]
    await drain_conversation(conversation_id)
    run_id = await _start_run(conversation_id)

    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"
    refused = await app.post(f"{base}/archive", headers=auth_headers)

    assert refused.status_code == 409
    assert "run in progress" in refused.json()["detail"]
    # Refused, not partially applied.
    assert (await _conversation(app, auth_headers))[0]["lifecycle"] == "open"

    # And the run itself is untouched — refusing is not a euphemism for stopping it.
    async with async_session_factory() as session:
        assert (await session.get(Run, run_id)).status == "running"


@pytest.mark.asyncio
async def test_the_archive_succeeds_once_the_run_finishes(
    app, auth_headers, drain_conversation
) -> None:
    await _sync_agents(app, auth_headers, "offline")
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Check the build"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]
    await drain_conversation(conversation_id)
    run_id = await _start_run(conversation_id)
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"

    assert (await app.post(f"{base}/archive", headers=auth_headers)).status_code == 409
    await _finish_run(run_id)
    assert (await app.post(f"{base}/archive", headers=auth_headers)).status_code == 200


@pytest.mark.asyncio
async def test_an_undelivered_queue_entry_refuses_the_archive(app, auth_headers) -> None:
    await _sync_agents(app, auth_headers, "offline")
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Check the build"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]

    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"
    refused = await app.post(f"{base}/archive", headers=auth_headers)

    assert refused.status_code == 409
    assert "waiting to be delivered" in refused.json()["detail"]
    assert (await _conversation(app, auth_headers))[0]["lifecycle"] == "open"

    # The entry is still queued — nothing was withdrawn or rehomed to make room.
    async with async_session_factory() as session:
        states = (
            await session.execute(
                select(InboundQueueEntry.state).where(
                    InboundQueueEntry.conversation_id == conversation_id
                )
            )
        ).scalars().all()
    assert states == ["queued"]


@pytest.mark.asyncio
async def test_the_archive_succeeds_once_the_queue_drains(
    app, auth_headers, drain_conversation
) -> None:
    await _sync_agents(app, auth_headers, "offline")
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Check the build"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"

    assert (await app.post(f"{base}/archive", headers=auth_headers)).status_code == 409
    await drain_conversation(conversation_id)
    assert (await app.post(f"{base}/archive", headers=auth_headers)).status_code == 200


@pytest.mark.asyncio
async def test_unarchiving_is_never_refused(app, auth_headers, drain_conversation) -> None:
    """Reopening obstructs nothing, so a run started against an archived conversation — however
    that happened — does not trap it in the archive."""
    await _sync_agents(app, auth_headers, "offline")
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": "Check the build"},
        headers=auth_headers,
    )
    conversation_id = created.json()["conversation_id"]
    await drain_conversation(conversation_id)
    base = f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}"
    assert (await app.post(f"{base}/archive", headers=auth_headers)).status_code == 200

    await _start_run(conversation_id)
    assert (await app.post(f"{base}/unarchive", headers=auth_headers)).status_code == 200
