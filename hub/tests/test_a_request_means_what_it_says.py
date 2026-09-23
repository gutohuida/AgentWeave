"""Round 4c: request contracts — a request means what it says, and the answer says what happened.

F176 + F184 (blank names), F243 (config could not be cleared), F244 (the roster hid config), F397
(re-archiving re-stamped), F204 + F210 (bodyless calls refused as malformed), F238 (settings writes
left no history), F255 (a malformed `since` was ignored), F257 (an unknown severity answered 200),
F282 (a linked path's refusal and record printed only the declared path). F214 and F216 are in
`test_requirement_coverage.py`, F232 in `test_permission_request_lifecycle.py`.
"""

import os
import subprocess
import sys

import pytest
from sqlalchemy import select

from hub import mcp_server
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EventLog
from hub.workspace_writes import classify

P = "/api/v1/projects/proj-test"

pytestmark = pytest.mark.asyncio


# --- F176 + F184 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["/runners", "/charters"])
@pytest.mark.parametrize("name", ["", "   "])
async def test_a_blank_name_is_refused(app, auth_headers, route, name):
    body = (
        {"name": name, "cli": "claude"} if route == "/runners" else {"name": name, "content": "x"}
    )

    refused = await app.post(P + route, json=body, headers=auth_headers)

    assert refused.status_code == 422, refused.text
    assert "visible character" in refused.text


@pytest.mark.parametrize("route", ["/runners", "/charters"])
async def test_a_name_is_stored_as_the_dialog_would_store_it(app, auth_headers, route):
    body = {"name": "  Reviewer  ", "cli": "claude"}
    if route == "/charters":
        body = {"name": "  Reviewer  ", "content": "x"}

    created = await app.post(P + route, json=body, headers=auth_headers)

    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Reviewer"
    renamed = await app.patch(
        f"{P}{route}/{created.json()['id']}", json={"name": "   "}, headers=auth_headers
    )
    assert renamed.status_code == 422, renamed.text


# --- F243 + F244 ---------------------------------------------------------------------------------


async def _agent_with_config(config):
    async with async_session_factory() as session:
        session.add(Agent(id="agt-beta", project_id="proj-test", name="beta", config=config))
        await session.commit()


async def _config():
    async with async_session_factory() as session:
        return (
            await session.execute(select(Agent.config).where(Agent.name == "beta"))
        ).scalar_one()


async def test_an_explicit_null_clears_the_config(app, auth_headers):
    await _agent_with_config({"read_only": True, "model": "x"})

    cleared = await app.patch(f"{P}/agents/beta", json={"config": None}, headers=auth_headers)

    assert cleared.status_code == 200, cleared.text
    assert await _config() == {}


async def test_a_null_key_removes_that_key_only(app, auth_headers):
    await _agent_with_config({"read_only": True, "model": "x"})

    patched = await app.patch(
        f"{P}/agents/beta", json={"config": {"read_only": None}}, headers=auth_headers
    )

    assert patched.status_code == 200, patched.text
    assert await _config() == {"model": "x"}


async def test_config_is_a_recursive_merge_patch(app, auth_headers):
    """RFC 7396: `{}` is a no-op, and a null removes the key it names at any depth — the review
    found a nested null stored as a value, and the whole nested object replaced."""
    await _agent_with_config({"read_only": True, "env_vars": {"A": "1", "B": "2"}})

    unchanged = await app.patch(f"{P}/agents/beta", json={"config": {}}, headers=auth_headers)
    assert unchanged.status_code == 200, unchanged.text
    assert await _config() == {"read_only": True, "env_vars": {"A": "1", "B": "2"}}

    nested = await app.patch(
        f"{P}/agents/beta",
        json={"config": {"env_vars": {"A": None, "C": "3"}}},
        headers=auth_headers,
    )
    assert nested.status_code == 200, nested.text
    assert await _config() == {"read_only": True, "env_vars": {"B": "2", "C": "3"}}


async def test_the_roster_carries_config_without_env_values(app, auth_headers):
    """An allow-list: a credential under any key nobody thought to deny stays off the roster."""
    await _agent_with_config(
        {
            "read_only": True,
            "env_vars": {"API_TOKEN": "s3cret"},
            "api_key": "s3cret",
            "mcp_servers": {"x": {"token": "s3cret"}},
        }
    )

    roster = await app.get(f"{P}/agents", headers=auth_headers)

    assert roster.status_code == 200, roster.text
    [beta] = [row for row in roster.json() if row["name"] == "beta"]
    assert beta["config"] == {"read_only": True}
    assert "s3cret" not in roster.text


# --- F397 ----------------------------------------------------------------------------------------


async def test_archiving_an_archived_agent_changes_nothing(app, auth_headers):
    await _agent_with_config({})
    first = await app.post(f"{P}/agents/beta/archive", headers=auth_headers)
    assert first.status_code == 200, first.text
    async with async_session_factory() as session:
        archived_at = (
            await session.execute(select(Agent.archived_at).where(Agent.name == "beta"))
        ).scalar_one()

    again = await app.post(f"{P}/agents/beta/archive", headers=auth_headers)

    assert again.status_code == 200, again.text
    assert again.json()["lifecycle"] == "archived"
    assert "already archived" in again.json()["message"]
    async with async_session_factory() as session:
        assert (
            await session.execute(select(Agent.archived_at).where(Agent.name == "beta"))
        ).scalar_one() == archived_at
        events = (
            await session.execute(
                select(EventLog.event_type).where(EventLog.event_type == "agent_archived")
            )
        ).all()
    assert len(events) == 1


