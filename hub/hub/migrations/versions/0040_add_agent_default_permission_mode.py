"""add agent default permission mode

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-08 19:05:00.000000

The posture an agent runs under when the conversation has not stated one. Nullable with no
backfill: NULL means "the built-in default", which is not the same as storing today's default on
every existing row — that would pin every agent to a value nobody chose the moment the default
moves. The same reasoning as `permission_timeout_seconds`.

No backfill from `config["yolo"]` either, even though a yolo agent is effectively at full access
today. The two stay reconciled from the write side (see `_apply_default_permission_mode` in
api/v1/agents.py): writing a posture rewrites `yolo`, so an agent whose posture was never set
keeps behaving exactly as it did, and one whose posture was set has a single answer.

Guarded for a missing table for the same reason as 0038 and 0039.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None

_TABLE = "agents"
_COLUMN = "default_permission_mode"


def _columns(conn) -> set[str] | None:
    """Columns of `agents`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(32), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
