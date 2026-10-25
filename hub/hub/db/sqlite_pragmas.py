"""The journal every SQLite connection the Hub opens runs in (`the-database-stays-fast-as-history-grows`).

D1: WAL with `synchronous=FULL` and a bounded WAL file. Measured on a 97MB copy of the operator's
database: a commit costs 0.76ms at p50 instead of the rollback journal's 10.8ms, and with a writer
committing flat out four readers of `/agents` saw p90 398ms instead of 3,493ms -- under a rollback
journal one writer's commit locks every reader out, under WAL readers keep reading the last
committed snapshot. `FULL`, not `NORMAL`: in WAL `NORMAL` may lose the last commits on power loss
and showed a 1.2s checkpoint stall; `FULL` keeps an acknowledged commit durable.

D2: when WAL cannot be set -- a database on a network share, a medium without shared memory, a
URI opened `nolock` -- SQLite answers `PRAGMA journal_mode=WAL` with the journal it keeps (or
raises). The connection is used anyway: an unusable Hub is worse than a slower one, and the
startup line (`hub/hub/main.py`) names the journal the database actually runs in.

`journal_mode` is a property of the file, so the first connection converts a rollback-journal
database and every later one finds it already WAL. `synchronous` and `journal_size_limit` are
per connection, which is why this runs on every connect rather than once.

Under WAL a backup is SQLite's backup API or `VACUUM INTO`, never a copy of the `.db` file: the
newest commits may still be in `agentweave.db-wal` (D3, `.claude/reference/hubs.md`).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

#: The size the WAL file is truncated back to after a checkpoint that resets it. SQLite's default
#: (-1) never shrinks it, so one burst would leave its high-water mark on disk for good.
JOURNAL_SIZE_LIMIT_BYTES = 64 * 1024 * 1024


def apply_pragmas(dbapi_connection: Any) -> Optional[str]:
    """Ask for WAL, full sync and the WAL bound on one fresh connection; return the journal mode
    SQLite answered with (None if the request raised). Never raises for a refused WAL (D2)."""
    cursor = dbapi_connection.cursor()
    try:
        mode: Optional[str] = None
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            row = cursor.fetchone()
            mode = str(row[0]).lower() if row else None
        except Exception as exc:  # noqa: BLE001 -- D2: a refused WAL leaves the journal it has
            logger.debug("PRAGMA journal_mode=WAL was refused: %s", exc)
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute(f"PRAGMA journal_size_limit={JOURNAL_SIZE_LIMIT_BYTES}")
        return mode
    finally:
        cursor.close()


def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:
    apply_pragmas(dbapi_connection)


def install(sync_engine: Engine) -> None:
    """Run `apply_pragmas` on every connection *sync_engine* opens. No-op for other databases."""
    if sync_engine.dialect.name != "sqlite":
        return
    if not event.contains(sync_engine, "connect", _on_connect):
        event.listen(sync_engine, "connect", _on_connect)
