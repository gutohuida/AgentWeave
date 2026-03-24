"""add settings column to projects

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-22 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # On fresh installs, projects is created by create_all (which includes
    # the settings column from the model). Only run ALTER TABLE on existing
    # databases where the table already exists without the column.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "projects" not in inspector.get_table_names():
        return  # fresh install — create_all will add the column
    existing_cols = {c["name"] for c in inspector.get_columns("projects")}
    if "settings" not in existing_cols:
        op.add_column(
            "projects",
            sa.Column("settings", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "projects" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("projects")}
    if "settings" in existing_cols:
        op.drop_column("projects", "settings")
