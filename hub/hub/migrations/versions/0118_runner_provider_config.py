"""a Copilot agent uses hooks and its own agents -- runners gain a nullable provider_config

Revision ID: 0118
Revises: 0117
Create Date: 2026-10-03 00:00:00.000000

`a-copilot-agent-uses-hooks-and-its-own-agents`, design D7 (group C, task 3.1): a Copilot runner
may name a model provider -- `{type, base_url, api_key_var}` -- so its runs bill an API key the
operator keeps in the Hub's environment. The column holds the variable's *name*, never a key.
Nullable; nothing is backfilled, since every runner stored before this change runs on its CLI's
own subscription.

Guarded for a missing `runners`, as `0033`/`0034` do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None

_TABLE = "runners"
_COLUMN = "provider_config"


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is None or _COLUMN in columns:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        batch_op.add_column(sa.Column(_COLUMN, sa.JSON, nullable=True))


def downgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is None or _COLUMN not in columns:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        batch_op.drop_column(_COLUMN)
