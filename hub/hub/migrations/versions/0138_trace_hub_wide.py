"""everything the Hub does is in a trace -- trace_settings.record_reads, ix_trace_spans_project_operation

Revision ID: 0138
Revises: 0137
Create Date: 2026-10-20 00:00:00.000000

`everything-the-hub-does-is-in-a-trace` (Tier 2, trace-hub-wide, trace-D4). One nullable-safe
column and one index; no existing row is read or rewritten, and nothing is backfilled.

* `trace_settings.record_reads` -- whether the operator's routine GET/HEAD requests (the app's
  polling) and the SSE stream are recorded as request spans too. Server default false: every
  existing project keeps skipping them, which is the default trace-D4 chose.
* `ix_trace_spans_project_operation` (project_id, operation, start_time) -- listing a project's
  traces of one kind (`GET /traces?operation=`) once requests, events and background work share
  the table with runs.

The downgrade drops the index and the column (a plain `DROP COLUMN`, SQLite 3.35+); traces already
written stay valid, and a project then records no reads, as before.

Guarded for a database without the tables (an upgrade from an early revision), and for a column or
index already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None

_INDEX = "ix_trace_spans_project_operation"


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = _tables()
    if "trace_settings" in tables and "record_reads" not in _columns("trace_settings"):
        op.add_column(
            "trace_settings",
            sa.Column("record_reads", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "trace_spans" in tables and _INDEX not in _indexes("trace_spans"):
        op.create_index(_INDEX, "trace_spans", ["project_id", "operation", "start_time"])


def downgrade() -> None:
    tables = _tables()
    if "trace_spans" in tables and _INDEX in _indexes("trace_spans"):
        op.drop_index(_INDEX, table_name="trace_spans")
    if "trace_settings" in tables and "record_reads" in _columns("trace_settings"):
        op.execute(sa.text("ALTER TABLE trace_settings DROP COLUMN record_reads"))
