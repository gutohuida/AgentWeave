"""add durable per-project charter seed marker

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-03 18:25:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "projects" not in tables:
        return
    columns = {column["name"] for column in sa.inspect(conn).get_columns("projects")}
    if "charters_seeded" not in columns:
        op.add_column(
            "projects",
            sa.Column(
                "charters_seeded",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    if "projects" not in tables:
        return
    columns = {column["name"] for column in sa.inspect(conn).get_columns("projects")}
    if "charters_seeded" in columns:
        with op.batch_alter_table("projects", recreate="never") as batch_op:
            batch_op.drop_column("charters_seeded")
