"""add worker invocations

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-08 22:10:00.000000

The accounting surface for out-of-band, single-purpose model calls — checkpoint generation first,
then the blind-resume probe. These are not turns and are deliberately not `runs`: a worker recorded
under an agent's name would make that agent look busy to the turn scheduler and stall its queue.

`runner_id` carries no foreign key. The record must outlive the runner it names, and an audit row
that a runner deletion can cascade away is not an audit row.

Guarded, like 0038-0041, so an upgrade starting from an early revision — or a re-run — does not
collide with a table the model has already created.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_TABLE = "worker_invocations"

_OUTCOMES = (
    "ok",
    "unsupported_cli",
    "unknown_model",
    "spawn_failed",
    "nonzero_exit",
    "timeout",
    "unparseable",
    "schema_invalid",
)


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if _TABLE in tables:
        return
    # Nothing to attach to yet: this revision can be reached by an upgrade that has not created
    # the projects table, in which case the model layer will build this one itself.
    if "projects" not in tables:
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("runner_id", sa.String(64), nullable=True),
        sa.Column("cli", sa.String(16), nullable=False),
        sa.Column("model", sa.String(256), nullable=True),
        sa.Column("conversation_id", sa.String(64), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_write_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd_micros", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('" + "', '".join(_OUTCOMES) + "')",
            name="ck_worker_invocations_outcome",
        ),
        sa.CheckConstraint(
            "error IS NOT NULL OR outcome = 'ok'",
            name="ck_worker_invocations_failure_explained",
        ),
    )
    op.create_index(
        "ix_worker_invocations_conversation_id", _TABLE, ["conversation_id"]
    )
    op.create_index(
        "ix_worker_invocations_project_created", _TABLE, ["project_id", "created_at"]
    )
    op.create_index("ix_worker_invocations_project_kind", _TABLE, ["project_id", "kind"])


def downgrade() -> None:
    if _TABLE not in _tables(op.get_bind()):
        return
    op.drop_index("ix_worker_invocations_project_kind", table_name=_TABLE)
    op.drop_index("ix_worker_invocations_project_created", table_name=_TABLE)
    op.drop_index("ix_worker_invocations_conversation_id", table_name=_TABLE)
    op.drop_table(_TABLE)
