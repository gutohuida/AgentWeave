"""approval runs the project's checks -- projects.checks, task_check_runs, override_reason

Revision ID: 0119
Revises: 0118
Create Date: 2026-10-06 00:00:00.000000

`approval-runs-the-projects-checks` (Tier 2). Additive only:

- `projects.checks`: nullable JSON, the operator's ordered check list. Null means no checks, which
  is every project stored before this change, so approval behaves exactly as it did.
- `task_check_runs`: one row per run of a project's checks on a task's would-merge commit.
- `task_transitions.override_reason`: nullable; why the operator approved over failing checks.

Guarded for missing tables, as `0033`/`0034` do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None

_STATES = ("running", "passed", "failed", "error", "interrupted")


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "projects" in tables and "checks" not in _columns(conn, "projects"):
        with op.batch_alter_table("projects", recreate="never") as batch_op:
            batch_op.add_column(sa.Column("checks", sa.JSON, nullable=True))
    if "task_transitions" in tables and "override_reason" not in _columns(conn, "task_transitions"):
        with op.batch_alter_table("task_transitions", recreate="never") as batch_op:
            batch_op.add_column(sa.Column("override_reason", sa.Text, nullable=True))
    if {"projects", "tasks"} <= tables and "task_check_runs" not in tables:
        op.create_table(
            "task_check_runs",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("task_id", sa.String(64), sa.ForeignKey("tasks.id"), nullable=False),
            sa.Column("main_sha", sa.String(64), nullable=False),
            sa.Column("target_shas", sa.JSON, nullable=False),
            sa.Column("merged_sha", sa.String(64), nullable=True),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("results", sa.JSON, nullable=False),
            sa.Column("error", sa.Text, nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "state IN ('" + "', '".join(_STATES) + "')", name="ck_task_check_runs_state"
            ),
        )
        op.create_index("ix_task_check_runs_task", "task_check_runs", ["task_id", "started_at"])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "task_check_runs" in tables:
        op.drop_index("ix_task_check_runs_task", table_name="task_check_runs")
        op.drop_table("task_check_runs")
    if "task_transitions" in tables and "override_reason" in _columns(conn, "task_transitions"):
        with op.batch_alter_table("task_transitions", recreate="never") as batch_op:
            batch_op.drop_column("override_reason")
    if "projects" in tables and "checks" in _columns(conn, "projects"):
        with op.batch_alter_table("projects", recreate="never") as batch_op:
            batch_op.drop_column("checks")
