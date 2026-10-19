"""Migration 0138 -- trace_settings.record_reads, ix_trace_spans_project_operation
(`everything-the-hub-does-is-in-a-trace`, Tier 2).

0138 runs on the operator's real database at their next restart. These pin that it adds one column
(false for every existing project, which keeps skipping reads) and one index, rewrites no row and
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


def test_0138_adds_record_reads_and_the_operation_index_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "traces.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("DROP INDEX ix_trace_spans_project_operation")
        conn.execute("ALTER TABLE trace_settings DROP COLUMN record_reads")
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0137')")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO trace_settings (project_id, otlp_headers, export_enabled, "
            "exported_spans, updated_at) VALUES ('proj-old', '{}', 0, 0, '2026-10-19T00:00:00')"
        )
        conn.commit()
    before = _schema(db_file)

    _upgrade_to(db_url, "0138")

    after = _schema(db_file)
    assert set(after) - set(before) == {"ix_trace_spans_project_operation"}
    assert [name for name in before if before[name] != after[name]] == ["trace_settings"]
    with sqlite3.connect(db_file) as conn:
        kept = conn.execute("SELECT project_id, record_reads FROM trace_settings").fetchall()
        index = [r[2] for r in conn.execute("PRAGMA index_info(ix_trace_spans_project_operation)")]
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version == ("0138",)
    assert kept == [("proj-old", 0)]  # an existing project keeps skipping reads
    assert index == ["project_id", "operation", "start_time"]

    _downgrade_to(db_url, "0137")

    assert _schema(db_file) == before


def test_0138_is_a_no_op_over_a_schema_create_all_built(tmp_path) -> None:
    db_file = tmp_path / "built.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0137')")
        conn.commit()
    before = _schema(db_file)
    _upgrade_to(db_url, "0138")
    assert _schema(db_file) == before
