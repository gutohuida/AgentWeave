"""The project's "profiles run in parallel" switch
(`one-profile-runs-many-turns-at-once-on-different-tasks`, FR-15, ac-switch-default, task `setting`).

Every project carries the switch, off for a project that existed before migration 0183 and for one
created afterwards; the projects API reads and changes it, and the migration adds it off and its
downgrade removes it without touching any other project data.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import text

from hub.db.engine import async_session_factory
from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

from .test_migration_0151_the_hub_may_override_checks import _add_project, _columns

COLUMN = "profiles_run_in_parallel"


@pytest.mark.asyncio
async def test_the_switch_is_off_for_an_existing_and_a_new_project_and_round_trips(
    app, auth_headers, tmp_path
):
    """ac-switch-default: a row written without the column (as every project before 0183 was) and
    a project created through the route both read off; turning it on reads back on, and off again.
    """
    async with async_session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO projects (id, name, created_at) "
                "VALUES ('proj-before', 'Before', CURRENT_TIMESTAMP)"
            )
        )
        await session.commit()
    created = await app.post(
        "/api/v1/projects/create",
        json={"path": str(tmp_path / "created"), "name": "Created"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    new_id = created.json()["id"]

    for project_id in ("proj-before", new_id):
        url = f"/api/v1/projects/{project_id}/settings"
        read = await app.get(url, headers=auth_headers)
        assert read.status_code == 200, read.text
        assert read.json()[COLUMN] is False

        saved = await app.put(url, json={COLUMN: True}, headers=auth_headers)
        assert saved.status_code == 200, saved.text
        assert saved.json()[COLUMN] is True
        read = await app.get(url, headers=auth_headers)
        assert read.json()[COLUMN] is True

        # A save naming another field leaves the switch as stored.
        other = await app.put(url, json={"hop_budget": 7}, headers=auth_headers)
        assert other.status_code == 200, other.text
        assert other.json()[COLUMN] is True

        off = await app.put(url, json={COLUMN: False}, headers=auth_headers)
        assert off.status_code == 200, off.text
        read = await app.get(url, headers=auth_headers)
        assert read.json()[COLUMN] is False


@pytest.mark.asyncio
async def test_the_switch_refuses_a_value_that_is_not_a_boolean(app, auth_headers):
    url = "/api/v1/projects/proj-test/settings"
    refused = await app.put(url, json={COLUMN: "sometimes"}, headers=auth_headers)
    assert refused.status_code == 422, refused.text
    read = await app.get(url, headers=auth_headers)
    assert read.json()[COLUMN] is False


def test_0183_adds_the_switch_off_keeps_every_project_and_round_trips(tmp_path):
    """0183 runs on the operator's real data: it adds the column off for every existing project,
    changes no other value, and the downgrade removes only the column."""
    db_file = tmp_path / "parallel.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0183')")
        conn.commit()
    _downgrade_to(db_url, "0182")
    with sqlite3.connect(db_file) as conn:
        assert COLUMN not in _columns(conn, "projects")
        _add_project(conn, "proj-a")
        _add_project(conn, "proj-b")
        conn.execute("UPDATE projects SET checks_give_way = 1 WHERE id = 'proj-b'")
        conn.commit()
        names = [row[1] for row in conn.execute("PRAGMA table_info(projects)")]
        before = conn.execute(f"SELECT {', '.join(names)} FROM projects ORDER BY id").fetchall()

    _upgrade_to(db_url, "0183")

    with sqlite3.connect(db_file) as conn:
        assert _columns(conn, "projects") == set(names) | {COLUMN}
        after = conn.execute(f"SELECT {', '.join(names)} FROM projects ORDER BY id").fetchall()
        switches = conn.execute(f"SELECT id, {COLUMN} FROM projects ORDER BY id").fetchall()
        _add_project(conn, "proj-new")
        created = conn.execute(f"SELECT {COLUMN} FROM projects WHERE id = 'proj-new'").fetchone()
        conn.commit()
    assert after == before
    assert switches == [("proj-a", 0), ("proj-b", 0)]
    assert created == (0,)

    _downgrade_to(db_url, "0182")

    with sqlite3.connect(db_file) as conn:
        assert COLUMN not in _columns(conn, "projects")
        assert _columns(conn, "projects") == set(names)
        ids = [row[0] for row in conn.execute("SELECT id FROM projects ORDER BY id")]
    assert ids == ["proj-a", "proj-b", "proj-new"]
