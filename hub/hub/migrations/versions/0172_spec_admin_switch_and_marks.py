"""an agent the operator trusts can tidy the specs -- the switch, the marks, an agent's fold

Revision ID: 0172
Revises: 0171
Create Date: 2026-11-09 01:00:00.000000

`an-agent-the-operator-trusts-can-tidy-the-specs`, task `hub-core` (Tier 2).

- `agents.can_admin_specs`, NOT NULL default 0: every existing agent reads off (FR-1).
- `spec_documents.superseded_at/by/reason/successor` and `held_at/held_note`, all nullable: no
  existing document is marked or held (FR-9, FR-11).
- `ck_spec_document_merges_actor_is_operator` widens to admit an agent's fold that names its run:
  `actor_kind = 'operator' OR (actor_kind = 'agent' AND run_id IS NOT NULL)`. SQLite cannot alter a
  CHECK in place, so `spec_document_merges` is rebuilt (`batch_alter_table`, recreate), as 0074
  rebuilt `spec_documents`. Its rows are copied unchanged; `run_id` has existed since 0074.

Runs on the operator's :8000 data at its next restart: back the database up first. Rollback is the
downgrade: delete the agent merge rows (the narrow CHECK would refuse them), restore the CHECK,
drop the six document columns and the agent column (plain `DROP COLUMN`, SQLite 3.35+, as 0171).
The marks and the switches are lost; the tidy events in `spec_document_events` stay, readable as
history.

Guarded for a database without the tables, for columns already present (a database built by
`create_all`) and for columns already absent on downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None

_MERGES = "spec_document_merges"
_CHECK = "ck_spec_document_merges_actor_is_operator"
_WIDE = "actor_kind = 'operator' OR (actor_kind = 'agent' AND run_id IS NOT NULL)"
_NARROW = "actor_kind = 'operator'"
_MARKS = (
    ("superseded_at", lambda: sa.DateTime(timezone=True)),
    ("superseded_by", lambda: sa.String(128)),
    ("superseded_reason", lambda: sa.Text()),
    ("superseded_successor", lambda: sa.String(255)),
    ("held_at", lambda: sa.DateTime(timezone=True)),
    ("held_note", lambda: sa.Text()),
)


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _columns(conn, table: str) -> set:
    return {c["name"] for c in sa.inspect(conn).get_columns(table)}


def _check_sql(conn) -> str:
    row = conn.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": _MERGES},
    ).first()
    return (row[0] or "") if row else ""


def _set_the_merge_check(conn, sql: str) -> None:
    with op.batch_alter_table(_MERGES, recreate="always") as batch_op:
        if _CHECK in _check_sql(conn):
            batch_op.drop_constraint(_CHECK, type_="check")
        batch_op.create_check_constraint(_CHECK, sql)


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if "agents" in present and "can_admin_specs" not in _columns(conn, "agents"):
        op.add_column(
            "agents",
            sa.Column("can_admin_specs", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        )

    if "spec_documents" in present:
        have = _columns(conn, "spec_documents")
        for name, type_ in _MARKS:
            if name not in have:
                op.add_column("spec_documents", sa.Column(name, type_(), nullable=True))

    if _MERGES in present and {"spec_documents", "projects"} <= present:
        if "run_id" not in _columns(conn, _MERGES):
            op.add_column(_MERGES, sa.Column("run_id", sa.String(64), nullable=True))
        if "agent' AND run_id IS NOT NULL" not in _check_sql(conn):
            _set_the_merge_check(conn, _WIDE)


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if _MERGES in present and {"spec_documents", "projects"} <= present:
        # The narrow CHECK would refuse these rows on the rebuild's copy.
        conn.execute(sa.text(f"DELETE FROM {_MERGES} WHERE actor_kind != 'operator'"))
        _set_the_merge_check(conn, _NARROW)

    if "spec_documents" in present:
        have = _columns(conn, "spec_documents")
        for name, _ in reversed(_MARKS):
            if name in have:
                op.execute(sa.text(f"ALTER TABLE spec_documents DROP COLUMN {name}"))

    if "agents" in present and "can_admin_specs" in _columns(conn, "agents"):
        op.execute(sa.text("ALTER TABLE agents DROP COLUMN can_admin_specs"))
