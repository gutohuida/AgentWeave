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

pytestmark = pytest.mark.asyncio


async def _await_background_run():
    while agent_trigger._background_runs:
        for task in list(agent_trigger._background_runs):
            await task


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
    the script raises `StopIteration` inside `spawn`, which is a spawn failure the test would see.
    """
    remaining_turns = iter(turns)

    def _spawn(*args, **kwargs):
        lines, exit_code = next(remaining_turns)
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
