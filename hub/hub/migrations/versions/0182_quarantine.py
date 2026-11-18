"""Quarantined tests, never-quarantine marks and the two quarantine settings -- quarantine

Revision ID: 0182
Revises: 0181
Create Date: 2026-11-18 09:00:00.000000

`the-slow-checks-run-once-per-landing-not-once-per-task-and-flaky-tests-are-quarantined`, FR-1,
FR-7, FR-8, FR-9. `quarantined_tests` holds each test quarantined for its check; `never_quarantine_
marks` the operator's marks; `projects.quarantine_threshold` (0.05) and `projects.quarantine_exit_
passes` (20) the project's two settings.

Runs on the operator's :8000 data at its next restart. Creates two empty tables and adds two
columns, every existing project taking the defaults from the server default; no existing row is
read, deleted or rewritten, and nothing is quarantined until a flip is recorded after deployment.
The downgrade drops the tables and the columns, losing only quarantine state, marks and settings
(nothing is then excused). Guarded for a database without `projects`, and for tables or columns
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0182"
down_revision = "0181"
branch_labels = None
depends_on = None

_QUARANTINED = "quarantined_tests"
_MARKS = "never_quarantine_marks"
_COLUMNS = (
    ("quarantine_threshold", sa.Float, "0.05"),
    ("quarantine_exit_passes", sa.Integer, "20"),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "projects" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("projects")}
    for name, kind, default in _COLUMNS:
        if name not in columns:
            op.add_column(
                "projects",
                sa.Column(name, kind(), nullable=False, server_default=default),
            )
    if _QUARANTINED not in tables:
        op.create_table(
            _QUARANTINED,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("check_name", sa.String(255), nullable=False),
            sa.Column("test_id", sa.String(1024), nullable=False),
            sa.Column("flake_rate", sa.Float(), nullable=False),
            sa.Column("flips", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("entered_at", sa.DateTime(), nullable=False),
            sa.Column("entered_by_run", sa.String(64), nullable=True),
            sa.Column("passes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fix_task_id", sa.String(64), nullable=True),
        )
        op.create_index(
            "uq_quarantined_tests_test",
            _QUARANTINED,
            ["project_id", "check_name", "test_id"],
            unique=True,
        )
        op.create_index("ix_quarantined_tests_fix_task_id", _QUARANTINED, ["fix_task_id"])
    if _MARKS not in tables:
        op.create_table(
            _MARKS,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("check_name", sa.String(255), nullable=False),
            sa.Column("test_id", sa.String(1024), nullable=False),
            sa.Column("marked_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "uq_never_quarantine_marks_test",
            _MARKS,
            ["project_id", "check_name", "test_id"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if _MARKS in tables:
        op.drop_index("uq_never_quarantine_marks_test", table_name=_MARKS)
        op.drop_table(_MARKS)
    if _QUARANTINED in tables:
        op.drop_index("ix_quarantined_tests_fix_task_id", table_name=_QUARANTINED)
        op.drop_index("uq_quarantined_tests_test", table_name=_QUARANTINED)
        op.drop_table(_QUARANTINED)
    if "projects" in tables:
        columns = {column["name"] for column in inspector.get_columns("projects")}
        for name, _kind, _default in _COLUMNS:
            if name in columns:
                op.execute(sa.text(f"ALTER TABLE projects DROP COLUMN {name}"))
