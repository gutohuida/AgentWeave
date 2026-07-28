"""add project_spec_snapshots table

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-28 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "project_spec_snapshots" in inspector.get_table_names():
        return  # fresh install — create_all already made the table
    op.create_table(
        "project_spec_snapshots",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("source_id", sa.String(64), primary_key=True),
        sa.Column("manifest_content", sa.Text, nullable=True),
        sa.Column("manifest_state", sa.String(16), nullable=False),
        sa.Column("inventory", sa.JSON, nullable=False),
        sa.Column("diagnostics", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "project_spec_snapshots" in inspector.get_table_names():
        op.drop_table("project_spec_snapshots")
