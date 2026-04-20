"""add agent self-registration columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-15 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("agents")]

    if "contact_mode" not in columns:
        op.add_column("agents", sa.Column("contact_mode", sa.String(32), nullable=True))
    if "self_registered" not in columns:
        op.add_column(
            "agents", sa.Column("self_registered", sa.Boolean, server_default="0", nullable=False)
        )
    if "mcp_endpoint" not in columns:
        op.add_column("agents", sa.Column("mcp_endpoint", sa.String(256), nullable=True))
    if "spawn_cmd" not in columns:
        op.add_column("agents", sa.Column("spawn_cmd", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("agents")]

    if "spawn_cmd" in columns:
        op.drop_column("agents", "spawn_cmd")
    if "mcp_endpoint" in columns:
        op.drop_column("agents", "mcp_endpoint")
    if "self_registered" in columns:
        op.drop_column("agents", "self_registered")
    if "contact_mode" in columns:
        op.drop_column("agents", "contact_mode")
