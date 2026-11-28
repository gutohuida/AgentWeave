"""indexes for the event-log fields project screens filter by

Revision ID: 0194
Revises: 0193
Create Date: 2026-11-28 00:00:00.000000

`screens-stop-repeating-work-on-every-read` (task event-log-indexes, FR-5). Overview, next-slice
offers, documents and the task lists find a build's retrospectives and a document's pre-mortems by
`json_extract(data, '$.job')` and `'$.subject.document'` (and the jobs list a job's firings by
`'$.job'` alone, newest first), its pre-mortem answers by `'$.document'`,
and a task's unstaffed review and held send-back by `'$.task_id'`. Nothing indexed those fields, so
each read searched every row of its event type (about 60 ms apiece on the operator's database).

Additive only: five partial expression indexes on `event_logs`, each over one event type, as 0144's
`ix_event_logs_context_*`; no row is changed. Building one evaluates the JSON of that type's rows
only. Each is guarded for its table missing and for being present already (a database built by
`create_all` and stamped earlier). Rollback: the downgrade drops the five, and the reads fall back
to searching the event type.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0194"
down_revision = "0193"
branch_labels = None
depends_on = None

_TABLE = "event_logs"

# (name, columns, event type). The expressions are those `hub/hub/event_log_lookups.py` queries
# name; SQLite matches an expression index only against the identical expression.
_INDEXES = (
    (
        "ix_event_logs_data_fired_job_document",
        [
            "project_id",
            sa.text("json_extract(data, '$.job')"),
            sa.text("json_extract(data, '$.subject.document')"),
            "timestamp",
        ],
        "manager_job_fired",
    ),
    (
        "ix_event_logs_data_fired_job_ts",
        ["project_id", sa.text("json_extract(data, '$.job')"), "timestamp"],
        "manager_job_fired",
    ),
    (
        "ix_event_logs_data_pre_mortem_answer_document",
        ["project_id", sa.text("json_extract(data, '$.document')"), "timestamp"],
        "pre_mortem_answered",
    ),
    (
        "ix_event_logs_data_unstaffed_task",
        ["project_id", sa.text("json_extract(data, '$.task_id')"), "timestamp"],
        "review_unstaffed",
    ),
    (
        "ix_event_logs_data_send_back_held_task",
        ["project_id", sa.text("json_extract(data, '$.task_id')"), "timestamp"],
        "send_back_held",
    ),
)


def _existing() -> set:
    # From `sqlite_master`, not the inspector, which does not reflect an index over an expression.
    rows = op.get_bind().execute(
        sa.text("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = :table"),
        {"table": _TABLE},
    )
    return {row[0] for row in rows}


def _has_table() -> bool:
    return _TABLE in set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if not _has_table():
        return
    existing = _existing()
    for name, columns, event_type in _INDEXES:
        if name in existing:
            continue
        op.create_index(name, _TABLE, columns, sqlite_where=sa.text(f"event_type = '{event_type}'"))


def downgrade() -> None:
    if not _has_table():
        return
    existing = _existing()
    for name, _columns, _event_type in reversed(_INDEXES):
        if name in existing:
            op.drop_index(name, table_name=_TABLE)
