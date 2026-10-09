"""the knowledge vault's settings -- vault_settings

Revision ID: 0124
Revises: 0123
Create Date: 2026-10-09 00:00:00.000000

`a-vault-the-operator-fills-with-text-and-agents-can-read` (Tier 2). One row per project holding
the vault's private location and default visibility. Nothing existing is copied or changed: a
project with no row uses the defaults. The vault's records are files, and no migration touches
them, so the downgrade only drops the table and loses the two settings.

Guarded for a table already present (a database built by `create_all` from these models and
stamped at an earlier revision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "vault_settings" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "vault_settings",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
        sa.Column("private_location", sa.String(1024), nullable=True),
        sa.Column("default_visibility", sa.String(16), nullable=False, server_default="tracked"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    if "vault_settings" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("vault_settings")
