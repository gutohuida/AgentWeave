"""Migration 0191 (`overview-at-a-glance-with-dashboard-and-briefing-tabs`, task visits-and-note).

It adds `overview_visits` and `overview_notes` and reads or rewrites nothing else: a project row
from before it reads as never visited, with no note, and the downgrade drops exactly the two tables.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from hub import overview_note_job
from hub.config import settings
from hub.db.models import Base

ALEMBIC_INI = Path(__file__).parent.parent / "hub" / "alembic.ini"
REVISION = "0191"
PREVIOUS_REVISION = "0190"
NEW_TABLES = {"overview_visits", "overview_notes"}


def _alembic(db_url: str, verb: str, revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        getattr(command, verb)(cfg, revision)


def _database_at_0190(db_file: Path) -> str:
    """Today's schema without the tables 0191 adds, stamped at 0190: the operator's database as it
    stands before their next restart."""
    built = sa.create_engine(f"sqlite:///{db_file}")
    try:
        Base.metadata.create_all(
            built, tables=[t for t in Base.metadata.sorted_tables if t.name not in NEW_TABLES]
        )
        with built.begin() as conn:
            conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(sa.text(f"INSERT INTO alembic_version VALUES ('{PREVIOUS_REVISION}')"))
    finally:
        built.dispose()
    return f"sqlite+aiosqlite:///{db_file}"


def _tables(db_file: Path) -> set:
    with sqlite3.connect(db_file) as conn:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _old_project(db_file: Path, folder: Path) -> tuple:
    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "INSERT INTO projects (id, name, created_at, working_directory, path_key, "
            "directory_state) VALUES ('proj-old', 'Old', '2026-01-01 00:00:00', ?, ?, 'available')",
            (str(folder), f"test:{folder}"),
        )
        conn.commit()
        return conn.execute("SELECT * FROM projects WHERE id = 'proj-old'").fetchone()


def test_the_upgrade_adds_both_tables_and_an_old_project_reads_never_visited(tmp_path) -> None:
    db_file = tmp_path / "hub.db"
    db_url = _database_at_0190(db_file)
    assert not NEW_TABLES & _tables(db_file)
    before = _old_project(db_file, tmp_path)

    _alembic(db_url, "upgrade", REVISION)

    assert _tables(db_file) >= NEW_TABLES
    with sqlite3.connect(db_file) as conn:
        assert conn.execute("SELECT * FROM projects WHERE id = 'proj-old'").fetchone() == before
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('overview_notes')")}
    assert "ix_overview_notes_project_id" in indexes

    async def _read():
        migrated = create_async_engine(db_url)
        try:
            async with async_sessionmaker(migrated)() as session:
                return (
                    await overview_note_job.visit_view(session, "proj-old"),
                    await overview_note_job.latest_note(session, "proj-old"),
                )
        finally:
            await migrated.dispose()

    # Alembic's env runs its own event loop, so the migration steps above are synchronous.
    assert asyncio.run(_read()) == (None, None)


def test_the_downgrade_drops_only_the_two_tables(tmp_path) -> None:
    db_file = tmp_path / "hub.db"
    db_url = _database_at_0190(db_file)
    before_upgrade = _tables(db_file)
    _alembic(db_url, "upgrade", REVISION)

    _alembic(db_url, "downgrade", PREVIOUS_REVISION)

    assert _tables(db_file) == before_upgrade


def test_the_upgrade_leaves_tables_create_all_already_made(tmp_path) -> None:
    """The guard: a database built by `create_all` already has both tables."""
    db_file = tmp_path / "hub.db"
    built = sa.create_engine(f"sqlite:///{db_file}")
    try:
        Base.metadata.create_all(built)
        with built.begin() as conn:
            conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(sa.text(f"INSERT INTO alembic_version VALUES ('{PREVIOUS_REVISION}')"))
    finally:
        built.dispose()

    _alembic(f"sqlite+aiosqlite:///{db_file}", "upgrade", REVISION)

    assert _tables(db_file) >= NEW_TABLES
