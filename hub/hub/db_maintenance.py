"""The Hub's database maintenance pass (`the-database-stays-fast-as-history-grows`, D4/D5).

Started in `main.lifespan` and cancelled with it. Each pass, off every request's path:

1. the trace retention sweep (`trace_retention.sweep`), batched so it never stalls a reader;
2. at least once a day, a refresh of the query planner's statistics. Measured: `ANALYZE` had never
   run on the operator's database (no `sqlite_stat1`), so the planner chose indexes blind.
   `analysis_limit` bounds the work to a sample per index, a few milliseconds on their data.

The first pass waits `FIRST_PASS_DELAY_SECONDS`, so it does not join the startup burst of
reconciliation and re-drained queues. Space the sweep frees is reused by SQLite; no VACUUM runs here
(it rewrites the whole file under an exclusive lock -- the operator's act, with the Hub stopped).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from . import trace_retention
from .db.engine import engine

logger = logging.getLogger(__name__)

FIRST_PASS_DELAY_SECONDS = 30.0
PASS_INTERVAL_SECONDS = 3600.0
STATISTICS_INTERVAL_SECONDS = 24 * 3600.0
#: Rows sampled per index by ANALYZE (SQLite's own recommendation for periodic runs is 100-1000).
ANALYSIS_LIMIT = 1000


async def refresh_statistics() -> None:
    """Refresh the query planner's statistics (`sqlite_stat1`). SQLite only."""
    if engine.dialect.name != "sqlite":
        return
    async with engine.connect() as conn:
        await conn.exec_driver_sql(f"PRAGMA analysis_limit={ANALYSIS_LIMIT}")
        await conn.exec_driver_sql("ANALYZE")
        await conn.commit()


async def run_pass(*, statistics_due: bool) -> None:
    """One maintenance pass. Each step's failure is logged and does not stop the other."""
    try:
        await trace_retention.sweep()
    except Exception as exc:  # noqa: BLE001 -- the next pass tries again
        logger.warning("Trace retention sweep failed (retried next pass): %s", exc)
    if statistics_due:
        try:
            await refresh_statistics()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Refreshing the database statistics failed (retried next pass): %s", exc)


async def maintain_forever() -> None:
    await asyncio.sleep(FIRST_PASS_DELAY_SECONDS)
    last_statistics: Optional[float] = None
    while True:
        due = (
            last_statistics is None
            or time.monotonic() - last_statistics >= STATISTICS_INTERVAL_SECONDS
        )
        await run_pass(statistics_due=due)
        if due:
            last_statistics = time.monotonic()
        await asyncio.sleep(PASS_INTERVAL_SECONDS)
