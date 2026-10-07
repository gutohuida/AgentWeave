"""drift watches the files its evidence is about -- evidence_footprints.watched_from

Revision ID: 0120
Revises: 0119
Create Date: 2026-10-07 00:00:00.000000

`drift-watches-the-files-its-evidence-is-about` (Tier 2). Additive only: a nullable JSON column
naming where a footprint's watched files came from (`["locator"]`, `["commit"]`, `["branch"]`,
`["merge"]`, or `[]` for none). Every row stored before this change stays NULL, which reads as
"recorded before watching": not scanned, listed, and rebuilt by the next Scan for drift where its
merge into the main line can be found (design D6). Nothing about an existing row changes here.

Guarded for a missing table, as `0033`/`0034` do.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0120"
down_revision = "0119"
branch_labels = None
depends_on = None


def _columns(conn, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if "evidence_footprints" not in set(sa.inspect(conn).get_table_names()):
        return
    if "watched_from" not in _columns(conn, "evidence_footprints"):
        with op.batch_alter_table("evidence_footprints", recreate="never") as batch_op:
            batch_op.add_column(sa.Column("watched_from", sa.JSON, nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if "evidence_footprints" not in set(sa.inspect(conn).get_table_names()):
        return
    if "watched_from" in _columns(conn, "evidence_footprints"):
        with op.batch_alter_table("evidence_footprints", recreate="never") as batch_op:
            batch_op.drop_column("watched_from")
