"""An agent is archived, never deleted.

Section 3b of openspec/changes/2026-08-08-agent-configuration-page. The decision under test is
not "archival works" but "deletion does not exist" — so the last test here asserts the absence of
a route, which is the only way a commitment not to add one survives the next person who wants one.
"""

from __future__ import annotations

import pytest


async def _register(app, auth_headers, name: str):
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": name, "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    return resp


async def _names(app, auth_headers, lifecycle: str | None = None):
    url = "/api/v1/projects/proj-test/agents"
    if lifecycle:
        url += f"?lifecycle={lifecycle}"
    resp = await app.get(url, headers=auth_headers)
    assert resp.status_code == 200
    return [a["name"] for a in resp.json()]


@pytest.mark.asyncio
async def test_archive_removes_the_agent_from_the_default_roster(app, auth_headers):
    await _register(app, auth_headers, "archie")
    assert "archie" in await _names(app, auth_headers)

    resp = await app.post(
        "/api/v1/projects/proj-test/agents/archie/archive", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["lifecycle"] == "archived"

    # The default listing is what every surface that offers an agent reads, so one filter here
    # is what takes an archived agent out of the rail, task assignment and peer recipients.
    assert "archie" not in await _names(app, auth_headers)


@pytest.mark.asyncio
async def test_an_archived_agent_is_reachable_when_asked_for(app, auth_headers):
    await _register(app, auth_headers, "findable")
    await app.post("/api/v1/projects/proj-test/agents/findable/archive", headers=auth_headers)

    # Without this the agent could be archived and then never unarchived, because its own
    # configuration page resolves the agent from the roster.
    assert "findable" in await _names(app, auth_headers, "archived")
    assert "findable" in await _names(app, auth_headers, "all")


@pytest.mark.asyncio
async def test_unarchive_restores_the_agent(app, auth_headers):
    await _register(app, auth_headers, "backagain")
    await app.post("/api/v1/projects/proj-test/agents/backagain/archive", headers=auth_headers)

    resp = await app.post(
        "/api/v1/projects/proj-test/agents/backagain/unarchive", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["lifecycle"] == "open"
    assert "backagain" in await _names(app, auth_headers)
    assert "backagain" not in await _names(app, auth_headers, "archived")


@pytest.mark.asyncio
async def test_archiving_is_idempotent(app, auth_headers):
    await _register(app, auth_headers, "twice")
    first = await app.post(
        "/api/v1/projects/proj-test/agents/twice/archive", headers=auth_headers
    )
    second = await app.post(
        "/api/v1/projects/proj-test/agents/twice/archive", headers=auth_headers
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["lifecycle"] == "archived"


@pytest.mark.asyncio
async def test_archiving_an_unknown_agent_is_404(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/ghost/archive", headers=auth_headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_a_running_agent_is_refused_with_a_reason(app, auth_headers):
    """Refused, not resolved. Stopping a live run from a settings page destroys work with no undo."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Run

    await _register(app, auth_headers, "busy")
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-archival-test",
                project_id="proj-test",
                agent="busy",
                status="running",
            )
        )
        await session.commit()

    resp = await app.post(
        "/api/v1/projects/proj-test/agents/busy/archive", headers=auth_headers
    )
    assert resp.status_code == 409
    assert "run in progress" in resp.json()["detail"]

    # And the run is untouched — the refusal did not stop it to get its way.
    assert "busy" in await _names(app, auth_headers)


@pytest.mark.asyncio
async def test_a_peer_send_to_an_archived_agent_is_refused_with_its_content(app, auth_headers):
    """The archived-*agent* case, which the archived-*conversation* contract does not cover.

    Opening a new conversation would not help: nothing runs an archived agent, so the entry would
    sit queued forever. So the send is refused — and it carries the sender's own content back, so
    retrying is mechanical rather than reconstructive.
    """
    await _register(app, auth_headers, "sender")
    await _register(app, auth_headers, "gone")
    await app.post("/api/v1/projects/proj-test/agents/gone/archive", headers=auth_headers)

    resp = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "sender",
            "to": "gone",
            "subject": "still there?",
            "content": "The thing I did not want to have to write twice.",
            "type": "message",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "archived" in detail
    assert "unarchive" in detail
    assert "The thing I did not want to have to write twice." in detail


@pytest.mark.asyncio
async def test_an_archived_agent_keeps_its_history(app, auth_headers):
    """Archival is tidying, not deletion — the messages an agent sent keep their attribution."""
    await _register(app, auth_headers, "historian")
    await _register(app, auth_headers, "listener")

    sent = await app.post(
        "/api/v1/projects/proj-test/messages",
        json={
            "from": "historian",
            "to": "listener",
            "subject": "before",
            "content": "Said before archiving.",
            "type": "message",
        },
        headers=auth_headers,
    )
    assert sent.status_code in (200, 201)

    await app.post("/api/v1/projects/proj-test/agents/historian/archive", headers=auth_headers)

    resp = await app.get("/api/v1/projects/proj-test/messages", headers=auth_headers)
    assert resp.status_code == 200
    payload = resp.json()
    rows = payload if isinstance(payload, list) else payload.get("messages", [])
    # The response serializes sender/recipient back to "from"/"to".
    mine = [m for m in rows if m.get("from") == "historian"]
    assert mine, "the archived agent's messages disappeared"
    assert any(m.get("content") == "Said before archiving." for m in mine)


@pytest.mark.asyncio
async def test_no_route_hard_deletes_an_agent(app, auth_headers):
    """The decision is that agents are archived, never deleted.

    Asserted as the absence of a route rather than as a comment, so adding one is a visible
    failure rather than a quiet reversal of the decision.
    """
    resp = await app.delete("/api/v1/projects/proj-test/agents/anything", headers=auth_headers)
    assert resp.status_code in (404, 405), (
        "A DELETE route for an agent appeared. Agents are archived, never deleted — see "
        "hub/hub/agent_lifecycle.py. If this is a deliberate reversal, change the spec first."
    )
