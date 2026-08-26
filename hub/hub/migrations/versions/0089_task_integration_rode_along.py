"""name the commits that rode along with an approved merge, not just the one it targeted

Revision ID: 0089
Revises: 0088
Create Date: 2026-08-26 03:25:00.000000

F58. `task_integration.integrate()` runs `git merge --no-ff <commit_sha>`, which brings in every
ancestor of `<commit_sha>` not already on the target branch — the commit's entire history, not its
diff alone — contradicting this module's own stated guarantee ("merge a commit, never a branch").
Live drive on 2026-08-26 found a merge for one approved task also landing a different, unapproved
task's test file and five scratch scripts, all sitting earlier on the same agent's branch.

The correct narrower merge semantics is a real design decision (cherry-pick range, single-commit
patch-apply, or per-task worktrees) — deliberately not made here. What this closes is a narrower,
decision-free gap: nothing told the operator *what actually landed* beyond the one commit sha
`integration-preview` and the history view already name. `rode_along_commits` records every commit
`git rev-list <main_branch>..<commit_sha>` finds reachable from the target and not yet on the main
branch, other than the target itself — computed before the merge runs, from the same repository
state the merge itself acts on.

Simple `ADD COLUMN`, no recreate: SQLite allows a new nullable-with-default text column without
rebuilding the table, unlike `0088`'s primary-key change. Guarded for a missing `task_integrations`
table, like `0033`/`0034`, because an upgrade starting from an early revision reaches this with only
that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None

_TABLE = "task_integrations"
_COLUMN = "rode_along_commits"


def _columns(conn) -> set[str] | None:
    """Columns of `task_integrations`, or None when the table is not there."""
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
        sa.Column(_COLUMN, sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    existing = _columns(op.get_bind())
    if existing is None or _COLUMN not in existing:
        return
    op.drop_column(_TABLE, _COLUMN)
