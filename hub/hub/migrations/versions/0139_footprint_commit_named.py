"""evidence footprints say whether the recorder named their commit -- evidence_footprints.commit_named

Revision ID: 0139
Revises: 0138
Create Date: 2026-10-21 00:00:00.000000

F761 (Tier 0 fix with a schema change). One nullable column; no existing row is read or rewritten,
and nothing is backfilled.

* `evidence_footprints.commit_named` -- whether the recorder named the commit the footprint is at
  (an operator's `commit`, or a locator that is one), as against the footprint taking the checkout's
  HEAD. The diff route answers no files for a piece that named nothing and sits on the main line,
  where it used to show whatever commit HEAD was as that piece's work. NULL for every existing row:
  unknown, and read exactly as before.

The downgrade drops the column (a plain `DROP COLUMN`, SQLite 3.35+). Guarded for a database
without the table (an upgrade from an early revision) and for a column already present (a database
built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None

_TABLE = "evidence_footprints"


def _has_table() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def _columns() -> set:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(_TABLE)}


def upgrade() -> None:
    if _has_table() and "commit_named" not in _columns():
        op.add_column(_TABLE, sa.Column("commit_named", sa.Boolean(), nullable=True))


def downgrade() -> None:
    if _has_table() and "commit_named" in _columns():
        op.execute(sa.text(f"ALTER TABLE {_TABLE} DROP COLUMN commit_named"))
