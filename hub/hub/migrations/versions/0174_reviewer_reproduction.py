"""A reviewer's reproduction on an acceptance -- six nullable columns on evidence_reviews

Revision ID: 0174
Revises: 0173
Create Date: 2026-11-10 23:00:00.000000

`evidence-review-sends-work-back-only-for-what-is-wrong-with-it`, task `reviewer-verifies`, FR-1
and FR-3. A reviewer accepting evidence on the task it reviews may attach what it ran itself: the
command, its output and the commit it ran on, and may correct the piece's summary and covers. They
are kept on the review row, attributed to the reviewer and its run, so the evidence row keeps what
its author recorded. `anchored_from_commit` is the commit the evidence named before the reviewer's
reproduction re-anchored it.

Runs on the operator's :8000 data at its next restart. No existing row is read or rewritten: every
existing review reads null in each column, which is today's behaviour (no reproduction). The
downgrade drops the columns (plain `DROP COLUMN`, SQLite 3.35+, as 0171 does).

Guarded for a database without the table and for a column already present (a database built by
`create_all`) or already absent on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0174"
down_revision = "0173"
branch_labels = None
depends_on = None

COLUMNS = (
    ("reproduction_command", sa.Text()),
    ("reproduction_output", sa.Text()),
    ("reproduction_commit", sa.String(64)),
    ("anchored_from_commit", sa.String(64)),
    ("corrected_summary", sa.Text()),
    ("corrected_covers", sa.String(16)),
)


def _columns(conn) -> set:
    if "evidence_reviews" not in set(sa.inspect(conn).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(conn).get_columns("evidence_reviews")}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if not columns:
        return
    for name, kind in COLUMNS:
        if name not in columns:
            op.add_column("evidence_reviews", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    columns = _columns(op.get_bind())
    for name, _kind in COLUMNS:
        if name in columns:
            op.execute(sa.text(f"ALTER TABLE evidence_reviews DROP COLUMN {name}"))
