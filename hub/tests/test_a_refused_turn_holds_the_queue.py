"""`a-spent-allowance-holds-the-queue` 2.4-2.6 — a turn the provider refused on usage grounds.

Finding F355. LoopEngine hit the provider's usage wall three times on 2026-09-14. Each time the
Hub re-delivered the refused input about ten seconds later into the same exhausted allowance,
cleared the conversation's sound provider session at the second attempt, and withdrew the input at
the third. These drive `_execute_run`'s end through the `_fake_pty` pattern
(`test_agent_trigger.py`), scripted as the harness emits a refusal: an init line, a
`rate_limit_event` carrying the measured reading, the notice, and an error result.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub import provider_allowance
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, EventLog, InboundQueueEntry, JobRun, Run

from ._background_runs import await_background_runs as _await_background_run

pytestmark = pytest.mark.asyncio


def _reading(resets_at_epoch):
    """The measured reading (the change's tasks.md, head)."""
    return {
        "status": "rejected",
        "resetsAt": resets_at_epoch,
        "rateLimitType": "five_hour",
        "overageStatus": "rejected",
        "overageDisabledReason": "out_of_credits",
        "isUsingOverage": False,
        "unifiedWindows": {"five_hour": {"utilization": 1.02, "resetsAt": resets_at_epoch}},
    }


def _line(payload):
    return json.dumps(payload) + "\n"


def _refused_turn(session_id, resets_at_epoch, *, is_error=True):
    notice = "You've hit your limit · resets 3:10am"
    return [
        _line({"type": "system", "subtype": "init", "session_id": session_id}),
        _line(
            {
                "type": "rate_limit_event",
                "rate_limit_info": _reading(resets_at_epoch),
                "session_id": session_id,
            }
        ),
        _line(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": notice}]},
                "session_id": session_id,
            }
        ),
        _line(
            {
                "type": "result",
                "subtype": "success",
                "is_error": is_error,
                "result": notice,
                "session_id": session_id,
            }
        ),
    ]


def _served_turn(session_id):
    return [
        _line({"type": "system", "subtype": "init", "session_id": session_id}),
        _line(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Done."}]},
                "session_id": session_id,
            }
        ),
        _line(
            {"type": "result", "subtype": "success", "is_error": False, "session_id": session_id}
        ),
    ]


def _scripted_pty(turns, *, on_wait=None):
    """A spawn replacement playing one scripted `(lines, exit_code)` turn per call.

    EOF forever after each turn's lines, for the reason `_fake_pty`'s docstring gives. A spawn past
    the script raises `RuntimeError`, a spawn failure the test sees. Not `StopIteration`, which is
    what `next()` would raise: `spawn` runs in an executor, and a `StopIteration` cannot be raised
    into a future, so the run never ended and the test hung instead of failing (measured).
    """
    remaining_turns = iter(turns)

    def _spawn(*args, **kwargs):
        turn = next(remaining_turns, None)
        if turn is None:
            raise RuntimeError("spawned past the end of the script")
        lines, exit_code = turn
        session = MagicMock()
        session.pid = 4343
        remaining = iter([*lines, ""])
        session.read.side_effect = lambda *a, **k: next(remaining, "")

        def _wait(*a, **k):
            if on_wait is not None:
                on_wait()
            return exit_code

        session.wait.side_effect = _wait
        return session

    return MagicMock(side_effect=_spawn)


async def _set_up(app, auth_headers, bind_runner, agent):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner(agent, cli="claude")


async def _operator_turn(app, auth_headers, agent, spawn):
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": agent, "message": "please do it", "session_mode": "new"},
                headers=auth_headers,
            )
            assert resp.status_code == 200
            await _await_background_run()
    return resp.json()["run_id"]


async def _entries(agent):
    async with async_session_factory() as db:
        result = await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent)
            .order_by(InboundQueueEntry.sequence)
        )
        return list(result.scalars().all())


async def _held_events():
    async with async_session_factory() as db:
        result = await db.execute(select(EventLog).where(EventLog.event_type == "queue_agent_held"))
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 2.4 — the refused turn's input goes back uncounted, and nothing re-spawns within the hold
# ---------------------------------------------------------------------------


