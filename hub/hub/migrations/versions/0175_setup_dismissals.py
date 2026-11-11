"""A project's dismissed set-up items -- setup_dismissals

Revision ID: 0175
Revises: 0174
Create Date: 2026-11-11 14:00:00.000000

`a-project-says-what-it-still-needs`, task `setup-state`, FR-3. The operator can dismiss a
project's repository item ('Not for this project'); the dismissal is a row here, keyed by project
and item, and showing the item again deletes it.

Runs on the operator's :8000 data at its next restart. A new table only: no existing row is read or
rewritten, and a project with no row has nothing dismissed, which is today's behaviour. The
downgrade drops the table, losing only the dismissals.

Guarded for a database without `projects` (an upgrade from an early revision) and for the table
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0175"
down_revision = "0174"
branch_labels = None
depends_on = None


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    tables = _tables(op.get_bind())
    if "setup_dismissals" in tables or "projects" not in tables:
        return
    op.create_table(
        "setup_dismissals",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("item", sa.String(32), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "item", name="pk_setup_dismissals"),
    )


def downgrade() -> None:
    if "setup_dismissals" in _tables(op.get_bind()):
        op.drop_table("setup_dismissals")
