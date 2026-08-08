"""add conversation peer binding

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-08 20:40:00.000000

Where a peer message lands. A send that names no conversation used to be delivered to whatever
thread the recipient touched most recently; it is now keyed on the sender's conversation, or —
for the Hub and the scheduler, which have none — on the sender's identity.

No backfill, deliberately. Historical peer traffic is already scattered across unrelated threads,
so backfilling would mean guessing which of three conversations an `ack` "really" belonged to.
Existing conversations keep both columns NULL and are never resolved by a binding; the next
message on a given line of work creates the bound thread.

Guarded for a missing table for the same reason as 0038-0040.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

_TABLE = "conversations"
_COLUMNS = ("bound_sender_conversation_id", "bound_sender_agent")
_INDEX = "ix_conversations_bound_sender_conversation_id"


def _columns(conn) -> set[str] | None:
    """Columns of `conversations`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return
    if "bound_sender_conversation_id" not in existing:
        op.add_column(
            _TABLE, sa.Column("bound_sender_conversation_id", sa.String(64), nullable=True)
        )
        # Every peer send looks the binding up, so the lookup gets an index. Created only
        # alongside the column, or a re-run would collide with the index the model already built.
        op.create_index(_INDEX, _TABLE, ["bound_sender_conversation_id"])
    if "bound_sender_agent" not in existing:
        op.add_column(_TABLE, sa.Column("bound_sender_agent", sa.String(64), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if "bound_sender_conversation_id" in existing:
        op.drop_index(_INDEX, table_name=_TABLE)
    for name in _COLUMNS:
        if name in existing:
            op.drop_column(_TABLE, name)
