"""add Run.instance_id

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-06 14:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_runs_instance_id"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "runs" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("runs")}
    if "instance_id" not in columns:
        op.add_column(
            "runs",
            sa.Column("instance_id", sa.String(64), nullable=True),
        )

    indexes = {index["name"] for index in sa.inspect(conn).get_indexes("runs")}
    if _INDEX_NAME not in indexes:
        op.create_index(_INDEX_NAME, "runs", ["instance_id"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "runs" not in set(inspector.get_table_names()):
        return

    indexes = {index["name"] for index in inspector.get_indexes("runs")}
    if _INDEX_NAME in indexes:
        op.drop_index(_INDEX_NAME, table_name="runs")
    columns = {column["name"] for column in sa.inspect(conn).get_columns("runs")}
    if "instance_id" in columns:
        with op.batch_alter_table("runs", recreate="never") as batch_op:
            batch_op.drop_column("instance_id")
