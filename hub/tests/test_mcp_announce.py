"""Whether a run's harness started the Hub's tool server, recorded per run, and waited for.

`a-run-reaches-the-hub-without-mcp`, design D1 and D9. `record_harness_mcp_status` is the one
writer of `Run.harness_mcp_status`, and it enforces a source precedence so the result does not
depend on the order the sources arrive in: the harness's own report outranks the announce, which
outranks Copilot's wait. `mcp_announce.wait` is how a runner that tests before its first prompt
learns its own run's answer: it registers before it checks, because the announce can come first.
"""

import asyncio
from datetime import datetime, timezone

import pytest

from hub import mcp_announce
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.launchability import record_harness_mcp_status


async def _run(run_id: str, *, token: str | None = None, stamped: bool = False) -> dict[str, str]:
    token = token or f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent="announcer",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
                mcp_adapter_online_at=(
                    datetime(2020, 1, 1, tzinfo=timezone.utc) if stamped else None
                ),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _status(run_id: str) -> str | None:
    async with async_session_factory() as session:
        row = await session.get(Run, run_id)
        assert row is not None
        return row.harness_mcp_status


async def _record(run_id: str, status: str, source: str) -> None:
    async with async_session_factory() as session:
        await record_harness_mcp_status(session, run_id, status, source=source)
        await session.commit()


async def _set(run_id: str, status: str | None) -> None:
    async with async_session_factory() as session:
        row = await session.get(Run, run_id)
        assert row is not None
        row.harness_mcp_status = status
        await session.commit()


# --- the announce route records `connected`, subject to the precedence --------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "before, after", [(None, "connected"), ("absent", "connected"), ("failed", "failed")]
)
async def test_the_announce_sets_connected_over_null_and_absent_never_over_failed(
    app, before, after
):
    headers = await _run(f"run-ann-{before}")
    await _set(f"run-ann-{before}", before)

    resp = await app.post("/api/v1/agent-actions/mcp-adapter-online", headers=headers)

    assert resp.status_code == 204
    assert await _status(f"run-ann-{before}") == after


@pytest.mark.asyncio
async def test_a_harness_failure_after_the_announce_is_recorded_failed(app):
    """R3: the announce is posted before the server answers `initialize`, so a harness that started
    the server and then failed it has already announced. Its own report decides."""
    headers = await _run("run-ann-then-failed")
    await app.post("/api/v1/agent-actions/mcp-adapter-online", headers=headers)
    assert await _status("run-ann-then-failed") == "connected"

    await _record("run-ann-then-failed", "failed", "harness")

    assert await _status("run-ann-then-failed") == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first, second, expected",
    [
        (("failed", "harness"), ("connected", "announce"), "failed"),
        (("absent", "wait"), ("connected", "announce"), "connected"),
        (("failed", "harness"), ("connected", "harness"), "connected"),
        (("connected", "announce"), ("absent", "wait"), "connected"),
        (("absent", "harness"), ("absent", "wait"), "absent"),
        ((None, None), ("absent", "wait"), "absent"),
    ],
)
async def test_the_precedence_is_the_same_whatever_order_the_sources_arrive_in(
    app, first, second, expected
):
    run_id = f"run-prec-{first[0]}-{first[1]}-{second[0]}-{second[1]}"
    await _run(run_id)
    if first[0] is not None:
        await _record(run_id, *first)

    await _record(run_id, *second)

    assert await _status(run_id) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, source",
    [("pending", "harness"), ("absent", "announce"), ("connected", "wait"), ("connected", "model")],
)
async def test_a_value_no_source_reports_is_refused(app, status, source):
    """An unrecognised vendor string is not a report (D1), and each source has one thing to say."""
    await _run(f"run-bad-{status}-{source}")
    with pytest.raises(ValueError):
        await _record(f"run-bad-{status}-{source}", status, source)


@pytest.mark.asyncio
async def test_recording_for_a_run_that_does_not_exist_changes_nothing(app):
    await _record("run-nobody", "failed", "harness")  # no exception, no row


@pytest.mark.asyncio
async def test_the_announce_writes_nothing_when_recording_raises(app, monkeypatch):
    """D1: the stamp and the status are one commit. If recording raises the route answers 500 and
    the stamp is not written either; the adapter swallows the failure and the waiter times out,
    the safe direction."""
    headers = await _run("run-ann-raises")

    async def boom(*args, **kwargs):
        raise RuntimeError("recording failed")

    monkeypatch.setattr("hub.api.v1.agent_actions.record_harness_mcp_status", boom)
    # The test client re-raises server exceptions; this one answers as the server does.
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app._transport.app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/agent-actions/mcp-adapter-online", headers=headers)

    assert resp.status_code == 500
    async with async_session_factory() as session:
        row = await session.get(Run, "run-ann-raises")
        assert row.mcp_adapter_online_at is None and row.harness_mcp_status is None


