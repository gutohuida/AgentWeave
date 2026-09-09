"""The one measurement behind "grounds": did this run's harness actually start the server?

`2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` §4. The Hub puts its canonical MCP
server on the runner's command line and, until this route existed, assumed a configured server was
an available one. A harness that forbids MCP by policy takes the configuration and starts nothing.
The adapter reporting in *is* the difference between those two cases, and it is the only one the
Hub can observe — `probe_mcp_registered` shelled a separate process that was never given the
config, so it answered a different question on both kinds of machine (`design.md` D10).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.launchability import harness_has_honoured_mcp


async def _actor(agent: str = "adapter-agent", run_id: str = "run-adapter") -> dict[str, str]:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _run_row(run_id: str) -> Run:
    async with async_session_factory() as session:
        row = await session.get(Run, run_id)
        assert row is not None
        return row


@pytest.mark.asyncio
async def test_the_adapter_reporting_in_stamps_the_run(app):
    headers = await _actor()
    assert (await _run_row("run-adapter")).mcp_adapter_online_at is None

    resp = await app.post("/api/v1/agent-actions/mcp-adapter-online", headers=headers)
    assert resp.status_code == 204

    assert (await _run_row("run-adapter")).mcp_adapter_online_at is not None


@pytest.mark.asyncio
async def test_the_first_report_wins_and_a_repeat_changes_nothing(app):
    """Idempotent: the instant the harness started the server is the fact, and an adapter that
    restarts inside one run did not make it happen later.

    **The first stamp is planted at a fixed past instant rather than made by a first POST**, and
    that is the whole difference between this test working and not. Written the obvious way — POST,
    read, POST, compare — it named nobody under the mutation that drops the `is None` guard, because
    the system clock on this machine has ~15.6 ms granularity: five consecutive
    `datetime.now(timezone.utc)` calls return the *same* value, so two ASGI round-trips overwrite
    with a timestamp indistinguishable from the one they replaced. A planted 2020 stamp cannot be
    confused with `now` on any clock.
    """
    headers = await _actor(run_id="run-adapter-twice")

    planted = datetime(2020, 1, 1, tzinfo=timezone.utc)
    async with async_session_factory() as session:
        row = await session.get(Run, "run-adapter-twice")
        assert row is not None
        row.mcp_adapter_online_at = planted
        await session.commit()

    assert (
        await app.post("/api/v1/agent-actions/mcp-adapter-online", headers=headers)
    ).status_code == 204
    assert (await _run_row("run-adapter-twice")).mcp_adapter_online_at == planted


@pytest.mark.asyncio
async def test_identity_comes_from_the_credential_and_nothing_else(app):
    """Which run is stamped is derived from the token's digest, never from the request — the rule
    the whole agent-actions namespace exists to keep. There is no body to name another run with,
    and an unauthenticated caller stamps nothing at all."""
    await _actor(run_id="run-adapter-auth")

    resp = await app.post("/api/v1/agent-actions/mcp-adapter-online")
    assert resp.status_code in (401, 403)
    assert (await _run_row("run-adapter-auth")).mcp_adapter_online_at is None


@pytest.mark.asyncio
async def test_grounds_are_read_per_agent_and_only_from_a_report(app):
    """`harness_has_honoured_mcp` is what `described_access_path` consults, and the two halves are
    asserted together: before any report it is False, after one it is True, and another agent in
    the same project is unaffected by its neighbour's harness."""
    await _actor(agent="grounded", run_id="run-grounded")
    await _actor(agent="ungrounded", run_id="run-ungrounded")

    async with async_session_factory() as session:
        assert await harness_has_honoured_mcp(session, "proj-test", "grounded") is False

        row = await session.get(Run, "run-grounded")
        assert row is not None
        row.mcp_adapter_online_at = datetime.now(timezone.utc)
        await session.commit()

    async with async_session_factory() as session:
        assert await harness_has_honoured_mcp(session, "proj-test", "grounded") is True
        assert await harness_has_honoured_mcp(session, "proj-test", "ungrounded") is False
        assert await harness_has_honoured_mcp(session, "proj-other", "grounded") is False


@pytest.mark.asyncio
async def test_a_stamped_run_is_the_only_kind_the_query_counts(app):
    """The query filters on the column rather than on the run's existence. Delete the
    `is_not(None)` clause and this fails while every test above still passes."""
    await _actor(agent="silent", run_id="run-silent-1")
    await _actor(agent="silent", run_id="run-silent-2")

    async with async_session_factory() as session:
        found = await session.execute(select(Run).where(Run.agent == "silent"))
        assert len(found.scalars().all()) == 2
        assert await harness_has_honoured_mcp(session, "proj-test", "silent") is False


def test_the_adapter_announces_before_it_serves():
    """The adapter half, and the reason the evidence is gathered at startup rather than from a
    tool call: a model told to use HTTP may never reach for a tool, so tool-call evidence would
    leave a permitted harness permanently undescribed. `main()` announces first and `mcp.run()`
    does not return, so the order is the whole behaviour.
    """
    import inspect

    from hub import mcp_server

    source = inspect.getsource(mcp_server.main)
    assert source.index("_announce_adapter_online()") < source.index("mcp.run(")

    announce = inspect.getsource(mcp_server._announce_adapter_online)
    assert '"/mcp-adapter-online"' in announce
    # Best-effort in every direction: an unreachable Hub, a missing credential and a route that
    # predates this call are none of them reasons to refuse to serve.
    assert "contextlib.suppress(Exception)" in announce


def test_the_announce_route_the_adapter_posts_to_is_one_the_app_mounts():
    """The two halves live in different processes — `mcp_server.py` may import only stdlib and
    fastmcp — so a typo in either path is invisible until a run makes it. This is the assertion
    that the two agree, the same shape `test_tool_surface_matches_server.py` uses.
    """
    from hub.main import create_app

    paths = {route.path for route in create_app().routes if hasattr(route, "path")}
    assert "/api/v1/agent-actions/mcp-adapter-online" in paths


def test_the_adapter_swallows_a_refusal_rather_than_failing_to_start(monkeypatch):
    """Driven rather than read: patch `_hub_request` to raise and call the announce. A Hub that
    404s this route — every Hub older than migration `0102` — must not stop the adapter serving.
    """
    from hub import mcp_server

    def _boom(*args, **kwargs):
        raise RuntimeError("no such route")

    monkeypatch.setattr(mcp_server, "_hub_request", _boom)
    mcp_server._announce_adapter_online()  # must not raise


def test_the_adapter_posts_exactly_once_to_the_announce_route(monkeypatch):
    from hub import mcp_server

    calls = []
    monkeypatch.setattr(mcp_server, "_hub_request", lambda *a, **k: calls.append(a))
    mcp_server._announce_adapter_online()
    assert calls == [("POST", "/mcp-adapter-online")]
