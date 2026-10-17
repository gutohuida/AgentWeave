"""evidence carries what it takes to judge it -- requirement_evidence.command, output, covers

Revision ID: 0130
Revises: 0129
Create Date: 2026-10-17 00:00:00.000000

`evidence-carries-what-it-takes-to-judge-it` (Tier 2, F673, decision vis-D5). Three nullable
columns: the command the recorder ran, the tail of its output, and whether the piece covers its
requirement fully or partly. Existing rows are not backfilled: they read null, which says no output
was recorded rather than inventing one. Plain `ADD COLUMN`s, so no table is rebuilt and nothing
else in the table changes.

The downgrade drops the three columns (a plain `DROP COLUMN`, SQLite 3.35+); nothing else reads
them.

Guarded for a database with no `requirement_evidence` table (an upgrade from a revision before
`0068`), and for a column already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("command", sa.Text()),
    ("output", sa.Text()),
    ("covers", sa.String(16)),
)


def _existing() -> set:
    bind = op.get_bind()
    if "requirement_evidence" not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns("requirement_evidence")}


def upgrade() -> None:
    existing = _existing()
    if not existing:
        return
    for name, type_ in _COLUMNS:
        if name not in existing:
            op.add_column("requirement_evidence", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    existing = _existing()
    if not existing:
        return
    # A plain DROP COLUMN (SQLite 3.35+), not a batch rebuild: rebuilding reflects the table's
    # foreign keys, and a database upgraded from an early revision may lack `tasks`.
    for name, _type in _COLUMNS:
        if name in existing:
            op.execute(sa.text(f"ALTER TABLE requirement_evidence DROP COLUMN {name}"))
