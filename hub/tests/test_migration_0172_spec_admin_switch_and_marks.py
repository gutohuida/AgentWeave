"""Migration 0172 -- the spec-admin switch, the document marks and an agent's fold
(`an-agent-the-operator-trusts-can-tidy-the-specs`, task `hub-core`, Tier 2).

0172 runs on the operator's real database at their next restart. These pin that every existing
agent reads the switch off, every existing document is unmarked and unheld, every existing merge row
survives the table rebuild, the widened CHECK admits an agent's fold only with its run, and the
downgrade deletes the agent merge rows, restores the narrow CHECK and drops the columns.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

MARKS = {
    "superseded_at",
    "superseded_by",
    "superseded_reason",
    "superseded_successor",
    "held_at",
    "held_note",
}


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _insert(conn, table: str, **values) -> None:
    """A row with every required column given a value (these tables have many)."""
    for _cid, name, kind, notnull, default, _pk in conn.execute(f"PRAGMA table_info({table})"):
        if name in values or not notnull or default is not None:
            continue
        kind = (kind or "").upper()
        values[name] = (
            "2026-11-09T00:00:00"
            if "DATE" in kind or "TIME" in kind
            else 0 if any(word in kind for word in ("INT", "BOOL", "FLOAT", "NUM")) else ""
        )
    names = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", list(values.values()))


def _merge(conn, merge_id: str, actor_kind: str, run_id=None) -> None:
    _insert(
        conn,
        "spec_document_merges",
        id=merge_id,
        project_id="proj-m",
        capability_document_id="doc-cap",
        change_document_id="doc-change",
        actor_kind=actor_kind,
        actor="someone",
        run_id=run_id,
        note="",
        created_at="2026-11-09T00:00:00",
    )


def test_0172_switch_off_marks_empty_merges_kept_and_round_trips(tmp_path):
    db_file = tmp_path / "spec-admin.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    # The schema as the models build it, stamped at 0172, then walked down: that is 0171's tables.
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0172')")
        conn.commit()
    _downgrade_to(db_url, "0171")

    with sqlite3.connect(db_file) as conn:
        assert "can_admin_specs" not in _columns(conn, "agents")
        assert not MARKS & _columns(conn, "spec_documents")
        _insert(conn, "projects", id="proj-m", name="proj-m")
        for agent in ("ag-1", "ag-2"):
            _insert(conn, "agents", id=agent, project_id="proj-m", name=agent)
        for doc, kind, phase in (
            ("doc-cap", "capability", "current"),
            ("doc-change", "change-spec", "approved"),
        ):
            _insert(
                conn,
                "spec_documents",
                id=doc,
                project_id="proj-m",
                path=f"spec/{doc}/spec.json",
                kind=kind,
                phase=phase,
            )
        _merge(conn, "merge-op", "operator")
        conn.commit()
        # The narrow CHECK, before: an agent's fold is refused even with its run.
        with pytest.raises(sqlite3.IntegrityError):
            _merge(conn, "merge-early", "agent", run_id="run-1")
        conn.rollback()
        merges_before = conn.execute("SELECT * FROM spec_document_merges").fetchall()

    _upgrade_to(db_url, "0172")

    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT id, can_admin_specs FROM agents ORDER BY id").fetchall() == [
            ("ag-1", 0),
            ("ag-2", 0),
        ]
        assert _columns(conn, "spec_documents") >= MARKS
        marks = ", ".join(sorted(MARKS))
        assert (
            conn.execute(f"SELECT {marks} FROM spec_documents").fetchall()
            == [(None,) * len(MARKS)] * 2
        )
        assert conn.execute("SELECT * FROM spec_document_merges").fetchall() == merges_before
        # An agent created after the migration reads off too.
        _insert(conn, "agents", id="ag-new", project_id="proj-m", name="ag-new")
        assert conn.execute(
            "SELECT can_admin_specs FROM agents WHERE id = 'ag-new'"
        ).fetchone() == (0,)
        # The widened CHECK: an agent's fold with its run is admitted, one without is refused.
        _merge(conn, "merge-agent", "agent", run_id="run-1")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            _merge(conn, "merge-runless", "agent")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            _merge(conn, "merge-system", "system", run_id="run-1")
        conn.rollback()
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(spec_document_merges)")}
        assert {
            "ix_spec_document_merges_capability",
            "ix_spec_document_merges_change",
        } <= indexes

    _downgrade_to(db_url, "0171")

    with sqlite3.connect(db_file) as conn:
        assert "can_admin_specs" not in _columns(conn, "agents")
        assert not MARKS & _columns(conn, "spec_documents")
        # The agent's merge row is gone; the operator's is kept as it was.
        assert conn.execute("SELECT * FROM spec_document_merges").fetchall() == merges_before
        with pytest.raises(sqlite3.IntegrityError):
            _merge(conn, "merge-late", "agent", run_id="run-1")
        conn.rollback()

    # And back up again, from a downgraded database.
    _upgrade_to(db_url, "0172")
    with sqlite3.connect(db_file) as conn:
        assert "can_admin_specs" in _columns(conn, "agents")
        _merge(conn, "merge-again", "agent", run_id="run-2")
        conn.commit()
