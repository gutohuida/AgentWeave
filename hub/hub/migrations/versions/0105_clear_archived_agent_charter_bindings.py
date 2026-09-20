"""an archived agent holds no charter binding

Revision ID: 0105
Revises: 0104
Create Date: 2026-09-20 22:00:00.000000

`an-archived-agent-holds-nothing-and-is-offered-nowhere`, group 3 (finding F185). `archive()`
now clears `charter_id` going forward (`hub/hub/agent_lifecycle.py`), but every agent archived
before this migration runs still holds its binding on disk. This migration rewrites those rows:

    UPDATE agents SET charter_id = NULL WHERE lifecycle = 'archived'

**This reaches the operator's live database the next time they restart their Hub.** It clears
charter bindings on agents they archived earlier — the decided remedy (design D5), not a side
effect.

**The downgrade is a documented no-op.** Which rows lost a binding here is not recorded anywhere;
there is nothing to restore. Pretending otherwise would require a shadow table this change does
not add.

Guarded for a missing `agents` table, like `0033`/`0034`, because an upgrade starting from an
early revision reaches this migration with only that revision's tables.

No `models.py` change: `Agent.charter_id` is already nullable
(`hub/hub/db/models.py:230-232`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None

_TABLE = "agents"


def _has_table(conn) -> bool:
    return _TABLE in set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    if not _has_table(conn):
        return
    op.execute(sa.text(f"UPDATE {_TABLE} SET charter_id = NULL WHERE lifecycle = 'archived'"))


def downgrade() -> None:
    """No-op: which rows lost a binding is not recorded, so there is nothing to restore."""
