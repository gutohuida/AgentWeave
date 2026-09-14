"""`a-spent-allowance-holds-the-queue` group 1 — recognising a refusal, and the hold it derives.

Finding F355. A turn the provider refused because the agent's usage allowance was spent used to be
counted like any other failure and re-delivered about ten seconds later into the same exhausted
allowance. The readings below are the measured shape: 69 of 69 refused runs on LoopEngine carried
`status: "rejected"` with an epoch `resetsAt` (design, *Context*).
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub import provider_allowance
from hub.db.engine import async_session_factory
from hub.db.models import Run, TurnUsage
from hub.provider_allowance import (
    HOLD_FLOOR,
    ProviderHold,
    agents_held,
    allowance_refusal,
    hold_busy_reason,
    hold_coalesce_reason,
    hold_sentence,
    provider_hold,
)
from hub.runner_events import AccountingSample
from hub.usage_accounting import record_turn_usage
from hub.utils import short_id

PROJECT = "proj-test"
NOW = datetime(2026, 9, 14, 1, 25, tzinfo=timezone.utc)


def _reading(resets_at, *, status="rejected", limit="five_hour"):
    """The measured reading (tasks.md, head), with its reset and status set."""
    epoch = resets_at.timestamp() if isinstance(resets_at, datetime) else resets_at
    return {
        "status": status,
        "resetsAt": epoch,
        "rateLimitType": limit,
        "overageStatus": "rejected",
        "overageDisabledReason": "out_of_credits",
        "isUsingOverage": False,
        "unifiedWindows": {"five_hour": {"utilization": 1.02, "resetsAt": epoch}},
    }


# ---------------------------------------------------------------------------
# 1.1 — recognition (design D1)
# ---------------------------------------------------------------------------


def test_the_measured_reading_is_recognised_with_its_reset_in_utc():
    refusal = allowance_refusal(_reading(1789351800))
    assert refusal is not None
    assert refusal.resets_at == datetime(2026, 9, 14, 2, 10, tzinfo=timezone.utc)
    assert refusal.limit_type == "five_hour"


@pytest.mark.parametrize(
    "allowance",
    [
        _reading(1789351800, status="allowed"),
        _reading(1789351800, status="allowed_warning"),
        {"status": "rejected", "rateLimitType": "five_hour"},
        {"status": "rejected", "resetsAt": True},
        None,
        ["rejected", 1789351800],
        "rejected",
    ],
    ids=["allowed", "allowed_warning", "no-resetsAt", "bool-resetsAt", "none", "list", "str"],
)
def test_anything_but_a_rejected_reading_with_a_numeric_reset_is_not_a_refusal(allowance):
    assert allowance_refusal(allowance) is None


def test_overage_rejected_on_a_served_turn_is_not_a_refusal():
    """Measured on completed runs: `overageStatus` describes the overage option, not this turn."""
    reading = _reading(1789351800, status="allowed")
    assert reading["overageStatus"] == "rejected"
    assert allowance_refusal(reading) is None


# ---------------------------------------------------------------------------
# 1.2 / 1.2b / 1.3 — the derived hold (design D3, D6)
# ---------------------------------------------------------------------------


async def _row(db, agent, *, observed_at, allowance=None, measured=False):
    run_id = f"run-{short_id()}"
    db.add(Run(id=run_id, project_id=PROJECT, agent=agent, status="failed"))
    await db.flush()
    db.add(
        TurnUsage(
            id=f"usage-{short_id()}",
            run_id=run_id,
            project_id=PROJECT,
            agent=agent,
            status="measured" if measured else "unavailable",
            total_tokens=100 if measured else None,
            allowance=allowance,
            observed_at=observed_at,
        )
    )
    await db.commit()
    return run_id


async def _refused(db, agent, *, observed_at=NOW, resets_at=None):
    return await _row(
        db,
        agent,
        observed_at=observed_at,
        allowance=_reading(resets_at or observed_at + timedelta(hours=1)),
        measured=False,
    )


async def test_a_refusal_an_hour_ahead_holds(app):
    async with async_session_factory() as db:
        run_id = await _refused(db, "dev")
        hold = await provider_hold(db, PROJECT, "dev", now=NOW + timedelta(minutes=5))
    assert hold is not None
    assert hold.hold_until == NOW + timedelta(hours=1)
    assert hold.run_id == run_id
    assert hold.limit_type == "five_hour"


async def test_a_later_served_turn_with_an_allowed_reading_releases(app):
    async with async_session_factory() as db:
        await _refused(db, "dev")
        await _row(
            db,
            "dev",
            observed_at=NOW + timedelta(seconds=30),
            allowance=_reading(NOW + timedelta(hours=5), status="allowed"),
            measured=True,
        )
        assert await provider_hold(db, PROJECT, "dev", now=NOW + timedelta(minutes=5)) is None


async def test_a_later_measured_turn_with_no_reading_releases(app):
    async with async_session_factory() as db:
        await _refused(db, "dev")
        await _row(db, "dev", observed_at=NOW + timedelta(seconds=30), measured=True)
        assert await provider_hold(db, PROJECT, "dev", now=NOW + timedelta(minutes=5)) is None


async def test_a_later_unavailable_row_with_no_reading_does_not_release(app):
    """The pre-spawn and crash-reconciliation rows say nothing about the provider."""
    async with async_session_factory() as db:
        await _refused(db, "dev")
        await _row(db, "dev", observed_at=NOW + timedelta(seconds=30))
        assert await provider_hold(db, PROJECT, "dev", now=NOW + timedelta(minutes=5)) is not None


async def test_sixty_uninformative_rows_after_a_refusal_still_hold(app):
    """(Round 2.) A fixed window of 50 would find no refusal and release a hold still enforced."""
    async with async_session_factory() as db:
        await _refused(db, "dev")
        for i in range(60):
            await _row(db, "dev", observed_at=NOW + timedelta(seconds=i + 1))
        assert await provider_hold(db, PROJECT, "dev", now=NOW + timedelta(minutes=5)) is not None


async def test_a_reset_already_past_holds_for_the_floor(app):
    async with async_session_factory() as db:
        observed = NOW - timedelta(seconds=10)
        await _refused(db, "dev", observed_at=observed, resets_at=NOW - timedelta(minutes=5))
        hold = await provider_hold(db, PROJECT, "dev", now=NOW)
    assert timedelta(seconds=60) == HOLD_FLOOR
    assert hold is not None
    assert hold.hold_until == observed + HOLD_FLOOR


async def test_another_agents_refusal_does_not_hold_this_agent(app):
    async with async_session_factory() as db:
        await _refused(db, "other")
        await _row(db, "dev", observed_at=NOW - timedelta(minutes=1), measured=True)
        assert await provider_hold(db, PROJECT, "dev", now=NOW + timedelta(minutes=5)) is None


async def test_the_hold_reads_the_module_clock_when_no_now_is_given(app, monkeypatch):
    """(Round 3.) No call site passes `now`, so this is what a test patches to end a hold."""
    async with async_session_factory() as db:
        await _refused(db, "dev")
        monkeypatch.setattr(provider_allowance, "_utcnow", lambda: NOW + timedelta(minutes=5))
        assert await provider_hold(db, PROJECT, "dev") is not None
        monkeypatch.setattr(provider_allowance, "_utcnow", lambda: NOW + timedelta(hours=2))
        assert await provider_hold(db, PROJECT, "dev") is None


async def test_agents_held_names_exactly_the_refused_agents(app):
    """1.2b. One of the two refused agents has a crash-reconciled row after its refusal."""
    async with async_session_factory() as db:
        await _refused(db, "alpha")
        await _refused(db, "beta")
        await _row(db, "beta", observed_at=NOW + timedelta(seconds=5))  # crash-reconciled
        await _row(db, "served", observed_at=NOW, measured=True)
        at = NOW + timedelta(minutes=5)
        held = await agents_held(db, PROJECT, now=at)
        assert held == {"alpha", "beta"}
        for agent in ("alpha", "beta", "served", "never-ran"):
            one = await provider_hold(db, PROJECT, agent, now=at)
            assert (one is not None) == (agent in held)


async def test_a_null_reading_written_by_the_real_writer_does_not_release(app):
    """1.3. `record_turn_usage(sample=None)` stores the JSON literal `null`, which is not SQL
    NULL, so an `allowance IS NOT NULL` filter would take that row for a reading."""
    async with async_session_factory() as db:
        await _refused(db, "dev")
        run_id = f"run-{short_id()}"
        db.add(Run(id=run_id, project_id=PROJECT, agent="dev", status="failed"))
        await db.flush()
        row = await record_turn_usage(
            db, run_id=run_id, project_id=PROJECT, agent="dev", runner="claude", sample=None
        )
        row.observed_at = NOW + timedelta(seconds=30)
        await db.commit()

        assert await provider_hold(db, PROJECT, "dev", now=NOW + timedelta(minutes=5)) is not None

        from sqlalchemy import select

        is_sql_null = await db.scalar(
            select(TurnUsage.allowance.is_(None)).where(TurnUsage.run_id == run_id)
        )
        assert is_sql_null is False


async def test_a_measured_sample_with_a_refusal_holds(app):
    """A refused run that used tokens (3 of dev's 51) is measured *and* a refusal; the reading
    decides it."""
    async with async_session_factory() as db:
        run_id = f"run-{short_id()}"
        db.add(Run(id=run_id, project_id=PROJECT, agent="dev", status="failed"))
        await db.flush()
        await record_turn_usage(
            db,
            run_id=run_id,
            project_id=PROJECT,
            agent="dev",
            runner="claude",
            sample=AccountingSample(
                source="claude",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                allowance=_reading(datetime.now(timezone.utc) + timedelta(hours=1)),
            ),
        )
        await db.commit()
        assert await provider_hold(db, PROJECT, "dev") is not None


# ---------------------------------------------------------------------------
# 1.4 — the sentences (design D6, D7, D9)
# ---------------------------------------------------------------------------


def _hold(limit="seven_day"):
    until = datetime(2026, 9, 14, 2, 10, tzinfo=timezone.utc)
    return ProviderHold(
        hold_until=until,
        resets_at=until,
        limit_type=limit,
        observed_at=until - timedelta(hours=1),
        run_id="run-x",
    )


def test_the_sentences_fit_at_the_longest_agent_name():
    agent = "a" * 32
    hold = _hold()
    assert len(hold_sentence(agent, hold)) == 285
    assert len(hold_busy_reason(agent, hold)) == 86
    assert len(hold_coalesce_reason(agent, hold)) == 161
    # `JobRun.error_summary` is `String(500)`.
    assert len(hold_coalesce_reason(agent, hold)) <= 500


@pytest.mark.parametrize("render", [hold_sentence, hold_busy_reason, hold_coalesce_reason])
def test_each_sentence_names_the_agent_and_the_hold_time(render):
    text = render("dev", _hold())
    assert "dev" in text
    assert "02:10 UTC" in text


def test_the_hold_sentence_reads_the_limit_and_omits_an_absent_one():
    assert "its seven-day usage limit is spent" in hold_sentence("dev", _hold())
    bare = hold_sentence("dev", _hold(limit=None))
    assert "its usage limit is spent" in bare
    assert "None" not in bare
