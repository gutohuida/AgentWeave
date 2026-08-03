"""drop the legacy project role configuration table

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-03 19:30:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "project_roles_config" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("project_roles_config")


def downgrade() -> None:
    if "project_roles_config" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "project_roles_config",
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("project_id"),
        )
