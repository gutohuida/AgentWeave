"""runs that did not judge the work -- task_check_runs.ended_by, and the checks_unjudged stall

Revision ID: 0162
Revises: 0161
Create Date: 2026-11-04 13:00:00.000000

`checks-know-their-phase-and-give-way-to-the-user` (FR-7, FR-9, FR-10). Two moves:

1. `task_check_runs.ended_by`, nullable: what ended a run that did not judge the work (`conflict`,
   `fault`, `timeout`), null for a verdict and for every row written before this revision. Additive,
   on live data: an existing row reads null, which every reader takes as before. No CHECK, so the
   large table is not recreated.
2. `checks_unjudged` joins `ck_stalls_cause`: a task's check run ended twice without judging its
   work, shown on the operator's Needs-you list. The constraint move recreates the small `stalls`
   table with `batch_alter_table`, as `0141` does (SQLite cannot alter a CHECK in place).

Rollback: the downgrade deletes `checks_unjudged` stalls (a notice, not work), restores the
constraint and drops the column (plain `DROP COLUMN`, SQLite 3.35+, as `0161` does); a run that did
not judge the work then reads as an `error` or `failed` row, as before this change.

Guarded for a database without the tables (an upgrade from an early revision) and for a column
already present (a database built by `create_all`).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None

_CAUSES = (
    "loop_stalled",
    "delivery_refused",
    "integration_skipped",
    "integration_failed",
    "review_unstaffed",
    "dead_run",
    "stuck_task",
    "no_progress",
)


def _replace_cause_constraint(causes) -> None:
    quoted = ", ".join(f"'{cause}'" for cause in causes)
    with op.batch_alter_table("stalls", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_stalls_cause", type_="check")
        batch_op.create_check_constraint("ck_stalls_cause", f"cause IN ({quoted})")


def _columns(table: str) -> set:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    columns = _columns("task_check_runs")
    if columns and "ended_by" not in columns:
        op.add_column("task_check_runs", sa.Column("ended_by", sa.String(16), nullable=True))
    if _columns("stalls"):
        _replace_cause_constraint(_CAUSES + ("checks_unjudged",))


def downgrade() -> None:
    if _columns("stalls"):
        op.execute(sa.text("DELETE FROM stalls WHERE cause = 'checks_unjudged'"))
        _replace_cause_constraint(_CAUSES)
    if "ended_by" in _columns("task_check_runs"):
        op.execute(sa.text("ALTER TABLE task_check_runs DROP COLUMN ended_by"))