async def test_unarchiving_an_open_agent_changes_nothing(app, auth_headers):
    """F397's mirror, from the review: a second `agent_unarchived` read like a real reopening."""
    await _agent_with_config({})

    resp = await app.post(f"{P}/agents/beta/unarchive", headers=auth_headers)

    assert resp.status_code == 200, resp.text
    assert "was not archived" in resp.json()["message"]
    async with async_session_factory() as session:
        events = (
            await session.execute(
                select(EventLog.event_type).where(EventLog.event_type == "agent_unarchived")
            )
        ).all()
    assert events == []


# --- F204 + F210 ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route",
    [
        "/project/documents/phase?path=spec/none.html&to=approved",
        "/project/documents/spec/none.html/proposals/prop-none/accept",
        "/project/documents/spec/none.html/proposals/prop-none/reject",
    ],
)
async def test_a_bodyless_decision_reaches_the_route(app, auth_headers, route):
    """Every field of these bodies is optional, so no body is a complete request. It used to be
    a 422 `body: Field required` before the route ran; now the route answers about the thing
    named, which here does not exist."""
    resp = await app.post(P + route, headers=auth_headers)

    assert resp.status_code != 422, resp.text
    assert resp.status_code == 404, resp.text


# --- F238 ----------------------------------------------------------------------------------------


async def _settings_events():
    async with async_session_factory() as session:
        return [
            row.data
            for row in (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "project_settings_updated")
                )
            ).scalars()
        ]


async def test_a_settings_change_is_recorded_with_what_changed(app, auth_headers):
    current = (await app.get(f"{P}/settings", headers=auth_headers)).json()
    was = current["hop_budget"]

    saved = await app.put(
        f"{P}/settings", json={**current, "hop_budget": was + 1}, headers=auth_headers
    )
    unchanged = await app.put(
        f"{P}/settings", json={**current, "hop_budget": was + 1}, headers=auth_headers
    )

    assert saved.status_code == 200, saved.text
    assert unchanged.status_code == 200, unchanged.text
    [event] = await _settings_events()
    assert event["changed"] == {"hop_budget": {"was": was, "now": was + 1}}
    assert event["settings"]["hop_budget"] == was + 1


# --- F255 + F257 ---------------------------------------------------------------------------------


async def test_a_malformed_since_is_refused(app, auth_headers):
    refused = await app.get(f"{P}/logs?since=not-a-timestamp", headers=auth_headers)
    valid = await app.get(f"{P}/logs?since=2099-01-01T00:00:00", headers=auth_headers)

    zulu = await app.get(f"{P}/logs?since=2099-01-01T00:00:00Z", headers=auth_headers)

    assert refused.status_code == 400, refused.text
    assert "'not-a-timestamp' is not an ISO 8601 timestamp" in refused.json()["detail"]
    # The example the refusal gives must itself be accepted.
    assert zulu.status_code == 200, zulu.text
    assert valid.status_code == 200 and valid.json() == []


@pytest.mark.parametrize("route", ["/logs", "/events/history"])
async def test_an_unknown_severity_is_refused_naming_the_known_ones(app, auth_headers, route):
    refused = await app.get(f"{P}{route}?severity=banana", headers=auth_headers)
    known = await app.get(f"{P}{route}?severity=warn", headers=auth_headers)
    everything = await app.get(f"{P}{route}?severity=all", headers=auth_headers)

    assert refused.status_code == 400, refused.text
    assert all(
        word in refused.json()["detail"] for word in ("'banana'", "info", "warn", "error", "all")
    )
    assert known.status_code == 200, known.text
    assert everything.status_code == 200, everything.text


# --- F282 ----------------------------------------------------------------------------------------


def _directory_link(link, target):
    """A link a path can pass through: a junction on Windows (no elevation needed, and what F282
    was measured with), a symlink elsewhere."""
    if sys.platform == "win32":
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True
        )
        if made.returncode != 0:
            pytest.skip(f"could not create a junction: {made.stderr!r}")
    else:
        os.symlink(target, link, target_is_directory=True)


async def test_a_linked_path_names_where_it_resolves(tmp_path):
    from hub.workspace_writes import resolved_elsewhere

    workspace = tmp_path / "ws"
    elsewhere = tmp_path / "elsewhere"
    workspace.mkdir()
    elsewhere.mkdir()
    _directory_link(workspace / "link", elsewhere)
    declared = str(workspace / "link" / "x.py")
    real_root = os.path.realpath(workspace)
    real_target = os.path.realpath(elsewhere / "x.py")

    # The refusal the agent gets: the declared path first, then where it really goes.
    why = mcp_server._where(declared, real_root)
    assert why.startswith(mcp_server._OUTSIDE)
    assert real_target in why.replace("\\\\", "\\")

    # The record and notice the operator reads: the resolved path beside the declared one.
    assert classify(declared, workspace_dir=str(workspace), project_root=None).kind == "outside"
    assert resolved_elsewhere(declared, workspace_dir=str(workspace)) == real_target


async def test_a_path_no_link_moved_reads_exactly_as_before(tmp_path):
    from hub.workspace_writes import resolved_elsewhere

    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = str(tmp_path / "outside.py")

    assert mcp_server._where(outside, os.path.realpath(workspace)) == mcp_server._OUTSIDE
    assert resolved_elsewhere(outside, workspace_dir=str(workspace)) is None
