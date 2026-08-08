"""add run snapshot commit sha

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-08 23:05:00.000000

What a turn changed on disk. `worktrees.snapshot_worktree` has returned this commit SHA since
worktrees existed, and both call sites in `agent_trigger.py` threw it away.

A checkpoint has to state what its conversation changed, and nothing else in the schema can
answer that: an agent's worktree — and therefore its branch — is shared by all of its concurrent
conversations, every auto-snapshot commit carries the identical message "Auto-snapshot: <agent>'s
turn", and pairing commits to turns by timestamp is guesswork. Recorded against the run, the
union over a conversation's runs is exact.

No backfill. The SHAs of past turns were never captured and cannot be recovered — a historical
conversation reports no changed files rather than a plausible-looking guess, which is the same
rule 0041 followed for peer bindings.

Guarded for a missing table, as 0038-0042 are.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

_TABLE = "runs"
_COLUMN = "snapshot_commit_sha"


def _columns(conn) -> set[str] | None:
    """Columns of `runs`, or None when the table is not there."""
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def upgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN in existing:
        return
    op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
