"""Instance-level operator SSE ticket/stream: server-stamped project identity,
inactive-project visibility, project collection lifecycle events, and reconnect.

Phase 4 of local-multi-project-workspace
(openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md,
"One live operator stream identifies every project event").
"""

import asyncio

import httpx
import pytest

from hub.sse import SSEManager, sse_manager

# ---------------------------------------------------------------------------
# Ticket issuance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_ticket_requires_instance_credential(app):
    resp = await app.get("/api/v1/events/ticket")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_operator_ticket_returns_signed_token_not_project_scoped(app, auth_headers):
    resp = await app.get("/api/v1/events/ticket", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"].startswith("aw_optick_")
    assert "expires_at" in body
    assert "project_id" not in body


# ---------------------------------------------------------------------------
# Stream auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_stream_accepts_instance_credential_and_stays_open(app, auth_headers):
    try:
        await asyncio.wait_for(app.get("/api/v1/events", headers=auth_headers), timeout=1.0)
    except (asyncio.TimeoutError, TimeoutError):
        pass  # expected: accepted, stream held open
    else:
        raise AssertionError("Operator stream returned immediately instead of staying open")


@pytest.mark.asyncio
async def test_operator_stream_accepts_operator_ticket_and_stays_open(app, auth_headers):
    ticket_resp = await app.get("/api/v1/events/ticket", headers=auth_headers)
    token = ticket_resp.json()["token"]
    try:
        await asyncio.wait_for(app.get("/api/v1/events", params={"token": token}), timeout=1.0)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    else:
        raise AssertionError("Operator stream returned immediately instead of staying open")


@pytest.mark.asyncio
async def test_operator_stream_rejects_no_credential(app):
    resp = await app.get("/api/v1/events")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_operator_stream_rejects_raw_api_key_in_token_query(app):
    try:
        resp = await app.get(
            "/api/v1/events",
            params={"token": "aw_live_testkey_abcdefgh"},
            timeout=httpx.Timeout(1.0),
        )
    except httpx.ReadTimeout:
        raise AssertionError(
            "Operator stream accepted a raw API key and hung instead of 401"
        ) from None
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_operator_stream_rejects_a_project_scoped_ticket(app, auth_headers):
    """A ticket minted for one project's stream must not unlock the instance stream."""
    project_ticket = await app.get("/api/v1/projects/proj-test/events/ticket", headers=auth_headers)
    token = project_ticket.json()["token"]
    resp = await app.get("/api/v1/events", params={"token": token}, timeout=httpx.Timeout(1.0))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_project_stream_rejects_an_operator_ticket(app, auth_headers):
    """The reverse must also hold: an instance ticket must not unlock a project stream."""
    operator_ticket = await app.get("/api/v1/events/ticket", headers=auth_headers)
    token = operator_ticket.json()["token"]
    resp = await app.get(
        "/api/v1/projects/proj-test/events", params={"token": token}, timeout=httpx.Timeout(1.0)
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Server-stamped project identity (unit-level, isolated SSEManager)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_stamps_project_id_for_operator_subscribers():
    manager = SSEManager()
    q = manager.subscribe_operator()
    await manager.broadcast("proj-real", "task_created", {"id": "task-1"})
    evt = q.get_nowait()
    assert evt.event == "task_created"
    import json

    payload = json.loads(evt.data)
    assert payload == {"id": "task-1", "project_id": "proj-real"}


@pytest.mark.asyncio
async def test_broadcast_overrides_a_caller_supplied_false_project_id():
    manager = SSEManager()
    q = manager.subscribe_operator()
    await manager.broadcast(
        "proj-real", "task_created", {"id": "task-1", "project_id": "proj-fake"}
    )
    import json

    payload = json.loads(q.get_nowait().data)
    assert payload["project_id"] == "proj-real"


@pytest.mark.asyncio
async def test_broadcast_still_reaches_project_subscribers_unstamped():
    """Internal/project channels are untouched — only the operator envelope is stamped."""
    manager = SSEManager()
    project_q = manager.subscribe("proj-real")
    operator_q = manager.subscribe_operator()
    await manager.broadcast("proj-real", "task_created", {"id": "task-1"})
    import json

    project_payload = json.loads(project_q.get_nowait().data)
    assert project_payload == {"id": "task-1"}
    operator_payload = json.loads(operator_q.get_nowait().data)
    assert operator_payload == {"id": "task-1", "project_id": "proj-real"}


@pytest.mark.asyncio
async def test_unsubscribe_operator_stops_delivery():
    manager = SSEManager()
    q = manager.subscribe_operator()
    manager.unsubscribe_operator(q)
    await manager.broadcast("proj-real", "task_created", {"id": "task-1"})
    assert q.empty()


# ---------------------------------------------------------------------------
# Inactive-project visibility: the one operator stream sees every project's
# events, not only the project currently open in a project-scoped stream.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_stream_receives_events_for_a_project_with_no_own_subscriber(
    app, auth_headers
):
    q = sse_manager.subscribe_operator()
    try:
        resp = await app.post(
            "/api/v1/projects/proj-test/tasks",
            json={"title": "Seen on the operator stream"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        evt = await asyncio.wait_for(q.get(), timeout=1.0)
        assert evt.event == "task_created"
        import json

        payload = json.loads(evt.data)
        assert payload["project_id"] == "proj-test"
    finally:
        sse_manager.unsubscribe_operator(q)


# ---------------------------------------------------------------------------
# Project collection lifecycle events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_project_created_reaches_the_operator_stream(app, auth_headers, tmp_path):
    q = sse_manager.subscribe_operator()
    try:
        target = tmp_path / "created"
        resp = await app.post(
            "/api/v1/projects/create",
            json={"path": str(target), "name": "Created Project"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        project_id = resp.json()["id"]
        evt = await asyncio.wait_for(q.get(), timeout=1.0)
        assert evt.event == "project_created"
        import json

        payload = json.loads(evt.data)
        assert payload["project_id"] == project_id
        assert payload["id"] == project_id
    finally:
        sse_manager.unsubscribe_operator(q)


@pytest.mark.asyncio
async def test_project_opened_reaches_the_operator_stream(app, auth_headers, tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    q = sse_manager.subscribe_operator()
    try:
        resp = await app.post(
            "/api/v1/projects/open", json={"path": str(original)}, headers=auth_headers
        )
        assert resp.status_code == 200, resp.text
        project_id = resp.json()["id"]
        evt = await asyncio.wait_for(q.get(), timeout=1.0)
        assert evt.event == "project_opened"
        import json

        assert json.loads(evt.data)["project_id"] == project_id
    finally:
        sse_manager.unsubscribe_operator(q)


@pytest.mark.asyncio
async def test_project_relocated_reaches_the_operator_stream(app, auth_headers, tmp_path):
    original = tmp_path / "original"
    relocated = tmp_path / "relocated"
    original.mkdir()
    opened = await app.post(
        "/api/v1/projects/open", json={"path": str(original)}, headers=auth_headers
    )
    project_id = opened.json()["id"]
    original.rename(relocated)

    q = sse_manager.subscribe_operator()
    try:
        resp = await app.post(
            f"/api/v1/projects/{project_id}/relocate",
            json={"path": str(relocated)},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        evt = await asyncio.wait_for(q.get(), timeout=1.0)
        assert evt.event == "project_relocated"
        import json

        assert json.loads(evt.data)["project_id"] == project_id
    finally:
        sse_manager.unsubscribe_operator(q)


@pytest.mark.asyncio
async def test_project_settings_updated_reaches_the_operator_stream(app, auth_headers):
    q = sse_manager.subscribe_operator()
    try:
        resp = await app.put(
            "/api/v1/projects/proj-test/settings",
            json={
                "name": "Renamed",
                "hop_budget": 9,
                "turn_delivery_cap": 4,
                "agent_budget": 12,
                "token_budget": 5000,
                "allow_agent_jobs": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        evt = await asyncio.wait_for(q.get(), timeout=1.0)
        assert evt.event == "project_settings_updated"
        import json

        assert json.loads(evt.data)["project_id"] == "proj-test"
    finally:
        sse_manager.unsubscribe_operator(q)


# ---------------------------------------------------------------------------
# Reconnect behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operator_ticket_supports_a_fresh_connection_after_disconnect(app, auth_headers):
    """The same ticket can back a second stream connection (e.g. after a drop),
    since it is time-bound rather than single-use."""
    ticket_resp = await app.get("/api/v1/events/ticket", headers=auth_headers)
    token = ticket_resp.json()["token"]

    for _ in range(2):
        try:
            await asyncio.wait_for(app.get("/api/v1/events", params={"token": token}), timeout=1.0)
        except (asyncio.TimeoutError, TimeoutError):
            pass
        else:
            raise AssertionError("Operator stream returned immediately instead of staying open")


@pytest.mark.asyncio
async def test_reconnecting_gets_a_clean_queue_with_no_stale_events():
    manager = SSEManager()
    first = manager.subscribe_operator()
    await manager.broadcast("proj-real", "task_created", {"id": "task-1"})
    manager.unsubscribe_operator(first)

    second = manager.subscribe_operator()
    assert second.empty()
