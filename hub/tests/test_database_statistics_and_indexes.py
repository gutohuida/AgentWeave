"""Planner statistics refresh, and the indexes the hot reads need (`stats-current`,
`hot-read-indexes`, `the-database-stays-fast-as-history-grows` D5/D6)."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from sqlalchemy import select, text

from hub import db_maintenance
from hub.context_readings import IS_CONTEXT_READING
from hub.db.engine import async_session_factory, engine
from hub.db.models import AgentOutput, EventLog

from .conftest import TEST_PROJECT_ID
from .test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

NOW = datetime(2026, 10, 25, 12, 0, 0, tzinfo=timezone.utc)


def _newest_context_reading():
    """The statement `output_recording.record_context_usage` reads the latest reading with."""
    return (
        select(EventLog)
        .where(
            EventLog.project_id == TEST_PROJECT_ID,
            IS_CONTEXT_READING,
            EventLog.agent == "builder",
        )
        .order_by(EventLog.timestamp.desc())
        .limit(1)
    )


async def _plan(statement) -> list:  # noqa: ANN001
    compiled = statement.compile(engine.sync_engine, compile_kwargs={"literal_binds": True})
    async with engine.connect() as conn:
        rows = await conn.execute(text("EXPLAIN QUERY PLAN " + str(compiled)))
        return [row[3] for row in rows]


async def _index_columns(name: str) -> list:
    async with engine.connect() as conn:
        return [row[2] for row in await conn.execute(text(f"PRAGMA index_info({name})"))]


async def _indexes(table: str) -> dict:
    async with engine.connect() as conn:
        names = [row[1] for row in await conn.execute(text(f"PRAGMA index_list({table})"))]
    return {name: await _index_columns(name) for name in names}


async def test_the_newest_context_reading_is_found_through_an_index(app) -> None:
    async with async_session_factory() as db:
        for i in range(50):
            db.add(
                EventLog(
                    id=f"evt-ctx-{i}",
                    project_id=TEST_PROJECT_ID,
                    event_type="context_warning" if i % 2 else "agent_output",
                    agent="builder" if i % 3 else "other",
                    data={},
                    timestamp=NOW,
                )
            )
        await db.commit()
    plan = await _plan(_newest_context_reading())
    used = [m.group(1) for line in plan for m in [re.search(r"INDEX (\w+)", line)] if m]
    assert used, plan
    # 0144's partial index: (project, agent, timestamp) over `context_warning` rows only.
    assert (await _index_columns(used[0]))[:3] == ["project_id", "agent", "timestamp"]
    async with engine.connect() as conn:
        definition = (
            await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE name = :n"), {"n": used[0]}
            )
        ).scalar()
    assert "event_type = 'context_warning'" in definition
    assert not any("TEMP B-TREE" in line for line in plan), plan  # newest first, from the index


async def test_no_agent_outputs_index_is_a_leading_prefix_of_another(app) -> None:
    indexes = {k: v for k, v in (await _indexes("agent_outputs")).items() if v}
    prefixes = [
        (a, b)
        for a in indexes
        for b in indexes
        if a != b and indexes[b][: len(indexes[a])] == indexes[a]
    ]
    assert prefixes == []
    # Every agent filter on agent_outputs also names the project, so a bare (agent) index only
    # costs a write per streamed line (measured: 7 indexes on the table).
    assert ["agent"] not in indexes.values()
    assert indexes["ix_agent_outputs_project_agent_run_sequence"][:2] == ["project_id", "agent"]


async def test_the_statistics_refresh_writes_sqlite_stat1(app) -> None:
    async with async_session_factory() as db:
        for i in range(30):
            db.add(
                AgentOutput(
                    id=f"out-stat-{i}",
                    project_id=TEST_PROJECT_ID,
                    agent="builder",
                    content="x",
                    kind="text",
                    sequence=i,
                    timestamp=NOW,
                )
            )
            db.add(
                EventLog(
                    id=f"evt-stat-{i}",
                    project_id=TEST_PROJECT_ID,
                    event_type="context_warning",
                    agent="builder",
                    data={},
                    timestamp=NOW,
                )
            )
        await db.commit()
    await db_maintenance.refresh_statistics()
    async with engine.connect() as conn:
        tables = {row[0] for row in await conn.execute(text("SELECT tbl FROM sqlite_stat1"))}
    assert {"agent_outputs", "event_logs"} <= tables


def _schema(db_file) -> dict:
    with sqlite3.connect(db_file) as conn:
        return {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index') "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }


def _at_0145(db_file, db_url) -> None:
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE INDEX ix_agent_outputs_agent ON agent_outputs (agent)")
        conn.execute(
            "CREATE INDEX ix_agent_outputs_project_agent ON agent_outputs (project_id, agent)"
        )
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0145')")
        conn.commit()


def test_0146_drops_the_two_redundant_output_indexes_and_round_trips(tmp_path) -> None:
    db_file = tmp_path / "idx.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _at_0145(db_file, db_url)
    before = _schema(db_file)

    _upgrade_to(db_url, "0146")

    after = _schema(db_file)
    assert set(before) - set(after) == {"ix_agent_outputs_agent", "ix_agent_outputs_project_agent"}
    assert set(after) - set(before) == set()
    assert all(after[name] == before[name] for name in after)

    _downgrade_to(db_url, "0145")

    assert _schema(db_file) == before


def test_0146_is_a_no_op_over_a_schema_create_all_built(tmp_path) -> None:
    db_file = tmp_path / "built.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0145')")
        conn.commit()
    before = _schema(db_file)
    _upgrade_to(db_url, "0146")
    assert _schema(db_file) == before
