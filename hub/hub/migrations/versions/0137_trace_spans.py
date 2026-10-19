"""traces of everything the Hub and its agents do -- trace_spans, trace_settings

Revision ID: 0137
Revises: 0134
Create Date: 2026-10-19 00:00:00.000000

`a-run-is-a-trace-you-can-export` (Tier 2, trace-1019). Two new tables and their indexes; no
existing table is read, changed or rebuilt, and nothing is backfilled: runs that ended before this
revision have no trace, which is true (nobody recorded one).

* `trace_spans` -- one row per OpenTelemetry-shaped span, written only by `hub/hub/traces.py`.
  Kept forever unless the operator clears it (trace-D3), so it grows with every run: each run's
  prompt and its (already bounded) output are stored a second time, as span content.
* `trace_settings` -- a project's OTLP push choice. No row means nothing is pushed.

The downgrade drops both tables, losing only the traces and the push settings.

Guarded for tables already present (a database built by `create_all` from these models and stamped
at an earlier revision). `down_revision` is this branch's head; it is re-chained at merge.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0137"
down_revision = "0135"
branch_labels = None
depends_on = None


def _tables() -> set:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _tables()
    if "trace_spans" not in tables:
        op.create_table(
            "trace_spans",
            sa.Column("span_id", sa.String(16), primary_key=True),
            sa.Column("trace_id", sa.String(32), nullable=False),
            sa.Column("parent_span_id", sa.String(16), nullable=True),
            sa.Column("project_id", sa.String(64), nullable=False),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("name", sa.String(256), nullable=False),
            sa.Column("operation", sa.String(32), nullable=False),
            sa.Column("status", sa.String(8), nullable=False, server_default="unset"),
            sa.Column("status_message", sa.Text(), nullable=True),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("trace_started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("attributes", sa.JSON(), nullable=False),
            sa.Column("events", sa.JSON(), nullable=False),
            sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint("status IN ('unset', 'ok', 'error')", name="ck_trace_spans_status"),
        )
        op.create_index("ix_trace_spans_trace_start", "trace_spans", ["trace_id", "start_time"])
        op.create_index(
            "ix_trace_spans_project_trace_started",
            "trace_spans",
            ["project_id", "trace_started_at"],
        )
        op.create_index(
            "ix_trace_spans_project_roots",
            "trace_spans",
            ["project_id", "parent_span_id", "start_time"],
        )
        op.create_index("ix_trace_spans_run", "trace_spans", ["run_id"])
        op.create_index(
            "ix_trace_spans_outbox", "trace_spans", ["project_id", "ended", "exported_at"]
        )
    if "trace_settings" not in tables:
        op.create_table(
            "trace_settings",
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
            sa.Column("otlp_endpoint", sa.String(1024), nullable=True),
            sa.Column("otlp_headers", sa.JSON(), nullable=False),
            sa.Column("export_enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_export_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("exported_spans", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    tables = _tables()
    if "trace_settings" in tables:
        op.drop_table("trace_settings")
    if "trace_spans" in tables:
        op.drop_table("trace_spans")
