"""add Conversation.runtime_overrides

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-05 01:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "conversations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "runtime_overrides" not in columns:
        op.add_column(
            "conversations", sa.Column("runtime_overrides", sa.JSON(), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "conversations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "runtime_overrides" in columns:
        with op.batch_alter_table("conversations", recreate="never") as batch_op:
            batch_op.drop_column("runtime_overrides")
