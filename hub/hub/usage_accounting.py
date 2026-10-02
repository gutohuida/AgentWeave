"""Durable, idempotent recording for normalized per-turn usage."""

from __future__ import annotations

import dataclasses
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Project, Run, TurnUsage
from .runner_events import AccountingSample
from .utils import short_id

logger = logging.getLogger(__name__)

#: Rows read looking for the project's newest qualifying Copilot reading (design D8). A page,
#: not everything: a long-lived project's `turn_usage` history should not be scanned in full
#: just to fill one `resetsAt`.
_PRIOR_QUOTA_PAGE = 50


async def record_turn_usage(
    db: AsyncSession,
    *,
    run_id: str,
    project_id: str,
    agent: str,
    # Optional because the two paths that end a run without ever parsing its output — a crash the
    # next Hub start reconciles, and an unhandled error mid-turn — may have no runner name to give.
    # An outcome recorded without one is still an outcome; refusing to record it was the defect.
    runner: Optional[str],
    sample: Optional[AccountingSample],
) -> TurnUsage:
    """Add one accounting outcome for a run, returning the existing row on retry.

    The caller owns the transaction so run completion and accounting can commit together.
    """
    result = await db.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    measured = sample is not None and sample.total_tokens is not None
    row = TurnUsage(
        id=f"usage-{short_id()}",
        run_id=run_id,
        project_id=project_id,
        agent=agent,
        status="measured" if measured else "unavailable",
        runner=runner,
        model=sample.model if sample is not None else None,
        input_tokens=sample.input_tokens if measured and sample is not None else None,
        output_tokens=sample.output_tokens if measured and sample is not None else None,
        total_tokens=sample.total_tokens if measured and sample is not None else None,
        cache_read_tokens=sample.cache_read_tokens if measured and sample is not None else None,
        cache_write_tokens=sample.cache_write_tokens if measured and sample is not None else None,
        reasoning_tokens=sample.reasoning_tokens if measured and sample is not None else None,
        api_equivalent_usd_micros=(
            sample.api_equivalent_usd_micros if sample is not None else None
        ),
        allowance=sample.allowance if sample is not None else None,
        # Copilot credits (design D5): written whether or not the turn is `measured`, unlike
        # the token fields above — a quota-refused turn has no tokens but may still carry a
        # settled charge or a session total worth keeping as the next run's baseline.
        ai_nano_aiu=sample.ai_nano_aiu if sample is not None else None,
        premium_requests=sample.premium_requests if sample is not None else None,
        session_nano_aiu_total=sample.session_nano_aiu_total if sample is not None else None,
        session_premium_requests_total=(
            sample.session_premium_requests_total if sample is not None else None
        ),
    )
    db.add(row)
    await db.flush()
    return row


async def copilot_session_baseline(
    db: AsyncSession, project_id: str, agent: str, session_id: Optional[str]
) -> Optional[Tuple[int, Optional[float]]]:
    """The last-written `turn_usage` row's session totals for this Copilot session (design D4).

    "Last written" means `ORDER BY turn_usage.rowid DESC` — insertion order — not `observed_at`,
    which a clock stepping backwards between two runs of the same session can reorder (review
    2026-09-28, finding 3). `turn_usage` has a `String` primary key, so it is a rowid table, as
    `_approval_outcome` relies on for `spec_document_events` (`api/v1/spec.py:262-281`).

    Returns None when there is no such row, or on any exception, logged.
    """
    if session_id is None:
        return None
    try:
        row = (
            await db.execute(
                select(TurnUsage.session_nano_aiu_total, TurnUsage.session_premium_requests_total)
                .select_from(TurnUsage)
                .join(Run, Run.id == TurnUsage.run_id)
                .where(
                    TurnUsage.project_id == project_id,
                    TurnUsage.agent == agent,
                    Run.session_id == session_id,
                    TurnUsage.session_nano_aiu_total.isnot(None),
                )
                .order_by(literal_column("turn_usage.rowid").desc())
                .limit(1)
            )
        ).first()
    except Exception:
        logger.exception(
            "copilot_session_baseline failed for project=%s agent=%s session=%s",
            project_id,
            agent,
            session_id,
        )
        return None
    if row is None:
        return None
    nano_aiu, premium = row
    return int(nano_aiu), premium


