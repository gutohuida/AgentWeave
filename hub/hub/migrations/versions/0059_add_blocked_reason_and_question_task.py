"""add the blocked reason and the question-to-task link

Revision ID: 0059
Revises: 0058
Create Date: 2026-08-10 22:10:00.000000

The two columns a waiting task needs.

`tasks.blocked_reason` is what the task is waiting for, in words. A blocked task stays in the
in_progress column rather than moving to one of its own, so this text is most of what tells the
operator the card is waiting on *them* rather than merely stalled.

`questions.blocked_task_id` is which task a blocking question parked, so answering it knows what to
release. A column rather than a join table: a question blocks at most one task and `ask_user` has no
way to name several. Recorded rather than re-derived from the asking run's binding, because a run
may be bound to a task the question was not about, and releasing the wrong task is worse than
releasing nothing.

Both nullable, no backfill, and none is possible: nothing before this migration could park a task,
so there is no historical block to describe and no historical question that parked one. Inventing
either would put text on cards that were never waiting.

Guarded, like 0038-0058.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None

_TASKS = "tasks"
_REASON = "blocked_reason"
_QUESTIONS = "questions"
_BLOCKED_TASK = "blocked_task_id"
_BLOCKED_TASK_INDEX = "ix_questions_blocked_task_id"


def _columns(conn, table):
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def _index_names(conn, table):
    return {index["name"] for index in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()

    tasks = _columns(conn, _TASKS)
    if tasks is not None and _REASON not in tasks:
        op.add_column(_TASKS, sa.Column(_REASON, sa.Text(), nullable=True))

    questions = _columns(conn, _QUESTIONS)
    if questions is not None and _BLOCKED_TASK not in questions:
        op.add_column(_QUESTIONS, sa.Column(_BLOCKED_TASK, sa.String(64), nullable=True))
        if _BLOCKED_TASK_INDEX not in _index_names(conn, _QUESTIONS):
            op.create_index(_BLOCKED_TASK_INDEX, _QUESTIONS, [_BLOCKED_TASK])


def downgrade() -> None:
    conn = op.get_bind()

    questions = _columns(conn, _QUESTIONS)
    if questions is not None and _BLOCKED_TASK in questions:
        if _BLOCKED_TASK_INDEX in _index_names(conn, _QUESTIONS):
            op.drop_index(_BLOCKED_TASK_INDEX, table_name=_QUESTIONS)
        op.drop_column(_QUESTIONS, _BLOCKED_TASK)

    tasks = _columns(conn, _TASKS)
    if tasks is not None and _REASON in tasks:
        op.drop_column(_TASKS, _REASON)
