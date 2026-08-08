"""Persistence contracts for directory-backed projects (phase 0.1)."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from hub.config import settings
from hub.db import models
from hub.db.engine import async_session_factory

ALEMBIC_INI = Path(__file__).parent.parent / "hub" / "alembic.ini"
DIRECTORY_STATES = {
    "unbound",
    "available",
    "missing",
    "unreadable",
    "not_directory",
    "identity_conflict",
}


def test_project_model_declares_nullable_legacy_directory_binding() -> None:
    columns = models.Project.__table__.columns

    assert columns["working_directory"].nullable is True
    assert columns["path_key"].nullable is True
    assert columns["directory_state"].nullable is False
    assert columns["last_opened_at"].nullable is True
    assert columns["last_seen_at"].nullable is True
    assert set(models.PROJECT_DIRECTORY_STATES) == DIRECTORY_STATES


def test_project_path_key_has_a_unique_database_constraint() -> None:
    path_key = models.Project.__table__.columns["path_key"]
    assert path_key.unique is True


async def _insert_project(session: AsyncSession, project_id: str, path_key: str) -> None:
    session.add(
        models.Project(
            id=project_id,
            name=project_id,
            working_directory=f"/workspace/{project_id}",
            path_key=path_key,
            directory_state="available",
        )
    )
    await session.commit()


async def _assert_duplicate_path_key_is_rejected() -> None:
    async with async_session_factory() as session:
        await _insert_project(session, "proj-path-one", "canonical:/workspace/shared")
        session.add(
            models.Project(
                id="proj-path-two",
                name="Duplicate path",
                working_directory="/workspace/alias",
                path_key="canonical:/workspace/shared",
                directory_state="available",
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
        else:
            raise AssertionError("duplicate canonical path_key was accepted")


def test_project_directory_binding_round_trips_and_is_unique(app) -> None:
    asyncio.run(_assert_duplicate_path_key_is_rejected())


async def _assert_invalid_directory_state_is_rejected() -> None:
    async with async_session_factory() as session:
        session.add(
            models.Project(
                id="proj-invalid-state",
                name="Invalid",
                directory_state="invented",
            )
        )
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
        else:
            raise AssertionError("invalid directory state was accepted")


def test_project_directory_state_is_database_constrained(app) -> None:
    asyncio.run(_assert_invalid_directory_state_is_rejected())


async def _assert_operator_credential_round_trip() -> None:
    credential_type = models.OperatorCredential
    async with async_session_factory() as session:
        credential = credential_type(
            id="aw_live_operator_0123456789abcdef",
            label="bootstrap",
            revoked=False,
        )
        session.add(credential)
        await session.commit()
        await session.refresh(credential)

        assert credential.id == "aw_live_operator_0123456789abcdef"
        assert credential.created_at is not None
        assert "project_id" not in credential_type.__table__.columns


def test_operator_credential_is_instance_scoped(app) -> None:
    asyncio.run(_assert_operator_credential_round_trip())


async def _assert_bootstrap_operator_credential_exists() -> None:
    async with async_session_factory() as session:
        credential = await session.scalar(
            select(models.OperatorCredential).where(
                models.OperatorCredential.id == "aw_live_testkey_abcdefgh"
            )
        )
        assert credential is not None
        assert credential.label == "bootstrap"
        assert credential.revoked is False


def test_init_db_bootstraps_the_same_secret_as_operator_credential(app) -> None:
    asyncio.run(_assert_bootstrap_operator_credential_exists())


def test_migration_0026_preserves_legacy_project_and_bootstrap_secret(tmp_path) -> None:
    db_file = tmp_path / "pre-project-workspace.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    bootstrap_secret = "aw_live_preserved_0123456789abcdef"
    created_at = datetime(2026, 8, 1, tzinfo=timezone.utc)

    async def _create_0025_state() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text(
                        "CREATE TABLE projects ("
                        "id VARCHAR(64) PRIMARY KEY, name VARCHAR(256) NOT NULL, "
                        "created_at DATETIME NOT NULL)"
                    )
                )
                await conn.execute(
                    sa.text(
                        "CREATE TABLE api_keys ("
                        "id VARCHAR(128) PRIMARY KEY, project_id VARCHAR(64) NOT NULL, "
                        "label VARCHAR(128) NOT NULL, revoked BOOLEAN NOT NULL, "
                        "created_at DATETIME NOT NULL)"
                    )
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO projects (id, name, created_at) "
                        "VALUES ('proj-default', 'Legacy', :created_at)"
                    ),
                    {"created_at": created_at},
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO api_keys "
                        "(id, project_id, label, revoked, created_at) VALUES "
                        "(:id, 'proj-default', 'bootstrap', 0, :created_at)"
                    ),
                    {"id": bootstrap_secret, "created_at": created_at},
                )
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0025')")
                )
        finally:
            await engine.dispose()

    async def _read_upgraded_state() -> tuple[dict[str, object], dict[str, object], str]:
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                project = (
                    (await conn.execute(sa.text("SELECT * FROM projects WHERE id='proj-default'")))
                    .mappings()
                    .one()
                )
                credential = (
                    (
                        await conn.execute(
                            sa.text("SELECT * FROM operator_credentials WHERE id=:id"),
                            {"id": bootstrap_secret},
                        )
                    )
                    .mappings()
                    .one()
                )
                version = (
                    await conn.execute(sa.text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
                return dict(project), dict(credential), version
        finally:
            await engine.dispose()

    asyncio.run(_create_0025_state())
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.upgrade(cfg, "head")

    project, credential, version = asyncio.run(_read_upgraded_state())
    assert version == "0045"
    assert project["name"] == "Legacy"
    assert project["working_directory"] is None
    assert project["path_key"] is None
    assert project["directory_state"] == "unbound"
    assert project["last_opened_at"] is None
    assert project["last_seen_at"] is None
    assert credential["id"] == bootstrap_secret
    assert credential["label"] == "bootstrap"
    assert credential["revoked"] in (False, 0)

    with sqlite3.connect(db_file) as conn:
        conn.execute("UPDATE projects SET path_key='windows:c:\\\\legacy' WHERE id='proj-default'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO projects (id, name, created_at, path_key) "
                "VALUES ('proj-duplicate', 'Duplicate', ?, 'windows:c:\\\\legacy')",
                (created_at,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE projects SET directory_state='invented' WHERE id='proj-default'")