async def test_a_refused_turn_requeues_its_input_uncounted_and_is_not_respawned(
    app, auth_headers, bind_runner
):
    """Also 4.2's persisted event. No `JobScheduler` runs here, so this shows too that arming the
    wake with none neither raises nor stops the run's end (design D5)."""
    from hub.scheduler import get_scheduler

    assert get_scheduler() is None
    agent = "held-claude"
    await _set_up(app, auth_headers, bind_runner, agent)
    resets_at = int(time.time()) + 3600
    spawn = _scripted_pty([(_refused_turn("sess-held-1", resets_at), 1)])

    run_id = await _operator_turn(app, auth_headers, agent, spawn)

    assert spawn.call_count == 1
    [entry] = await _entries(agent)
    assert entry.state == "queued"
    assert entry.delivery_attempts == 0
    assert entry.allowance_refusals == 1
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        conversation = await agent_trigger.get_conversation_by_id(db, run.conversation_id)
        assert conversation.provider_session_id == "sess-held-1"

    [event] = await _held_events()
    assert event.severity == "warn"
    assert event.data["agent"] == agent
    assert event.data["run_id"] == run_id
    assert event.data["entry_ids"] == [entry.id]
    assert event.data["limit_type"] == "five_hour"
    assert event.data["resets_at"] == event.data["hold_until"]


# ---------------------------------------------------------------------------
# 2.4b — the two conditions (Round 4 — REV, design D2)
# ---------------------------------------------------------------------------


async def test_a_refusal_whose_reset_has_passed_is_counted(app, auth_headers, bind_runner):
    """A `rejected` reading whose reset is not after the run's end states no wait with an end, so
    it takes the counted path and the delivery limits end it. The hold's 60 s floor still applies,
    so nothing re-spawns here either."""
    agent = "stale-claude"
    await _set_up(app, auth_headers, bind_runner, agent)
    spawn = _scripted_pty([(_refused_turn("sess-stale-1", int(time.time()) - 1), 1)])

    await _operator_turn(app, auth_headers, agent, spawn)

    assert spawn.call_count == 1
    [entry] = await _entries(agent)
    assert entry.state == "queued"
    assert entry.delivery_attempts == 1
    assert entry.allowance_refusals == 0


async def test_a_refusal_the_finalizer_could_not_record_is_counted_and_arms_nothing(
    app, auth_headers, bind_runner
):
    """The loud branch: the finalizing session cannot see its run row, so no `TurnUsage` is
    recorded and no hold exists. An uncounted requeue or a wake there would describe a hold that
    does not exist. No existing test reaches this branch, so the lookup is patched from the moment
    the process exits."""
    from sqlalchemy.ext.asyncio import AsyncSession

    agent = "unseen-claude"
    await _set_up(app, auth_headers, bind_runner, agent)
    finalizing = {"on": False}
    real_get = AsyncSession.get

    async def _get(self, entity, ident, *args, **kwargs):
        if finalizing["on"] and entity is Run:
            return None
        return await real_get(self, entity, ident, *args, **kwargs)

    armed = MagicMock()
    spawn = _scripted_pty(
        [(_refused_turn("sess-unseen-1", int(time.time()) + 3600), 1)],
        on_wait=lambda: finalizing.update(on=True),
    )
    with patch.object(AsyncSession, "get", _get):  # noqa: SIM117
        with patch("hub.api.v1.agent_trigger.arm_allowance_wake", armed):
            await _operator_turn(app, auth_headers, agent, spawn)

    assert finalizing["on"] is True
    [entry] = await _entries(agent)
    assert entry.delivery_attempts == 1
    assert entry.allowance_refusals == 0
    armed.assert_not_called()
    assert await _held_events() == []


# ---------------------------------------------------------------------------
# 2.5 — the refused turn's own firing stays in progress (Round 2, design D10)
# ---------------------------------------------------------------------------


