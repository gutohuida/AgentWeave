"""Migration 0162 -- runs that did not judge the work (`checks-know-their-phase-and-give-way-to-the-
user`, FR-7-FR-10).

0162 runs on the operator's real database at their next restart. These pin that it adds a nullable
`task_check_runs.ended_by` (every existing run reads null, as before), lets `stalls.cause` be
`checks_unjudged` while keeping the table's rows and its one-open-stall-per-key index, and that the
downgrade drops the column, deletes only the new kind of stall and restores the old constraint.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

from .test_migration_0151_the_hub_may_override_checks import _add_project

_STALL = (
    "INSERT INTO stalls (id, project_id, key, cause, reason, first_seen_at, last_seen_at, "
    "seen_count, mender_turns, outcome, outcome_detail) VALUES (?, 'proj-old', ?, ?, 'why', "
    "'2026-11-04T00:00:00', '2026-11-04T00:00:00', 1, 0, 'open', '')"
)


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _open_key_index(conn) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'ix_stalls_open_key'"
    ).fetchone()
    return (row[0] or "") if row else ""


def test_0162_adds_ended_by_and_the_unjudged_stall_and_round_trips(tmp_path):
    db_file = tmp_path / "unjudged.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0162')")
        conn.commit()
    _downgrade_to(db_url, "0161")
    with sqlite3.connect(db_file) as conn:
        assert "ended_by" not in _columns(conn, "task_check_runs")
        _add_project(conn, "proj-old")
        conn.execute(_STALL, ("stall-old", "dead_run:run-1", "dead_run"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_STALL, ("stall-new", "checks_unjudged:task-1", "checks_unjudged"))
        conn.execute(
            "INSERT INTO task_check_runs (id, project_id, task_id, main_sha, target_shas, state, "
            "results, error, started_at) VALUES ('chk-old', 'proj-old', 'task-old', 'a', '[]', "
            "'error', '[]', 'x does not merge cleanly', '2026-11-04T00:00:00')"
        )
        conn.commit()

    _upgrade_to(db_url, "0162")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT ended_by FROM task_check_runs").fetchall() == [(None,)]
        conn.execute(_STALL, ("stall-new", "checks_unjudged:task-1", "checks_unjudged"))
        conn.commit()
        assert sorted(conn.execute("SELECT id, cause FROM stalls")) == [
            ("stall-new", "checks_unjudged"),
            ("stall-old", "dead_run"),
        ]
        index = _open_key_index(conn)
        assert "UNIQUE" in index.upper() and "ended_at IS NULL" in index, index
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_STALL, ("stall-twice", "checks_unjudged:task-1", "checks_unjudged"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_STALL, ("stall-bad", "nonsense:1", "nonsense"))

    _downgrade_to(db_url, "0161")

    with sqlite3.connect(db_file) as conn:
        assert "ended_by" not in _columns(conn, "task_check_runs")
        assert [row[0] for row in conn.execute("SELECT id FROM stalls")] == ["stall-old"]
        assert conn.execute("SELECT count(*) FROM task_check_runs").fetchone() == (1,)
        assert "ended_at IS NULL" in _open_key_index(conn)
