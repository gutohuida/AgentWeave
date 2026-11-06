"""a conversation records the checkpoint it started from -- conversations.started_from_checkpoint_id

Revision ID: 0165
Revises: 0164
Create Date: 2026-11-06 01:00:00.000000

`start-a-conversation-from-any-checkpoint-with-any-agent` (FR-7). The operator can start a new
conversation from any written checkpoint, for any agent; the conversation records which checkpoint
that was, so the checkpoint can list the conversations started from it and each one can link back.
Additive, on live data: a nullable column and its index, no backfill, every existing row reads null
(started from no checkpoint). No CHECK and no ForeignKey, so the table is not recreated.

Rollback: the downgrade drops the index and the column (plain `DROP COLUMN`, SQLite 3.35+, as
`0164` does); the record of where started conversations came from is lost, and nothing else.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0165"
down_revision = "0164"
branch_labels = None
depends_on = None

_TABLE = "conversations"
_COLUMN = "started_from_checkpoint_id"
_INDEX = "ix_conversations_started_from_checkpoint_id"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns() -> set:
    inspector = _inspector()
    if not inspector.has_table(_TABLE):
        return set()
    return {column["name"] for column in inspector.get_columns(_TABLE)}


def _indexes() -> set:
    inspector = _inspector()
    if not inspector.has_table(_TABLE):
        return set()
    return {index["name"] for index in inspector.get_indexes(_TABLE)}


def upgrade() -> None:
    columns = _columns()
    if not columns:
        return
    if _COLUMN not in columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))
    if _INDEX not in _indexes():
        op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    if _INDEX in _indexes():
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in _columns():
        op.execute(sa.text(f"ALTER TABLE {_TABLE} DROP COLUMN {_COLUMN}"))
