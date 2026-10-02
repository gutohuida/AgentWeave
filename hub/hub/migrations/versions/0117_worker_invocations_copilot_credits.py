"""a Copilot run shows its credits -- worker_invocations gains two nullable credit columns

Revision ID: 0117
Revises: 0116
Create Date: 2026-10-02 00:00:00.000000

`a-copilot-run-shows-its-credits`, design D5 (task 2.1/2.2's `worker_invocations` half; `0116`
did the `turn_usage` half). `ai_nano_aiu` and `premium_requests` are a Copilot one-shot call's
own credit charge. Both nullable; nothing is backfilled, since a call recorded before this
change never saw a Copilot checkpoint.

Guarded for a missing `worker_invocations`, as `0033`/`0034` do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None

_TABLE = "worker_invocations"
_COLUMNS = (
    ("ai_nano_aiu", sa.BigInteger),
    ("premium_requests", sa.Float),
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
