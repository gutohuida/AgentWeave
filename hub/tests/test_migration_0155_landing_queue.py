"""Migration 0155 -- the landing queue and its batches (`approved-work-merges-in-batches`, slice E,
Tier 2).

0155 runs on the operator's real database at their next restart. These pin that it adds the two
tables and two nullable columns on `task_integrations`, rewrites no existing row (an integration
recorded before reads no batch and no override), and that the downgrade removes exactly what it added
and keeps every row it found.
"""

from __future__ import annotations

import sqlite3

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')")}


def _tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_0155_adds_the_landing_queue_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "landing.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0155')")
        conn.commit()
    _downgrade_to(db_url, "0152")
    with sqlite3.connect(db_file) as conn:
        assert not {"task_landings", "landing_batches"} & _tables(conn)
        assert not {"batch_id", "override_reason"} & _columns(conn, "task_integrations")
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
        conn.execute(
            "INSERT INTO task_integrations (id, project_id, task_id, outcome, reason, "
            "rode_along_commits, mechanism, actor_kind, actor, created_at) VALUES ('tint-old', "
            "'proj-old', 'task-old', 'merged', '', '', 'local', 'operator', 'operator', "
            "'2026-10-01T00:00:00')"
        )
        conn.commit()

    _upgrade_to(db_url, "0155")

    with sqlite3.connect(db_file) as conn:
        assert {"task_landings", "landing_batches"} <= _tables(conn)
        assert {"batch_id", "override_reason"} <= _columns(conn, "task_integrations")
        assert conn.execute(
            "SELECT batch_id, override_reason FROM task_integrations WHERE id = 'tint-old'"
        ).fetchone() == (None, None)
        conn.execute(
            "INSERT INTO task_landings (id, project_id, task_id, order_key, created_at, "
            "updated_at) VALUES ('land-1', 'proj-old', 'task-old', 1.0, '2026-10-27T00:00:00', "
            "'2026-10-27T00:00:00')"
        )
        assert conn.execute(
            "SELECT state, kind, unchecked, reason FROM task_landings WHERE id = 'land-1'"
        ).fetchone() == ("queued", "approval", 0, "")
        conn.execute(
            "INSERT INTO landing_batches (id, project_id, base_sha, task_ids, prefixes, results, "
            "narrowing, created_at) VALUES ('lbat-1', 'proj-old', 'abc', '[]', '[]', '[]', '[]', "
            "'2026-10-27T00:00:00')"
        )
        conn.commit()

    _downgrade_to(db_url, "0152")

    with sqlite3.connect(db_file) as conn:
        assert not {"task_landings", "landing_batches"} & _tables(conn)
        assert not {"batch_id", "override_reason"} & _columns(conn, "task_integrations")
        assert conn.execute("SELECT id, outcome FROM task_integrations").fetchall() == [
            ("tint-old", "merged")
        ]
        assert conn.execute("SELECT id, status FROM tasks").fetchall() == [("task-old", "approved")]
