"""agent_outputs loses two indexes that served nothing -- ix_agent_outputs_project_agent, ix_agent_outputs_agent

Revision ID: 0146
Revises: 0145
Create Date: 2026-10-25 00:00:00.000000

`the-database-stays-fast-as-history-grows` (Tier 2, task `stats-indexes`, D6). Indexes only: no row
is read, rewritten or deleted.

* `ix_agent_outputs_project_agent` (project_id, agent) is a leading prefix of
  `ix_agent_outputs_project_agent_run_sequence`, `ix_agent_outputs_project_agent_ts` and
  `ix_agent_outputs_project_agent_session_ts` (the last two from `0144`).
* `ix_agent_outputs_agent` (agent): every agent filter on agent_outputs in `hub/hub` also names the
  project, so the bare index answered no query.

Each cost a write on every streamed output line. The newest-context-reading index this slice's D6
also asked for is `0144`'s partial `ix_event_logs_context_agent_ts`
(`the-app-stays-responsive-while-agents-run`); a second one would only double that write.

The downgrade recreates both, so the schema is back exactly. Guarded for a database without the
table (an upgrade from an early revision) and for an index already absent or present (a database
built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None

_DROPPED = (
    ("ix_agent_outputs_project_agent", ["project_id", "agent"]),
    ("ix_agent_outputs_agent", ["agent"]),
)


def _indexes() -> set:
    return {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("agent_outputs")}


def _present() -> bool:
    return "agent_outputs" in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if not _present():
        return
    existing = _indexes()
    for name, _columns in _DROPPED:
        if name in existing:
            op.drop_index(name, table_name="agent_outputs")


def downgrade() -> None:
    if not _present():
        return
    existing = _indexes()
    for name, columns in _DROPPED:
        if name not in existing:
            op.create_index(name, "agent_outputs", columns)
