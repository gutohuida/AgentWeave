"""the Hub may override checks is removed -- drop projects.checks_auto_override

Revision ID: 0167
Revises: 0166
Create Date: 2026-11-06 08:00:00.000000

`failures-already-known-are-on-a-list-not-re-argued` (Tier 2), task `ui`, FR-15. The setting 0151
added governed the shared-failure automatic override and fix-task filing; task `gates` removed the
first and every read of the setting, and task `list` files a fix task for every entry whatever it
said, so the column governs nothing. The project settings route stopped accepting the field in the
same task, and the settings page lost its switch, so no save from the app sends it.

Runs on the operator's :8000 data at its next restart. Only the one column is dropped (plain `DROP
COLUMN`, SQLite 3.35+, as 0151's downgrade does); no other row or column is read or changed. The
downgrade adds it back with its old default, on, for every project: the value each project had
unless the operator turned it off, which is the one thing a rollback loses.

Guarded for a database without the table (an upgrade from an early revision) and for the column
already absent (a database built by `create_all`) or already present on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if "projects" in _tables(conn) and "checks_auto_override" in _columns(conn, "projects"):
        op.execute(sa.text("ALTER TABLE projects DROP COLUMN checks_auto_override"))


def downgrade() -> None:
    conn = op.get_bind()
    if "projects" in _tables(conn) and "checks_auto_override" not in _columns(conn, "projects"):
        op.add_column(
            "projects",
            sa.Column(
                "checks_auto_override", sa.Boolean(), nullable=False, server_default=sa.text("1")
            ),
        )
