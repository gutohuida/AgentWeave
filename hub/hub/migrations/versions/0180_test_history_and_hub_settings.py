"""Per-test history and the Hub's check concurrency -- test_history, hub_settings

Revision ID: 0180
Revises: 0179
Create Date: 2026-11-17 15:00:00.000000

`landing-time-and-test-flakiness-are-measured`, FR-5, FR-6, FR-10. `test_history` holds one row per
test per check run, from which a test's flake rate and last flip are read; `hub_settings` holds the
Hub's own settings, its check concurrency first.

Runs on the operator's :8000 data at its next restart. Creates two new tables; no existing row is
read, deleted or rewritten, and history starts empty (nothing is rebuilt from older runs). The
downgrade drops both tables, losing only the recorded history and the setting (the Hub then runs
its default of 2 checks at once). Guarded for a table already present (a database built by
`create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0180"
down_revision = "0179"
branch_labels = None
depends_on = None

_HISTORY = "test_history"
_SETTINGS = "hub_settings"
_INDEXES = (
    ("ix_test_history_test", ["project_id", "check_name", "test_id", "id"]),
    ("ix_test_history_run", ["check_run_id"]),
)


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if _HISTORY not in tables:
        op.create_table(
            _HISTORY,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("check_name", sa.String(255), nullable=False),
            sa.Column("test_id", sa.String(1024), nullable=False),
            sa.Column("file", sa.String(1024), nullable=False, server_default=""),
            sa.Column("outcome", sa.String(16), nullable=False),
            sa.Column("check_run_id", sa.String(64), nullable=False),
            sa.Column("phase", sa.String(16), nullable=False),
            sa.Column("commit_sha", sa.String(64), nullable=True),
            sa.Column("recorded_at", sa.DateTime(), nullable=False),
        )
        for name, columns in _INDEXES:
            op.create_index(name, _HISTORY, columns)
    if _SETTINGS not in tables:
        op.create_table(
            _SETTINGS,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("check_concurrency", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if _SETTINGS in tables:
        op.drop_table(_SETTINGS)
    if _HISTORY in tables:
        for name, _columns in _INDEXES:
            op.drop_index(name, table_name=_HISTORY)
        op.drop_table(_HISTORY)
