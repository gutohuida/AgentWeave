"""a build remembers its reopenings -- builds.reopenings

Revision ID: 0159
Revises: 0158
Create Date: 2026-11-02 00:00:00.000000

`every-task-comes-with-a-recommended-builder-and-checker` (FR-8, FR-15). A follow-up filed against a
finished build reopens it, and the record shows that, with what the Overview warning names.

Additive and nullable, on live data: no existing row changes, and null reads as never reopened.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0152` does). A build
reopened before it keeps running, with no record of the reopening and no warning.

Guarded for a database without the table (an upgrade from an early revision) and for a column already
present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0159"
down_revision = "0158"
branch_labels = None
depends_on = None


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("builds"):
        return set()
    return {column["name"] for column in inspector.get_columns("builds")}


def upgrade() -> None:
    columns = _columns()
    if columns and "reopenings" not in columns:
        op.add_column("builds", sa.Column("reopenings", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "reopenings" in _columns():
        op.drop_column("builds", "reopenings")
