"""add agent description

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-08 18:20:00.000000

A short line saying what an agent is for. Nullable with no backfill: an agent that predates the
column has no description, and inventing one from its name would put words in the operator's
mouth. NULL and "" are the same state to every reader, and the write path normalizes blank to
NULL so only one of them can ever be stored.

Guarded for a missing table for the same reason as 0038 — an upgrade starting from an early
revision reaches here with only that revision's tables, and `create_all` builds the rest from
the model with this column already on it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

_TABLE = "agents"


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
    if "description" not in existing:
        op.add_column(_TABLE, sa.Column("description", sa.String(256), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None:
        return
    if "description" in existing:
        op.drop_column(_TABLE, "description")
