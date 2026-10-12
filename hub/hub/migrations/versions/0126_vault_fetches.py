"""how often agents read each vault entry -- vault_fetches

Revision ID: 0126
Revises: 0125
Create Date: 2026-10-12 00:00:00.000000

`the-vault-map-is-shaped-by-what-agents-ask-for` (Tier 2). One row per vault entry per project,
holding the number of times agents have read it and when they last did. Nothing existing is copied
or changed: an entry with no row has never been read. The vault's records are files and no
migration touches them, so the downgrade only drops the table and loses the counts.

Guarded for a table already present (a database built by `create_all` from these models and
stamped at an earlier revision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "vault_fetches" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "vault_fetches",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("entry_id", sa.String(64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "entry_id", name="pk_vault_fetches"),
    )


def downgrade() -> None:
    if "vault_fetches" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("vault_fetches")
