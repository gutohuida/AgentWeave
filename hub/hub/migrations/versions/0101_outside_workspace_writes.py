"""record the writes a run made outside the directory it was given

Revision ID: 0101
Revises: 0100
Create Date: 2026-09-04 03:10:00.000000

`2026-09-03-a-write-outside-the-workspace-is-recorded`, filed as F115, designs D5 and D11.

A workspace is a working directory, not a wall. Under every posture except the default one, an
agent handed `--dangerously-skip-permissions` or `acceptEdits` can name an absolute path anywhere on
the machine and the write lands there — into another agent's worktree, into the operator's own
checkout, anywhere. Nothing recorded that it happened. `Run.workspace_dir` says where the run
*started*; it has never been a statement about where the run's writes ended up, and F71's evidence
footprinting reads it as though it were.

**Two columns, one migration** (design D10). They are one fact recorded twice for two readers: the
run column is the durable record, and the evidence column is that record as it stood when a
footprint was captured, so a reader looking at accepted evidence can see that some of the work it
describes may not be in the tree the footprint names. Splitting them across two revisions would
give the same change two head bumps for no reader's benefit.

**Nullable, no server default, no backfill** — migration `0096`'s own precedent for `workspace_dir`
and `0043`'s for `snapshot_commit_sha`. `NULL` means *nobody was looking*, which is exactly what is
true of every run and every footprint that predates the detector. An empty list means *observed, and
nothing left the workspace*. That distinction is the whole value of the record: a backfilled `[]`
would claim every historical run was watched and found clean, which is the claim of coverage design
D12 spends its length refusing to let this change make.

Guarded per table for a missing table the way `0033`/`0034`/`0075`/`0095`/`0096`/`0100` are: an
upgrade starting from an early revision reaches here with only that revision's tables, and
`create_all` builds the rest from the model with the columns already on them. The two guards are
independent because the two tables enter the schema at different revisions.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None

_COLUMN = "outside_workspace_writes"
_TABLES = ("runs", "evidence_footprints")


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    for table in _TABLES:
        if table not in present:
            continue
        if _COLUMN not in _columns(conn, table):
            op.add_column(table, sa.Column(_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)
    for table in _TABLES:
        if table in present and _COLUMN in _columns(conn, table):
            op.drop_column(table, _COLUMN)
