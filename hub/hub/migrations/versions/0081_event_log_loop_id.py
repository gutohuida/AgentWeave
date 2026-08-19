"""a per-loop history home for event_logs

Revision ID: 0081
Revises: 0080
Create Date: 2026-08-19 06:45:00.000000

`2026-08-18-a-loop-writes-its-own-queue` design D13, task A4.1. `event_logs` is indexed by
`project_id` and `agent`, not by loop — retrieving one loop's history meant scanning unindexed
JSON. One additive nullable column, `event_logs.loop_id`, plus its own composite index alongside
`ix_event_logs_project_ts`, same "no `batch_alter_table` recreate needed" shape as `0075`/`0077`/
`0078`/`0079`/`0080`. NULL for every event that is not about a specific loop — most rows; no
backfill, matching every prior additive column in this series (there is nothing to derive a past
row's loop from without re-parsing its JSON `data`, exactly the scan this column exists to avoid
for future rows).

Guarded for a missing table, matching `0071`/`0073`/`0075`/`0077`/`0078`/`0079`/`0080`'s own
precedent for an upgrade starting from an early revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def _tables(conn: sa.engine.Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn: sa.engine.Connection, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def _indexes(conn: sa.engine.Connection, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(table) if index["name"]}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "event_logs" in present:
        columns = _columns(conn, "event_logs")
        if "loop_id" not in columns:
            op.add_column("event_logs", sa.Column("loop_id", sa.String(64), nullable=True))
        indexes = _indexes(conn, "event_logs")
        if "ix_event_logs_loop_ts" not in indexes:
            op.create_index(
                "ix_event_logs_loop_ts", "event_logs", ["loop_id", "timestamp"], unique=False
            )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "event_logs" in present:
        indexes = _indexes(conn, "event_logs")
        if "ix_event_logs_loop_ts" in indexes:
            op.drop_index("ix_event_logs_loop_ts", table_name="event_logs")
        columns = _columns(conn, "event_logs")
        if "loop_id" in columns:
            op.drop_column("event_logs", "loop_id")
