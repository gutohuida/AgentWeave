"""Durable, idempotent recording for normalized per-turn usage."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Project, TurnUsage
from .runner_events import AccountingSample
from .utils import short_id


async def record_turn_usage(
    db: AsyncSession,
    *,
    run_id: str,
    project_id: str,
    agent: str,
    runner: str,
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
    )
    db.add(row)
    await db.flush()
    return row


def _summary_from_row(row: Any, *, agent: Optional[str] = None) -> Dict[str, Any]:
    measured_turns = int(row.measured_turns or 0)
    summary: Dict[str, Any] = {
        "input_tokens": int(row.input_tokens) if measured_turns and row.input_tokens is not None else None,
        "output_tokens": (
            int(row.output_tokens) if measured_turns and row.output_tokens is not None else None
        ),
        "total_tokens": int(row.total_tokens) if measured_turns and row.total_tokens is not None else None,
        "measured_turns": measured_turns,
        "unavailable_turns": int(row.unavailable_turns or 0),
        "api_equivalent_usd_micros": (
            int(row.api_equivalent_usd_micros)
            if row.api_equivalent_usd_micros is not None
            else None
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
    )


def budget_state(limit_tokens: Optional[int], used_tokens: Optional[int]) -> Dict[str, Any]:
    used = used_tokens or 0
    return {
        "limit_tokens": limit_tokens,
        "used_tokens": used,
        "remaining_tokens": (
            max(0, limit_tokens - used) if limit_tokens is not None else None
        ),
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
        }
        for row in recent_rows
    ]
    latest_allowance = next(
        (row.allowance for row in recent_rows if isinstance(row.allowance, dict)), None
    )
    cost = project_summary["api_equivalent_usd_micros"]
    total = project_summary["total_tokens"]
    if latest_allowance is not None:
        preferred_display = {
            "kind": "allowance",
            "label": "Rate-limit allowance",
            "allowance": latest_allowance,
        }
    elif cost is not None:
        preferred_display = {
            "kind": "api_equivalent",
            "label": "API-equivalent estimate",
            "usd_micros": cost,
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
