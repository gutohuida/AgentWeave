"""add project_specs table

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-23 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "project_specs" in inspector.get_table_names():
        return  # fresh install — create_all already made the table
    op.create_table(
        "project_specs",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("path", sa.String(255), primary_key=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "project_specs" in inspector.get_table_names():
        op.drop_table("project_specs")
