"""add agent config column

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-20 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("agents")]

    if "config" not in columns:
        op.add_column("agents", sa.Column("config", sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("agents")]

    if "config" in columns:
        op.drop_column("agents", "config")
