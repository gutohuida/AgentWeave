"""Durable, idempotent recording for normalized per-turn usage."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import TurnUsage
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
