"""give checkpoints a real ordering key, so "which is newest" cannot tie

Revision ID: 0088
Revises: 0087
Create Date: 2026-08-26 03:00:00.000000

F55. `latest_checkpoint`, `latest_checkpoint_for_loop` and `checkpoint_by_task_author`
(`hub/hub/checkpoints.py`) all answered "which checkpoint is newest" by
`order_by(Checkpoint.created_at.desc(), Checkpoint.id.desc())`. Two checkpoints created in the
same clock tick tie on `created_at`: measured directly on this machine,
`[datetime.now(timezone.utc) for _ in range(5)]` returned five identical values back to back —
Windows' clock resolution is coarser than the microsecond precision the value implies, and a real
occurrence whenever two loop firings complete within one tick, not a one-in-a-million race.
`Checkpoint.id` cannot break the tie either: it is `ckpt-` + a random short id, with no
relationship to insertion order, so roughly half the time the tie-break picked the *older*
checkpoint as "latest" and a briefing was composed from stale content, silently.

`sequence` is the same fix already applied to `TaskTransition`, `InboundQueueEntry` and
`Conversation` (migration `0073`, same reasoning): an autoincrement integer the database itself
hands out in insertion order, so two rows committed in the same transaction still come back in the
order they were actually created. Making `sequence` the primary key, not `id`, is the same shape
those tables use — SQLite can only give a column real autoincrement when it is the table's sole
`INTEGER PRIMARY KEY` — and it is why `hub/hub/checkpoints.py:get_checkpoint_by_id` exists now:
every `session.get(Checkpoint, ...)` call site looked a checkpoint up by its `ckpt-...` string id
while `id` was still the primary key, and `session.get()` resolves by primary key.

The table is recreated (`batch_alter_table(..., recreate="always")`) because SQLite cannot change
which column is the primary key in place — the same reason `0073` recreates `conversations` for
the identical change. Existing rows get `sequence` values in whatever order SQLite's
`INSERT INTO ... SELECT` visits them during the copy, which for a table whose declared primary key
was never `INTEGER` is insertion order — the same order they were actually created in.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None

_TABLE = "checkpoints"


def _columns(conn) -> set[str] | None:
    """Columns of `checkpoints`, or None when it or its foreign key targets are not there.

    Upgrades starting from an early revision reach this migration with only that revision's
    tables; `create_all` builds the rest from the model, `sequence` as the primary key included.
    """
    inspector = sa.inspect(conn)
    if not {_TABLE, "projects", "conversations"} <= set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or "sequence" in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.add_column(sa.Column("sequence", sa.Integer(), nullable=True))
        batch_op.alter_column("id", existing_type=sa.String(64), nullable=False)
        batch_op.create_primary_key("pk_checkpoints", ["sequence"])
        batch_op.create_unique_constraint("uq_checkpoints_id", ["id"])


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or "sequence" not in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint("pk_checkpoints", type_="primary")
        batch_op.drop_constraint("uq_checkpoints_id", type_="unique")
        batch_op.drop_column("sequence")
        batch_op.create_primary_key("pk_checkpoints_id", ["id"])
