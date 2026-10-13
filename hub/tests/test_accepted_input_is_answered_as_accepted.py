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


# --- Slice 2 (design D4): the six other routes that schedule after committing input ----------
#
# Each site is a setup that leaves the route one request away, and the request itself. Every test
# asks two things of it: with `schedule_agent` raising a lock, the route answers what it answers
# when scheduling succeeds; and with the route's post-commit event raising, the agent is still
# scheduled (the event used to raise out of the route before the schedule was reached).

PROJECT_URL = "/api/v1/projects/proj-test"


class _Recorder:
    """A `schedule_agent` that records who it was asked to start; raises *error* if given."""

    def __init__(self, error=None):
        self.error = error
        self.agents = []

    async def __call__(self, project_id, agent):
        self.agents.append(agent)
        if self.error is not None:
            raise self.error
        return ScheduleResult(waiting_reason="queue is empty", terminal_failure=False)


async def _site_message(app, auth_headers, add_agent, bind_runner):
    await add_agent("recipient")

    async def _send():
        return await app.post(
            f"{PROJECT_URL}/messages",
            json={"to": "recipient", "content": "hello"},
            headers=auth_headers,
        )

    return _send, ["recipient"], 201


async def _site_request_agent(app, auth_headers, add_agent, bind_runner):
    from .test_request_agent_models_an_existing_agent import _actor

    await add_agent("tmpl")
    await bind_runner("tmpl", cli="claude")
    headers = await _actor(run_id="run-d4-request")

    async def _request():
        return await app.post(
            "/api/v1/agent-actions/agents/request",
            json={"name": "requested", "template": "tmpl", "task": "help"},
            headers=headers,
        )

    return _request, ["requested"], 201


async def _site_runner_rebind(app, auth_headers, add_agent, bind_runner):
    await add_agent("unbound")
    created = await app.post(
        f"{PROJECT_URL}/runners",
        json={"name": "late-runner", "cli": "claude"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    runner_id = created.json()["id"]

    async def _bind():
        return await app.patch(
            f"{PROJECT_URL}/agents/unbound", json={"runner_id": runner_id}, headers=auth_headers
        )

    return _bind, ["unbound"], 200


async def _site_answer(app, auth_headers, add_agent, bind_runner):
    from hub.db.models import Question, Run

    async with async_session_factory() as db:
        db.add(Run(id="run-d4-asked", project_id="proj-test", agent="asker", status="completed"))
        db.add(
            Question(
                id="q-d4",
                project_id="proj-test",
                from_agent="asker",
                question="which?",
                blocking=True,
                created_by_run_id="run-d4-asked",
                options=[{"label": "yes"}, {"label": "no"}],
            )
        )
        await db.commit()

    async def _answer():
        return await app.patch(
            f"{PROJECT_URL}/questions/q-d4",
            json={"answer": "yes", "labels": ["yes"]},
            headers=auth_headers,
        )

    return _answer, ["asker"], 200


async def _site_release(app, auth_headers, add_agent, bind_runner):
    from hub.db.models import Conversation, Project
    from hub.inbound_queue import new_entry

    await add_agent("held")
    entry = new_entry(
        project_id="proj-test",
        agent="held",
        origin_type="agent",
        origin_agent="relay",
        content="held over the budget",
        hop_depth=2,
        conversation_id="conv-d4-held",
    )
    async with async_session_factory() as db:
        (await db.get(Project, "proj-test")).hop_budget = 1
        db.add(
            Conversation(id="conv-d4-held", project_id="proj-test", agent="held", lifecycle="open")
        )
        db.add(entry)
        await db.commit()
    entry_id = entry.id

    async def _release():
        return await app.post(
            f"{PROJECT_URL}/queue/entries/{entry_id}/release", headers=auth_headers
        )

    return _release, ["held"], 200


async def _site_budget(app, auth_headers, add_agent, bind_runner):
    from hub.conversations import new_conversation
    from hub.inbound_queue import new_entry

    async with async_session_factory() as db:
        for name in ("first", "second"):
            conversation = new_conversation(project_id="proj-test", agent=name, origin="operator")
            db.add(conversation)
            db.add(
                new_entry(
                    project_id="proj-test",
                    agent=name,
                    origin_type="operator",
                    content="waiting on the budget",
                    hop_depth=0,
                    conversation_id=conversation.id,
                )
            )
        await db.commit()

    async def _raise_budget():
        return await app.patch(
            f"{PROJECT_URL}/accounting/budget",
            json={"token_budget": 10_000_000},
            headers=auth_headers,
        )

    return _raise_budget, ["first", "second"], 200


# (setup, the module whose `persist_event` the route calls, the post-commit events it writes)
SITES = {
    "message": (_site_message, "messages", {"message_created", "queue_entry_queued"}),
    "request_agent": (_site_request_agent, "agents", {"agent_requested", "queue_entry_queued"}),
    "runner_rebind": (_site_runner_rebind, "agents", set()),
    "answer": (_site_answer, "questions", {"question_answered", "queue_entry_queued"}),
    "release": (_site_release, "inbound_queue", {"queue_entry_released"}),
    "budget": (_site_budget, "accounting", {"accounting_budget_updated"}),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(SITES))
async def test_a_locked_start_does_not_fail_a_route_that_committed_input(
    site, app, auth_headers, add_agent, bind_runner
):
    setup, _, _ = SITES[site]
    act, agents, ok = await setup(app, auth_headers, add_agent, bind_runner)
    locked = _Recorder(_locked())
    with patch("hub.turn_scheduler.schedule_agent", locked):
        resp = await act()
        await _settle_retries()
    assert resp.status_code == ok, resp.text
    # Every agent with committed input was tried, including after an earlier one raised (budget).
    assert set(agents) <= set(locked.agents)


@pytest.mark.asyncio
@pytest.mark.parametrize("site", sorted(name for name, (_, _, events) in SITES.items() if events))
async def test_a_failed_post_commit_event_still_starts_the_agent(
    site, app, auth_headers, add_agent, bind_runner
):
    setup, module, events = SITES[site]
    act, agents, ok = await setup(app, auth_headers, add_agent, bind_runner)
    real = utils.persist_event
    refused = []

    async def _persist(session, project_id, event_type, *args, **kwargs):
        if event_type in events:
            refused.append(event_type)
            raise _locked()
        return await real(session, project_id, event_type, *args, **kwargs)

    scheduled = _Recorder()
    with (
        patch("hub.utils.persist_event", _persist),
        patch(f"hub.api.v1.{module}.persist_event", _persist, create=True),
        patch("hub.turn_scheduler.schedule_agent", scheduled),
    ):
        resp = await act()
    assert refused, f"none of {events} was attempted"
    assert resp.status_code == ok, resp.text
    assert set(agents) <= set(scheduled.agents)
