"""Migration 0143 -- a check run may be `superseded` (`checks-wait-less`, FR-3).

0143 runs on the operator's real database at their next restart. These pin that it widens only
`ck_task_check_runs_state`, keeps every existing run as it was, and that the downgrade records a
superseded run as `interrupted` and restores the narrow CHECK.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

_ROW = (
    "INSERT INTO task_check_runs (id, project_id, task_id, main_sha, target_shas, state, results, "
    "error, started_at) VALUES (?, 'proj-old', 'task-old', 'abc', '[]', ?, '[]', '', "
    "'2026-10-24T00:00:00')"
)


def test_0143_admits_superseded_keeps_rows_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "checks.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    # The schema as the models build it, stamped at 0143, then walked down: that is 0142's table.
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0143')")
        conn.commit()
    _downgrade_to(db_url, "0142")
    with sqlite3.connect(db_file) as conn:
        conn.execute(_ROW, ("chk-old", "passed"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_ROW, ("chk-early", "superseded"))
        conn.commit()

    _upgrade_to(db_url, "0143")

    with sqlite3.connect(db_file) as conn:
        conn.execute(_ROW, ("chk-new", "superseded"))
        conn.commit()
        rows = conn.execute("SELECT id, state FROM task_check_runs ORDER BY id").fetchall()
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('task_check_runs')")}
    assert rows == [("chk-new", "superseded"), ("chk-old", "passed")]
    assert "ix_task_check_runs_task" in indexes

    _downgrade_to(db_url, "0142")

    with sqlite3.connect(db_file) as conn:
        rows = conn.execute("SELECT id, state FROM task_check_runs ORDER BY id").fetchall()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_ROW, ("chk-later", "superseded"))
    assert rows == [("chk-new", "interrupted"), ("chk-old", "passed")]
