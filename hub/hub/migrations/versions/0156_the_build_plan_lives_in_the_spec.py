"""the build plan lives in the spec -- builds.people

Revision ID: 0156
Revises: 0155
Create Date: 2026-10-29 00:00:00.000000

`the-build-plan-lives-in-the-spec-and-every-task-goes-to-its-people` (Tier 2). A build records the
people the operator chose for it: the default builder, the default checker, and each task's builder
and checker (`{"builder", "checker", "tasks": {key: {"builder", "checker"}}}`), so a build that has
left the spec document (only the running and the most recent ended one are kept there, FR-6) still
says who it was given to.

Additive only: one nullable JSON column. No backfill and no existing row is read or rewritten: a
build recorded before this reads no people of its own, and its view falls back to its tasks'
builders, which is what it recorded.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0152` does).

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "builds" not in set(inspector.get_table_names()):
        return
    if "people" not in {c["name"] for c in inspector.get_columns("builds")}:
        op.add_column("builds", sa.Column("people", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "builds" not in set(inspector.get_table_names()):
        return
    if "people" in {c["name"] for c in inspector.get_columns("builds")}:
        op.execute(sa.text("ALTER TABLE builds DROP COLUMN people"))
