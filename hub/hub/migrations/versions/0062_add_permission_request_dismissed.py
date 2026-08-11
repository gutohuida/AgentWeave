"""add the dismissed state to permission requests

Revision ID: 0062
Revises: 0061
Create Date: 2026-08-11 16:05:00.000000

`permission_requests.dismissed` and `permission_requests.dismissed_at` — the operator has finished
looking at an expired request and cleared it from view.

Beside `status` rather than folded into it, for the same reason `questions.declined` sits beside
`answered` in 0061. `status` is the run-facing fact: what the agent was told, and the record of who
authorised what. Tidying a card away says nothing about that, and a "dismissed" status would read
as a decision to every reader of the column — including the run's own poll loop.

`dismissed` is NOT NULL with a server default of false, because SQLite rewrites the table to add a
NOT NULL column and existing rows need a value from the database rather than from the ORM.

**No backfill, and the absence is the decision.** Expired requests that predate this column stay
visible. Marking them dismissed would claim the operator cleared something they were never shown a
way to clear, and the whole point of keeping an expired card is that the operator sees it.

Guarded, like 0038-0061.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

_REQUESTS = "permission_requests"
_DISMISSED = "dismissed"
_DISMISSED_AT = "dismissed_at"


def _columns(conn, table):
    inspector = sa.inspect(conn)
    if table not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()

    requests = _columns(conn, _REQUESTS)
    if requests is None:
        return
    if _DISMISSED not in requests:
        op.add_column(
            _REQUESTS,
            sa.Column(_DISMISSED, sa.Boolean(), nullable=False, server_default="0"),
        )
    if _DISMISSED_AT not in requests:
        op.add_column(
            _REQUESTS, sa.Column(_DISMISSED_AT, sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()

    requests = _columns(conn, _REQUESTS)
    if requests is None:
        return
    if _DISMISSED_AT in requests:
        op.drop_column(_REQUESTS, _DISMISSED_AT)
    if _DISMISSED in requests:
        op.drop_column(_REQUESTS, _DISMISSED)
