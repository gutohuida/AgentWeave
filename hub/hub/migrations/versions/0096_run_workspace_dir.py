"""record the directory a run actually executed in

Revision ID: 0096
Revises: 0095
Create Date: 2026-08-27 18:40:00.000000

`2026-08-27-work-is-isolated-per-task`, design D7.

Evidence recorded during a turn is footprinted at the HEAD of "the agent's checkout", which
`requirement_evidence.footprint_root` derives from the actor's name alone. Once work is isolated per
task that derivation has no correct form: the right directory depends on the turn rather than on the
agent, and every available derivation is wrong in some case. `RequirementEvidence.task_id` is
supplied by the agent and optional, so it can be absent or wrong; `Run.task_id` gives the wrong tree
for a **review** run, which binds to the task it is inspecting but executes in a detached review
checkout.

Recording what the run was actually handed makes all five cases — task workspace, per-agent
workspace, grandfathered task, review checkout, and a project with no repository — one rule.

**Nullable, with no backfill.** Runs that predate this column executed somewhere nobody wrote down,
and there is no way to recover it: a per-agent worktree path could be *computed* for them, but for a
review run that computation is exactly the wrong answer this change exists to fix, and writing a
plausible directory into a column meant to record a fact would make old rows indistinguishable from
new ones. `NULL` means "not recorded", and `footprint_root` falls back to the behaviour those runs
already had. Migration 0043 set the same precedent for `snapshot_commit_sha`.

Guarded for a missing table the way `0033`/`0034`/`0075`/`0095` are: an upgrade starting from an
early revision reaches here with only that revision's tables, and `create_all` builds the rest from
the model with the column already on it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None

_TABLE = "runs"
_COLUMN = "workspace_dir"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn):
        return
    if _COLUMN not in _columns(conn, _TABLE):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Text(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE in _tables(conn) and _COLUMN in _columns(conn, _TABLE):
        op.drop_column(_TABLE, _COLUMN)
