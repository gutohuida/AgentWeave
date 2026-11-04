"""Migration 0163 -- a checkpoint has a title (`every-checkpoint-findable-and-readable`, FR-11,
FR-13).

0163 runs on the operator's real database at their next restart. These pin that it adds five
nullable columns to `checkpoints`, that a checkpoint stored before it keeps its row and reads NULL
in each (the state the one-time fill looks for), and that the downgrade drops them again while
keeping the row.
"""

from __future__ import annotations

import sqlite3

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

_NEW = {"title", "summary", "title_made_by", "title_reason", "unreadable_answer"}


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_0163_adds_the_title_columns_keeps_old_checkpoints_and_round_trips(tmp_path):
    db_file = tmp_path / "titles.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0163')")
        conn.commit()

    _downgrade_to(db_url, "0162")
    with sqlite3.connect(db_file) as conn:
        assert not (_NEW & _columns(conn, "checkpoints"))
        conn.execute(
            "INSERT INTO checkpoints (id, project_id, conversation_id, agent, trigger, status, "
            "lineage_id, body, created_at) VALUES ('ckpt-old', 'proj-old', 'conv-old', 'dev', "
            "'operator', 'ready', 'ckpt-old', '## Objective\n\nOld work.', '2026-11-02T00:00:00')"
        )
        conn.commit()

    _upgrade_to(db_url, "0163")
    with sqlite3.connect(db_file) as conn:
        assert _columns(conn, "checkpoints") >= _NEW
        row = conn.execute(
            "SELECT id, body, title, summary, title_made_by, title_reason, unreadable_answer "
            "FROM checkpoints"
        ).fetchall()
        assert row == [("ckpt-old", "## Objective\n\nOld work.", None, None, None, None, None)]
        conn.execute(
            "UPDATE checkpoints SET title = 'Old work', summary = 'Old work.', "
            "title_made_by = 'model'"
        )
        conn.commit()

    _downgrade_to(db_url, "0162")
    with sqlite3.connect(db_file) as conn:
        assert not (_NEW & _columns(conn, "checkpoints"))
        assert conn.execute("SELECT id, body FROM checkpoints").fetchall() == [
            ("ckpt-old", "## Objective\n\nOld work.")
        ]
