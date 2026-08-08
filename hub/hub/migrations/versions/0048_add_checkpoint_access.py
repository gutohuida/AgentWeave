"""add checkpoint access grants and citations

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-09 02:00:00.000000

Two independent grants on the agent, both closed by default, and the citations a checkpoint
carries.

`can_read_checkpoints` and `can_recall` are separate because summary access is not transcript
access: a checkpoint is a deliberate, bounded distillation, while recall returns another agent's
raw recorded output verbatim. One flag would make the narrower grant inexpressible.

They live on the agent row and nowhere else. A charter is behaviour text the model reads; if it
could widen access, prose an agent can be persuaded to write would become an authorisation
mechanism.

Guarded, like 0038-0047.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

_AGENT_COLUMNS = ("can_read_checkpoints", "can_recall")


def _columns(conn, table: str):
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()

    existing = _columns(conn, "agents")
    if existing is not None:
        for name in _AGENT_COLUMNS:
            if name not in existing:
                op.add_column(
                    "agents",
                    sa.Column(name, sa.Boolean(), nullable=False, server_default="0"),
                )

    existing = _columns(conn, "checkpoints")
    if existing is not None and "citations" not in existing:
        op.add_column("checkpoints", sa.Column("citations", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()

    existing = _columns(conn, "checkpoints")
    if existing is not None and "citations" in existing:
        op.drop_column("checkpoints", "citations")

    existing = _columns(conn, "agents")
    if existing is not None:
        for name in _AGENT_COLUMNS:
            if name in existing:
                op.drop_column("agents", name)
