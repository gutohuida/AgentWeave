"""add checkpoint auto continue

Revision ID: 0049
Revises: 0048
Create Date: 2026-08-09 03:10:00.000000

Whether a successor conversation starts working the moment it is handed its checkpoint.

Off by default: a turn nobody asked for costs tokens. But off must not mean "type a message to
continue" — that was the reported friction, and inventing a message is a strange price for
resuming work the Hub already summarised. Off now means an explicit Continue button.

Guarded, like 0038-0048.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

_COLUMN = "checkpoint_auto_continue"


def _columns(conn):
    inspector = sa.inspect(conn)
    if "projects" not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns("projects")}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(
        "projects",
        sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column("projects", _COLUMN)
