"""runner configuration a workspace held at its last approved launch -- workspace_fingerprints

Revision ID: 0133
Revises: 0132
Create Date: 2026-10-18 00:00:00.000000

F737 (Tier 2). One row per workspace a turn started in, holding the fingerprint of its runner
configuration (`.claude/settings*.json`, `.claude/hooks/`, `.mcp.json`, `.codex/`, `.github/hooks/`).
A launch whose workspace differs from its row is held for the operator. A new table only: nothing
existing is copied or changed, and every workspace's first launch after this revision records its
baseline. The downgrade drops the table; launches then start without the check, which is the
behaviour before this revision, and an upgrade after that starts every baseline afresh.

Guarded for a table already present (a database built by `create_all` from these models and
stamped at an earlier revision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "workspace_fingerprints" in tables or "projects" not in tables:
        return
    op.create_table(
        "workspace_fingerprints",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("workspace_key", sa.String(1024), nullable=False),
        sa.Column("workspace_dir", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("recorded_by", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "workspace_key"),
    )


def downgrade() -> None:
    if "workspace_fingerprints" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("workspace_fingerprints")
