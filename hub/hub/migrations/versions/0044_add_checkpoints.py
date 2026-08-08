"""add checkpoints

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-08 23:20:00.000000

The checkpoint record: a structured envelope the Hub computes and can therefore check, carrying
one markdown body only the model can write.

`status <> 'ready' OR body IS NOT NULL` is the constraint that matters. The defect this change
removes is a readiness signal that meant "the run stopped" — a checkpoint with nothing in it was
reported ready twice, observed. Making that state unrepresentable at the schema level means no
future code path can reintroduce it by accident.

Guarded, like 0038-0043.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None

_TABLE = "checkpoints"

_TRIGGERS = (
    "context_pressure",
    "operator",
    "delegation",
    "run_failure",
    "task_completion",
)
_STATUSES = ("ready", "unwritten", "failed")
_VISIBILITIES = ("private", "project", "granted")


def _tables(conn) -> set[str]:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    tables = _tables(op.get_bind())
    if _TABLE in tables:
        return
    # Reachable by an upgrade that has not created what this table points at; the model layer
    # builds it in that case.
    if "projects" not in tables or "conversations" not in tables:
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(64),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("agent", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="private"),
        sa.Column("previous_checkpoint_id", sa.String(64), nullable=True),
        sa.Column("lineage_id", sa.String(64), nullable=False),
        sa.Column("covers_from_run_id", sa.String(64), nullable=True),
        sa.Column("covers_through_run_id", sa.String(64), nullable=True),
        sa.Column("worker_invocation_id", sa.String(64), nullable=True),
        sa.Column("runner", sa.String(32), nullable=True),
        sa.Column("model", sa.String(256), nullable=True),
        sa.Column("files_changed", sa.JSON(), nullable=True),
        sa.Column("tasks", sa.JSON(), nullable=True),
        sa.Column("open_questions", sa.JSON(), nullable=True),
        sa.Column("permission_decisions", sa.JSON(), nullable=True),
        sa.Column("runtime_overrides", sa.JSON(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("probe_status", sa.String(16), nullable=True),
        sa.Column("probe_findings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "trigger IN ('" + "', '".join(_TRIGGERS) + "')", name="ck_checkpoints_trigger"
        ),
        sa.CheckConstraint(
            "status IN ('" + "', '".join(_STATUSES) + "')", name="ck_checkpoints_status"
        ),
        sa.CheckConstraint(
            "visibility IN ('" + "', '".join(_VISIBILITIES) + "')",
            name="ck_checkpoints_visibility",
        ),
        sa.CheckConstraint(
            "status <> 'ready' OR body IS NOT NULL", name="ck_checkpoints_ready_has_a_body"
        ),
    )
    op.create_index("ix_checkpoints_conversation_id", _TABLE, ["conversation_id"])
    op.create_index("ix_checkpoints_agent", _TABLE, ["agent"])
    op.create_index("ix_checkpoints_lineage_id", _TABLE, ["lineage_id"])
    op.create_index(
        "ix_checkpoints_conversation_created", _TABLE, ["conversation_id", "created_at"]
    )
    op.create_index("ix_checkpoints_project_agent", _TABLE, ["project_id", "agent"])


def downgrade() -> None:
    if _TABLE not in _tables(op.get_bind()):
        return
    for index in (
        "ix_checkpoints_project_agent",
        "ix_checkpoints_conversation_created",
        "ix_checkpoints_lineage_id",
        "ix_checkpoints_agent",
        "ix_checkpoints_conversation_id",
    ):
        op.drop_index(index, table_name=_TABLE)
    op.drop_table(_TABLE)
