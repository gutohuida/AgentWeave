"""add session_id column to messages

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-01 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "messages" not in inspector.get_table_names():
        return  # fresh install — create_all will add the column
    existing_cols = {c["name"] for c in inspector.get_columns("messages")}
    if "session_id" not in existing_cols:
        op.add_column(
            "messages",
            sa.Column("session_id", sa.String(128), nullable=True),
        )
        op.create_index("ix_messages_session_id", "messages", ["session_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "messages" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("messages")}
    if "session_id" in existing_cols:
        op.drop_index("ix_messages_session_id", table_name="messages")
        op.drop_column("messages", "session_id")