async def test_a_refused_firing_stays_in_progress_until_its_input_is_delivered(
    app, auth_headers, bind_runner, monkeypatch
):
    """The firing whose turn hit the wall used to read `failed` while its input waited for the
    reset; at the reset the delivering run found no `in_progress` row to flip, so the history read
    `failed` for an instruction that was carried out. The hold is ended by the module clock, since
    nothing on the scheduler's path passes its own `now` (Round 3)."""
    from hub.scheduler import JobScheduler
    from hub.turn_scheduler import schedule_agent

    agent = "job-held-claude"
    await _set_up(app, auth_headers, bind_runner, agent)
    spawn = _scripted_pty(
        [
            (_refused_turn("sess-job-1", int(time.time()) + 3600), 1),
            (_served_turn("sess-job-1"), 0),
        ]
    )
    async with async_session_factory() as db:
        db.add(
            AIJob(
                id="job-held-plain",
                project_id="proj-test",
                name="Held plain job",
                agent=agent,
                message="standing instruction",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=True,
            )
        )
        await db.commit()

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                job = await db.get(AIJob, "job-held-plain")
                await JobScheduler()._fire_job_internal(job, "scheduled", session=db)
            await _await_background_run()

            assert spawn.call_count == 1
            async with async_session_factory() as db:
                [firing] = (
                    (await db.execute(select(JobRun).where(JobRun.job_id == "job-held-plain")))
                    .scalars()
                    .all()
                )
            assert firing.status == "in_progress"

            monkeypatch.setattr(
                provider_allowance,
                "_utcnow",
                lambda: datetime.now(timezone.utc) + timedelta(hours=2),
            )
            await schedule_agent("proj-test", agent)
            await _await_background_run()

    assert spawn.call_count == 2
    async with async_session_factory() as db:
        firing = await db.get(JobRun, firing.id)
    assert firing.status == "completed"


# ---------------------------------------------------------------------------
# 2.6 — a completed turn with a refusal reading arms the wake (Round 2, design D5)
# ---------------------------------------------------------------------------


async def test_a_completed_turn_with_a_refusal_reading_arms_the_wake(
    app, auth_headers, bind_runner
):
    """The hold is derived from the reading, whatever the run's status, so a turn cut off late
    that still exited 0 holds the queue too. Armed only for a failed run, that hold would have no
    wake, and nothing would come back at the reset. Its input completed, so none is returned."""
    agent = "late-claude"
    await _set_up(app, auth_headers, bind_runner, agent)
    resets_at = int(time.time()) + 3600
    spawn = _scripted_pty([(_refused_turn("sess-late-1", resets_at, is_error=False), 0)])
    armed = MagicMock()

    with patch("hub.api.v1.agent_trigger.arm_allowance_wake", armed):
        run_id = await _operator_turn(app, auth_headers, agent, spawn)

    async with async_session_factory() as db:
        assert (await db.get(Run, run_id)).status == "completed"
    [entry] = await _entries(agent)
    assert entry.state == "delivered"
    assert entry.allowance_refusals == 0
    armed.assert_called_once_with(
        "proj-test", agent, datetime.fromtimestamp(resets_at, tz=timezone.utc)
    )
    [event] = await _held_events()
    assert event.data["entry_ids"] == []


# ---------------------------------------------------------------------------
# 3.1 — the hold check in `_attempt_turn` (design D4)
# ---------------------------------------------------------------------------


async def _hold(agent, *, observed_ago=timedelta(minutes=1), resets_in=timedelta(hours=1)):
    """A refusal recorded for *agent*, as `_execute_run` records one, without a turn to make it."""
    from hub.db.models import TurnUsage
    from hub.utils import short_id

    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        run_id = f"run-{short_id()}"
        db.add(Run(id=run_id, project_id="proj-test", agent=agent, status="failed"))
        await db.flush()
        db.add(
            TurnUsage(
                id=f"usage-{short_id()}",
                run_id=run_id,
                project_id="proj-test",
                agent=agent,
                status="unavailable",
                allowance=_reading((now + resets_in).timestamp()),
                observed_at=now - observed_ago,
            )
        )
        await db.commit()


async def _queue(agent, conversation_id, *, origin_type, content):
    from hub.db.models import Conversation
    from hub.inbound_queue import new_entry

    async with async_session_factory() as db:
        if await db.get(Conversation, conversation_id) is None:
            db.add(
                Conversation(
                    id=conversation_id, project_id="proj-test", agent=agent, lifecycle="open"
                )
            )
        entry = new_entry(
            project_id="proj-test",
            agent=agent,
            origin_type=origin_type,
            origin_agent="peer" if origin_type == "agent" else None,
            content=content,
            hop_depth=0,
            conversation_id=conversation_id,
        )
        db.add(entry)
        await db.commit()
        return entry.id


