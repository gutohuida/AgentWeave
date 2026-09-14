"""A provider's refusal on usage grounds, and the hold on an agent's queue that follows from it.

`a-spent-allowance-holds-the-queue`, designs D1, D3, D5 and D9 (finding F355). A Claude turn the
provider refuses because the account's usage limit is spent used to be counted like any other
failure: re-delivered about ten seconds later into the same exhausted allowance, its provider
session cleared at the second attempt and its input withdrawn at the third. Measured on LoopEngine
(2026-09-14): 69 of 69 such runs carried the refusal as a structured reading, `status: "rejected"`
with an epoch `resetsAt`, and the refused session was sound and resumable.

**The hold is derived, not stored.** The reading is already recorded, on `turn_usage.allowance`,
in the transaction that ends the run. A stored `held_until` would be a second copy that can drift
and would need its own release path. Derived, it survives a restart, and it is released by the
next outcome that is not a refusal, whoever caused it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import TurnUsage

logger = logging.getLogger(__name__)

#: The spin guard (design D3). A `rejected` reading whose `resetsAt` is already past — clock skew,
#: or a provider that reset late — would otherwise release at once, refuse again and requeue: a
#: tight loop of spawns. The floor caps that at one refused spawn a minute per agent. It is not a
#: backoff policy; it only bounds a pathological reading, and the delivery limits end such a
#: refusal because it is counted (design D2).
HOLD_FLOOR = timedelta(seconds=60)

#: Rows read per page while looking for an agent's newest informative row. A page, not a window:
#: every spawn failure after a refusal adds an uninformative row, and a fixed window those rows
#: overflow would find no refusal and release a hold the provider still enforces (design D3).
_PAGE = 50


def _utcnow() -> datetime:
    """The one clock the hold reads (design, *Risks*).

    `provider_hold` and `agents_held` default to it, and no call site passes its own `now`, so a
    test that has to end a hold without waiting for the reset patches this function.
    """
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AllowanceRefusal:
    """The provider's structured word that this turn was refused on usage grounds."""

    resets_at: datetime
    limit_type: Optional[str] = None


def allowance_refusal(allowance: Any) -> Optional[AllowanceRefusal]:
    """Recognise a refusal by `status == "rejected"` and a numeric `resetsAt` (design D1).

    - **Not the harness's prose.** *"resets 3:10am (Europe/Lisbon)"* has no date, is in the
      harness's locale, and its wording is the harness's to change; the reading carries the same
      instant.
    - **Not `overageStatus`.** It read `rejected` on completed runs too, so it describes the
      overage option, not this turn.
    - **No `resetsAt`, no refusal.** Without a reset time there is nothing to hold until, so the
      run keeps the ordinary counted path. A guessed backoff is a policy nobody has decided.
    """
    if not isinstance(allowance, dict) or allowance.get("status") != "rejected":
        return None
    resets_at = allowance.get("resetsAt")
    if isinstance(resets_at, bool) or not isinstance(resets_at, (int, float)):
        return None
    limit_type = allowance.get("rateLimitType")
    return AllowanceRefusal(
        resets_at=datetime.fromtimestamp(resets_at, tz=timezone.utc),
        limit_type=limit_type if isinstance(limit_type, str) and limit_type else None,
    )


@dataclass(frozen=True)
class ProviderHold:
    """An agent whose provider's last word was a refusal, and until when that word stands."""

    hold_until: datetime
    resets_at: datetime
    limit_type: Optional[str]
    observed_at: datetime
    run_id: str


def hold_for_reading(allowance: Any, observed_at: datetime, run_id: str) -> Optional[ProviderHold]:
    """The hold one recorded reading establishes, whether or not it has already ended."""
    refusal = allowance_refusal(allowance)
    if refusal is None:
        return None
    return ProviderHold(
        hold_until=max(refusal.resets_at, observed_at + HOLD_FLOOR),
        resets_at=refusal.resets_at,
        limit_type=refusal.limit_type,
        observed_at=observed_at,
        run_id=run_id,
    )


def _is_informative(row: TurnUsage) -> bool:
    """Whether a row says anything about the provider (design D3).

    Four paths write a row with no sample at all — the transport-failure tail, a spawn that never
    started, a Codex app-server run that never started, and crash reconciliation — and if one of
    them ended a hold, a Hub restart or a missing CLI would release an agent the provider is still
    refusing. A `measured` row is informative even with no reading: the provider served tokens.

    A Python check, deliberately. A row written with no reading stores the JSON literal `null`,
    which `allowance IS NOT NULL` matches, and `json_type` is SQLite's alone.
    """
    return isinstance(row.allowance, dict) or row.status == "measured"


