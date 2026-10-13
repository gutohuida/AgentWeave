"""Input the Hub committed is answered as accepted, and a failure to start it is retried (F349).

`POST /agent/trigger` commits the operator's input as a queue entry and only then writes an event
and calls `schedule_agent`. A `database is locked` from either used to propagate: the route answered
500 for a message that was in the queue, and nothing started it. Slice 1 of
`openspec/changes/input-the-hub-accepted-is-answered-as-accepted` (design D1-D3a): the trigger
route, the shared helper and the retry. The other post-commit sites (D4) and the firing path (D6)
are later slices.

Patch `hub.turn_scheduler.schedule_agent`: the route imports it inside the function and
`schedule_accepted` resolves it as a module global, so the module attribute is what both read.
"""

import asyncio
import logging
import sqlite3
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from hub import run_reconciliation, turn_scheduler, utils
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, InboundQueueEntry
from hub.turn_scheduler import ScheduleResult

TRIGGER = "/api/v1/projects/proj-test/agent/trigger"
AGENT = "locked-claude"


def _locked() -> OperationalError:
    return OperationalError("UPDATE x", {}, sqlite3.OperationalError("database is locked"))


@pytest.fixture(autouse=True)
def _retries_are_instant(monkeypatch):
    monkeypatch.setattr(turn_scheduler, "RETRY_DELAYS", (0, 0, 0), raising=False)
    run_reconciliation._deferred_schedules.clear()
    yield
    run_reconciliation._deferred_schedules.clear()


