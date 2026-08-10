"""add task divergence policy and transition origin

Revision ID: 0056
Revises: 0055
Create Date: 2026-08-10 20:14:00.000000

Two columns that together make the run-boundary check possible and answerable.

`task_transitions.origin` records what caused a transition to be *requested*: `actor` when someone
asked, `runtime` when the Hub made the move on a run's behalf at a moment the run did not choose.
Without it this whole capability eats itself — the divergence check asks "did this run advance its
task?", and the runtime's own automatic move to `in_progress` is a transition by that run on that
task, so it would answer yes for every bound run and the check would report nothing.

`tasks.divergence_policy` and `tasks.escalation_agent` say what should happen when the answer is no:
surface it, retry the same agent once, or reassign to a stronger agent and run that one.

Both defaults are the pre-change behaviour, which is why no backfill is needed and none is done.
Every transition recorded before this migration was asked for by an actor, because nothing else
could write one. Every task predating it gets `surface`, so shipping this cannot start a run nobody
asked for on a board of existing work.

Server defaults are set as well as Python-side defaults: SQLite rewrites the table to add a NOT NULL
column, and existing rows need a value from the database rather than from the ORM.

Guarded, like 0038-0055.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None

_TASKS = "tasks"
_POLICY = "divergence_policy"
_ESCALATION = "escalation_agent"
_TRANSITIONS = "task_transitions"
_ORIGIN = "origin"


def _columns(conn, table):
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()

    tasks = _columns(conn, _TASKS)
    if tasks is not None:
        if _POLICY not in tasks:
            op.add_column(
                _TASKS,
                sa.Column(
                    _POLICY,
                    sa.String(16),
                    nullable=False,
                    server_default="surface",
                ),
            )
        if _ESCALATION not in tasks:
            op.add_column(_TASKS, sa.Column(_ESCALATION, sa.String(64), nullable=True))

    transitions = _columns(conn, _TRANSITIONS)
    if transitions is not None and _ORIGIN not in transitions:
        op.add_column(
            _TRANSITIONS,
            sa.Column(_ORIGIN, sa.String(16), nullable=False, server_default="actor"),
        )


def downgrade() -> None:
    conn = op.get_bind()

    transitions = _columns(conn, _TRANSITIONS)
    if transitions is not None and _ORIGIN in transitions:
        op.drop_column(_TRANSITIONS, _ORIGIN)

    tasks = _columns(conn, _TASKS)
    if tasks is not None:
        if _ESCALATION in tasks:
            op.drop_column(_TASKS, _ESCALATION)
        if _POLICY in tasks:
            op.drop_column(_TASKS, _POLICY)
