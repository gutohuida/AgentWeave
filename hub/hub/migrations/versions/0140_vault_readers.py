"""which agents read each vault entry -- vault_readers

Revision ID: 0140
Revises: 0139
Create Date: 2026-10-20 00:00:00.000000

`the-vault-names-who-read-an-entry` (Tier 2, F901). One row per vault entry per agent per project,
holding how many times that agent read it and when it last did. A new table only: no existing row is
read, copied or changed, and nothing is backfilled (reads counted in `vault_fetches` before this
revision stay unattributed). The downgrade drops the table and loses only the attribution; the
counts in `vault_fetches` are untouched.

Guarded for a table already present (a database built by `create_all` from these models and
stamped at an earlier revision).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "vault_readers" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "vault_readers",
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("entry_id", sa.String(64), nullable=False),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "entry_id", "agent", name="pk_vault_readers"),
    )


def downgrade() -> None:
    if "vault_readers" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_table("vault_readers")