# --- `mcp_announce.wait` ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wait_returns_at_once_when_the_run_is_already_stamped(app):
    await _run("run-wait-stamped", stamped=True)
    started = asyncio.get_running_loop().time()

    assert await mcp_announce.wait("run-wait-stamped", 1.0) is True
    assert asyncio.get_running_loop().time() - started < 0.5


@pytest.mark.asyncio
async def test_wait_returns_soon_after_the_announce_arrives_during_it(app):
    headers = await _run("run-wait-live")

    async def announce_later():
        await asyncio.sleep(0.2)
        await app.post("/api/v1/agent-actions/mcp-adapter-online", headers=headers)

    task = asyncio.create_task(announce_later())
    started = asyncio.get_running_loop().time()
    assert await mcp_announce.wait("run-wait-live", 5.0) is True
    assert asyncio.get_running_loop().time() - started < 1.5
    await task


@pytest.mark.asyncio
async def test_wait_times_out_when_nothing_announces(app):
    await _run("run-wait-silent")
    started = asyncio.get_running_loop().time()

    assert await mcp_announce.wait("run-wait-silent", 0.4) is False
    assert asyncio.get_running_loop().time() - started >= 0.35


@pytest.mark.asyncio
async def test_wait_registers_before_it_checks(app, monkeypatch):
    """Review fix 5: the announce commits and notifies *while* the row check runs, after the check
    has read the row as unset. Register-then-check sees the notification at once; check-then-
    register misses it and waits out the timeout."""
    await _run("run-wait-race")
    real_check = mcp_announce._stamped

    async def racing_check(run_id):
        seen = await real_check(run_id)  # reads "unset"
        async with async_session_factory() as session:
            row = await session.get(Run, run_id)
            row.mcp_adapter_online_at = datetime.now(timezone.utc)
            await session.commit()
        mcp_announce.notify(run_id)
        monkeypatch.setattr(mcp_announce, "_stamped", real_check)
        return seen

    monkeypatch.setattr(mcp_announce, "_stamped", racing_check)
    monkeypatch.setattr(mcp_announce, "POLL_SECONDS", 10.0)  # a re-check cannot rescue it
    started = asyncio.get_running_loop().time()

    assert await mcp_announce.wait("run-wait-race", 5.0) is True
    assert asyncio.get_running_loop().time() - started < 1.0


@pytest.mark.asyncio
async def test_a_stamp_written_with_no_notify_is_seen_within_one_poll(app, monkeypatch):
    await _run("run-wait-quiet")
    monkeypatch.setattr(mcp_announce, "POLL_SECONDS", 0.1)

    async def stamp_quietly():
        await asyncio.sleep(0.2)
        async with async_session_factory() as session:
            row = await session.get(Run, "run-wait-quiet")
            row.mcp_adapter_online_at = datetime.now(timezone.utc)
            await session.commit()

    task = asyncio.create_task(stamp_quietly())
    started = asyncio.get_running_loop().time()
    assert await mcp_announce.wait("run-wait-quiet", 5.0) is True
    assert asyncio.get_running_loop().time() - started < 1.0
    await task


@pytest.mark.asyncio
async def test_wait_ends_within_one_poll_when_interrupted(app, monkeypatch):
    await _run("run-wait-interrupt")
    monkeypatch.setattr(mcp_announce, "POLL_SECONDS", 0.1)
    stop = {"now": False}

    async def interrupt_later():
        await asyncio.sleep(0.2)
        stop["now"] = True

    task = asyncio.create_task(interrupt_later())
    started = asyncio.get_running_loop().time()
    assert (
        await mcp_announce.wait("run-wait-interrupt", 5.0, should_interrupt=lambda: stop["now"])
        is False
    )
    assert asyncio.get_running_loop().time() - started < 1.0
    await task


@pytest.mark.asyncio
async def test_wait_is_total_when_the_row_check_raises(app, monkeypatch):
    """D9: a failing check counts as "not yet", so the wait ends at its timeout, never raises."""

    async def broken(run_id):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(mcp_announce, "_stamped", broken)
    monkeypatch.setattr(mcp_announce, "POLL_SECONDS", 0.05)

    assert await mcp_announce.wait("run-wait-broken", 0.2) is False


@pytest.mark.asyncio
async def test_a_finished_wait_leaves_no_registration_behind(app):
    await _run("run-wait-cleanup")
    await mcp_announce.wait("run-wait-cleanup", 0.1)
    assert "run-wait-cleanup" not in mcp_announce._waiters
