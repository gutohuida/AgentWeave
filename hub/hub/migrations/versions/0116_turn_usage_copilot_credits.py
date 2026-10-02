"""a Copilot run shows its credits -- turn_usage gains four nullable credit columns

Revision ID: 0116
Revises: 0115
Create Date: 2026-10-02 00:00:00.000000

`a-copilot-run-shows-its-credits`, design D4/D5 (task 2.1's `TurnUsage` half only; the
`worker_invocations` columns are a separate, not-yet-built piece of the same task). `ai_nano_aiu`
and `premium_requests` are this run's own Copilot credit charge; `session_nano_aiu_total` and
`session_premium_requests_total` are the session checkpoint this run ended at, read back as the
next run's baseline by `usage_accounting.copilot_session_baseline`. All four nullable; nothing is
backfilled, since a run recorded before this change never saw a Copilot checkpoint.

Guarded for a missing `turn_usage`, as `0033`/`0034` do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None

_TABLE = "turn_usage"
_COLUMNS = (
    ("ai_nano_aiu", sa.BigInteger),
    ("premium_requests", sa.Float),
    ("session_nano_aiu_total", sa.BigInteger),
    ("session_premium_requests_total", sa.Float),
)


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is None:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        for name, type_ in _COLUMNS:
            if name not in columns:
                batch_op.add_column(sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    columns = _columns(op.get_bind())
    if columns is None:
        return
    with op.batch_alter_table(_TABLE, recreate="never") as batch_op:
        for name, _type in _COLUMNS:
            if name in columns:
                batch_op.drop_column(name)
