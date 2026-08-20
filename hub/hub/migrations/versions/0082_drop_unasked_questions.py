"""retire the unasked-question backstop

Revision ID: 0082
Revises: 0081
Create Date: 2026-08-20 13:20:00.000000

The backstop read a completed run's final assistant text and, if it ended in a question that
had never been routed through `ask_user`, opened a row so the operator was told a question
existed. It was added because a Codex run was measured writing its question into the final
message and ending the turn, stranding itself on an answer that could not arrive.

The operator has retired it: a guess about whether trailing prose is a question is not
something they want the product making on their behalf. An agent that needs an answer has
`ask_user`, and a turn that ends without calling it simply ends.

Dropping the table rather than leaving it orphaned — nothing reads it, and a table no code
knows about is a worse legacy than a migration that removes one. The index goes with it
implicitly on every backend we target, but it is dropped explicitly first so the intent is
readable in the migration rather than inferred from the table drop.

Guarded for a missing table, matching `0071` onward's precedent for an upgrade starting from
an early revision. There is no downgrade data path: the rows were a derived signal about runs
that have already finished, so recreating the table empty restores the schema exactly and
loses nothing that could be recomputed anyway.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

_TABLE = "unasked_questions"
_INDEX = "ix_unasked_questions_project_status"


def _tables(conn: sa.engine.Connection) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _indexes(conn: sa.engine.Connection, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(table) if index["name"]}


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn):
        return
    if _INDEX in _indexes(conn, _TABLE):
        op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE in _tables(conn):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False, index=True),
        sa.Column("run_id", sa.String(64), nullable=True, index=True),
        sa.Column("conversation_id", sa.String(64), nullable=True, index=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
    )
    op.create_index(_INDEX, _TABLE, ["project_id", "status"])
