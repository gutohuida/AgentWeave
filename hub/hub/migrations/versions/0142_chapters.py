"""chapter versions, and a job's automatic choice

Revision ID: 0142
Revises: 0141
Create Date: 2026-10-23 23:00:00.000000

`the-thread-reads-as-chapters-the-manager-writes` (store task). Two additive moves, nothing read,
copied or backfilled:

1. A new `chapter_versions` table: one append-only row per saved state of a project's chapters.
2. `manager_jobs.automatic`, default true: whether a job fires on its own trigger or only on the
   operator's button. Every existing row keeps the behaviour it has, which is firing on its trigger.

Both are guarded for being present already (a database built by `create_all` and stamped at an
earlier revision). Rollback: the downgrade drops the table and the column, losing the chapter
versions and the choice only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "projects" not in tables:
        return
    if "chapter_versions" not in tables:
        op.create_table(
            "chapter_versions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("author", sa.String(64), nullable=False),
            sa.Column("asked_by", sa.String(64), nullable=True),
            sa.Column("asked_for", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("chapters", sa.JSON(), nullable=False),
            sa.Column("known_knots", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_chapter_versions_project_version",
            "chapter_versions",
            ["project_id", "version"],
            unique=True,
        )
    if "manager_jobs" in tables:
        columns = {c["name"] for c in inspector.get_columns("manager_jobs")}
        if "automatic" not in columns:
            with op.batch_alter_table("manager_jobs") as batch_op:
                batch_op.add_column(
                    sa.Column("automatic", sa.Boolean(), nullable=False, server_default="1")
                )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "manager_jobs" in tables:
        columns = {c["name"] for c in inspector.get_columns("manager_jobs")}
        if "automatic" in columns:
            with op.batch_alter_table("manager_jobs") as batch_op:
                batch_op.drop_column("automatic")
    if "chapter_versions" in tables:
        op.drop_index("ix_chapter_versions_project_version", table_name="chapter_versions")
        op.drop_table("chapter_versions")
