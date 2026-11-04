"""a checkpoint has a title -- checkpoints.title, summary, title_made_by, title_reason, unreadable_answer

Revision ID: 0163
Revises: 0162
Create Date: 2026-11-04 17:00:00.000000

`every-checkpoint-findable-and-readable` (FR-9, FR-11, FR-13). Five nullable columns on
`checkpoints`: the title and summary the generation writes in the same call as the body, who made
them (`model`, `hub_from_body`, `hub_from_facts`), why the Hub made them when it did, and the raw
text of an answer that could not be read. Additive, on live data: every existing checkpoint reads
NULL in all five, which is the state the one-time fill looks for. No CHECK, so the table (whose
constraint names `0088` pinned) is not recreated.

Rollback: the downgrade drops the five columns (plain `DROP COLUMN`, SQLite 3.35+, as `0161` and
`0162` do); the view then shows the trigger and date where a title is missing, as before.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None

_NEW_COLUMNS = (
    ("title", sa.String(120)),
    ("summary", sa.Text()),
    ("title_made_by", sa.String(16)),
    ("title_reason", sa.Text()),
    ("unreadable_answer", sa.Text()),
)


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    columns = _columns("checkpoints")
    if not columns:
        return
    for name, type_ in _NEW_COLUMNS:
        if name not in columns:
            op.add_column("checkpoints", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    columns = _columns("checkpoints")
    for name, _ in reversed(_NEW_COLUMNS):
        if name in columns:
            op.execute(sa.text(f"ALTER TABLE checkpoints DROP COLUMN {name}"))
