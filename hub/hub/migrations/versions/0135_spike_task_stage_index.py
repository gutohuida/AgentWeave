"""SPIKE (throwaway): tasks.stage_index, a task's position in its document's delivery.stages

Revision ID: 0135
Revises: 0134
Create Date: 2026-10-18 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None


def _existing() -> set:
    bind = op.get_bind()
    if "tasks" not in set(sa.inspect(bind).get_table_names()):
        return set()
    return {c["name"] for c in sa.inspect(bind).get_columns("tasks")}


def upgrade() -> None:
    existing = _existing()
    if existing and "stage_index" not in existing:
        op.add_column(
            "tasks", sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    if "stage_index" in _existing():
        op.execute(sa.text("ALTER TABLE tasks DROP COLUMN stage_index"))
