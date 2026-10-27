"""Migration 0151 -- the Hub may override checks (`a-red-main-does-not-hold-the-night`, slice M).

0151 runs on the operator's real database at their next restart. These pin that it adds
`task_transitions.override_by`, backfilled `operator` exactly where an override reason exists (every
override before it was the operator's), and `projects.checks_auto_override`, on for every existing
project; and that the downgrade drops both and keeps every row.
"""

from __future__ import annotations

import sqlite3

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

_TRANSITION = (
    "INSERT INTO task_transitions (id, project_id, task_id, from_status, to_status, actor_kind, "
    "override_reason, created_at) VALUES (?, 'proj-old', 'task-old', 'under_review', 'approved', "
    "'operator', ?, '2026-10-26T00:00:00')"
)


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_project(conn, project_id: str) -> None:
    """A project row with every required column given a value (the table has many)."""
    values = {"id": project_id, "name": project_id}
    for _cid, name, kind, notnull, default, _pk in conn.execute("PRAGMA table_info(projects)"):
        if name in values or not notnull or default is not None:
            continue
        kind = (kind or "").upper()
        values[name] = (
            "2026-10-26T00:00:00"
            if "DATE" in kind or "TIME" in kind
            else 0 if any(word in kind for word in ("INT", "BOOL", "FLOAT", "NUM")) else ""
        )
    names = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO projects ({names}) VALUES ({marks})", list(values.values()))


def test_0151_backfills_operator_overrides_defaults_the_setting_on_and_round_trips(tmp_path):
    db_file = tmp_path / "override.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    # The schema as the models build it, stamped at 0151, then walked down: that is 0149's tables.
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0151')")
        conn.commit()
    _downgrade_to(db_url, "0149")
    with sqlite3.connect(db_file) as conn:
        assert "override_by" not in _columns(conn, "task_transitions")
        assert "checks_auto_override" not in _columns(conn, "projects")
        assert "merges_branch_tip" not in _columns(conn, "tasks")
        _add_project(conn, "proj-old")
        conn.execute(_TRANSITION, ("ttr-reason", "main carries the defect"))
        conn.execute(_TRANSITION, ("ttr-plain", None))
        conn.commit()

    _upgrade_to(db_url, "0151")

    with sqlite3.connect(db_file) as conn:
        rows = conn.execute(
            "SELECT id, override_by, override_reason FROM task_transitions ORDER BY id"
        ).fetchall()
        setting = conn.execute(
            "SELECT checks_auto_override FROM projects WHERE id = 'proj-old'"
        ).fetchone()
        _add_project(conn, "proj-new")
        created = conn.execute(
            "SELECT checks_auto_override FROM projects WHERE id = 'proj-new'"
        ).fetchone()
        tip = [r for r in conn.execute("PRAGMA table_info(tasks)") if r[1] == "merges_branch_tip"]
        conn.commit()
    # Every existing task is an ordinary one: only a fix task the Hub files merges its branch tip.
    assert [(r[3], r[4]) for r in tip] == [(1, "0")], tip
    assert rows == [
        ("ttr-plain", None, None),
        ("ttr-reason", "operator", "main carries the defect"),
    ]
    assert setting == (1,) and created == (1,)

    _downgrade_to(db_url, "0149")

    with sqlite3.connect(db_file) as conn:
        assert "override_by" not in _columns(conn, "task_transitions")
        assert "checks_auto_override" not in _columns(conn, "projects")
        assert "merges_branch_tip" not in _columns(conn, "tasks")
        assert conn.execute("SELECT count(*) FROM task_transitions").fetchone() == (2,)
        assert conn.execute("SELECT count(*) FROM projects").fetchone() == (2,)
