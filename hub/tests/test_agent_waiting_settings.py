"""How long an agent waits on the operator is the operator's to set, per agent."""

from __future__ import annotations

import importlib

import pytest
from sqlalchemy import select

from hub.api.v1.agents import MAX_WAITING_SECONDS, MIN_WAITING_SECONDS
from hub.db.engine import async_session_factory
from hub.db.models import Agent

PROJECT = "proj-test"


async def _register(app, auth_headers, name: str = "waiter") -> None:
    resp = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {name: {}}}},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text


async def _row(name: str = "waiter") -> Agent:
    async with async_session_factory() as db:
        return (
            await db.execute(
                select(Agent).where(Agent.project_id == PROJECT, Agent.name == name)
            )
        ).scalars().one()


async def _patch(app, auth_headers, body: dict, name: str = "waiter"):
    return await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/{name}", json=body, headers=auth_headers
    )


@pytest.mark.asyncio
async def test_an_agent_starts_with_no_waits_of_its_own(app, auth_headers):
    """Unset means the built-in default, not a copy of it — a row storing today's number would
    keep saying it after the default moved."""
    await _register(app, auth_headers)
    row = await _row()
    assert row.permission_timeout_seconds is None
    assert row.question_timeout_seconds is None


@pytest.mark.asyncio
async def test_both_waits_round_trip(app, auth_headers):
    await _register(app, auth_headers)
    resp = await _patch(
        app, auth_headers, {"permission_timeout_seconds": 60, "question_timeout_seconds": 300}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["permission_timeout_seconds"] == 60
    assert resp.json()["question_timeout_seconds"] == 300

    row = await _row()
    assert row.permission_timeout_seconds == 60
    assert row.question_timeout_seconds == 300


@pytest.mark.asyncio
async def test_null_clears_back_to_the_default(app, auth_headers):
    await _register(app, auth_headers)
    await _patch(app, auth_headers, {"question_timeout_seconds": 300})
    resp = await _patch(app, auth_headers, {"question_timeout_seconds": None})
    assert resp.status_code == 200
    assert (await _row()).question_timeout_seconds is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", [MIN_WAITING_SECONDS - 1, MAX_WAITING_SECONDS + 1, 0, -30, "sixty", 12.5, True]
)
async def test_a_value_outside_the_range_or_the_wrong_type_is_refused(app, auth_headers, value):
    """Validated in the API, not only the UI: this endpoint takes a raw dict, so without it a bad
    value reaches the column and surfaces later as a run waiting a nonsense length of time."""
    await _register(app, auth_headers)
    resp = await _patch(app, auth_headers, {"question_timeout_seconds": value})
    assert resp.status_code == 400, resp.text
    assert (await _row()).question_timeout_seconds is None


@pytest.mark.asyncio
async def test_the_bounds_are_inclusive(app, auth_headers):
    await _register(app, auth_headers)
    for value in (MIN_WAITING_SECONDS, MAX_WAITING_SECONDS):
        resp = await _patch(app, auth_headers, {"question_timeout_seconds": value})
        assert resp.status_code == 200, resp.text
        assert (await _row()).question_timeout_seconds == value


@pytest.mark.asyncio
async def test_the_waits_appear_on_the_agent_roster(app, auth_headers):
    """The settings tab renders current values from the roster it already loads."""
    await _register(app, auth_headers)
    await _patch(app, auth_headers, {"permission_timeout_seconds": 45})
    listed = await app.get(f"/api/v1/projects/{PROJECT}/agents", headers=auth_headers)
    entry = next(a for a in listed.json() if a["name"] == "waiter")
    assert entry["permission_timeout_seconds"] == 45
    assert entry["question_timeout_seconds"] is None


# --- reaching the tool ------------------------------------------------------------------------


def _reloaded_mcp_server(monkeypatch, **env):
    """Re-import the tool module under a given environment, as a spawned run would start it."""
    import hub.mcp_server as mcp_server

    for key in ("AW_DECISION_TIMEOUT", "AW_QUESTION_TIMEOUT"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return importlib.reload(mcp_server)


def test_the_tool_honours_a_configured_wait(monkeypatch):
    module = _reloaded_mcp_server(
        monkeypatch, AW_DECISION_TIMEOUT="45", AW_QUESTION_TIMEOUT="300"
    )
    try:
        assert module.OPERATOR_DECISION_TIMEOUT == 45
        assert module.QUESTION_ANSWER_TIMEOUT == 300
    finally:
        _reloaded_mcp_server(monkeypatch)


def test_the_tool_falls_back_to_the_measured_defaults(monkeypatch):
    module = _reloaded_mcp_server(monkeypatch)
    assert module.OPERATOR_DECISION_TIMEOUT == 120
    assert module.QUESTION_ANSWER_TIMEOUT == 240


@pytest.mark.parametrize("bad", ["", "soon", "0", "-5", "99999", "60.5"])
def test_an_unusable_wait_falls_back_rather_than_failing_the_run(monkeypatch, bad):
    """A turn that dies because a setting was mistyped is worse than one that waits the standard
    time."""
    module = _reloaded_mcp_server(monkeypatch, AW_QUESTION_TIMEOUT=bad)
    try:
        assert module.QUESTION_ANSWER_TIMEOUT == 240
    finally:
        _reloaded_mcp_server(monkeypatch)


def test_the_tool_and_the_api_agree_on_the_bounds(monkeypatch):
    """`mcp_server` restates them because it is spawned standalone and cannot import the API."""
    module = _reloaded_mcp_server(monkeypatch)
    assert module.MIN_WAITING_SECONDS == MIN_WAITING_SECONDS
    assert module.MAX_WAITING_SECONDS == MAX_WAITING_SECONDS


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, 120),
        ({"AW_DECISION_TIMEOUT": "45"}, 45),
        ({"AW_DECISION_TIMEOUT": "nope"}, 120),
        ({"AW_DECISION_TIMEOUT": "5"}, 120),
        ({"AW_DECISION_TIMEOUT": "9999"}, 120),
    ],
)
def test_the_codex_wait_reads_the_same_variable(env, expected):
    """One carrier for one setting, so the two transports cannot drift apart."""
    from hub.api.v1.agent_trigger import _codex_decision_timeout

    assert _codex_decision_timeout(env) == expected
