"""A profile's pool of runners -- agent_pool_entries

Revision ID: 0186
Revises: 0185
Create Date: 2026-11-19 11:00:00.000000

`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-its-pool`, FR-1 and FR-2. Each agent
gets a pool: entries of a project runner plus an optional effort, one of them the default.
`agents.runner_id` stays and names the default entry's runner.

Runs on the operator's :8000 data at its next restart. Creates one table and seeds it: every agent
with a runner gets one entry on that runner, no effort, marked default; an agent with no runner
gets none. No existing row is changed or deleted, so every agent runs exactly as before.

The seed runs whether or not this migration created the table. `init_db` runs `create_all` before
`alembic upgrade`, so on a real startup the table already exists, empty, when this runs; a guard
that returned early on "table present" would leave every agent with an empty pool. It is
idempotent: an agent that already has an entry is skipped.

Rollback: the downgrade drops the table, losing only pool edits made since; `agents.runner_id`
still names each agent's default runner, which is what the code before this change reads. Guarded
for a database without `agents` or `runners` (an upgrade from an early revision, as 0033/0034 are).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0186"
down_revision = "0185"
branch_labels = None
depends_on = None

_TABLE = "agent_pool_entries"
_INDEXES = (
    ("ix_agent_pool_entries_agent", ["agent_id"]),
    ("ix_agent_pool_entries_runner", ["runner_id"]),
)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if not {"agents", "runners", "projects"} <= tables:
        return
    if _TABLE not in tables:
        op.create_table(
            _TABLE,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False),
            sa.Column("runner_id", sa.String(64), sa.ForeignKey("runners.id"), nullable=False),
            sa.Column("effort", sa.String(32), nullable=True),
            sa.Column("is_default", sa.Boolean(), server_default="0", nullable=False),
            sa.Column("position", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    existing = {ix["name"] for ix in sa.inspect(bind).get_indexes(_TABLE)}
    for name, columns in _INDEXES:
        if name not in existing:
            op.create_index(name, _TABLE, columns)

    # Every agent with a runner, and no entry yet: one entry on that runner, no effort, default.
    # An agent whose runner_id names a runner that no longer exists is seeded too, so that
    # `runner_id` and the default entry agree as they must; the start path refuses it as before.
    rows = bind.execute(
        sa.text(
            "SELECT a.id, a.project_id, a.runner_id FROM agents a "
            "WHERE a.runner_id IS NOT NULL "
            f"AND NOT EXISTS (SELECT 1 FROM {_TABLE} e WHERE e.agent_id = a.id)"
        )
    ).fetchall()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for agent_id, project_id, runner_id in rows:
        bind.execute(
            sa.text(
                f"INSERT INTO {_TABLE} "
                "(id, project_id, agent_id, runner_id, effort, is_default, position, created_at) "
                "VALUES (:id, :project_id, :agent_id, :runner_id, NULL, 1, 0, :created_at)"
            ),
            {
                "id": f"pool-{uuid.uuid4().hex[:12]}",
                "project_id": project_id,
                "agent_id": agent_id,
                "runner_id": runner_id,
                "created_at": now,
            },
        )


def downgrade() -> None:
    if _TABLE in sa.inspect(op.get_bind()).get_table_names():
        for name, _ in _INDEXES:
            op.drop_index(name, table_name=_TABLE)
        op.drop_table(_TABLE)
