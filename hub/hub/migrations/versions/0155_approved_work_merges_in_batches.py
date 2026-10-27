"""approved work merges in batches -- task_landings, landing_batches; task_integrations.batch_id /
override_reason

Revision ID: 0155
Revises: 0152
Create Date: 2026-10-27 00:00:00.000000

`approved-work-merges-in-batches` (slice E, Tier 2). Approval queues the task's work for landing
(`task_landings`, one row per landing attempt, its merge targets frozen at approval) and the Hub
lands queued work in batches checked once (`landing_batches`). An integration record names the batch
that merged it and the override it landed under, where one did.

Numbered 0155 with `down_revision` 0152 because slice D2 builds beside it and takes 0153/0154; the
orchestrator relinks the chain at merge.

Additive only: two new tables and two nullable columns on `task_integrations`. No backfill and no
existing row is read or rewritten: an integration recorded before this reads no batch and no
override, which is true of it.

Rollback: the downgrade drops both tables and both columns (plain `DROP COLUMN`, SQLite 3.35+, as
`0147` and `0152` do). A task queued at that moment stays approved with no merged integration, shown
"verified, not integrated", and the existing Try again lands it.

Guarded for a database without the tables (an upgrade from an early revision) and for tables or
columns already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0155"
down_revision = "0152"
branch_labels = None
depends_on = None

_INTEGRATION_COLUMNS = (
    ("batch_id", sa.String(64)),
    ("override_reason", sa.Text()),
)


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set:
    return {i["name"] for i in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "task_landings" not in tables and {"projects", "tasks"} <= tables:
        op.create_table(
            "task_landings",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column("batch_id", sa.String(64), nullable=True),
            sa.Column("state", sa.String(16), nullable=False, server_default="queued"),
            sa.Column("kind", sa.String(16), nullable=False, server_default="approval"),
            sa.Column("targets", sa.JSON(), nullable=True),
            sa.Column("order_key", sa.Float(), nullable=False),
            sa.Column("unchecked", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("override_reason", sa.Text(), nullable=True),
            sa.Column("override_by", sa.String(16), nullable=True),
            sa.Column("actor_kind", sa.String(16), nullable=False, server_default="operator"),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("waits_on", sa.String(64), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("landed_sha", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
    if "task_landings" in _tables(conn):
        present = _indexes(conn, "task_landings")
        if "ix_task_landings_project_state" not in present:
            op.create_index(
                "ix_task_landings_project_state",
                "task_landings",
                ["project_id", "state", "order_key"],
            )
        if "ix_task_landings_task" not in present:
            op.create_index("ix_task_landings_task", "task_landings", ["task_id", "created_at"])
    if "landing_batches" not in tables and "projects" in tables:
        op.create_table(
            "landing_batches",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("base_sha", sa.String(64), nullable=False),
            sa.Column("state", sa.String(16), nullable=False, server_default="checking"),
            sa.Column("task_ids", sa.JSON(), nullable=False),
            sa.Column("prefixes", sa.JSON(), nullable=False),
            sa.Column("merged_sha", sa.String(64), nullable=True),
            sa.Column("check_run_id", sa.String(64), nullable=True),
            sa.Column("results", sa.JSON(), nullable=False),
            sa.Column("narrowing", sa.JSON(), nullable=False),
            sa.Column("override_reason", sa.Text(), nullable=True),
            sa.Column("override_by", sa.String(16), nullable=True),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
    if "landing_batches" in _tables(conn):
        if "ix_landing_batches_project" not in _indexes(conn, "landing_batches"):
            op.create_index(
                "ix_landing_batches_project", "landing_batches", ["project_id", "created_at"]
            )
    if "task_integrations" in tables:
        have = _columns(conn, "task_integrations")
        for name, kind in _INTEGRATION_COLUMNS:
            if name not in have:
                op.add_column("task_integrations", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "task_integrations" in tables:
        have = _columns(conn, "task_integrations")
        for name, _ in _INTEGRATION_COLUMNS:
            if name in have:
                op.execute(sa.text(f"ALTER TABLE task_integrations DROP COLUMN {name}"))
    for table in ("task_landings", "landing_batches"):
        if table in tables:
            for name in _indexes(conn, table):
                op.drop_index(name, table_name=table)
            op.drop_table(table)