async def copilot_prior_quota_reading(
    db: AsyncSession, project_id: str, *, now: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """The project's newest Copilot allowance reading whose `resetsAt` is still ahead, read
    across **every agent** (design D8, review finding 1(b)): a quota refusal lands on a run's
    first call, which has no `assistant.usage` and so no snapshot of its own, and the quota is
    per GitHub account, so another of the project's Copilot agents states the same reset.
    `ORDER BY turn_usage.rowid DESC`, as `copilot_session_baseline` reads insertion order
    (review finding 3) — not `observed_at`. Returns None on no qualifying row, or on any
    exception, logged.
    """
    current = now if now is not None else datetime.now(timezone.utc)
    try:
        rows = (
            (
                await db.execute(
                    select(TurnUsage.allowance)
                    .where(TurnUsage.project_id == project_id, TurnUsage.runner == "copilot")
                    .order_by(literal_column("turn_usage.rowid").desc())
                    .limit(_PRIOR_QUOTA_PAGE)
                )
            )
            .scalars()
            .all()
        )
    except Exception:
        logger.exception("copilot_prior_quota_reading failed for project=%s", project_id)
        return None
    for allowance in rows:
        if not isinstance(allowance, dict):
            continue
        resets_at = allowance.get("resetsAt")
        if isinstance(resets_at, bool) or not isinstance(resets_at, (int, float)):
            continue
        if resets_at > current.timestamp():
            return allowance
    return None


async def settle_copilot_credits(
    db: AsyncSession,
    sample: Optional[AccountingSample],
    *,
    project_id: str,
    agent: str,
    session_id: Optional[str],
) -> Optional[AccountingSample]:
    """Design D4: credits are the larger of the session-checkpoint difference across runs and
    this run's own per-call sum — never charged twice, never negative, correct whether or not
    the session's checkpoint continues counting after a `session/load`.

    Acts on every sample whose `credit_session_new` is not None (only `CopilotUsageLedger.finish`
    sets it); any other sample is returned unchanged. Never raises: a failed baseline read is "no
    baseline" (`copilot_session_baseline` already returns None for that), and any other exception
    here is logged, returning `sample` with its ledger-provisional per-call credits untouched.
    """
    if sample is None or sample.credit_session_new is None:
        return sample

    try:
        if sample.credit_session_new:
            baseline_total: Optional[int] = 0
            baseline_premium: Optional[float] = 0.0
        else:
            baseline = await copilot_session_baseline(db, project_id, agent, session_id)
            if baseline is None:
                baseline_total, baseline_premium = None, None
            else:
                baseline_total, baseline_premium = baseline

        per_call = sample.ai_nano_aiu  # the ledger's provisional per-call sum, or None
        checkpoint_total = sample.session_nano_aiu_total
        checkpoint_premium = sample.session_premium_requests_total

        diff: Optional[int] = (
            checkpoint_total - baseline_total
            if checkpoint_total is not None and baseline_total is not None
            else None
        )

        if diff is not None and diff >= (per_call or 0):
            ai_nano_aiu: Optional[int] = diff
            premium_requests: Optional[float] = None
            if checkpoint_premium is not None and baseline_premium is not None:
                premium_diff = checkpoint_premium - baseline_premium
                if premium_diff >= 0:
                    premium_requests = premium_diff
        else:
            ai_nano_aiu = per_call
            premium_requests = None

        # The fallback stores the total it reached, so the next run's difference doesn't charge
        # the same spend again (D4). A run that saw a checkpoint always stores that checkpoint's
        # own totals, whichever figure it was charged.
        if checkpoint_total is not None:
            stored_total: Optional[int] = checkpoint_total
            stored_premium: Optional[float] = checkpoint_premium
        elif per_call is not None and baseline_total is not None:
            stored_total = baseline_total + per_call
            stored_premium = None
        else:
            stored_total = None
            stored_premium = None

        # D8: the ledger could not read the project's prior reading (D2, no database), so a
        # refused run with none of its own named no `resetsAt`. Fill it now, only when this run
        # is already `rejected` and still carries none — never for an `allowed` reading, and
        # never overwriting a `resetsAt` this run's own snapshot already named.
        allowance = sample.allowance
        if (
            isinstance(allowance, dict)
            and allowance.get("status") == "rejected"
            and "resetsAt" not in allowance
        ):
            prior = await copilot_prior_quota_reading(db, project_id)
            if prior is not None:
                allowance = dict(allowance, resetsAt=prior.get("resetsAt"))

        return dataclasses.replace(
            sample,
            allowance=allowance,
            ai_nano_aiu=ai_nano_aiu,
            premium_requests=premium_requests,
            session_nano_aiu_total=stored_total,
            session_premium_requests_total=stored_premium,
        )
    except Exception:
        logger.exception(
            "settle_copilot_credits failed for project=%s agent=%s session=%s",
            project_id,
            agent,
            session_id,
        )
        return sample


def _summary_from_row(row: Any, *, agent: Optional[str] = None) -> Dict[str, Any]:
    measured_turns = int(row.measured_turns or 0)
    summary: Dict[str, Any] = {
        "input_tokens": (
            int(row.input_tokens) if measured_turns and row.input_tokens is not None else None
        ),
        "output_tokens": (
            int(row.output_tokens) if measured_turns and row.output_tokens is not None else None
        ),
        "total_tokens": (
            int(row.total_tokens) if measured_turns and row.total_tokens is not None else None
        ),
        "measured_turns": measured_turns,
        "unavailable_turns": int(row.unavailable_turns or 0),
        "api_equivalent_usd_micros": (
            int(row.api_equivalent_usd_micros)
            if row.api_equivalent_usd_micros is not None
            else None
        ),
        "unpriced_turns": int(row.unpriced_turns or 0),
        # Copilot's credits (D5, D6): null where no turn reported one, never a zero.
        "ai_nano_aiu": int(row.ai_nano_aiu) if row.ai_nano_aiu is not None else None,
        "premium_requests": (
            float(row.premium_requests) if row.premium_requests is not None else None
        ),
    }
    if agent is not None:
        summary = {"agent": agent, **summary}
    return summary


def _aggregate_columns() -> tuple[Any, ...]:
    measured = TurnUsage.status == "measured"
    unavailable = TurnUsage.status == "unavailable"
    return (
        func.sum(case((measured, TurnUsage.input_tokens), else_=None)).label("input_tokens"),
        func.sum(case((measured, TurnUsage.output_tokens), else_=None)).label("output_tokens"),
        func.sum(case((measured, TurnUsage.total_tokens), else_=None)).label("total_tokens"),
        func.sum(case((measured, 1), else_=0)).label("measured_turns"),
        func.sum(case((unavailable, 1), else_=0)).label("unavailable_turns"),
        func.sum(TurnUsage.api_equivalent_usd_micros).label("api_equivalent_usd_micros"),
        func.sum(case((TurnUsage.api_equivalent_usd_micros.is_(None), 1), else_=0)).label(
            "unpriced_turns"
        ),
        func.sum(TurnUsage.ai_nano_aiu).label("ai_nano_aiu"),
        func.sum(TurnUsage.premium_requests).label("premium_requests"),
    )


def budget_state(limit_tokens: Optional[int], used_tokens: Optional[int]) -> Dict[str, Any]:
    used = used_tokens or 0
    return {
        "limit_tokens": limit_tokens,
        "used_tokens": used,
        "remaining_tokens": (max(0, limit_tokens - used) if limit_tokens is not None else None),
        "exhausted": limit_tokens is not None and used >= limit_tokens,
    }


async def accounting_snapshot(
    db: AsyncSession, project_id: str, *, recent_limit: int = 50
) -> Dict[str, Any]:
    """Derive project/agent totals and presentation state from immutable usage rows."""
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} does not exist")

    project_result = await db.execute(
        select(*_aggregate_columns()).where(TurnUsage.project_id == project_id)
    )
    project_summary = _summary_from_row(project_result.one())

    agent_result = await db.execute(
        select(TurnUsage.agent, *_aggregate_columns())
        .where(TurnUsage.project_id == project_id)
        .group_by(TurnUsage.agent)
        .order_by(TurnUsage.agent)
    )
    agents: List[Dict[str, Any]] = [
        _summary_from_row(row, agent=row.agent) for row in agent_result.all()
    ]

    recent_result = await db.execute(
        select(TurnUsage)
        .where(TurnUsage.project_id == project_id)
        .order_by(TurnUsage.observed_at.desc(), TurnUsage.id.desc())
        .limit(recent_limit)
    )
    recent_rows = list(recent_result.scalars().all())
    recent_turns = [
        {
            "id": row.id,
            "run_id": row.run_id,
            "agent": row.agent,
            "status": row.status,
            "runner": row.runner,
            "model": row.model,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "total_tokens": row.total_tokens,
            "cache_read_tokens": row.cache_read_tokens,
            "cache_write_tokens": row.cache_write_tokens,
            "reasoning_tokens": row.reasoning_tokens,
            "api_equivalent_usd_micros": row.api_equivalent_usd_micros,
            "allowance": row.allowance if isinstance(row.allowance, dict) else None,
            "observed_at": row.observed_at.isoformat(),
            "ai_nano_aiu": row.ai_nano_aiu,
            "premium_requests": row.premium_requests,
        }
        for row in recent_rows
    ]
    latest_allowance_row = next(
        (row for row in recent_rows if isinstance(row.allowance, dict)), None
    )
    latest_allowance = latest_allowance_row.allowance if latest_allowance_row else None
    cost = project_summary["api_equivalent_usd_micros"]
    total = project_summary["total_tokens"]
    if latest_allowance is not None:
        preferred_display = {
            "kind": "allowance",
            "label": "Rate-limit allowance",
            "allowance": latest_allowance,
            # Whose allowance it is: the row's own runner, so a label never names the wrong one.
            "runner": latest_allowance_row.runner,
        }
    elif cost is not None:
        preferred_display = {
            "kind": "api_equivalent",
            "label": "API-equivalent estimate",
            "usd_micros": cost,
            "unpriced_turns": project_summary["unpriced_turns"],
        }
    elif total is not None:
        preferred_display = {"kind": "tokens", "label": "Tokens", "total_tokens": total}
    else:
        preferred_display = {"kind": "unavailable", "label": "Usage unavailable"}

    return {
        "project": project_summary,
        "agents": agents,
        "budget": budget_state(project.token_budget, total),
        "preferred_display": preferred_display,
        "recent_turns": recent_turns,
    }


async def conversation_usage(
    db: AsyncSession, project_id: str, conversation_id: str
) -> Dict[str, Any]:
    """Aggregate usage across every run in one conversation.

    Unlike `accounting_snapshot`'s `recent_turns`, this is not capped at the last N rows — a
    conversation's own turns can fall out of the project-wide recent window long before the
    conversation is done, so the rollup shown for it has to be a real aggregate, not a slice.
    """
    result = await db.execute(
        select(*_aggregate_columns())
        .select_from(TurnUsage)
        .join(Run, Run.id == TurnUsage.run_id)
        .where(TurnUsage.project_id == project_id, Run.conversation_id == conversation_id)
    )
    return _summary_from_row(result.one())


async def project_budget_state(db: AsyncSession, project_id: str) -> Dict[str, Any]:
    """Return the lightweight budget facts needed on the turn-scheduling hot path."""
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} does not exist")
    used = await db.scalar(
        select(func.sum(TurnUsage.total_tokens)).where(
            TurnUsage.project_id == project_id,
            TurnUsage.status == "measured",
        )
    )
    return budget_state(project.token_budget, int(used) if used is not None else None)
