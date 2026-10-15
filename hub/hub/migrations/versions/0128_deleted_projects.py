"""project ids this database deleted -- deleted_projects

Revision ID: 0128
Revises: 0127
Create Date: 2026-10-15 00:00:00.000000

`a-deleted-project-stays-deleted` (Tier 2, F609, decision fix-D1). One row per project id this
database deletes, so reopening that project's folder registers a new project instead of adopting
the marker's id. Nothing existing is copied or changed: projects deleted before this revision are
not known, and their folders are still adopted under their old id. The downgrade drops the table;
a reopen then adopts a deleted id again, which is the behaviour before this revision.

Guarded for a table already present (a database built by `create_all` from these models and
stamped at an earlier revision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "deleted_projects" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "deleted_projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    if "deleted_projects" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("deleted_projects")
