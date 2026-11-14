"""A dashboard's version, last editor and kept earlier version -- dashboards_edit_history

Revision ID: 0178
Revises: 0177
Create Date: 2026-11-14 02:00:00.000000

`change-a-dashboard-by-asking`, task `edit-store-and-tools`, FR-5, FR-6, FR-9. An agent edits a
saved dashboard in place against the version it read; the Hub keeps the version each write replaced
so one undo restores it.

Runs on the operator's :8000 data at its next restart. Adds three columns to `dashboards` with
defaults (every existing dashboard becomes version 1, never edited) and creates one table; no
existing row is deleted or rewritten. The downgrade drops the table and the columns, losing only
edit history, never a dashboard's name, description or panels.

Guarded for a database without `dashboards` (an upgrade from an early revision) and for the columns
and table already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0178"
down_revision = "0177"
branch_labels = None
depends_on = None

_COLUMNS = ("version", "edited_by", "edited_at")


def _state(conn) -> tuple:
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    columns = (
        {column["name"] for column in inspector.get_columns("dashboards")}
        if "dashboards" in tables
        else set()
    )
    return tables, columns


def upgrade() -> None:
    tables, columns = _state(op.get_bind())
    if "dashboards" not in tables:
        return
    if "version" not in columns:
        op.add_column(
            "dashboards",
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
    if "edited_by" not in columns:
        op.add_column("dashboards", sa.Column("edited_by", sa.String(32), nullable=True))
    if "edited_at" not in columns:
        op.add_column("dashboards", sa.Column("edited_at", sa.DateTime(), nullable=True))
    if "dashboard_versions" not in tables:
        op.create_table(
            "dashboard_versions",
            sa.Column("dashboard_id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("panels", sa.JSON(), nullable=False),
            sa.Column("edited_by", sa.String(32), nullable=True),
            sa.Column("edited_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_dashboard_versions_project_id", "dashboard_versions", ["project_id"])


def downgrade() -> None:
    tables, columns = _state(op.get_bind())
    if "dashboard_versions" in tables:
        op.drop_index("ix_dashboard_versions_project_id", table_name="dashboard_versions")
        op.drop_table("dashboard_versions")
    for column in _COLUMNS:
        if column in columns:
            op.execute(sa.text(f"ALTER TABLE dashboards DROP COLUMN {column}"))
