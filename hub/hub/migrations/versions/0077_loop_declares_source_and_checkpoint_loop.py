"""a loop declares its source document; a checkpoint carries which loop it belongs to

Revision ID: 0077
Revises: 0076
Create Date: 2026-08-18 22:50:00.000000

`2026-08-18-a-loop-writes-its-own-queue` design D1/D4. Two additive, nullable columns, no
existing constraint touched — same "no `batch_alter_table` recreate needed" shape as `0075`/`0076`:

(a) `loops.spec_document_id` — deliberately no `ForeignKey`, the identical SQLite-irreversibility
    reasoning `tasks.spec_document_id`/`tasks.loop_id` already state (`models.py:636-647`, restated
    once more on `Loop.spec_document_id` itself rather than a third time here). A unique index
    (`ix_loops_spec_document_id`, named the way `0020`'s `Run.capability_token_hash` names its own
    `unique=True, index=True` column rather than a `uq_`-prefixed name — the model declares both
    flags on the column, and SQLAlchemy's own naming convention for that shape is `ix_<table>_
    <column>`, so a migration-created index under any other name would not match what `create_all`
    produces for a brand-new database, and a later downgrade would silently fail to find it) so at
    most one loop can declare a given document, mirroring `loops.job_id`'s own uniqueness reasoning
    (`0075`).
(b) `checkpoints.loop_id` — same "deliberately not a ForeignKey" shape, design D4. A plain
    (non-unique) index, since many checkpoints belong to one loop.

Guarded for a missing table on every step, matching `0071`/`0073`/`0075`'s own precedent for an
upgrade starting from an early revision.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(conn).get_columns(table)}


def _indexes(conn, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(conn).get_indexes(table)}


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "loops" in present:
        columns = _columns(conn, "loops")
        if "spec_document_id" not in columns:
            # Deliberately no ForeignKey: same SQLite undroppable-column reasoning
            # `tasks.spec_document_id`'s own comment already states, unmodified for this column.
            op.add_column("loops", sa.Column("spec_document_id", sa.String(64), nullable=True))
        if "ix_loops_spec_document_id" not in _indexes(conn, "loops"):
            op.create_index("ix_loops_spec_document_id", "loops", ["spec_document_id"], unique=True)

    if "checkpoints" in present:
        columns = _columns(conn, "checkpoints")
        if "loop_id" not in columns:
            # No ForeignKey either, design D4 — same reasoning as every other loop-adjacent column.
            op.add_column("checkpoints", sa.Column("loop_id", sa.String(64), nullable=True))
        if "ix_checkpoints_loop_id" not in _indexes(conn, "checkpoints"):
            op.create_index("ix_checkpoints_loop_id", "checkpoints", ["loop_id"])


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "checkpoints" in present:
        if "ix_checkpoints_loop_id" in _indexes(conn, "checkpoints"):
            op.drop_index("ix_checkpoints_loop_id", table_name="checkpoints")
        if "loop_id" in _columns(conn, "checkpoints"):
            op.drop_column("checkpoints", "loop_id")

    if "loops" in present:
        if "ix_loops_spec_document_id" in _indexes(conn, "loops"):
            op.drop_index("ix_loops_spec_document_id", table_name="loops")
        if "spec_document_id" in _columns(conn, "loops"):
            op.drop_column("loops", "spec_document_id")
