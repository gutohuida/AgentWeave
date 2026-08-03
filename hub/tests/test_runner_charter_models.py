"""Tests for the Runner and Charter models — runner-agent-charter-separation phase 0.

Covers the `runner-registry` and `agent-charter` capability specs' data-model
requirements: project-scoped Runner/Charter records, and Agent's nullable
runner_id/charter_id bindings. See
openspec/changes/runner-agent-charter-separation/design.md for why these are
separate Hub DB tables rather than a config file or hardcoded dict.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from hub.config import settings
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Charter, Project, Runner

ALEMBIC_INI = Path(__file__).parent.parent / "hub" / "alembic.ini"


# ---------------------------------------------------------------------------
# ORM round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_model_round_trips_through_the_orm(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-runner-test", name="Runner Model Test"))
        runner = Runner(
            id="runner-test-0001",
            project_id="proj-runner-test",
            name="Claude default",
            cli="claude",
            model="claude-sonnet-5",
        )
        session.add(runner)
        await session.commit()
        await session.refresh(runner)

        assert runner.cli == "claude"
        assert runner.model == "claude-sonnet-5"
        assert runner.flags is None
        assert runner.created_at is not None
        assert runner.updated_at is not None


@pytest.mark.asyncio
async def test_runner_cli_is_constrained_to_claude_or_codex(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-runner-cli-test", name="Runner CLI Test"))
        session.add(
            Runner(
                id="runner-bad-cli",
                project_id="proj-runner-cli-test",
                name="Bogus",
                cli="opencode",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_charter_model_round_trips_through_the_orm(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-charter-test", name="Charter Model Test"))
        charter = Charter(
            id="charter-test-0001",
            project_id="proj-charter-test",
            name="Backend Developer",
            content="# Backend Developer\n\nOwns APIs, database, business logic.",
        )
        session.add(charter)
        await session.commit()
        await session.refresh(charter)

        assert charter.name == "Backend Developer"
        assert "Backend Developer" in charter.content
        assert charter.created_at is not None
        assert charter.updated_at is not None


@pytest.mark.asyncio
async def test_agent_binds_to_a_runner_and_a_charter(app) -> None:
    async with async_session_factory() as session:
        session.add(Project(id="proj-binding-test", name="Binding Test"))
        session.add(
            Runner(id="runner-bind", project_id="proj-binding-test", name="Claude", cli="claude")
        )
        session.add(
            Charter(
                id="charter-bind",
                project_id="proj-binding-test",
                name="Backend",
                content="Backend charter",
            )
        )
        agent = Agent(
            id="agent-bind",
            project_id="proj-binding-test",
            name="claude",
            runner_id="runner-bind",
            charter_id="charter-bind",
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)

        assert agent.runner_id == "runner-bind"
        assert agent.charter_id == "charter-bind"


@pytest.mark.asyncio
async def test_agent_runner_and_charter_bindings_are_optional(app) -> None:
    """An agent with no runner/charter bound must still be a valid, loadable row —
    the runner-registry and agent-charter specs both require this (an agent with no
    binding is refused at trigger/context time, not at the data-model level)."""
    async with async_session_factory() as session:
        session.add(Project(id="proj-unbound-test", name="Unbound Test"))
        agent = Agent(id="agent-unbound", project_id="proj-unbound-test", name="claude")
        session.add(agent)
        await session.commit()
        await session.refresh(agent)

        assert agent.runner_id is None
        assert agent.charter_id is None


# ---------------------------------------------------------------------------
# Migration 0023
# ---------------------------------------------------------------------------


def test_migration_0023_adds_runners_charters_and_agent_bindings(tmp_path) -> None:
    """An existing deployment stamped at 0022 (no runners/charters tables, no
    agents.runner_id/charter_id columns) must upgrade cleanly to 0023."""
    db_file = tmp_path / "runner-charter-0022.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _create_old_state() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text("CREATE TABLE projects (id VARCHAR(64) PRIMARY KEY, name VARCHAR(256))")
                )
                await conn.execute(
                    sa.text("INSERT INTO projects (id, name) VALUES ('proj-old', 'Old')")
                )
                await conn.execute(
                    sa.text(
                        "CREATE TABLE agents (id VARCHAR(64) PRIMARY KEY, "
                        "project_id VARCHAR(64) NOT NULL, name VARCHAR(64) NOT NULL)"
                    )
                )
                await conn.execute(
                    sa.text(
                        "INSERT INTO agents (id, project_id, name) "
                        "VALUES ('agent-old', 'proj-old', 'claude')"
                    )
                )
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0022')")
                )
        finally:
            await engine.dispose()

    async def _inspect_upgraded_state():
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:

                def _inspect(sync_conn):
                    inspector = sa.inspect(sync_conn)
                    return (
                        set(inspector.get_table_names()),
                        {c["name"] for c in inspector.get_columns("agents")},
                    )

                return await conn.run_sync(_inspect)
        finally:
            await engine.dispose()

    _run(_create_old_state())
    _run_alembic_with(db_url)
    tables, agent_columns = _run(_inspect_upgraded_state())

    assert "runners" in tables
    assert "charters" in tables
    assert {"runner_id", "charter_id"} <= agent_columns

    async def _existing_agent_loads_with_null_bindings():
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        sa.text("SELECT runner_id, charter_id FROM agents WHERE id = 'agent-old'")
                    )
                ).one()
                return row
        finally:
            await engine.dispose()

    row = _run(_existing_agent_loads_with_null_bindings())
    assert row.runner_id is None
    assert row.charter_id is None


def test_migration_0024_adds_durable_charter_seed_marker(tmp_path) -> None:
    db_file = tmp_path / "charter-seed-marker-0023.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"

    async def _create_0023_state() -> None:
        engine = create_async_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    sa.text("CREATE TABLE projects (id VARCHAR(64) PRIMARY KEY, name VARCHAR(256))")
                )
                await conn.execute(
                    sa.text("INSERT INTO projects (id, name) VALUES ('proj-old', 'Old')")
                )
                await conn.execute(
                    sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
                )
                await conn.execute(
                    sa.text("INSERT INTO alembic_version (version_num) VALUES ('0023')")
                )
        finally:
            await engine.dispose()

    async def _read_marker() -> int:
        engine = create_async_engine(db_url)
        try:
            async with engine.connect() as conn:
                return (
                    await conn.execute(
                        sa.text("SELECT charters_seeded FROM projects WHERE id = 'proj-old'")
                    )
                ).scalar_one()
        finally:
            await engine.dispose()

    _run(_create_0023_state())
    _run_alembic_with(db_url)
    assert _run(_read_marker()) == 0


def _run_alembic_with(db_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    with patch.object(settings, "database_url", db_url):
        command.upgrade(cfg, "head")


def _run(coro):
    import asyncio

    return asyncio.run(coro)
