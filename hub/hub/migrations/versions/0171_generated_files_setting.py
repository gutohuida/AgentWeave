"""generated files are rebuilt when work lands -- projects.generated_files

Revision ID: 0171
Revises: 0170
Create Date: 2026-11-08 12:00:00.000000

`generated-files-are-rebuilt-when-work-lands-instead-of-sending-it-back`, task `setting`, FR-1.
Adds the nullable JSON column `projects.generated_files` (`{paths, command, timeout_seconds}`).

Runs on the operator's :8000 data at its next restart. No existing row is read or rewritten: every
existing project reads null, which is no generated files and today's behaviour (FR-2). The
downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as 0161 does), losing only the
operator's saved setting.

Guarded for a database without the table and for a column already present (a database built by
`create_all`) or already absent on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0171"
down_revision = "0170"
branch_labels = None
depends_on = None


def _columns(conn) -> set:
    if "projects" not in set(sa.inspect(conn).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(conn).get_columns("projects")}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if columns and "generated_files" not in columns:
        op.add_column("projects", sa.Column("generated_files", sa.JSON(), nullable=True))


def downgrade() -> None:
    if "generated_files" in _columns(op.get_bind()):
        op.execute(sa.text("ALTER TABLE projects DROP COLUMN generated_files"))
