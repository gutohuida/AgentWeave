"""Migration 0137 -- trace_spans, trace_settings (`a-run-is-a-trace-you-can-export`, Tier 2).

The hazard this change names is that 0137 runs on the operator's real database at their next
restart. These pin that it only adds the two tables and their indexes, leaves every existing table
byte-for-byte as it was, and that the downgrade removes exactly those two.
"""

from __future__ import annotations

import sqlite3

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

INDEXES = {
    "ix_trace_spans_trace_start",
    "ix_trace_spans_project_trace_started",
    "ix_trace_spans_project_roots",
    "ix_trace_spans_run",
    "ix_trace_spans_outbox",
}


def _tables(db_file) -> dict:
    with sqlite3.connect(db_file) as conn:
        return {
            row[0]: row[1]
            for row in conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'")
        }


def test_0137_adds_the_trace_tables_and_changes_nothing_else(tmp_path) -> None:
    db_file = tmp_path / "traces.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("DROP TABLE trace_spans")
        conn.execute("DROP TABLE trace_settings")
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0135')")
        conn.execute(
            "INSERT INTO turn_usage (id, run_id, project_id, agent, status, observed_at) "
            "VALUES ('usage-old', 'run-old', 'proj-old', 'a', 'unavailable', "
            "'2026-10-18T00:00:00')"
        )
        conn.commit()
    before = _tables(db_file)

    _upgrade_to(db_url, "0137")

    after = _tables(db_file)
    assert set(after) - set(before) == {"trace_spans", "trace_settings"}
    assert {name: after[name] for name in before} == before
    with sqlite3.connect(db_file) as conn:
        columns = {r[1]: r for r in conn.execute("PRAGMA table_info(trace_spans)")}
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(trace_spans)")}
        kept = conn.execute("SELECT count(*) FROM turn_usage").fetchone()
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version == ("0137",)
    assert kept == (1,)
    assert columns["span_id"][5] == 1  # the primary key
    assert columns["end_time"][3] == 0  # nullable: a span still open
    assert indexes >= INDEXES

    _downgrade_to(db_url, "0135")

    assert _tables(db_file) == before


def test_0137_is_a_no_op_over_tables_create_all_built(tmp_path) -> None:
    db_file = tmp_path / "built.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0135')")
        conn.commit()
    before = _tables(db_file)
    _upgrade_to(db_url, "0137")
    assert _tables(db_file) == before
