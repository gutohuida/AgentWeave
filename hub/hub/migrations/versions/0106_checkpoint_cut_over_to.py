"""a checkpoint records the conversation it was cut over to

Revision ID: 0106
Revises: 0105
Create Date: 2026-09-25 00:30:00.000000

`a-checkpoint-is-handed-over-once-and-says-where-it-went` (findings F293, F294). Whether a
conversation had been handed over was inferred from its lifecycle, and reopening it cleared the
inference; two presses at once read the same clean state. The handover is now a fact on the
checkpoint: `cut_over_to_conversation_id`, claimed by a conditional UPDATE, backed by a partial
unique index on `conversation_id` so two different checkpoints of one conversation cannot both
hand it over.

**Backfill (design D5).** Every delivered cutover is an `InboundQueueEntry` whose content is the
delivery preamble followed by `# Checkpoint ckpt-...`, addressed to the successor. Walked one row at
a time in `sequence` order, taking each entry's first such id only: a checkpoint is set only if it
is still NULL and no sibling (same conversation) was set by an earlier entry, so a database that
already holds a fork keeps its first handover and the index can still be created. Ids matching no
checkpoint are skipped and counted. It reaches the operator's live database; measured on
2026-09-24 the backfill wrote zero rows there.

Guarded for a missing `checkpoints` table, because an upgrade starting from an early revision
reaches this with only that revision's tables.
"""

from __future__ import annotations

import logging
import re

import sqlalchemy as sa
from alembic import op

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_TABLE = "checkpoints"
_COLUMN = "cut_over_to_conversation_id"
_INDEX = "ix_checkpoints_one_handover_per_conversation"
_PREAMBLE_START = "This conversation continues earlier work.%"
_CHECKPOINT_LINE = re.compile(r"^# Checkpoint (ckpt-\S+)$", re.MULTILINE)


def _columns(conn) -> set[str] | None:
    inspector = sa.inspect(conn)
    if _TABLE not in set(inspector.get_table_names()):
        return None
    return {col["name"] for col in inspector.get_columns(_TABLE)}


def _indexes(conn) -> set[str]:
    if _TABLE not in set(sa.inspect(conn).get_table_names()):
        return set()
    return {idx["name"] for idx in sa.inspect(conn).get_indexes(_TABLE) if idx["name"]}


def _backfill(conn) -> None:
    if "inbound_queue_entries" not in set(sa.inspect(conn).get_table_names()):
        return
    entries = conn.execute(
        sa.text(
            "SELECT conversation_id, content FROM inbound_queue_entries "
            "WHERE origin_type = 'checkpoint' AND content LIKE :preamble ORDER BY sequence"
        ),
        {"preamble": _PREAMBLE_START},
    ).fetchall()
    handed: set[str] = set()  # conversations already handed over by an earlier entry
    set_count = skipped = 0
    for successor_id, content in entries:
        match = _CHECKPOINT_LINE.search(content or "")
        if match is None or successor_id is None:
            skipped += 1
            continue
        row = conn.execute(
            sa.text(f"SELECT conversation_id, {_COLUMN} FROM {_TABLE} WHERE id = :id"),
            {"id": match.group(1)},
        ).first()
        if row is None or row[1] is not None or row[0] in handed:
            skipped += 1
            continue
        conn.execute(
            sa.text(f"UPDATE {_TABLE} SET {_COLUMN} = :successor WHERE id = :id"),
            {"successor": successor_id, "id": match.group(1)},
        )
        handed.add(row[0])
        set_count += 1
    logger.info("0106 backfill: %d checkpoint(s) set, %d entry(ies) skipped", set_count, skipped)


def upgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return
    if _COLUMN not in existing:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(64), nullable=True))
        _backfill(conn)
    if _INDEX not in _indexes(conn):
        op.create_index(
            _INDEX,
            _TABLE,
            ["conversation_id"],
            unique=True,
            sqlite_where=sa.text(f"{_COLUMN} IS NOT NULL"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    existing = _columns(conn)
    if existing is None:
        return
    if _INDEX in _indexes(conn):
        op.drop_index(_INDEX, table_name=_TABLE)
    if _COLUMN in existing:
        op.drop_column(_TABLE, _COLUMN)
