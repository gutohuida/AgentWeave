"""Migration 0152 -- builds, and a task's build, level and builder (`a-build-has-a-driver-a-level-
and-its-people`, slice D, Tier 2).

0152 runs on the operator's real database at their next restart. These pin that it adds the
`builds` table with one running build per document, three nullable columns on `tasks` and one on
`task_transitions`, rewrites no existing row (an existing task reads no build and no level), and that
the downgrade removes exactly what it added and keeps every row it found.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')")}


def _tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


_BUILD = (
    "INSERT INTO builds (id, project_id, document_id, state, driver, level, builders, reviewers, "
    "landing, created_at) VALUES (?, 'proj-old', 'doc-1', ?, 'flow', 'gated', '[]', '[]', 'main', "
    "'2026-10-27T00:00:00')"
)


def test_0152_adds_builds_and_levels_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "builds.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0152')")
        conn.commit()
    _downgrade_to(db_url, "0149")
    with sqlite3.connect(db_file) as conn:
        assert "builds" not in _tables(conn)
        assert not {"build_id", "level", "builder"} & _columns(conn, "tasks")
        assert "level" not in _columns(conn, "task_transitions")
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('proj-old', 'Old', "
            "'2026-10-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO tasks (id, project_id, title, description, status, priority, created_at, "
            "updated, divergence_policy, workspace_scheme) VALUES ('task-old', 'proj-old', 'Old', "
            "'', 'approved', 'medium', '2026-10-01T00:00:00', '2026-10-01T00:00:00', 'surface', "
            "'task')"
        )
        conn.commit()

    _upgrade_to(db_url, "0152")

    with sqlite3.connect(db_file) as conn:
        assert {"build_id", "level", "builder"} <= _columns(conn, "tasks")
        assert "level" in _columns(conn, "task_transitions")
        assert conn.execute(
            "SELECT build_id, level, builder FROM tasks WHERE id = 'task-old'"
        ).fetchone() == (None, None, None)
        conn.execute(_BUILD, ("build-1", "running"))
        conn.execute(_BUILD, ("build-2", "stopped"))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_BUILD, ("build-3", "running"))
        conn.commit()
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('builds')")}
        assert "ux_builds_document_running" in indexes

    _downgrade_to(db_url, "0149")

    with sqlite3.connect(db_file) as conn:
        assert "builds" not in _tables(conn)
        assert not {"build_id", "level", "builder"} & _columns(conn, "tasks")
        assert "level" not in _columns(conn, "task_transitions")
        assert conn.execute("SELECT id, status FROM tasks").fetchall() == [("task-old", "approved")]
