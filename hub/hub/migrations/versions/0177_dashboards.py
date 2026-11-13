"""A project's saved dashboards -- dashboards

Revision ID: 0177
Revises: 0176
Create Date: 2026-11-13 12:00:00.000000

`ask-any-agent-for-a-dashboard-and-get-one-that-stays`, task `dashboard-store-and-tools`, FR-9. An
agent saves a dashboard (a name, the question it answers and its panels' queries and chart kinds)
and the project's Dashboards screen lists and runs it.

Runs on the operator's :8000 data at its next restart. A new table only: no existing row is read or
rewritten. The downgrade drops the table, losing only saved dashboards.

Guarded for a database without `projects` (an upgrade from an early revision) and for the table
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0177"
down_revision = "0176"
branch_labels = None
depends_on = None


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    tables = _tables(op.get_bind())
    if "dashboards" in tables or "projects" not in tables:
        return
    op.create_table(
        "dashboards",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("panels", sa.JSON(), nullable=False),
        sa.Column("author", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "name", name="uq_dashboards_project_name"),
    )
    op.create_index("ix_dashboards_project_id", "dashboards", ["project_id"])


def downgrade() -> None:
    if "dashboards" in _tables(op.get_bind()):
        op.drop_index("ix_dashboards_project_id", table_name="dashboards")
        op.drop_table("dashboards")
