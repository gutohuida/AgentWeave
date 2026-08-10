"""add the conversation's task binding

Revision ID: 0060
Revises: 0059
Create Date: 2026-08-10 22:40:00.000000

`conversations.task_id` — the durable half of the run→task binding.

Before it, only the first run of a conversation was bound: starting work from a board card sent a
task id, a follow-up typed into the composer did not, and nothing carried the binding across turns.
A five-turn piece of work was therefore checked once, at the end of turn one, and was invisible for
the turn where the agent actually stopped.

Nullable, and **no backfill** — deliberately, not for want of a plausible one. A conversation that
predates this column was not bound to anything, and guessing a binding from the tasks its agent
happened to touch would start checking runs nobody asked to be checked, on threads whose operators
never opted in. The mechanism only ever binds forward.

Guarded, like 0038-0059.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

_CONVERSATIONS = "conversations"
_TASK = "task_id"
_TASK_INDEX = "ix_conversations_task_id"


def _columns(conn, table):
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def _index_names(conn, table):
    return {index["name"] for index in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()

    conversations = _columns(conn, _CONVERSATIONS)
    if conversations is not None and _TASK not in conversations:
        op.add_column(_CONVERSATIONS, sa.Column(_TASK, sa.String(64), nullable=True))
        if _TASK_INDEX not in _index_names(conn, _CONVERSATIONS):
            op.create_index(_TASK_INDEX, _CONVERSATIONS, [_TASK])


def downgrade() -> None:
    conn = op.get_bind()

    conversations = _columns(conn, _CONVERSATIONS)
    if conversations is not None and _TASK in conversations:
        if _TASK_INDEX in _index_names(conn, _CONVERSATIONS):
            op.drop_index(_TASK_INDEX, table_name=_CONVERSATIONS)
        op.drop_column(_CONVERSATIONS, _TASK)
