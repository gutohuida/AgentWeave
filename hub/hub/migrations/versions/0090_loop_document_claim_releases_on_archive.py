"""an archived loop's document claim no longer blocks a new loop forever

Revision ID: 0090
Revises: 0089
Create Date: 2026-08-26 03:55:00.000000

F53. `loops.spec_document_id` carried an unconditional `unique=True` (`0077`,
`ix_loops_spec_document_id`), so a loop's row keeps occupying its document even after the loop is
archived. `_check_spec_document_conflict` (`hub/hub/api/v1/jobs.py`) can be taught to ignore
archived loops — and now is — but the INSERT for a replacement loop still hits this same
unconditional index and fails with a raw `IntegrityError`, not the intended 409. Live reproduction,
2026-08-26: create a loop against a document, archive it (one call, no second step), try to create
a second loop against the same document — permanent conflict, forever, confirmed against the row
data directly (`loop_id` still stamped on the tasks it had adopted).

This does not resolve F53 in full: the tasks an archived loop already adopted keep its `loop_id`
(the caller-side `_adopt_document_tasks` guard is unchanged), which is a genuine judgement call
about already-started work, left for the operator. This closes only the decision-free half — a
document is not permanently unusable just because the loop that first claimed it was archived.

Replaces the unconditional unique index with a partial one, unique only where `archived_at IS
NULL` — the same "one live claimant" guarantee, scoped to loops still alive. Safe against existing
data: the old index already enforced global uniqueness, so no subset of live rows can violate the
narrower constraint either. Guarded for a missing table/index, matching `0033`/`0034`'s own
precedent for an upgrade starting from an early revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None

_TABLE = "loops"
_OLD_INDEX = "ix_loops_spec_document_id"
_NEW_INDEX = "ux_loops_spec_document_live"


def _indexes(conn) -> set[str]:
    if _TABLE not in set(sa.inspect(conn).get_table_names()):
        return set()
    return {idx["name"] for idx in sa.inspect(conn).get_indexes(_TABLE) if idx["name"]}


def upgrade() -> None:
    conn = op.get_bind()
    existing = _indexes(conn)
    if not existing and _TABLE not in set(sa.inspect(conn).get_table_names()):
        return

    if _OLD_INDEX in existing:
        op.drop_index(_OLD_INDEX, table_name=_TABLE)
    # A plain (non-unique) index under the old name, matching the model's `index=True` and
    # SQLAlchemy's own default naming convention for a bare-`index=True` column — a later
    # `create_all` on a fresh database would otherwise disagree with what this migration leaves.
    if _OLD_INDEX not in _indexes(conn):
        op.create_index(_OLD_INDEX, _TABLE, ["spec_document_id"])
    if _NEW_INDEX not in _indexes(conn):
        op.create_index(
            _NEW_INDEX,
            _TABLE,
            ["spec_document_id"],
            unique=True,
            sqlite_where=sa.text("archived_at IS NULL"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _TABLE not in set(sa.inspect(conn).get_table_names()):
        return
    existing = _indexes(conn)

    if _NEW_INDEX in existing:
        op.drop_index(_NEW_INDEX, table_name=_TABLE)
    if _OLD_INDEX in existing:
        op.drop_index(_OLD_INDEX, table_name=_TABLE)
    if _OLD_INDEX not in _indexes(conn):
        op.create_index(_OLD_INDEX, _TABLE, ["spec_document_id"], unique=True)
