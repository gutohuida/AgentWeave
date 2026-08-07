"""add conversation_id to the tables that block a run

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-07 23:56:00.000000

`questions`, `permission_requests` and `unasked_questions` each hold a row that stops a run until
an operator acts. Navigation shows that state per conversation, on a surface that re-renders on
every SSE event, so the link has to be one column rather than a join through `runs`.

`unasked_questions.conversation_id` already exists and is already populated — only its index is
added here. The other two columns are new and stay NULL for existing rows: the run that opened
them may be gone, and inventing an attribution is worse than admitting there isn't one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

# table -> (column to add or None if it already exists, index name)
_TARGETS = {
    "questions": "ix_questions_conversation_id",
    "permission_requests": "ix_permission_requests_conversation_id",
    "unasked_questions": "ix_unasked_questions_conversation_id",
}


def _state(conn, table: str) -> tuple[set[str], set[str]] | None:
    """(columns, index names) for `table`, or None when the table is not there.

    Upgrades starting from an early revision reach this migration with only the tables those
    revisions created; `create_all` builds the rest from the model, these columns included.
    """
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    columns = {col["name"] for col in inspector.get_columns(table)}
    indexes = {idx["name"] for idx in inspector.get_indexes(table)}
    return columns, indexes


def upgrade() -> None:
    conn = op.get_bind()
    for table, index_name in _TARGETS.items():
        state = _state(conn, table)
        if state is None:
            continue
        columns, indexes = state
        if "conversation_id" not in columns:
            op.add_column(table, sa.Column("conversation_id", sa.String(64), nullable=True))
        if index_name not in indexes:
            op.create_index(index_name, table, ["conversation_id"])


def downgrade() -> None:
    conn = op.get_bind()
    for table, index_name in _TARGETS.items():
        state = _state(conn, table)
        if state is None:
            continue
        columns, indexes = state
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)
        # `unasked_questions.conversation_id` predates this migration — 0032 created it, so
        # dropping it here would undo something this revision never did.
        if table != "unasked_questions" and "conversation_id" in columns:
            op.drop_column(table, "conversation_id")
