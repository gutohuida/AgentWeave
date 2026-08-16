"""give conversations a real ordering key, so "most recent" cannot tie

Revision ID: 0073
Revises: 0072
Create Date: 2026-08-16 03:00:00.000000

`hub/hub/conversations.py` answers "which of this agent's conversations is most recent" in three
places — `inherit_runtime_overrides`, `latest_open_conversation`, `peer_bound_conversation` — and
all three ordered by `created_at` alone. Two conversations created inside the same clock tick tie:
Windows' default timer granularity is ~15.6ms, so this is a real race, not a theoretical one, and
it is exactly what made `test_the_most_recent_overrides_win` fail roughly half the time in a full
test run. `Conversation.id` cannot break the tie either — it is `conv-` + a random short id, so
ordering by it orders by nothing.

`sequence` is the same fix already applied to `TaskTransition` and `InboundQueueEntry` (see the
reasoning at `hub/hub/db/models.py` on `TaskTransition.sequence`): an autoincrement integer that
the database itself hands out in insertion order, so two rows committed in the same transaction —
sharing a timestamp to the microsecond — still come back in the order they were actually created.

Making `sequence` (not `id`) the primary key is the same shape those two tables use, and it is why
`hub/hub/conversations.py:get_conversation_by_id` exists now: every `session.get(Conversation, …)`
call site looked a conversation up by its `conv-…` string id while `id` was still the primary key.
`session.get()` resolves by primary key, so leaving those call sites unchanged after this migration
would have made every one of them silently stop matching. They were all rewritten to
`get_conversation_by_id`, which looks up by the `id` column directly.

SQLite can only give a column real autoincrement (`rowid` aliasing) when it is the table's sole
`INTEGER PRIMARY KEY`, so `id` moves off the primary key and picks up an explicit `UNIQUE NOT NULL`
constraint to keep exactly the guarantee it had as the primary key — every foreign key elsewhere in
the schema (`inbound_queue_entries.conversation_id`, `messages.conversation_id`, …) references
`conversations.id` by value, not by primary-key-ness, and SQLite does not enforce those foreign keys
at all (no `PRAGMA foreign_keys=ON` anywhere in this codebase), so nothing downstream needs to
change.

The table is recreated (`batch_alter_table(..., recreate="always")`) because SQLite cannot change
which column is the primary key in place — the same reason `0035` and `0058` recreate this table
and `inbound_queue_entries` for their own constraint changes. Recreating reflects `conversations`,
and reflecting it resolves its foreign key to `projects`, so the guard mirrors `0035`'s.

Existing rows get `sequence` values in whatever order SQLite's `INSERT INTO … SELECT` visits them
during the copy, which for a table whose declared primary key was never `INTEGER` (so nothing has
ever reordered its physical storage) is insertion order — the same order they were actually
created in. Nothing is backfilled by date; the numbers just start wherever real history already put
them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None

_TABLE = "conversations"


def _columns(conn) -> set[str] | None:
    """Columns of `conversations`, or None when it or its foreign key target is not there.

    Upgrades starting from an early revision reach this migration with only the tables those
    revisions created; `create_all` builds the rest from the model, `sequence` as the primary key
    included.
    """
    inspector = sa.inspect(conn)
    if not {_TABLE, "projects"} <= set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or "sequence" in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.add_column(sa.Column("sequence", sa.Integer(), nullable=True))
        batch_op.alter_column("id", existing_type=sa.String(64), nullable=False)
        batch_op.create_primary_key("pk_conversations", ["sequence"])
        batch_op.create_unique_constraint("uq_conversations_id", ["id"])


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or "sequence" not in existing:
        return
    with op.batch_alter_table(_TABLE, recreate="always") as batch_op:
        batch_op.drop_constraint("pk_conversations", type_="primary")
        batch_op.drop_constraint("uq_conversations_id", type_="unique")
        batch_op.drop_column("sequence")
        batch_op.create_primary_key("pk_conversations_id", ["id"])
