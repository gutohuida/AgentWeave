"""give a conversation a lineage that survives a checkpoint cutover

Revision ID: 0085
Revises: 0084
Create Date: 2026-08-21 23:30:00.000000

`conversations-continue` design D3: delivery needs "the line of work", not "the conversation
id", because a checkpoint cutover replaces the id. `lineage_id` answers that with one indexed
equality rather than a recursive predecessor walk — the same shape `checkpoints.lineage_id`
(`0044`) already uses.

Backfilled to each row's own `id`, same as `0016`'s `color_index`: existing conversations are
each their own lineage, which is what makes the backfill safe — the forward lookup on a
self-lineage row resolves exactly as the old equality test did (design.md, "Risks").
`checkpoint_cutover.py` (phase 2 of this change) is what makes two rows share a lineage going
forward; nothing here reconstructs a cutover chain from history.

Guarded for a missing `conversations` table, like `0033`/`0034`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None

_TABLE = "conversations"
_COLUMN = "lineage_id"
_INDEX = "ix_conversations_lineage_id"


def _columns(conn) -> set[str] | None:
    """Columns of `conversations`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return

    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))
        op.create_index(_INDEX, _TABLE, [_COLUMN])

    conn.execute(sa.text(f"UPDATE {_TABLE} SET {_COLUMN} = id WHERE {_COLUMN} IS NULL"))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
