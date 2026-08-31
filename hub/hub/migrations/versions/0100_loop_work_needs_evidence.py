"""a loop declares whether its work needs evidence before it reaches the main branch

Revision ID: 0100
Revises: 0099
Create Date: 2026-08-31 04:30:00.000000

Break 1 of `2026-08-30-why-a-flow-cannot-land-its-work`, filed as F124.

A loop with no spec document has no requirements, so its tasks carry no `TaskRequirementLink`, so
`task_integration.integration_targets` is structurally empty for them — forever, since there is no
requirement any evidence could ever be recorded against. Approval therefore records "no accepted
evidence names a commit, so there is nothing to merge" while the work sits committed on
`agentweave/task/<id>`, approved and unreachable from the main branch. The record is true about the
evidence and false about the world.

The column is where the operator says which of the two regimes a loop is in. NULL is not "false":
it means "the product's current default", resolved at the point of use by
`task_integration.merge_targets`, for the reason `loops.control` already gives — a row that stores
today's default keeps asserting it after the default moves. Nullable also keeps "the operator said
no" and "the operator did not say" distinguishable, so a later change of default is one line rather
than a data migration.

No backfill, and deliberately no server default. `loops` holds flows as well as loops (a flow is a
`Loop` with a `spec_document_id`), so a `server_default` of either value would silently answer this
question for every flow in every existing database. The resolver reads `spec_document_id` before it
reaches any default, which is what keeps `approval-refuses-unaccepted-evidence` load-bearing for
flows; that only works while this column stays NULL for them.

Guarded for a missing table the way `0033`/`0034`/`0075`/`0095`/`0096`/`0097`/`0098` are: an
upgrade starting from an early revision reaches here with only that revision's tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None

_TABLE = "loops"
_COLUMN = "work_needs_evidence"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def upgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in _tables(conn):
        return
    if _COLUMN not in _columns(conn, _TABLE):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.Boolean(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE in _tables(conn) and _COLUMN in _columns(conn, _TABLE):
        op.drop_column(_TABLE, _COLUMN)
