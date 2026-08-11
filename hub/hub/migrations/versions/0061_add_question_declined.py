"""add the declined state to questions

Revision ID: 0061
Revises: 0060
Create Date: 2026-08-11 10:15:00.000000

`questions.declined` and `questions.declined_at` — the operator closed a question without answering
it.

Beside `answered` rather than folded into it. An empty answer claims the operator said nothing in
response; declining claims they chose not to respond at all, and every existing reader of `answered`
would otherwise treat one as the other — including the check that decides whether a run ending with
an outstanding question parks its task.

`declined` is NOT NULL with a server default of false, because SQLite rewrites the table to add a
NOT NULL column and existing rows need a value from the database rather than from the ORM.

**No backfill, and the absence is the decision.** Marking historical unanswered questions as declined
would claim the operator made a decision they never made — the record exists precisely to say that
they were asked and chose not to answer.

Guarded, like 0038-0060.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

_QUESTIONS = "questions"
_DECLINED = "declined"
_DECLINED_AT = "declined_at"


def _columns(conn, table):
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()

    questions = _columns(conn, _QUESTIONS)
    if questions is None:
        return
    if _DECLINED not in questions:
        op.add_column(
            _QUESTIONS,
            sa.Column(_DECLINED, sa.Boolean(), nullable=False, server_default="0"),
        )
    if _DECLINED_AT not in questions:
        op.add_column(
            _QUESTIONS, sa.Column(_DECLINED_AT, sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()

    questions = _columns(conn, _QUESTIONS)
    if questions is None:
        return
    if _DECLINED_AT in questions:
        op.drop_column(_QUESTIONS, _DECLINED_AT)
    if _DECLINED in questions:
        op.drop_column(_QUESTIONS, _DECLINED)
