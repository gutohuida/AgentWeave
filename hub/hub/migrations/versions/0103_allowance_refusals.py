"""count the deliveries a provider refused on usage grounds, apart from failed ones

Revision ID: 0103
Revises: 0102
Create Date: 2026-09-14 14:40:00.000000

`a-spent-allowance-holds-the-queue`, task 2.1, designs D2 and D8 (finding F355). A turn refused
because the agent's provider allowance is spent returns its input without counting it against
`delivery_attempts`: the refusal is not the input's fault, and counting it cleared a sound provider
session at the second attempt and withdrew the operator's message at the third. The refused
delivery is still a delivery that was cut off, so it is counted here, where the retry note reads
both counts and the queue status's "attempts left" keeps meaning counted attempts.

**Default 0, with a server default,** following `0072`'s `delivery_attempts`: every existing entry
has been refused zero times as far as anything recorded, and a row written by a process still
running old code must also read correctly.

Guarded for a missing `inbound_queue_entries` table, like `0033`/`0034`, because an upgrade starting
from an early revision reaches this with only that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None

_TABLE = "inbound_queue_entries"
_COLUMN = "allowance_refusals"


def _columns(conn) -> set[str] | None:
    """Columns of `inbound_queue_entries`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
