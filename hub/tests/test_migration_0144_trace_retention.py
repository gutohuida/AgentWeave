"""Migration 0144 -- trace_settings.retention_days (`the-database-stays-fast-as-history-grows`, Tier 2).

0144 runs on the operator's real database at their next restart. These pin that it adds one
nullable column (NULL: the Hub's default window for every existing project), rewrites no row,
changes no other table, and that the downgrade puts the schema back exactly.
"""

from __future__ import annotations

import sqlite3

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to


def _schema(db_file) -> dict:
    with sqlite3.connect(db_file) as conn:
        return {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index') "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }


def _at_0143(db_file, db_url) -> None:
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("ALTER TABLE trace_settings DROP COLUMN retention_days")
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0143')")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO trace_settings (project_id, otlp_headers, export_enabled, "
            "exported_spans, record_reads, updated_at) "
            "VALUES ('proj-old', '{}', 0, 0, 1, '2026-10-19T00:00:00')"
        )
        conn.commit()


def test_0144_adds_a_nullable_retention_window_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "traces.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _at_0143(db_file, db_url)
    before = _schema(db_file)

    _upgrade_to(db_url, "0144")

    after = _schema(db_file)
    assert set(after) == set(before)
    assert [name for name in before if before[name] != after[name]] == ["trace_settings"]
    with sqlite3.connect(db_file) as conn:
        kept = conn.execute(
            "SELECT project_id, record_reads, retention_days FROM trace_settings"
        ).fetchall()
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version == ("0144",)
    assert kept == [("proj-old", 1, None)]  # the Hub's default window

    _downgrade_to(db_url, "0143")

    assert _schema(db_file) == before
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT project_id, record_reads FROM trace_settings").fetchall() == [
            ("proj-old", 1)
        ]


def test_0144_is_a_no_op_over_a_schema_create_all_built(tmp_path) -> None:
    db_file = tmp_path / "built.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0143')")
        conn.commit()
    before = _schema(db_file)
    _upgrade_to(db_url, "0144")
    assert _schema(db_file) == before
