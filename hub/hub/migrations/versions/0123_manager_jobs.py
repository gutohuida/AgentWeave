"""the Hub's background jobs -- manager_jobs

Revision ID: 0123
Revises: 0122
Create Date: 2026-10-09 00:00:00.000000

`the-hubs-background-jobs-are-configured-on-a-manager-page` (Tier 2). One row per project and job
holding what the operator chose: enabled, runner_id, model. Conversation titling is the first job:
every project whose `conversation_title_mode` is `generate`, or that had chosen a title runner, gets
a `conversation-titles` row (enabled exactly when the mode was `generate`), so titles keep behaving
as configured.

The two project columns are kept, unread, so the downgrade has somewhere to write: it copies each
row's enabled flag and runner back and drops the table. Only the per-job model is lost, and it did
not exist before. A later cleanup migration drops the columns.

Guarded for a table already present (a database built by `create_all` from these models and
stamped at an earlier revision) and for a missing `projects` table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None

_JOB = "conversation-titles"


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "manager_jobs" not in tables:
        op.create_table(
            "manager_jobs",
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("job", sa.String(64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("runner_id", sa.String(64), nullable=True),
            sa.Column("model", sa.String(256), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("project_id", "job", name="pk_manager_jobs"),
        )
    if "projects" not in tables:
        return
    columns = {column["name"] for column in sa.inspect(conn).get_columns("projects")}
    if not {"conversation_title_mode", "conversation_title_runner_id"} <= columns:
        return
    conn.execute(
        sa.text(
            "INSERT INTO manager_jobs (project_id, job, enabled, runner_id, model, updated_at) "
            "SELECT p.id, :job, p.conversation_title_mode = 'generate', "
            "p.conversation_title_runner_id, NULL, CURRENT_TIMESTAMP FROM projects p "
            "WHERE (p.conversation_title_mode = 'generate' "
            "OR p.conversation_title_runner_id IS NOT NULL) "
            "AND NOT EXISTS (SELECT 1 FROM manager_jobs m "
            "WHERE m.project_id = p.id AND m.job = :job)"
        ),
        {"job": _JOB},
    )


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "manager_jobs" not in tables:
        return
    if "projects" in tables:
        row = "FROM manager_jobs m WHERE m.project_id = projects.id AND m.job = :job"
        conn.execute(
            sa.text(
                "UPDATE projects SET "
                "conversation_title_mode = (SELECT CASE WHEN m.enabled THEN 'generate' "
                f"ELSE 'truncate' END {row}), "
                f"conversation_title_runner_id = (SELECT m.runner_id {row}) "
                f"WHERE EXISTS (SELECT 1 {row})"
            ),
            {"job": _JOB},
        )
    op.drop_table("manager_jobs")
