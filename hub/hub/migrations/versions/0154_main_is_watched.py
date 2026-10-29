"""main is watched -- task_integrations.merged_sha, projects.main_tip_seen, main_notices

Revision ID: 0154
Revises: 0153
Create Date: 2026-10-27 00:00:00.000000

`amendments-main-watch-and-the-next-slice` (slice D2, Tier 2), task `main-watch`. The Hub records
the merge commit each integration makes (`merged_sha`), so the main watch can tell its own moves of
main from anyone else's by sha; it persists the tip it last accounted for on the project
(`main_tip_seen`), so a restart neither loses nor re-raises a move; and a move it raises opens, or
joins, the project's one open `main_notices` row until the operator marks it seen.

Two nullable columns and a new table: nothing existing is read or rewritten. A null
`main_tip_seen` makes the first look record the tip and raise nothing (on the operator's database
both projects with a main branch start there). Integrations recorded before this carry no merge
sha; only moves after the first look are classified, so none of them is read.

Downgrade drops the table and the two columns (plain `DROP COLUMN`, SQLite 3.35+, as 0152 does),
losing the notices and the recorded tips, and nothing else.

Guarded for a database without the tables (an upgrade from an early revision) and for columns or a
table already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0154"
down_revision = "0153"
branch_labels = None
depends_on = None


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set:
    return {i["name"] for i in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "task_integrations" in tables and "merged_sha" not in _columns(conn, "task_integrations"):
        op.add_column("task_integrations", sa.Column("merged_sha", sa.String(64), nullable=True))
    if "projects" in tables and "main_tip_seen" not in _columns(conn, "projects"):
        op.add_column("projects", sa.Column("main_tip_seen", sa.String(64), nullable=True))
    if "main_notices" not in tables and "projects" in tables:
        op.create_table(
            "main_notices",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("branch", sa.String(255), nullable=False),
            sa.Column("old_tip", sa.String(64), nullable=False),
            sa.Column("new_tip", sa.String(64), nullable=False),
            sa.Column("commits", sa.JSON(), nullable=False),
            sa.Column("rewrite", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("seen_at", sa.DateTime(), nullable=True),
            sa.Column("seen_by", sa.String(128), nullable=True),
        )
    if "main_notices" in _tables(conn) and "ix_main_notices_project" not in _indexes(
        conn, "main_notices"
    ):
        op.create_index("ix_main_notices_project", "main_notices", ["project_id", "seen_at"])


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "main_notices" in tables:
        for name in _indexes(conn, "main_notices"):
            op.drop_index(name, table_name="main_notices")
        op.drop_table("main_notices")
    if "projects" in tables and "main_tip_seen" in _columns(conn, "projects"):
        op.execute(sa.text("ALTER TABLE projects DROP COLUMN main_tip_seen"))
    if "task_integrations" in tables and "merged_sha" in _columns(conn, "task_integrations"):
        op.execute(sa.text("ALTER TABLE task_integrations DROP COLUMN merged_sha"))
