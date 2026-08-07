"""add Question.options

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-07 14:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "questions" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("questions")}
    if "options" not in columns:
        # server_default so rows written before this migration read as "open-ended" rather
        # than NULL, which the JSON column would hand back as None instead of a list.
        op.add_column(
            "questions",
            sa.Column("options", sa.JSON(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "questions" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("questions")}
    if "options" in columns:
        op.drop_column("questions", "options")