async def _newest_informative(db: AsyncSession, project_id: str, agent: str) -> Optional[TurnUsage]:
    offset = 0
    while True:
        rows = (
            (
                await db.execute(
                    select(TurnUsage)
                    .where(TurnUsage.project_id == project_id, TurnUsage.agent == agent)
                    .order_by(TurnUsage.observed_at.desc())
                    .offset(offset)
                    .limit(_PAGE)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if _is_informative(row):
                return row
        if len(rows) < _PAGE:
            return None
        offset += _PAGE


async def last_refusal(db: AsyncSession, project_id: str, agent: str) -> Optional[ProviderHold]:
    """The hold *agent*'s newest informative row establishes, **whether or not it has ended**.

    `provider_hold` answers *is the agent held now*. A Hub start asks the other question (designs
    D5 and D10): was the provider's last word a refusal, so that queued input is still promised a
    delivery, by a wake if the reset is ahead and by a re-drain now if it fell while the Hub was
    down.
    """
    row = await _newest_informative(db, project_id, agent)
    if row is None:
        return None
    return hold_for_reading(row.allowance, row.observed_at, row.run_id)


async def provider_hold(
    db: AsyncSession, project_id: str, agent: str, *, now: Optional[datetime] = None
) -> Optional[ProviderHold]:
    """The hold on *agent*'s queue, read from the provider's most recent word about it (D3)."""
    hold = await last_refusal(db, project_id, agent)
    current = now if now is not None else _utcnow()
    if hold is None or current >= hold.hold_until:
        return None
    return hold


async def agents_held(
    db: AsyncSession, project_id: str, *, now: Optional[datetime] = None
) -> Set[str]:
    """Every agent in *project_id* that `provider_hold` holds, read at one `now` (design D6)."""
    current = now if now is not None else _utcnow()
    agents = (
        (
            await db.execute(
                select(TurnUsage.agent).where(TurnUsage.project_id == project_id).distinct()
            )
        )
        .scalars()
        .all()
    )
    held: Set[str] = set()
    for agent in agents:
        if await provider_hold(db, project_id, agent, now=current) is not None:
            held.add(agent)
    return held


def _clock(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%H:%M")


def hold_sentence(agent: str, hold: ProviderHold) -> str:
    """What the operator is told about a held queue (design D9). Derived, never stored."""
    limit = f"{hold.limit_type.replace('_', '-')} " if hold.limit_type else ""
    until = hold.hold_until.astimezone(timezone.utc)
    return (
        f"{agent}'s provider refused its last turn: its {limit}usage limit is spent until "
        f"{_clock(until)} UTC ({until.isoformat()}). The Hub holds its queue until then and does "
        "not count the refusal against any input. A new message from the operator is tried once "
        "sooner."
    )


def hold_busy_reason(agent: str, hold: ProviderHold) -> str:
    """The loop busy guard's short form (design D6)."""
    return f"{agent} is held until {_clock(hold.hold_until)} UTC by its provider's usage limit"


def hold_coalesce_reason(agent: str, hold: ProviderHold) -> str:
    """A plain job's coalesced firing (design D7). Must fit `JobRun.error_summary`'s 500."""
    return (
        f"{agent}'s provider usage limit is spent until {_clock(hold.hold_until)} UTC, and this "
        "job's earlier firing is still queued for it. This firing adds nothing."
    )


def allowance_wake_job_id(project_id: str, agent: str) -> str:
    return f"allowance-wake:{project_id}:{agent}"


async def _allowance_wake(project_id: str, agent: str) -> None:
    """What the wake runs: the re-drain a startup reconciliation also uses (design D5)."""
    from .run_reconciliation import schedule_or_defer

    await schedule_or_defer({(project_id, agent)})


def arm_allowance_wake(project_id: str, agent: str, when: datetime) -> None:
    """Start *agent*'s queue again at *when*, the end of its hold (design D5).

    The turn scheduler has no tick, so without this a hold would end and nothing would come back.
    A one-shot date job on the running `JobScheduler`, whose store is in memory by design (F351),
    so it adds nothing to the database; `arm_held_queues` re-arms at start. One id per agent with
    `replace_existing`, so a renewed refusal moves the wake rather than adding one.

    Never raises into its caller, which is a run's end. With no running scheduler — most tests, and
    anything before `init_scheduler` — it does nothing; the next start's re-arm covers it.
    """
    from .scheduler import get_scheduler

    scheduler = get_scheduler()
    if scheduler is None or scheduler.scheduler is None:
        logger.debug("No job scheduler running; the wake for %r at %s is not armed", agent, when)
        return
    try:
        from apscheduler.triggers.date import DateTrigger

        # Never in the past: a date under APScheduler's misfire grace would still run, but one
        # beyond it is dropped. The floor keeps `when` ahead in practice; this makes it certain.
        run_date = max(when, _utcnow() + timedelta(seconds=1))
        scheduler.scheduler.add_job(
            func=_allowance_wake,
            trigger=DateTrigger(run_date=run_date, timezone="UTC"),
            id=allowance_wake_job_id(project_id, agent),
            args=[project_id, agent],
            replace_existing=True,
        )
    except Exception as exc:
        logger.error("Failed to arm the allowance wake for %r: %s", agent, exc)


async def arm_held_queues() -> int:
    """Re-arm every wake a restart dropped (design D5). Returns how many agents it covered.

    The wake lives in the job scheduler's memory store, so a restart loses it. Called from
    `lifespan()` after `init_scheduler()`, for every agent with queued input whose newest
    *informative* row is a refusal. The newest row would not do: crash reconciliation runs just
    before, in the same `lifespan`, and writes an uninformative row that would hide the refusal.

    A reset still ahead is armed at the hold's end. One that fell while the Hub was down is
    re-drained now (or at the first request, `schedule_or_defer`): the Hub promised that delivery.
    """
    from .db.engine import async_session_factory
    from .db.models import InboundQueueEntry
    from .run_reconciliation import schedule_or_defer

    to_arm: list[tuple[str, str, datetime]] = []
    to_schedule: set[tuple[str, str]] = set()
    async with async_session_factory() as db:
        pairs = (
            await db.execute(
                select(InboundQueueEntry.project_id, InboundQueueEntry.agent)
                .where(InboundQueueEntry.state == "queued")
                .distinct()
            )
        ).all()
        now = _utcnow()
        for project_id, agent in pairs:
            hold = await last_refusal(db, project_id, agent)
            if hold is None:
                continue
            if now < hold.hold_until:
                to_arm.append((project_id, agent, hold.hold_until))
            else:
                to_schedule.add((project_id, agent))
    for project_id, agent, when in to_arm:
        arm_allowance_wake(project_id, agent, when)
    if to_schedule:
        await schedule_or_defer(to_schedule)
    return len(to_arm) + len(to_schedule)
