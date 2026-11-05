"""Migration 0164 -- a check run records when it got its slot (`the-build-card-shows-where-check-
time-went`, FR-1).

0164 runs on the operator's real database at their next restart. These pin that it adds the nullable
`slot_at` to `task_check_runs`, that a run stored before it keeps its row and reads NULL (an unknown
wait, never backfilled), and that the downgrade drops the column again while keeping the row.
"""

from __future__ import annotations

import sqlite3

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_0164_adds_slot_at_keeps_old_runs_and_round_trips(tmp_path):
    db_file = tmp_path / "slots.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0164')")
        conn.commit()

    _downgrade_to(db_url, "0163")
    with sqlite3.connect(db_file) as conn:
        assert "slot_at" not in _columns(conn, "task_check_runs")
        conn.execute(
            "INSERT INTO task_check_runs (id, project_id, task_id, main_sha, target_shas, state, "
            "results, error, started_at, ended_at) VALUES ('chk-old', 'proj-old', 'task-old', "
            "'abc', '[]', 'passed', '[]', '', '2026-11-05 10:00:00', '2026-11-05 11:00:00')"
        )
        conn.commit()

    _upgrade_to(db_url, "0164")
    with sqlite3.connect(db_file) as conn:
        assert "slot_at" in _columns(conn, "task_check_runs")
        assert conn.execute("SELECT id, state, slot_at FROM task_check_runs").fetchall() == [
            ("chk-old", "passed", None)
        ]
        conn.execute("UPDATE task_check_runs SET slot_at = '2026-11-05 10:20:00'")
        conn.commit()

    _downgrade_to(db_url, "0163")
    with sqlite3.connect(db_file) as conn:
        assert "slot_at" not in _columns(conn, "task_check_runs")
        assert conn.execute("SELECT id, state FROM task_check_runs").fetchall() == [
            ("chk-old", "passed")
        ]