async def _await_a_bounded_number_of_runs(rounds=20):
    """`_await_background_run`, but a scheduler that re-spawns at every run's end cannot hang it.

    That is the failure 3.1's second mutation produces: without the `arrived_at` condition the
    run-end re-drain probes again after each refusal, for ever. Bounded, the test fails on the
    spawn count instead of never finishing.
    """
    for _ in range(rounds):
        if not agent_trigger._background_runs:
            return
        for task in list(agent_trigger._background_runs):
            await task
    for task in list(agent_trigger._background_runs):
        task.cancel()


async def _schedule(agent, spawn):
    from hub.turn_scheduler import schedule_agent

    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", agent)
            await _await_a_bounded_number_of_runs()
    return result


async def test_autonomous_input_queued_during_a_hold_starts_no_turn(app, auth_headers, bind_runner):
    """A peer message reaching a held agent waits for the reset, uncounted, and the scheduler's
    answer is the hold sentence. Not a terminal failure: the input will be delivered."""
    agent = "hold-autonomous"
    await _set_up(app, auth_headers, bind_runner, agent)
    await _hold(agent)
    await _queue(agent, "conv-hold-auto", origin_type="agent", content="a peer's note")
    spawn = _scripted_pty([])

    result = await _schedule(agent, spawn)

    assert spawn.call_count == 0
    async with async_session_factory() as db:
        hold = await provider_allowance.provider_hold(db, "proj-test", agent)
    assert result.waiting_reason == provider_allowance.hold_sentence(agent, hold)
    assert result.terminal_failure is False
    [entry] = await _entries(agent)
    assert (entry.state, entry.delivery_attempts) == ("queued", 0)


async def _probe_behind_an_autonomous_head(app, auth_headers, bind_runner, agent):
    """An operator message sent after the refusal, in a conversation of its own, queued behind an
    autonomous head. The probe turn is the one the queue would start: the head's."""
    await _set_up(app, auth_headers, bind_runner, agent)
    await _hold(agent)
    await _queue(agent, f"conv-{agent}-auto", origin_type="agent", content="the head")
    await _queue(agent, f"conv-{agent}-op", origin_type="operator", content="I bought credits")
    spawn = _scripted_pty([(_refused_turn(f"sess-{agent}", int(time.time()) + 3600), 1)])
    await _schedule(agent, spawn)
    return spawn


async def test_operator_input_after_the_refusal_probes_once_even_behind_an_autonomous_head(
    app, auth_headers, bind_runner
):
    """Only the operator can change the allowance, so their new input is tried once. Keyed on the
    whole queue: keyed on the turn's own entries, it could never probe from behind the head."""
    spawn = await _probe_behind_an_autonomous_head(app, auth_headers, bind_runner, "hold-probe")

    assert spawn.call_count == 1


async def test_after_the_probe_is_refused_nothing_more_starts(app, auth_headers, bind_runner):
    """The renewed reading is later than every entry already queued, so the same operator input
    cannot probe twice. Without that condition the run-end re-drain would probe again at once."""
    agent = "hold-probed"
    spawn = await _probe_behind_an_autonomous_head(app, auth_headers, bind_runner, agent)
    assert spawn.call_count == 1

    result = await _schedule(agent, spawn)

    assert spawn.call_count == 1
    assert result.waiting_reason.startswith(f"{agent}'s provider refused its last turn")
    assert {entry.state for entry in await _entries(agent)} == {"queued"}


async def test_after_the_hold_ends_the_scheduler_starts_a_turn(
    app, auth_headers, bind_runner, monkeypatch
):
    """Ended by the module clock: `_attempt_turn` passes no `now` (Round 3)."""
    agent = "hold-ended"
    await _set_up(app, auth_headers, bind_runner, agent)
    await _hold(agent)
    await _queue(agent, "conv-hold-ended", origin_type="agent", content="waited for the reset")
    spawn = _scripted_pty([(_served_turn("sess-hold-ended"), 0)])
    monkeypatch.setattr(
        provider_allowance, "_utcnow", lambda: datetime.now(timezone.utc) + timedelta(hours=2)
    )

    await _schedule(agent, spawn)

    assert spawn.call_count == 1
    [entry] = await _entries(agent)
    assert entry.state == "delivered"


