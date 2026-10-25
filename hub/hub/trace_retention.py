"""Trace spans are kept for a bounded window (`the-database-stays-fast-as-history-grows`, D4).

Measured on the operator's database: `trace_spans` grew about 10.8MB a day and was the largest
table after four days, with nothing pruning it. The Hub now deletes, for each project, every span
that started before the project's retention window (`trace_settings.retention_days`, else
`DEFAULT_RETENTION_DAYS`), from its maintenance pass (`db_maintenance`), never on a request's path.

A span is judged by its own `start_time`, not its trace's start: an `aw.deliver` span can start
hours before the trace it is filed under (measured: up to ~18h), and "every span newer than the
window is still present" holds only span by span.

retention-no-stall: the first sweep on the operator's database removes tens of thousands of spans.
It is never one statement. Each batch reads at most `BATCH_SIZE` ids (a read: under WAL it takes no
lock a reader waits on), deletes exactly those in a short transaction, commits, and yields for
`PAUSE_SECONDS` so other writers and the event loop get in between batches.

Agent outputs, events, messages and runs are the operator's history and are not pruned here. Freed
pages are reused by SQLite; returning them to the disk (VACUUM) is the operator's act, with the Hub
stopped, because it rewrites the whole file under an exclusive lock.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from sqlalchemy import delete, select

from .db.engine import async_session_factory
from .db.models import TraceSettings, TraceSpan

logger = logging.getLogger(__name__)

#: The window a project that never chose one keeps (decided 2026-10-25 for the first build; about
#: 150MB of traces at the measured 10.8MB a day). Changing it reaches every project whose
#: `retention_days` is NULL.
DEFAULT_RETENTION_DAYS = 14
MIN_RETENTION_DAYS = 1
MAX_RETENTION_DAYS = 3650

#: Spans per delete transaction. A span carries up to tens of KB of attributes; 500 keeps one
#: batch's write lock to a few milliseconds on the operator's data.
BATCH_SIZE = 500
PAUSE_SECONDS = 0.05


def effective_days(row: Optional[TraceSettings]) -> int:
    """The window a project keeps: its own, else the Hub's default."""
    if row is not None and row.retention_days:
        return int(row.retention_days)
    return DEFAULT_RETENTION_DAYS


async def windows() -> Dict[str, int]:
    """Every project that has spans or settings, with the window it keeps."""
    async with async_session_factory() as db:
        # A loop, not `dict(result)`: a Result exposes `.keys()`, so dict() takes the mapping path
        # (the same trap `api/v1/agents.py` names at its active-task counts).
        chosen: Dict[str, Optional[int]] = {}
        rows = await db.execute(select(TraceSettings.project_id, TraceSettings.retention_days))
        for project_id, days in rows:
            chosen[project_id] = days
        with_spans = (await db.execute(select(TraceSpan.project_id).distinct())).scalars().all()
    return {
        project_id: int(chosen.get(project_id) or DEFAULT_RETENTION_DAYS)
        for project_id in set(with_spans) | set(chosen)
    }


async def sweep_project(project_id: str, cutoff: datetime) -> int:
    """Delete every span of *project_id* that started before *cutoff*, a batch at a time."""
    deleted = 0
    while True:
        async with async_session_factory() as db:
            ids = (
                (
                    await db.execute(
                        select(TraceSpan.span_id)
                        .where(TraceSpan.project_id == project_id, TraceSpan.start_time < cutoff)
                        .limit(BATCH_SIZE)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                return deleted
            await db.execute(
                delete(TraceSpan)
                .where(TraceSpan.span_id.in_(ids))
                .execution_options(synchronize_session=False)
            )
            await db.commit()
        deleted += len(ids)
        await asyncio.sleep(PAUSE_SECONDS)


async def sweep(now: Optional[datetime] = None) -> Dict[str, dict]:
    """One retention pass over every project. Returns, per project, its window, cutoff and the
    number of spans deleted."""
    now = now or datetime.now(timezone.utc)
    report: Dict[str, dict] = {}
    for project_id, days in sorted((await windows()).items()):
        cutoff = now - timedelta(days=days)
        removed = await sweep_project(project_id, cutoff)
        report[project_id] = {"window_days": days, "cutoff": cutoff, "deleted": removed}
        if removed:
            logger.info(
                "Trace retention: removed %d span(s) of %s older than %d days",
                removed,
                project_id,
                days,
            )
    return report