@pytest.fixture
async def agent(app, auth_headers, bind_runner):
    synced = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {AGENT: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert synced.status_code == 200
    await bind_runner(AGENT, cli="claude")
    return AGENT


async def _settle_retries() -> None:
    while turn_scheduler._pending_retries:
        await asyncio.gather(*list(turn_scheduler._pending_retries.values()))
        await asyncio.sleep(0)


class _Flaky:
    """A `schedule_agent` that raises *first* times, then answers an inert result."""

    def __init__(self, error, first=1):
        self.error = error
        self.first = first
        self.calls = 0

    async def __call__(self, project_id, agent):
        self.calls += 1
        if self.calls <= self.first:
            raise self.error
        return ScheduleResult(waiting_reason="queue is empty", terminal_failure=False)


async def _entries():
    async with async_session_factory() as db:
        return (await db.execute(select(InboundQueueEntry))).scalars().all()


async def _post(app, auth_headers, message="hi"):
    return await app.post(
        TRIGGER,
        json={"agent": AGENT, "message": message, "session_mode": "new"},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_a_locked_schedule_after_the_commit_is_answered_as_queued(app, auth_headers, agent):
    flaky = _Flaky(_locked(), first=1)
    with patch("hub.turn_scheduler.schedule_agent", flaky):
        resp = await _post(app, auth_headers)
        await _settle_retries()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert "will try again" in body["waiting_reason"]
    rows = await _entries()
    assert [r.id for r in rows] == [body["queue_entry_id"]]
    assert rows[0].state == "queued"


@pytest.mark.asyncio
async def test_the_hub_retries_the_start_it_could_not_make(app, auth_headers, agent):
    flaky = _Flaky(_locked(), first=1)
    with patch("hub.turn_scheduler.schedule_agent", flaky):
        resp = await _post(app, auth_headers)
        await _settle_retries()
    assert resp.status_code == 200, resp.text
    assert flaky.calls == 2


@pytest.mark.asyncio
async def test_a_start_that_stays_locked_is_deferred_and_drained_by_the_next_request(
    app, auth_headers, agent
):
    flaky = _Flaky(_locked(), first=4)  # the route's call and the three retries
    with patch("hub.turn_scheduler.schedule_agent", flaky):
        resp = await _post(app, auth_headers)
        await _settle_retries()
        assert resp.status_code == 200, resp.text
        assert flaky.calls == 4
        assert run_reconciliation.has_deferred_schedules()
        drained = await run_reconciliation.drain_deferred_schedules()
        assert drained == 1
    assert flaky.calls == 5
    assert not run_reconciliation.has_deferred_schedules()


@pytest.mark.asyncio
async def test_a_failed_event_write_does_not_fail_the_accepted_input(app, auth_headers, agent):
    real = utils.persist_event
    seen = []

    async def _persist(session, project_id, event_type, *args, **kwargs):
        if event_type == "queue_entry_queued":
            seen.append(event_type)
            raise _locked()
        return await real(session, project_id, event_type, *args, **kwargs)

    scheduled = _Flaky(_locked(), first=0)
    with (
        patch("hub.utils.persist_event", _persist),
        patch("hub.api.v1.agent_trigger.persist_event", _persist),
        patch("hub.turn_scheduler.schedule_agent", scheduled),
    ):
        resp = await _post(app, auth_headers)
    assert seen, "the queued event was never attempted"
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    # The event failing must not skip the start: the entry is queued and nothing else would start it.
    assert scheduled.calls == 1


@pytest.mark.asyncio
async def test_a_start_that_raised_after_a_run_took_the_input_is_answered_as_running(
    app, auth_headers, agent
):
    async def _took_it_then_raised(project_id, agent):
        async with async_session_factory() as db:
            entry = (await db.execute(select(InboundQueueEntry))).scalars().one()
            entry.state = "delivered"
            entry.delivered_in_run_id = "run-took-it"
            await db.commit()
        raise _locked()

    with patch("hub.turn_scheduler.schedule_agent", _took_it_then_raised):
        resp = await _post(app, auth_headers)
        await _settle_retries()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["run_id"] == "run-took-it"


@pytest.mark.asyncio
async def test_a_failure_that_cannot_clear_is_logged_once_and_not_retried(
    app, auth_headers, agent, caplog
):
    flaky = _Flaky(ValueError("a bug, not a lock"), first=99)
    with caplog.at_level(logging.WARNING), patch("hub.turn_scheduler.schedule_agent", flaky):
        resp = await _post(app, auth_headers)
        await _settle_retries()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert "will try again" not in body["waiting_reason"]
    assert flaky.calls == 1
    assert not run_reconciliation.has_deferred_schedules()
    assert [r.state for r in await _entries()] == ["queued"]
    logged = [r for r in caplog.records if "a bug, not a lock" in (r.exc_text or r.getMessage())]
    assert len(logged) == 1


def test_only_a_busy_or_locked_database_is_transient():
    assert turn_scheduler.is_transient(sqlite3.OperationalError("database is locked"))
    assert turn_scheduler.is_transient(_locked())
    assert not turn_scheduler.is_transient(ValueError("x"))
    assert not turn_scheduler.is_transient(IntegrityError("INSERT", {}, Exception("dup")))


@pytest.mark.asyncio
async def test_a_retry_that_meets_a_non_transient_error_stops_there(caplog):
    class _Then:
        calls = 0

        async def __call__(self, project_id, agent):
            _Then.calls += 1
            raise _locked() if _Then.calls == 1 else ValueError("now a bug")

    with caplog.at_level(logging.WARNING), patch("hub.turn_scheduler.schedule_agent", _Then()):
        result = await turn_scheduler.schedule_accepted("proj-test", "a")
        await _settle_retries()
    assert result.terminal_failure is False
    assert _Then.calls == 2
    assert not run_reconciliation.has_deferred_schedules()


@pytest.mark.asyncio
async def test_a_drain_that_raises_a_lock_is_not_lost():
    flaky = _Flaky(_locked(), first=1)
    run_reconciliation._deferred_schedules.add(("proj-test", "a"))
    with patch("hub.turn_scheduler.schedule_agent", flaky):
        await run_reconciliation.drain_deferred_schedules()
        await _settle_retries()
    assert flaky.calls == 2


@pytest.mark.asyncio
async def test_accepted_event_failure_is_logged_and_swallowed(app, caplog):
    async def _boom(*args, **kwargs):
        raise _locked()

    with caplog.at_level(logging.WARNING), patch("hub.utils.persist_event", _boom):
        await utils.persist_accepted_event("proj-test", "queue_entry_queued", {"x": 1})
    assert any("queue_entry_queued" in r.getMessage() for r in caplog.records)
    async with async_session_factory() as db:
        written = await db.execute(
            select(EventLog).where(EventLog.event_type == "queue_entry_queued")
        )
        assert written.scalars().all() == []
