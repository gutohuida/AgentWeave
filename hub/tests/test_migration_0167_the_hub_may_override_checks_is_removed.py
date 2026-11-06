"""Migration 0167 -- 'The Hub may override checks' is removed
(`failures-already-known-are-on-a-list-not-re-argued`, FR-15, task `ui`).

0167 runs on the operator's real database at their next restart. These pin that it drops
`projects.checks_auto_override` and nothing else -- every project row and every other column value
survives -- and that the downgrade adds the column back, on (its old default) for every project.
"""

from __future__ import annotations

import sqlite3

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

from .test_migration_0151_the_hub_may_override_checks import _add_project, _columns


def test_0167_drops_the_setting_keeps_every_project_and_round_trips(tmp_path):
    db_file = tmp_path / "override-gone.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    # The schema as the models build it, stamped at 0167, then walked down: that is 0166's tables.
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0167')")
        conn.commit()
        assert "checks_auto_override" not in _columns(conn, "projects")
    _downgrade_to(db_url, "0166")
    with sqlite3.connect(db_file) as conn:
        assert "checks_auto_override" in _columns(conn, "projects")
        _add_project(conn, "proj-on")
        _add_project(conn, "proj-off")
        conn.execute(
            "UPDATE projects SET checks_auto_override = 0, checks_give_way = 1 "
            "WHERE id = 'proj-off'"
        )
        conn.commit()
        before = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        names = [row[1] for row in conn.execute("PRAGMA table_info(projects)")]

    _upgrade_to(db_url, "0167")

    with sqlite3.connect(db_file) as conn:
        assert _columns(conn, "projects") == set(names) - {"checks_auto_override"}
        kept = [c for c in names if c != "checks_auto_override"]
        after = conn.execute(f"SELECT {', '.join(kept)} FROM projects ORDER BY id").fetchall()
    index = [names.index(c) for c in kept]
    assert after == [tuple(row[i] for i in index) for row in before]

    _downgrade_to(db_url, "0166")

    with sqlite3.connect(db_file) as conn:
        rows = conn.execute("SELECT id, checks_auto_override FROM projects ORDER BY id").fetchall()
        _add_project(conn, "proj-new")
        created = conn.execute(
            "SELECT checks_auto_override FROM projects WHERE id = 'proj-new'"
        ).fetchone()
    # Back on for every project, the old default: the one value a rollback cannot restore is an
    # operator's "off".
    assert rows == [("proj-off", 1), ("proj-on", 1)]
    assert created == (1,)
