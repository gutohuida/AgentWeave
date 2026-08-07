"""add permission_requests

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-07 11:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None

_TABLE = "permission_requests"
_INDEX_PROJECT_STATUS = "ix_permission_requests_project_status"
_INDEX_AGENT = "ix_permission_requests_agent"
_INDEX_RUN = "ix_permission_requests_run_id"
_INDEX_STATUS = "ix_permission_requests_status"


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
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("tool_use_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("tool_input", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("decided_by", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
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
