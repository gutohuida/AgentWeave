"""a build remembers the operator dismissed it -- builds.attention_dismissed

Revision ID: 0190
Revises: 0189
Create Date: 2026-11-20 18:00:00.000000

`profiles-threads-and-builds-everywhere` (FR-3, D3). The operator dismisses a build that needs them
from the sidebar; the dismissal stores `{"at", "fingerprint"}`, the needs it was made against, so a
new stall, a new question or another stop brings the build back.

Runs on the operator's :8000 data at its next restart. Additive and nullable: no existing row
changes, and null reads as never dismissed.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0159` does); every
build needing the operator is then listed again. Guarded for a database without the table (an
upgrade from an early revision) and for a column already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0190"
down_revision = "0189"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("builds"):
        return set()
    return {column["name"] for column in inspector.get_columns("builds")}


def upgrade() -> None:
    columns = _columns()
    if columns and "attention_dismissed" not in columns:
        op.add_column("builds", sa.Column("attention_dismissed", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "attention_dismissed" in _columns():
        op.drop_column("builds", "attention_dismissed")
