"""give a document an archived phase and a capability kind that lives outside the phase machine

Revision ID: 0074
Revises: 0073
Create Date: 2026-08-16 22:40:00.000000

`spec_lifecycle`'s phase machine has always stopped at `approved` — there was no way to say a
change's work is finished and its record is now history, and no way to hold a document describing
current, shipped behaviour rather than a change under discussion. This closes both gaps.

`archived` is reachable only from `approved` (an operator act, enforced in `transition()` the same
way approval already is — see `spec_lifecycle.py`), and has no transition back out. `current` is
reachable only through document creation (`kind == "capability"`), never through `transition()` at
all — a capability document is created there and stays there.

Two new CHECKs land alongside the phase CHECK's recreate, at no extra cost since the table is
already being rebuilt: `kind` has never been constrained at the database layer before (the original
`0065` table just declares it `String(32)`), so `ck_spec_documents_kind` is the first statement of
its vocabulary as a real constraint, not just `spec_payload.KINDS`' say-so at the Python layer.
`ck_spec_documents_kind_phase` ties `kind = 'capability'` to `phase = 'current'` in both directions —
the strongest available statement that a capability document's phase is never anything else and no
other document's phase is ever `current`, enforceable even against a row inserted by something other
than `spec_lifecycle.create_document`. Both are the same shape `0058` already uses to tie
`origin_type` and `origin_agent` together.

`spec_document_merges` is new: one row per (capability document, change document) an operator has
folded together. `actor_kind = 'operator'` is a *stronger* CHECK than the generic `actor_kind IN
(...)` every other actor-kind column in this schema uses, because this table exists specifically to
make the operator's-authorship rule true even against a caller that reaches it directly.

Table recreation for `spec_documents`, because SQLite cannot alter a CHECK constraint in place — the
same approach `0035`/`0058`/`0073` take, including the guard on `projects`, whose foreign key
reflection would otherwise raise on a database alembic reaches without `create_all`.
`spec_document_merges` is a plain guarded `create_table`, following `0065`'s
`spec_document_events` exactly: the table is new, so there is no existing CHECK to fight SQLite's
in-place-ALTER limitation on.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

# Mirrors spec_payload.KINDS plus "capability" (task 4.4/4.5 in the openspec change) — this file
# cannot import hub.spec_payload (migrations run standalone), so the vocabulary is restated here the
# same way every other migration that recreates a CHECK restates its own values.
_KINDS = ("baseline", "system-map", "roadmap", "change-spec", "capability")
_PHASES = ("exploring", "proposed", "approved", "archived", "current")
_MERGE_TABLE = "spec_document_merges"


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def _widen_the_phase_check() -> None:
    with op.batch_alter_table("spec_documents", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_spec_documents_phase", type_="check")
        batch_op.create_check_constraint(
            "ck_spec_documents_phase", "phase IN ('" + "', '".join(_PHASES) + "')"
        )


def _add_the_kind_checks() -> None:
    with op.batch_alter_table("spec_documents", recreate="always") as batch_op:
        batch_op.create_check_constraint(
            "ck_spec_documents_kind", "kind IN ('" + "', '".join(_KINDS) + "')"
        )
        batch_op.create_check_constraint(
            "ck_spec_documents_kind_phase",
            "(kind = 'capability' AND phase = 'current') OR "
            "(kind != 'capability' AND phase != 'current')",
        )


def upgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if {"spec_documents", "projects"} <= present:
        # Three steps, for the mirror image of the reason `downgrade()` needs three — see the
        # comment there. The rewrite in the middle has to happen while the phase CHECK is already
        # wide enough to allow `current` but the paired CHECK is not yet in force to forbid the
        # `(capability, approved)` state the rows are arriving in.
        _widen_the_phase_check()

        # The inverse of the downgrade's rewrite, and the thing that makes rollback two-way rather
        # than one-way. On a database reaching 0074 for the first time this matches nothing —
        # `capability` was not in the kind vocabulary before this migration, so no such row can
        # exist. It matters only for a database that has been *down* to 0073 and is coming back:
        # the downgrade parks capability documents at `approved` because `current` no longer
        # exists, and `ck_spec_documents_kind_phase` would then reject the rows it copies.
        conn.execute(
            sa.text("UPDATE spec_documents SET phase = 'current' WHERE kind = 'capability'")
        )

        _add_the_kind_checks()

    if _MERGE_TABLE not in present and {"spec_documents", "projects"} <= present:
        op.create_table(
            _MERGE_TABLE,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column(
                "capability_document_id",
                sa.String(64),
                sa.ForeignKey("spec_documents.id"),
                nullable=False,
            ),
            sa.Column(
                "change_document_id",
                sa.String(64),
                sa.ForeignKey("spec_documents.id"),
                nullable=False,
            ),
            sa.Column("actor_kind", sa.String(16), nullable=False),
            sa.Column("actor", sa.String(128), nullable=False, server_default=""),
            sa.Column("run_id", sa.String(64), nullable=True),
            sa.Column("note", sa.String(2000), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "actor_kind = 'operator'", name="ck_spec_document_merges_actor_is_operator"
            ),
        )
        op.create_index(
            "ix_spec_document_merges_capability",
            _MERGE_TABLE,
            ["capability_document_id", "created_at"],
        )
        op.create_index(
            "ix_spec_document_merges_change", _MERGE_TABLE, ["change_document_id", "created_at"]
        )


def downgrade() -> None:
    conn = op.get_bind()
    present = _tables(conn)

    if _MERGE_TABLE in present:
        op.drop_index("ix_spec_document_merges_change", table_name=_MERGE_TABLE)
        op.drop_index("ix_spec_document_merges_capability", table_name=_MERGE_TABLE)
        op.drop_table(_MERGE_TABLE)

    if {"spec_documents", "projects"} <= present:
        # Three steps, and the order is the whole difficulty: the rows have to be rewritten while
        # neither the constraint they currently satisfy nor the constraint they will end up
        # satisfying is in force. A capability row is `(kind='capability', phase='current')`, so
        # `ck_spec_documents_kind_phase` rejects moving it to `approved`; but the narrowed phase
        # CHECK rejects leaving it at `current`, and a batch recreate applies its new CHECKs to the
        # copied rows, so a single recreate cannot straddle the rewrite either way.
        #
        # So: drop the paired CHECK first (recreate 1), rewrite the rows while only the wide
        # five-value phase CHECK is in force, then narrow that CHECK (recreate 2).
        with op.batch_alter_table("spec_documents", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_spec_documents_kind_phase", type_="check")
            batch_op.drop_constraint("ck_spec_documents_kind", type_="check")

        # `archived` and `current` are recoverable states, not data to discard: the closest
        # existing phase for both is `approved` — the state an archived document was in
        # immediately beforehand, and the closest existing meaning to "settled, not being decided
        # about" for a capability document, the same choice `0058`'s own downgrade makes for a
        # retired value with no equivalent left.
        conn.execute(
            sa.text(
                "UPDATE spec_documents SET phase = 'approved' "
                "WHERE phase IN ('archived', 'current')"
            )
        )

        with op.batch_alter_table("spec_documents", recreate="always") as batch_op:
            batch_op.drop_constraint("ck_spec_documents_phase", type_="check")
            batch_op.create_check_constraint(
                "ck_spec_documents_phase",
                "phase IN ('exploring', 'proposed', 'approved')",
            )
