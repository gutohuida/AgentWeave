"""add unasked_questions

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-07 18:30:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

_TABLE = "unasked_questions"
_INDEX_AGENT = "ix_unasked_questions_agent"
_INDEX_RUN = "ix_unasked_questions_run_id"
_INDEX_STATUS = "ix_unasked_questions_status"
_INDEX_PROJECT_STATUS = "ix_unasked_questions_project_status"


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE in set(inspector.get_table_names()):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("conversation_id", sa.String(64), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(_INDEX_AGENT, _TABLE, ["agent"])
    op.create_index(_INDEX_RUN, _TABLE, ["run_id"])
    op.create_index(_INDEX_STATUS, _TABLE, ["status"])
    op.create_index(_INDEX_PROJECT_STATUS, _TABLE, ["project_id", "status"])


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return
    op.drop_table(_TABLE)
