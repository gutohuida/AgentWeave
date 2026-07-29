"""add structured stream fields to agent outputs

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-29 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_RUN_ORDERING_INDEX = "ix_agent_outputs_project_agent_run_sequence"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_outputs" not in inspector.get_table_names():
        return  # fresh install — create_all will add the columns and index

    existing_cols = {column["name"] for column in inspector.get_columns("agent_outputs")}
    if "kind" not in existing_cols:
        op.add_column("agent_outputs", sa.Column("kind", sa.String(16), nullable=True))
    if "payload" not in existing_cols:
        op.add_column("agent_outputs", sa.Column("payload", sa.JSON(), nullable=True))
    if "run_id" not in existing_cols:
        op.add_column("agent_outputs", sa.Column("run_id", sa.String(64), nullable=True))
    if "sequence" not in existing_cols:
        op.add_column("agent_outputs", sa.Column("sequence", sa.Integer(), nullable=True))

    existing_indexes = {index["name"] for index in sa.inspect(conn).get_indexes("agent_outputs")}
    if _RUN_ORDERING_INDEX not in existing_indexes:
        op.create_index(
            _RUN_ORDERING_INDEX,
            "agent_outputs",
            ["project_id", "agent", "run_id", "sequence"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "agent_outputs" not in inspector.get_table_names():
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("agent_outputs")}
    if _RUN_ORDERING_INDEX in existing_indexes:
        op.drop_index(_RUN_ORDERING_INDEX, table_name="agent_outputs")

    existing_cols = {column["name"] for column in sa.inspect(conn).get_columns("agent_outputs")}
    for column_name in ("sequence", "run_id", "payload", "kind"):
        if column_name in existing_cols:
            op.drop_column("agent_outputs", column_name)
