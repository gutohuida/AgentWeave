"""a structural dedupe key for questions, apart from their prose

Revision ID: 0104
Revises: 0103
Create Date: 2026-09-19 23:10:00.000000

`a-refused-capability-reaches-the-operator`, task 0.3, design D15 (finding F376). Deduping a
question by its exact text makes the operator-facing sentence a structural identifier nothing
declares as one: editing the wording — a typo, a softer tone, the setting renamed — silently stops
matching every record already resolved. `subject_key` is that identifier instead, written by the
caller and never derived from `question`.

**Nullable, backfilling nothing.** Every existing row keeps `subject_key = NULL`; the partial
predicate on the index below excludes NULL keys, so it cannot fail on existing data.

**Partial unique index**, not a plain one: D17 opens a second record once the first for a key is
resolved (answered or declined), so only unresolved, keyed rows are constrained. This is what makes
two refusals arriving together resolve to the same row — the database refuses the second insert
instead of a `SELECT` racing it.

Guarded for a missing `questions` table, like `0033`/`0034`, because an upgrade starting from an
early revision reaches this with only that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None

_TABLE = "questions"
_COLUMN = "subject_key"
_INDEX = "ix_questions_open_subject_key"


def _columns(conn) -> set[str] | None:
    """Columns of `questions`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def _indexes(conn) -> set[str]:
    if _TABLE not in set(sa.inspect(conn).get_table_names()):
        return set()
    return {idx["name"] for idx in sa.inspect(conn).get_indexes(_TABLE) if idx["name"]}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(200), nullable=True))
    if _INDEX not in _indexes(conn):
        op.create_index(
            _INDEX,
            _TABLE,
            ["project_id", _COLUMN],
            unique=True,
            sqlite_where=sa.text("answered = 0 AND declined = 0 AND subject_key IS NOT NULL"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return
    if _INDEX in _indexes(conn):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
