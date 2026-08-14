"""record which document declared a task, so approval can create work idempotently

Revision ID: 0071
Revises: 0070
Create Date: 2026-08-14 02:00:00.000000

A specification's payload has always been able to declare its own tasks — a key, a description, and
the requirement keys each serves — validated on save and read by the completeness check. Nothing ever
materialised them, so an operator approving a document got nineteen requirements and an empty board,
and re-described the decomposition by hand.

These two columns are what let approval create that work without creating it twice. Every existing
task gets NULL for both, which is the truth about them: nobody declared them.

The unique index needs no partial clause. NULLs compare as distinct for uniqueness, so the
overwhelming majority of tasks — the undeclared ones — are unconstrained by it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def _tables(conn) -> set[str]:
    """An upgrade starting from an early revision reaches this migration with only the tables
    those revisions created; `create_all` builds the rest from the model."""
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if "tasks" not in present:
        return

    columns = _columns(conn, "tasks")
    if "spec_document_id" not in columns:
        # Deliberately no ForeignKey in the migration: SQLite cannot add one to an existing table
        # without rebuilding it, and the model declares the relationship for anything created fresh.
        op.add_column("tasks", sa.Column("spec_document_id", sa.String(64), nullable=True))
        op.create_index("ix_tasks_spec_document_id", "tasks", ["spec_document_id"])
    if "spec_task_key" not in columns:
        op.add_column("tasks", sa.Column("spec_task_key", sa.String(64), nullable=True))

    if "uq_tasks_spec_declaration" not in _indexes(conn, "tasks"):
        op.create_index(
            "uq_tasks_spec_declaration",
            "tasks",
            ["project_id", "spec_document_id", "spec_task_key"],
            unique=True,
        )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    if "tasks" not in present:
        return

    indexes = _indexes(conn, "tasks")
    if "uq_tasks_spec_declaration" in indexes:
        op.drop_index("uq_tasks_spec_declaration", table_name="tasks")
    if "ix_tasks_spec_document_id" in indexes:
        op.drop_index("ix_tasks_spec_document_id", table_name="tasks")

    columns = _columns(conn, "tasks")
    if "spec_task_key" in columns:
        op.drop_column("tasks", "spec_task_key")
    if "spec_document_id" in columns:
        op.drop_column("tasks", "spec_document_id")
