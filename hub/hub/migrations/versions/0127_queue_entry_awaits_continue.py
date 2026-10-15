"""a held checkpoint successor waits for Continue -- inbound_queue_entries.awaits_continue

Revision ID: 0127
Revises: 0126
Create Date: 2026-10-15 00:00:00.000000

`a-held-successor-waits-for-continue` (Tier 2, F598). With auto-continue off a cutover queued the
successor's checkpoint entry as ordinary queued input, so the next project-wide redrain started it.
The flag marks it as waiting for the operator's Continue.

The backfill holds every still-queued checkpoint entry in a project whose auto-continue is off: on
a live database those successors were promised the same Continue button, and without the flag the
next redrain would start them. Entries in auto-continue-on projects, and every entry that is not a
queued checkpoint entry, are left at false. The downgrade drops the column and touches no entry
state, so held successors become ordinary queued entries again (the behaviour before this change).

Guarded for a missing table and for a column already present.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0127"
down_revision = "0126"
branch_labels = None
depends_on = None

_TABLE = "inbound_queue_entries"
_COLUMN = "awaits_continue"


def _columns(conn):
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default="0"),
    )
    # An upgrade replayed from an early revision reaches here without a `projects` table (the
    # 0063 test does); there is nothing to hold then.
    if "projects" not in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.execute(
        "UPDATE inbound_queue_entries SET awaits_continue = 1 "
        "WHERE state = 'queued' AND origin_type = 'checkpoint' AND project_id IN "
        "(SELECT id FROM projects WHERE checkpoint_auto_continue = 0)"
    )


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_column(_COLUMN)
