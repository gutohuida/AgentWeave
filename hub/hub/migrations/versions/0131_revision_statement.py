"""how a requirement changed -- spec_requirement_revisions.statement

Revision ID: 0131
Revises: 0130
Create Date: 2026-10-17 00:00:00.000000

`how-a-requirement-changed-and-what-proved-it` (Tier 2, slice requirement-story). One nullable
column: the wording a revision introduced. A digest records that a requirement's meaning moved, not
what it said, so the wording is recorded from now on; existing rows read null, which says the
wording was not recorded rather than inventing one. A plain `ADD COLUMN`; no table is rebuilt.

The downgrade drops the column (a plain `DROP COLUMN`, SQLite 3.35+); nothing else reads it.

Guarded for a database with no `spec_requirement_revisions` table (an upgrade from an early
revision), and for a column already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0131"
down_revision = "0130"
branch_labels = None
depends_on = None

_TABLE = "spec_requirement_revisions"


def _existing() -> set:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    existing = _existing()
    if existing and "statement" not in existing:
        op.add_column(_TABLE, sa.Column("statement", sa.Text(), nullable=True))


def downgrade() -> None:
    # A plain DROP COLUMN, not a batch rebuild: rebuilding reflects the table's foreign keys, and a
    # database upgraded from an early revision may lack the tables they name.
    if "statement" in _existing():
        op.execute(sa.text(f"ALTER TABLE {_TABLE} DROP COLUMN statement"))
