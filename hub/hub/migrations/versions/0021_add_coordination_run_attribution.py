"""add run attribution to coordination effects

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-03 03:20:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

_COLUMNS = {
    "messages": ("created_by_run_id",),
    "tasks": ("created_by_run_id", "updated_by_run_id"),
    "questions": ("created_by_run_id",),
}


def upgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        existing_columns = {column["name"] for column in sa.inspect(conn).get_columns(table)}
        for column in columns:
            if column not in existing_columns:
                op.add_column(table, sa.Column(column, sa.String(64), nullable=True))
            index_name = f"ix_{table}_{column}"
            indexes = {index["name"] for index in sa.inspect(conn).get_indexes(table)}
            if index_name not in indexes:
                op.create_index(index_name, table, [column])


def downgrade() -> None:
    conn = op.get_bind()
    tables = set(sa.inspect(conn).get_table_names())
    for table, columns in reversed(tuple(_COLUMNS.items())):
        if table not in tables:
            continue
        for column in reversed(columns):
            index_name = f"ix_{table}_{column}"
            indexes = {index["name"] for index in sa.inspect(conn).get_indexes(table)}
            if index_name in indexes:
                op.drop_index(index_name, table_name=table)
            existing_columns = {c["name"] for c in sa.inspect(conn).get_columns(table)}
            if column in existing_columns:
                with op.batch_alter_table(table, recreate="never") as batch_op:
                    batch_op.drop_column(column)
