"""a chat's own worktree -- conversations.own_worktree

Revision ID: 0184
Revises: 0183
Create Date: 2026-11-18 22:30:00.000000

`one-profile-runs-many-turns-at-once-on-different-tasks` (FR-13, D6). A chat the operator opens
while the project's "profiles run in parallel" switch is on works in a git worktree of its own, on
`thread/<agent>/<lineage>`. Decided when the chat is opened and kept whatever the switch does later,
so it is a column on the conversation rather than a read of the switch at each turn.

Runs on the operator's :8000 data at its next restart. Additive: every existing conversation reads
false, so it keeps the agent's shared worktree exactly as before; no existing row is read or
rewritten.

Rollback: the downgrade drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0183` does); every
conversation then uses the agent's shared worktree again. Thread branches left behind are ordinary
git branches the operator can merge or delete; their worktrees are under `.agentweave/threads/`.

Guarded for a database without the table (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0184"
down_revision = "0183"
branch_labels = None
depends_on = None

_COLUMN = "own_worktree"


def _columns() -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("conversations"):
        return set()
    return {column["name"] for column in inspector.get_columns("conversations")}


def upgrade() -> None:
    columns = _columns()
    if columns and _COLUMN not in columns:
        op.add_column(
            "conversations",
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )


def downgrade() -> None:
    if _COLUMN in _columns():
        op.execute(sa.text(f"ALTER TABLE conversations DROP COLUMN {_COLUMN}"))
