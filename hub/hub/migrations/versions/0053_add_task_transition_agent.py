"""add task transition actor agent

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-10 18:10:00.000000

Author/reviewer separation compares the **agent**, not the run.

0052 recorded only `run_id`, and the rule built on it asked "did this run also complete the task?".
First live use walked straight through it: an agent completed a task on one run and approved it on
its next. Every turn is a new run, so the check was satisfied by an agent merely continuing its own
work — it forbade nothing. `actor_agent` is what the rule reads now.

Denormalised rather than joined through `runs`: this is an integrity record and has to answer "who
approved this" on its own, without depending on a run row that may later be pruned.

Nullable, because an operator transition has no agent — which is also how an operator action stays
distinguishable from an agent one beyond `actor_kind`.

No backfill. Rows written by 0052 keep `actor_agent` NULL, and the rule treats NULL as "not the
same agent" — so a task completed before this migration can still be approved by anyone. That is
the honest outcome: the agent that completed it was never recorded, and inventing one would put a
guess into the record this table exists to keep true.

Guarded, like 0038-0052.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_TABLE = "task_transitions"
_COLUMN = "actor_agent"
_INDEX = "ix_task_transitions_actor_agent"


def _columns(conn):
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))
    op.create_index(_INDEX, _TABLE, [_COLUMN])


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
