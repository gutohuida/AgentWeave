"""failures already known are on a list -- known_failing_tests, unlisted_test_failures,
main_check_runs

Revision ID: 0166
Revises: 0165
Create Date: 2026-11-06 03:00:00.000000

`failures-already-known-are-on-a-list-not-re-argued` (Tier 2), task `list`. Each project keeps one
list of tests known to fail on main or known to be flaky, each entry with its owner fix task
(`known_failing_tests`, FR-1); the last task to fail a test not on the list, so a second task
failing it next triggers one re-run of it on main (`unlisted_test_failures`, FR-13); and the runs on
main's tree no task asked for (`main_check_runs`, FR-3, FR-13).

**Seeded, on live data** (FR-1, `ac-seeded`): one entry for each test named by a fix task the Hub
filed (a `checks_fix_task_filed` event row, `flaky_tests.FIX_TASK_EVENT`) whose task is still open
(not `approved` or `rejected`) now, with that task as its owner, its kind from the event's `kinds`,
first and last seen at the event's time, and the event's run as the run that added it. Where one
test was filed twice, the latest filing owns it, as `flaky_tests.fix_tasks_by_test` reads them. The
check is the event's one check, or where it names several, the one whose result in the filing run
named the test. Only the three new tables are written; no existing row is read for writing or
changed.

Downgrade drops the three tables, and with them the list: nothing else is touched, and the gates
until task `gates` lands read nothing from it.

Guarded for a database without the tables it reads (an upgrade from an early revision) and for a
table already present (a database built by `create_all`, which is then not seeded twice).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from alembic import op

revision = "0166"
down_revision = "0165"
branch_labels = None
depends_on = None

FIX_TASK_EVENT = "checks_fix_task_filed"
CLOSED = ("approved", "rejected")
FAILS_ON_MAIN = "fails on main"
FLAKY = "flaky"


def _tables(conn) -> set:
    return set(sa.inspect(conn).get_table_names())


def _indexes(conn, table: str) -> set:
    return {i["name"] for i in sa.inspect(conn).get_indexes(table)}


def _json(value: Any) -> Any:
    if isinstance(value, (bytes, str)):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def _check_of(conn, data: Dict[str, Any], test: str) -> str:
    """The check a filed test belongs to: the event's one check, else the one whose result in the
    filing run named it, else the first the event names."""
    checks = [str(c) for c in data.get("checks") or [] if c]
    if len(checks) == 1:
        return checks[0]
    run_id = data.get("run_id")
    if run_id and "task_check_runs" in _tables(conn):
        row = conn.execute(
            sa.text("SELECT results FROM task_check_runs WHERE id = :id"), {"id": run_id}
        ).first()
        for result in (_json(row[0]) if row is not None else None) or []:
            if not isinstance(result, dict):
                continue
            named = [
                *(result.get("shared_tests") or []),
                *(result.get("flaky_tests") or []),
                *(result.get("failed_tests") or []),
                *((result.get("flaky") or {}).get("tests") or []),
            ]
            if test in [str(t).strip() for t in named]:
                return str(result.get("name") or "check")
    return checks[0] if checks else "check"


def _seed(conn) -> None:
    tables = _tables(conn)
    if "event_logs" not in tables or "tasks" not in tables:
        return
    rows = conn.execute(
        sa.text(
            "SELECT project_id, data, timestamp FROM event_logs WHERE event_type = :kind "
            "ORDER BY timestamp ASC, id ASC"
        ),
        {"kind": FIX_TASK_EVENT},
    ).all()
    filings = []
    for project_id, raw, timestamp in rows:
        data = _json(raw)
        if isinstance(data, dict) and data.get("task_id"):
            filings.append((project_id, data, timestamp))
    if not filings:
        return
    statuses = {
        row[0]: row[1]
        for row in conn.execute(
            sa.text("SELECT id, status FROM tasks WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            {"ids": sorted({data["task_id"] for _, data, _ in filings})},
        ).all()
    }
    # (project, test) -> (data, timestamp): the latest filing whose task is still open.
    latest: Dict[Tuple[str, str], Tuple[Dict[str, Any], Any]] = {}
    for project_id, data, timestamp in filings:
        status = statuses.get(data["task_id"])
        if status is None or status in CLOSED:
            continue
        for test in data.get("tests") or []:
            key = str(test).strip()
            if key:
                latest[(project_id, key)] = (data, timestamp)
    seen: set = set()
    entries: List[Dict[str, Optional[Any]]] = []
    for (project_id, test), (data, timestamp) in latest.items():
        check = _check_of(conn, data, test)
        if (project_id, check, test) in seen:
            continue
        seen.add((project_id, check, test))
        kinds = data.get("kinds") if isinstance(data.get("kinds"), dict) else {}
        kind = FLAKY if kinds.get(test) == FLAKY else FAILS_ON_MAIN
        entries.append(
            {
                "id": f"kf-{uuid.uuid4().hex[:12]}",
                "project_id": project_id,
                "check_name": check,
                "test": test,
                "kind": kind,
                "added_by_run": data.get("run_id"),
                "fix_task_id": data["task_id"],
                "at": timestamp,
            }
        )
    for entry in entries:
        # The event's own stored time is copied as stored: no live value is re-encoded.
        conn.execute(
            sa.text(
                "INSERT INTO known_failing_tests (id, project_id, check_name, test, kind, "
                "first_seen, last_seen, added_by_run, fix_task_id, passes, counted_runs) "
                "VALUES (:id, :project_id, :check_name, :test, :kind, :at, :at, :added_by_run, "
                ":fix_task_id, 0, '[]')"
            ),
            entry,
        )


def upgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    if "projects" not in tables:
        return
    created = "known_failing_tests" not in tables
    if created:
        op.create_table(
            "known_failing_tests",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("check_name", sa.String(255), nullable=False),
            sa.Column("test", sa.String(1024), nullable=False, server_default=""),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("first_seen", sa.DateTime(), nullable=False),
            sa.Column("last_seen", sa.DateTime(), nullable=False),
            sa.Column("added_by_run", sa.String(64), nullable=True),
            sa.Column("fix_task_id", sa.String(64), nullable=True),
            sa.Column("passes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("counted_runs", sa.JSON(), nullable=False, server_default="[]"),
        )
    indexes = _indexes(conn, "known_failing_tests")
    if "uq_known_failing_tests_test" not in indexes:
        op.create_index(
            "uq_known_failing_tests_test",
            "known_failing_tests",
            ["project_id", "check_name", "test"],
            unique=True,
        )
    if "ix_known_failing_tests_fix_task_id" not in indexes:
        op.create_index(
            "ix_known_failing_tests_fix_task_id", "known_failing_tests", ["fix_task_id"]
        )
    if "unlisted_test_failures" not in tables:
        op.create_table(
            "unlisted_test_failures",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("check_name", sa.String(255), nullable=False),
            sa.Column("test", sa.String(1024), nullable=False),
            sa.Column("task_id", sa.String(64), nullable=False),
            sa.Column("run_id", sa.String(64), nullable=False),
            sa.Column("at", sa.DateTime(), nullable=False),
        )
    if "uq_unlisted_test_failures_test" not in _indexes(conn, "unlisted_test_failures"):
        op.create_index(
            "uq_unlisted_test_failures_test",
            "unlisted_test_failures",
            ["project_id", "check_name", "test"],
            unique=True,
        )
    if "main_check_runs" not in tables:
        op.create_table(
            "main_check_runs",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("main_sha", sa.String(64), nullable=False),
            sa.Column("reason", sa.String(32), nullable=False),
            sa.Column("tests", sa.JSON(), nullable=False),
            sa.Column("state", sa.String(16), nullable=False),
            sa.Column("results", sa.JSON(), nullable=False),
            sa.Column("error", sa.Text(), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
        )
    if "ix_main_check_runs_project" not in _indexes(conn, "main_check_runs"):
        op.create_index(
            "ix_main_check_runs_project", "main_check_runs", ["project_id", "main_sha", "reason"]
        )
    if created:
        _seed(conn)


def downgrade() -> None:
    conn = op.get_bind()
    tables = _tables(conn)
    for table in ("main_check_runs", "unlisted_test_failures", "known_failing_tests"):
        if table in tables:
            for name in _indexes(conn, table):
                op.drop_index(name, table_name=table)
            op.drop_table(table)
