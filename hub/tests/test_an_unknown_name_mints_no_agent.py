"""F618: a name that was never an agent stays not an agent, whatever route it is sent to.

`POST /agents/{name}/heartbeat` and `/output` wrote a row under any name, and `GET /agents` listed
every name seen in 24 hours of heartbeats, output and mail, so one write minted an `open` agent
the Overview counted against the agent budget. The roster is now the `agents` table, and every
agent-keyed route refuses a name with no row. Decision D9 (fix-1015) deleted `/compact` and
`/new-session` (their `hub` sender was itself listed as an agent).
"""

import pytest

BASE = "/api/v1/projects/proj-test"


async def _names(app, auth_headers):
    resp = await app.get(f"{BASE}/agents", headers=auth_headers)
    assert resp.status_code == 200
    return sorted(a["name"] for a in resp.json())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path, body",
    [
        ("heartbeat", {"status": "active", "message": "hi"}),
        ("output", {"content": "hello"}),
    ],
)
async def test_a_write_under_an_unknown_name_is_refused_and_lists_nothing(
    app, auth_headers, add_agent, path, body
):
    await add_agent("solo")
    resp = await app.post(f"{BASE}/agents/ghost/{path}", json=body, headers=auth_headers)
    assert resp.status_code == 404, resp.text
    assert "ghost is not an agent" in resp.json()["detail"]
    assert await _names(app, auth_headers) == ["solo"]
    status = await app.get(f"{BASE}/queue/ghost/status", headers=auth_headers)
    assert status.status_code == 404


@pytest.mark.asyncio
async def test_a_write_under_a_real_agent_still_lands(app, auth_headers, add_agent):
    await add_agent("solo")
    resp = await app.post(
        f"{BASE}/agents/solo/heartbeat", json={"status": "active"}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    resp = await app.post(f"{BASE}/agents/solo/output", json={"content": "x"}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert await _names(app, auth_headers) == ["solo"]


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["compact", "new-session"])
async def test_compact_and_new_session_are_gone(app, auth_headers, add_agent, path):
    await add_agent("solo")
    resp = await app.post(f"{BASE}/agents/solo/{path}", headers=auth_headers)
    assert resp.status_code in (404, 405), resp.text
    assert await _names(app, auth_headers) == ["solo"]


@pytest.mark.asyncio
async def test_mail_and_activity_under_other_names_do_not_join_the_roster(
    app, auth_headers, add_agent
):
    """The 24-hour activity fallback had no live source after the watchdog was deleted; a name
    only seen in a message is not an agent."""
    from hub.db.engine import async_session_factory
    from hub.db.models import Message

    await add_agent("solo")
    async with async_session_factory() as s:
        s.add(
            Message(
                id="msg-f618-ghost",
                project_id="proj-test",
                sender="hub",
                recipient="phantom",
                content="x",
                type="message",
            )
        )
        await s.commit()
    assert await _names(app, auth_headers) == ["solo"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        f"{BASE}/agents/nosuch/timeline",
        f"{BASE}/agents/nosuch/output",
        f"{BASE}/agent/sessions/nosuch",
    ],
)
async def test_a_read_under_an_unknown_name_is_refused(app, auth_headers, url):
    resp = await app.get(url, headers=auth_headers)
    assert resp.status_code == 404, resp.text
    assert "nosuch is not an agent" in resp.json()["detail"]
