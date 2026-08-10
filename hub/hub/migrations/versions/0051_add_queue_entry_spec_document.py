"""add inbound queue entry spec document

Revision ID: 0051
Revises: 0050
Create Date: 2026-08-10 09:00:00.000000

Which specification document the operator had open when they sent this input.

On the entry rather than passed straight through the scheduler, for the same reason `work_dir`
is: the route queues the input and only *then* asks the scheduler to start a turn, so a busy
agent's turn begins later, from a different call, out of the request that carried the value. A
message like "why does this say that?" is unanswerable without the document it was sent about,
so losing it on a delayed delivery would degrade exactly the case the queue exists to serve.

Nullable, because almost every entry has no document: input from an agent, a job, a checkpoint,
or the ordinary conversation surface is not sent from the specification workspace at all. NULL
means "no document was open", which the context renderer turns into no text rather than a guess.

Guarded, like 0038-0050.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

_TABLE = "inbound_queue_entries"
_COLUMN = "spec_document"


def _columns(conn):
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(512), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
