"""indexes for each agent's and conversation's newest context reading and output

Revision ID: 0144
Revises: 0143
Create Date: 2026-10-25 00:00:00.000000

`the-app-stays-responsive-while-agents-run` (task lists-flat, design D5). GET /agents and both
conversation lists read each agent's and each conversation's newest `context_warning` row and each
agent's newest output. Without these indexes those reads scan every row the project ever recorded,
so their cost grows with history.

Additive only: five indexes, no row read, copied or changed. Three are partial on `event_logs`
(`event_type = 'context_warning'`), two of them over a JSON path of `data`; every existing
`context_warning` row on the operator's and the trial databases holds valid JSON, so building
them cannot fail on a row. Each is guarded for its table missing and for being present already
(a database built by `create_all` and stamped at an earlier revision). Rollback: the downgrade
drops the five indexes, and the reads fall back to scanning.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None

_CONTEXT = sa.text("event_type = 'context_warning'")

_INDEXES = (
    ("ix_event_logs_context_agent_ts", "event_logs", ["project_id", "agent", "timestamp"], True),
    (
        "ix_event_logs_context_conversation_ts",
        "event_logs",
        ["project_id", sa.text("json_extract(data, '$.conversation_id')"), "timestamp"],
        True,
    ),
    (
        "ix_event_logs_context_session_ts",
        "event_logs",
        ["project_id", sa.text("json_extract(data, '$.session_id')"), "timestamp"],
        True,
    ),
    (
        "ix_agent_outputs_project_agent_ts",
        "agent_outputs",
        ["project_id", "agent", "timestamp"],
        False,
    ),
    (
        "ix_agent_outputs_project_agent_session_ts",
        "agent_outputs",
        ["project_id", "agent", "session_id", "timestamp"],
        False,
    ),
)


def _existing(table: str) -> set:
    # From `sqlite_master`, not the inspector: SQLAlchemy does not reflect an index over an
    # expression, so the inspector would miss two of these and the guard would never fire.
    rows = op.get_bind().execute(
        sa.text("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = :table"),
        {"table": table},
    )
    return {row[0] for row in rows}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for name, table, columns, partial in _INDEXES:
        if table not in tables or name in _existing(table):
            continue
        op.create_index(name, table, columns, **({"sqlite_where": _CONTEXT} if partial else {}))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    for name, table, _columns, _partial in reversed(_INDEXES):
        if table in tables and name in _existing(table):
            op.drop_index(name, table_name=table)
