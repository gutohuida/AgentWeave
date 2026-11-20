"""The profile an agent was folded into -- agents.folded_into

Revision ID: 0188
Revises: 0187
Create Date: 2026-11-20 01:00:00.000000

`fold-duplicate-agents-into-one-profile-with-their-history-kept`, FR-4 and FR-11. One nullable
column naming, by name, the profile an agent was folded into.

Runs on the operator's :8000 data at its next restart. Adds a column only; no row is changed and
nothing is backfilled, so with nothing folded every row reads NULL and every agent behaves exactly
as before (criterion no-fold-no-change).

Rollback: the downgrade drops the column. A fold done since is then indistinguishable from a plain
archival: the folded agent stays archived, and its re-pointed work stays with the profile. Guarded
for a missing table, as 0033/0034 are.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0188"
down_revision = "0187"
branch_labels = None
depends_on = None

_TABLE = "agents"
_COLUMN = "folded_into"


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    present = _columns(op.get_bind())
    if present is None or _COLUMN in present:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        batch_op.add_column(sa.Column(_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    present = _columns(op.get_bind())
    if present is None or _COLUMN not in present:
        return
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.drop_column(_COLUMN)
