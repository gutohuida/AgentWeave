"""a stopped turn's interrupted call, estimated -- turn_usage.estimated_input_tokens

Revision ID: 0134
Revises: 0133
Create Date: 2026-10-18 00:00:00.000000

F697 (Tier 1). One nullable column. On an `unavailable` row of a Claude turn the operator stopped,
`estimated_input_tokens` is the interrupted call's input as estimated from the turn's last context
reading; the CLI reports that call nowhere. An estimate, never a measurement: no measured total,
used-token figure or budget reads it. Existing rows read null (no estimate). Nothing is backfilled
or rewritten. A plain `ADD COLUMN`; no table is rebuilt.

The downgrade drops it (a plain `DROP COLUMN`, SQLite 3.35+); nothing else reads it.

Guarded for a database without the table (an upgrade from an early revision), and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None

_TABLE, _COLUMN = "turn_usage", "estimated_input_tokens"


def _existing() -> set:
    bind = op.get_bind()
    if _TABLE not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns(_TABLE)}


def upgrade() -> None:
    existing = _existing()
    if existing and _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Integer(), nullable=True))


def downgrade() -> None:
    # A plain DROP COLUMN, not a batch rebuild: rebuilding reflects the table's foreign keys, and a
    # database upgraded from an early revision may lack the tables they name.
    if _COLUMN in _existing():
        op.execute(sa.text(f"ALTER TABLE {_TABLE} DROP COLUMN {_COLUMN}"))
