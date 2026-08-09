"""add conversation checkpoint warning

Revision ID: 0050
Revises: 0049
Create Date: 2026-08-09 04:00:00.000000

Where a conversation stands with its checkpoint threshold: NULL (not warned), `due` (crossed and
waiting on the operator), or `dismissed` (the operator chose to keep working).

`offered` used to generate a checkpoint the moment the threshold was crossed, which billed a model
call whether or not the operator wanted one — and at a low threshold billed it again every turn.
It now warns, and the warning can be waved away.

One column rather than a `warned` boolean and a `dismissed` boolean. Those two together make
"dismissed but never warned" representable, which has no meaning and which every reader would have
to decide about.

Guarded, like 0038-0049.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

_TABLE = "conversations"
_COLUMN = "checkpoint_warning"


def _columns(conn):
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(16), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