# ---------------------------------------------------------------------------
# 3.2 — the wake (design D5)
# ---------------------------------------------------------------------------


class _RecordingScheduler:
    """Stands in for a running `JobScheduler`: `arm_allowance_wake` reads `.scheduler` only."""

    def __init__(self):
        self.scheduler = MagicMock()


async def test_the_wake_is_one_date_job_per_agent_at_the_holds_end(monkeypatch):
    import hub.scheduler as scheduler_module

    recording = _RecordingScheduler()
    monkeypatch.setattr(scheduler_module, "_scheduler_instance", recording)
    now = datetime(2026, 9, 14, 1, 25, tzinfo=timezone.utc)
    monkeypatch.setattr(provider_allowance, "_utcnow", lambda: now)

    provider_allowance.arm_allowance_wake("proj-test", "dev", now + timedelta(minutes=45))
    provider_allowance.arm_allowance_wake("proj-test", "dev", now - timedelta(minutes=5))

    first, second = recording.scheduler.add_job.call_args_list
    assert first.kwargs["id"] == "allowance-wake:proj-test:dev"
    assert first.kwargs["replace_existing"] is True
    assert first.kwargs["trigger"].run_date == now + timedelta(minutes=45)
    # Never in the past: beyond APScheduler's misfire grace a past date would be dropped.
    assert second.kwargs["trigger"].run_date == now + timedelta(seconds=1)


async def test_a_second_refusal_moves_the_wake_rather_than_adding_one(app, monkeypatch):
    import hub.scheduler as scheduler_module
    from hub.scheduler import JobScheduler

    scheduler = JobScheduler()
    await scheduler.start()
    monkeypatch.setattr(scheduler_module, "_scheduler_instance", scheduler)
    try:
        later = datetime.now(timezone.utc) + timedelta(hours=2)
        provider_allowance.arm_allowance_wake(
            "proj-test", "dev", datetime.now(timezone.utc) + timedelta(hours=1)
        )
        provider_allowance.arm_allowance_wake("proj-test", "dev", later)
        [wake] = [job for job in scheduler.scheduler.get_jobs() if job.id.startswith("allowance")]
        assert wake.next_run_time == later
    finally:
        await scheduler.shutdown()


async def test_the_wake_starts_the_turn_at_the_reset_with_no_other_call(
    app, auth_headers, bind_runner, monkeypatch
):
    """A real `JobScheduler`. The bound address is made known first, or `schedule_or_defer` would
    defer the wake to a first request that never comes, and the test would time out whether or not
    the wake was armed (Round 2). So the armed job is asserted before its date passes too."""
    import asyncio

    import hub.scheduler as scheduler_module
    from hub import bound_address
    from hub.scheduler import JobScheduler

    agent = "wake-claude"
    await _set_up(app, auth_headers, bind_runner, agent)
    monkeypatch.setattr(provider_allowance, "HOLD_FLOOR", timedelta(seconds=1))
    monkeypatch.setattr(bound_address, "known", lambda: True)
    spawn = _scripted_pty(
        [
            (_refused_turn("sess-wake-1", int(time.time()) + 2), 1),
            (_served_turn("sess-wake-1"), 0),
        ]
    )
    scheduler = JobScheduler()
    await scheduler.start()
    monkeypatch.setattr(scheduler_module, "_scheduler_instance", scheduler)
    try:
        run_id = await _operator_turn(app, auth_headers, agent, spawn)
        assert spawn.call_count == 1
        assert scheduler.scheduler.get_job(f"allowance-wake:proj-test:{agent}") is not None

        with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                for _ in range(100):
                    await asyncio.sleep(0.1)
                    if spawn.call_count == 2:
                        break
                await _await_background_run()
    finally:
        await scheduler.shutdown()

    assert spawn.call_count == 2
    [entry] = await _entries(agent)
    assert entry.state == "delivered"
    assert entry.delivered_in_run_id != run_id
