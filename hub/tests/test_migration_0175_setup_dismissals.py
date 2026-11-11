"""Migration 0175 (`a-project-says-what-it-still-needs`, task `setup-state`).

It adds `setup_dismissals` and reads or rewrites nothing else, so a project row written before it
carries its set-up items from its state now, the agent item among them (ac-existing, FR-5), with
nothing dismissed (FR-3).
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from hub import project_workspace
from hub.config import settings
from hub.db.models import Base, Project
from hub.project_setup import project_setup

ALEMBIC_INI = Path(__file__).parent.parent / "hub" / "alembic.ini"
REVISION = "0175"
PREVIOUS_REVISION = "0174"


def _alembic(db_url: str, verb: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        getattr(command, verb)(cfg, revision)


def _database_at_0174(db_file: Path) -> str:
    """Today's schema without the table 0175 adds, stamped at 0174: the operator's database as it
    stands before their next restart."""
    built = sa.create_engine(f"sqlite:///{db_file}")
    try:
        Base.metadata.create_all(
            built,
            tables=[t for t in Base.metadata.sorted_tables if t.name != "setup_dismissals"],
        )
        with built.begin() as conn:
            conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(sa.text(f"INSERT INTO alembic_version VALUES ('{PREVIOUS_REVISION}')"))
    finally:
        built.dispose()
    return f"sqlite+aiosqlite:///{db_file}"


def _tables(db_file: Path) -> set[str]:
    with sqlite3.connect(db_file) as conn:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _project_row_before_0175(db_file: Path, folder: Path) -> tuple:
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, working_directory, path_key, "
            "directory_state) VALUES ('proj-old', 'Old', '2026-01-01 00:00:00', ?, ?, 'available')",
            (str(folder), f"test:{folder}"),
        )
        conn.commit()
        return conn.execute("SELECT * FROM projects WHERE id = 'proj-old'").fetchone()


def test_a_project_row_from_before_0175_carries_the_agent_item(tmp_path, monkeypatch) -> None:
    """ac-existing (FR-5): nothing about set-up is recorded on the row, and none is needed."""
    db_file = tmp_path / "hub.db"
    folder = tmp_path / "old-project"
    folder.mkdir()
    db_url = _database_at_0174(db_file)
    assert "setup_dismissals" not in _tables(db_file)
    before = _project_row_before_0175(db_file, folder)

    _alembic(db_url, "upgrade", REVISION)

    assert "setup_dismissals" in _tables(db_file)
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT * FROM projects WHERE id = 'proj-old'").fetchone() == before
        assert conn.execute("SELECT COUNT(*) FROM setup_dismissals").fetchone() == (0,)

    async def _resolve(session, project_id, *, hub_data_directory=None):
        del session, hub_data_directory
        return project_workspace.ProjectWorkspace(
            project_id=project_id, root=folder, path_key=f"test:{folder}"
        )

    monkeypatch.setattr(project_workspace, "resolve_project_workspace", _resolve)

    async def _read():
        migrated = create_async_engine(db_url)
        try:
            async with async_sessionmaker(migrated)() as session:
                return await project_setup(session, await session.get(Project, "proj-old"))
        finally:
            await migrated.dispose()

    # Alembic's env runs its own event loop, so the migration steps above are synchronous.
    setup = asyncio.run(_read())

    assert [item.id for item in setup.items] == ["repository", "agent"]
    assert setup.dismissed == []


def test_the_downgrade_drops_only_the_table(tmp_path) -> None:
    db_file = tmp_path / "hub.db"
    db_url = _database_at_0174(db_file)
    _alembic(db_url, "upgrade", REVISION)
    before = _tables(db_file)

    _alembic(db_url, "downgrade", PREVIOUS_REVISION)

    assert _tables(db_file) == before - {"setup_dismissals"}


def test_the_upgrade_leaves_a_table_create_all_already_made(tmp_path) -> None:
    """The guard: a database built by `create_all` already has the table."""
    db_file = tmp_path / "hub.db"
    db_url = _database_at_0174(db_file)
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "CREATE TABLE setup_dismissals (project_id VARCHAR(64) NOT NULL, item VARCHAR(32) "
            "NOT NULL, dismissed_at DATETIME NOT NULL, PRIMARY KEY (project_id, item))"
        )
        conn.commit()

    _alembic(db_url, "upgrade", REVISION)

    assert "setup_dismissals" in _tables(db_file)
