"""add hashed per-run capability credentials

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-03 03:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_INDEX_NAME = "ix_runs_capability_token_hash"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "runs" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("runs")}
    if "capability_token_hash" not in columns:
        op.add_column(
            "runs",
            sa.Column("capability_token_hash", sa.String(64), nullable=True),
        )

    indexes = {index["name"] for index in sa.inspect(conn).get_indexes("runs")}
    if _INDEX_NAME not in indexes:
        op.create_index(
            _INDEX_NAME,
            "runs",
            ["capability_token_hash"],
            unique=True,
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "runs" not in set(inspector.get_table_names()):
        return

    indexes = {index["name"] for index in inspector.get_indexes("runs")}
    if _INDEX_NAME in indexes:
        op.drop_index(_INDEX_NAME, table_name="runs")
    columns = {column["name"] for column in sa.inspect(conn).get_columns("runs")}
    if "capability_token_hash" in columns:
        with op.batch_alter_table("runs", recreate="never") as batch_op:
            batch_op.drop_column("capability_token_hash")
