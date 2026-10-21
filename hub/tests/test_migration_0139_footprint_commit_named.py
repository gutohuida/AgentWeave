"""Migration 0139 -- evidence_footprints.commit_named (F761).

0139 runs on the operator's real database at their next restart. These pin that it adds one nullable
column, leaves every existing footprint NULL (unknown, read as before), changes no other table, and
that the downgrade puts the schema back exactly.
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


def test_0139_adds_commit_named_leaves_existing_rows_null_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "footprints.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("ALTER TABLE evidence_footprints DROP COLUMN commit_named")
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0138')")
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute(
            "INSERT INTO evidence_footprints (id, project_id, evidence_id, kind, commit_sha, "
            "observed_at) VALUES ('efp-old', 'proj-old', 'ev-old', 'git', 'abc', "
            "'2026-10-19T00:00:00')"
        )
        conn.commit()
    before = _schema(db_file)

    _upgrade_to(db_url, "0139")

    after = _schema(db_file)
    assert set(after) == set(before)
    assert [name for name in before if before[name] != after[name]] == ["evidence_footprints"]
    with sqlite3.connect(db_file) as conn:
        kept = conn.execute("SELECT id, commit_named FROM evidence_footprints").fetchall()
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    assert version == ("0139",)
    assert kept == [("efp-old", None)]

    _downgrade_to(db_url, "0138")

    assert _schema(db_file) == before


def test_0139_is_a_no_op_over_a_schema_create_all_built(tmp_path) -> None:
    db_file = tmp_path / "built.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0138')")
        conn.commit()
    before = _schema(db_file)
    _upgrade_to(db_url, "0139")
    assert _schema(db_file) == before
