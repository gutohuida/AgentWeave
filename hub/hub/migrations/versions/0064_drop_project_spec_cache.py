"""drop the project spec content cache and its reconciliation snapshots

Revision ID: 0064
Revises: 0063
Create Date: 2026-08-12 17:40:00.000000

`project_specs` was a push-fed content cache and `project_spec_snapshots` a per-source
reconciliation record. Both existed for one stated reason — the Hub could not see a project's
files — and that reason is gone: `ProjectWorkspace` resolves a registered project's directory in
both deployment modes, so the file on disk is the document.

Neither table has a reachable writer. `POST /project/specs/sync` and `/specs/reconcile` were only
ever called by `HttpTransport.push_spec` / `reconcile_specs`, which were called by the watchdog and
by `agentweave spec push` — the watchdog is deleted and that command is among the 51 removed from
the CLI.

**This discards cached content that has no file on disk.** In the normal case the cache duplicated
files that are still there and dropping it loses nothing. Where the file is gone, the project's
source directory was removed or replaced, and the cache is holding content the operator already
deleted. The alternative — a migration writing files to a path read out of a database row — fails
exactly where it matters: in the container deployment the working directory may not be mounted at
upgrade time.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

_TABLES = ("project_specs", "project_spec_snapshots")


def _existing(conn) -> set[str]:
    """Which of the two tables are actually present.

    An upgrade starting from an early revision reaches this migration with only the tables those
    revisions created, so neither is guaranteed to exist — the same guard `0033`/`0034` use.
    """
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    present = _existing(op.get_bind())
    for table in _TABLES:
        if table in present:
            op.drop_table(table)


def downgrade() -> None:
    present = _existing(op.get_bind())

    if "project_specs" not in present:
        op.create_table(
            "project_specs",
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
            sa.Column("path", sa.String(255), primary_key=True),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )

    if "project_spec_snapshots" not in present:
        op.create_table(
            "project_spec_snapshots",
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), primary_key=True),
            sa.Column("source_id", sa.String(64), primary_key=True),
            sa.Column("manifest_content", sa.Text, nullable=True),
            sa.Column("manifest_state", sa.String(16), nullable=False),
            sa.Column("inventory", sa.JSON, nullable=False),
            sa.Column("diagnostics", sa.JSON, nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    # The rows are not recoverable. Downgrade restores the shape, not the content.
