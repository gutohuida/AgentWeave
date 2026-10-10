"""a run divergence outlives its task -- run_divergences.task_id becomes nullable

Revision ID: 0125
Revises: 0124
Create Date: 2026-10-10 00:00:00.000000

F564 (`overhaul-task-delete-divergence`, Tier 2: a schema change on a table that holds the
operator's history). `RunDivergence` is a record that nothing deletes -- "how often does this agent
drop its work?" must stay answerable -- yet deleting a task deleted its divergence rows. The delete
now clears `task_id`, as it does on `runs`, which needs the column to accept NULL.

Nothing is copied or rewritten: existing rows keep their `task_id`. SQLite cannot drop a NOT NULL
in place, so the table is recreated (`batch_alter_table(..., recreate="always")`), which carries its
indexes and the two named CHECK constraints. The downgrade restores NOT NULL and so has to remove
the rows whose task is gone (they have nothing to point at); that is the only loss, and only on a
downgrade.

Guarded for a missing table (an upgrade from an early revision reaches this with only that
revision's tables; `create_all` builds the rest from the model, nullable included) and for a column
already nullable.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None

_TABLE = "run_divergences"


def _task_id_nullable(conn) -> bool | None:
    """Whether `run_divergences.task_id` accepts NULL, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    for col in inspector.get_columns(_TABLE):
        if col["name"] == "task_id":
            return bool(col["nullable"])
    return None


def upgrade() -> None:
    if _task_id_nullable(op.get_bind()) is not False:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.alter_column("task_id", existing_type=sa.String(64), nullable=True)


def downgrade() -> None:
    if _task_id_nullable(op.get_bind()) is not True:
        return
    op.execute(sa.text(f"DELETE FROM {_TABLE} WHERE task_id IS NULL"))
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.alter_column("task_id", existing_type=sa.String(64), nullable=False)
