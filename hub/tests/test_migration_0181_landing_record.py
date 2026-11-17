"""Migration 0181 on a database from before it (`landing-time-and-test-flakiness-are-measured`,
FR-7, FR-8): an existing project is given the landing dashboard, and an old batch's record stays
NULL and reads 'not recorded'.

In a `test_migration*` module so the suite's prepared-database cache serves its climbs
(`conftest._migration_tests_share_prepared_databases`).
"""

from __future__ import annotations

import sqlite3

from hub import landing_dashboard

from .test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to


def _by_name(columns, row) -> dict:
    return dict(zip(columns, row, strict=True))


def test_migration_0181_gives_an_existing_project_the_dashboard_and_leaves_old_batches_null(
    tmp_path,
) -> None:
    """ac-dashboard-every-project, an existing project, and ac-old-batch-null on the migrated
    database: a project and a batch from 0180; after 0181 the project has the dashboard once, the
    batch's new fields are NULL, and every panel's query runs on that file, the batch's wait
    reading 'not recorded'. The downgrade removes both again."""
    db_file = tmp_path / "existing.db"
    url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(url))
    _upgrade_to(url, "head")
    _downgrade_to(url, "0180")
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('proj-old', 'Old', '2026-11-01 00:00:00')"
        )
        conn.execute(
            "INSERT INTO landing_batches (id, project_id, base_sha, state, task_ids, prefixes, "
            "results, narrowing, error, created_at, ended_at) VALUES ('lbat-old', 'proj-old', "
            "'abc', 'landed', '[]', '[]', '[]', '[]', '', '2026-11-16 10:00:00.000000', "
            "'2026-11-16 10:30:00.000000')"
        )
    _upgrade_to(url, "0181")
    _upgrade_to(url, "0181")  # a second run inserts nothing more
    with sqlite3.connect(db_file) as conn:
        dashboards = conn.execute(
            "SELECT project_id, author, panels FROM dashboards WHERE name = ?",
            (landing_dashboard.NAME,),
        ).fetchall()
        assert [(d[0], d[1]) for d in dashboards] == [("proj-old", "hub")]
        assert conn.execute(
            "SELECT ready_at, slot_at, checks_ended_at, check_runs FROM landing_batches"
        ).fetchall() == [(None, None, None, None)]
        for panel in landing_dashboard.PANELS:
            conn.execute(panel["query"]).fetchall()  # each runs on the migrated file
        cursor = conn.execute(landing_dashboard.BATCHES_SQL)
        columns = [c[0] for c in cursor.description]
        [row] = [_by_name(columns, r) for r in cursor.fetchall()]
        assert row["wait (min)"] == "not recorded" and row["check runs"] == "not recorded", row
    _downgrade_to(url, "0180")
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT count(*) FROM dashboards").fetchone() == (0,)
        columns = {r[1] for r in conn.execute("PRAGMA table_info('landing_batches')")}
        assert not columns & {"ready_at", "slot_at", "checks_ended_at", "check_runs"}
