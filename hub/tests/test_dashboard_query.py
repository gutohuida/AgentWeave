"""The dashboard query service at its seam (`ask-any-agent-for-a-dashboard-and-get-one-that-stays`,
FR-1 to FR-7 and FR-14): `hub.dashboard_query.run_query` over two seeded projects on one database.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, List

import pytest
from sqlalchemy import text

from hub import config, dashboard_query
from hub.dashboard_query import QueryRefused, query_reference, run_query
from hub.db.engine import async_session_factory
from hub.db.models import (
    AgentOutput,
    ApiKey,
    OperatorCredential,
    Project,
    Run,
    Task,
    TraceSettings,
    TraceSpan,
)

from ._loop_lag import STALL_LIMIT, LagProbe

SECRET = "zz-secret-value-" + secrets.token_hex(4)
MARKER = "LEAK-MARKER-7731"
A, B = "proj-dqa000000001", "proj-dqb000000002"


def _ts(minutes: float) -> datetime:
    return datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)


async def _seed() -> None:
    async with async_session_factory() as db:
        db.add(OperatorCredential(id=f"aw_live_{SECRET}op", label="op"))
        for pid, statuses, markers in (
            (A, ["pending", "pending", "approved", "in_progress"], 3),
            (B, ["pending", "approved", "approved"], 5),
        ):
            db.add(
                Project(
                    id=pid,
                    name=pid,
                    working_directory=f"C:/{SECRET}/{pid}",
                    path_key=f"c:/{SECRET}/{pid}",
                )
            )
            db.add(ApiKey(id=f"aw_live_{SECRET}{pid}", project_id=pid, label="k"))
            db.add(
                TraceSettings(project_id=pid, otlp_headers={"authorization": f"Bearer {SECRET}"})
            )
            for n, status in enumerate(statuses):
                task_id = f"task-{pid[-4:]}{n:04d}"
                db.add(
                    Task(id=task_id, project_id=pid, title=f"t{n}", description="d", status=status)
                )
                db.add(
                    Run(
                        id=f"run-{pid[-4:]}{n:04d}",
                        project_id=pid,
                        agent="builder",
                        task_id=task_id,
                        status="completed",
                        initiator="autonomous",
                        capability_token_hash=f"{SECRET}-token-{pid}-{n}",
                        workspace_dir=f"C:/{SECRET}/ws/{n}",
                    )
                )
            for n in range(markers):
                db.add(
                    AgentOutput(
                        id=f"out-{pid[-4:]}{n}",
                        project_id=pid,
                        agent="b",
                        content=f"saw {MARKER} {n}",
                    )
                )
            db.add(
                AgentOutput(
                    id=f"out-{pid[-4:]}x", project_id=pid, agent="b", content="nothing here"
                )
            )
            for tool, count, seconds in (
                (("Read", 3, 2), ("Bash", 2, 5)) if pid == A else (("Read", 7, 1),)
            ):
                for k in range(count):
                    start = _ts(k)
                    db.add(
                        TraceSpan(
                            span_id=secrets.token_hex(8),
                            trace_id=secrets.token_hex(16),
                            project_id=pid,
                            name=f"execute_tool {tool}",
                            operation="execute_tool",
                            status="ok",
                            start_time=start,
                            end_time=start + timedelta(seconds=seconds),
                            ended=True,
                            trace_started_at=start,
                            attributes={
                                "gen_ai.tool.call.arguments": json.dumps({"p": f"{pid}-{tool}-{k}"})
                            },
                            events=[],
                        )
                    )
        await db.commit()
        await db.execute(
            text(
                "insert into workspace_fingerprints (project_id, workspace_key, workspace_dir, fingerprint, "
                "digest, recorded_by, recorded_at) values (:p, :k, :d, '{}', 'x', 'baseline', '2026-11-13')"
            ),
            {"p": A, "k": f"c:/{SECRET}/fp", "d": f"C:/{SECRET}/fp"},
        )
        await db.commit()


async def _direct(sql: str, **params: Any) -> List[List[Any]]:
    async with async_session_factory() as db:
        return [list(r) for r in (await db.execute(text(sql), params)).fetchall()]


async def _refused(sql: str, project_id: str = A) -> QueryRefused:
    with pytest.raises(QueryRefused) as caught:
        await run_query(project_id, sql)
    return caught.value


@pytest.fixture
async def seeded(app):
    await _seed()
    return app


# ------------------------------------------------------------------------------------- FR-1


async def test_counts_tasks_by_status_like_a_hand_written_count(seeded):
    result = await run_query(
        A, "select status, count(*) as n from tasks group by status order by status"
    )
    want = await _direct(
        "select status, count(*) from tasks where project_id = :p group by status order by status",
        p=A,
    )
    assert result["columns"] == ["status", "n"]
    assert result["rows"] == want and want
    assert result["row_count"] == len(want) and result["truncated"] is False
    assert isinstance(result["elapsed_ms"], float)


# ------------------------------------------------------------------------------------- FR-2


async def test_every_row_is_the_projects_own_whatever_the_query_says(seeded):
    a_tasks = {r[0] for r in await _direct("select id from tasks where project_id = :p", p=A)}
    unfiltered = await run_query(A, "select id, project_id from tasks")
    assert {r[0] for r in unfiltered["rows"]} == a_tasks
    assert all(r[1] == A for r in unfiltered["rows"])

    joined = await run_query(
        A, "select t.id, t.project_id, r.project_id from tasks t join runs r on r.task_id = t.id"
    )
    assert joined["rows"] and all(r[1] == A and r[2] == A for r in joined["rows"])

    projects = await run_query(A, "select id, name from projects")
    assert projects["rows"] == [[A, A]]

    # Even asking for B by name answers nothing of B's.
    assert (await run_query(A, f"select count(*) from tasks where project_id = '{B}'"))["rows"] == [
        [0]
    ]


@pytest.mark.parametrize(
    "sql",
    [
        "select * from main.tasks",
        "select * from temp.sqlite_master",
        "select * from sqlite_master",
        "select * from pragma_database_list",
        "with tasks as (select * from main.tasks) select * from tasks",
        "select * from deleted_projects",
        "select * from alembic_version",
    ],
)
async def test_nothing_reaches_around_the_views(seeded, sql):
    refused = await _refused(sql)
    assert refused.code in ("not_queryable", "query_error")
    assert B not in refused.message


# ------------------------------------------------------------------------------------- FR-3


@pytest.mark.parametrize(
    "item, sql",
    [
        ("api_keys", "select * from api_keys"),
        ("api_keys", "select k.id from api_keys as k"),
        ("api_keys", "select t.id from tasks t join api_keys k on k.project_id = t.project_id"),
        ("api_keys", "select (select id from api_keys limit 1)"),
        ("api_keys", 'select * from "API_KEYS"'),
        ("operator_credentials", "select * from operator_credentials"),
        ("capability_token_hash", "select capability_token_hash from runs"),
        ("capability_token_hash", "select r.capability_token_hash as h from runs r"),
        (
            "capability_token_hash",
            "select t.id from tasks t join runs r on r.capability_token_hash = t.id",
        ),
        ("capability_token_hash", "select x from (select [capability_token_hash] as x from runs)"),
        ("otlp_headers", "select otlp_headers from trace_settings"),
        ("working_directory", "select working_directory from projects"),
        ("path_key", "select path_key from projects"),
        ("workspace_dir", "select workspace_dir from runs"),
        ("workspace_fingerprints", "select * from workspace_fingerprints"),
        ("work_dir", "select work_dir from inbound_queue_entries"),
    ],
)
async def test_credentials_and_paths_are_refused_by_name(seeded, item, sql):
    refused = await _refused(sql)
    assert refused.code == "not_queryable"
    assert item in refused.message
    assert SECRET not in refused.message


@pytest.mark.parametrize("table", ["runs", "projects", "trace_settings"])
async def test_select_star_carries_no_credential_or_path(seeded, table):
    result = await run_query(A, f"select * from {table}")
    assert result["rows"]
    assert SECRET not in json.dumps(result)
    assert not set(result["columns"]) & {
        "capability_token_hash",
        "workspace_dir",
        "working_directory",
        "path_key",
        "otlp_headers",
    }


async def test_a_marker_in_a_string_literal_is_not_a_column(seeded):
    result = await run_query(
        A, "select count(*) from agent_outputs where content like '%workspace_dir%'"
    )
    assert result["rows"] == [[0]]


# ------------------------------------------------------------------------------------- FR-4


async def _state() -> Any:
    schema = await _direct("select type, name, sql from sqlite_master order by type, name")
    counts = [
        (await _direct(f"select count(*) from {t}"))[0][0] for t in ("tasks", "runs", "projects")
    ]
    titles = await _direct("select title from tasks order by id")
    return schema, counts, titles


@pytest.mark.parametrize(
    "sql",
    [
        "insert into tasks (id, project_id, title, description, status, priority, created_at, updated) "
        "values ('task-ro', 'x', 't', 'd', 'pending', 'low', '2026-01-01', '2026-01-01')",
        "update tasks set title = 'changed'",
        "delete from runs",
        "drop table tasks",
        "attach database 'file:dq-attached.db' as other",
        "create table x (a)",
        "pragma query_only = off",
        "with x as (select 1) delete from runs",
        "  /* lead */ -- line\n update tasks set title = 'c'",
    ],
)
async def test_writes_schema_changes_and_attach_are_refused(seeded, sql, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = await _state()
    refused = await _refused(sql)
    assert refused.code == "read_only", refused.message
    assert await _state() == before
    assert not (tmp_path / "dq-attached.db").exists()


async def test_a_recursive_cte_is_a_read(seeded):
    result = await run_query(
        A,
        "with recursive c(x) as (select 1 union all select x + 1 from c where x < 5) "
        "select sum(x) from c",
    )
    assert result["rows"] == [[15]]


# ------------------------------------------------------------------------------------- FR-5


async def test_regex_counts_three_markers(seeded):
    result = await run_query(
        A, r"select count(*) from agent_outputs where content regexp 'LEAK-MARKER-\d{4}'"
    )
    assert result["rows"] == [[3]]


async def test_an_invalid_regex_is_a_query_error(seeded):
    refused = await _refused("select count(*) from agent_outputs where content regexp '(unclosed'")
    assert refused.code == "query_error" and "regular expression" in refused.message


async def test_spans_by_tool_and_tool_arguments_are_the_projects(seeded):
    result = await run_query(
        A,
        "select name, count(*) as spans, "
        "round(sum((julianday(end_time) - julianday(start_time)) * 86400.0), 3) as seconds "
        "from trace_spans group by name order by name",
    )
    assert result["rows"] == [["execute_tool Bash", 2, 10.0], ["execute_tool Read", 3, 6.0]]

    args = await run_query(
        A, "select json_extract(attributes, '$.\"gen_ai.tool.call.arguments\"') from trace_spans"
    )
    patterns = sorted(json.loads(r[0])["p"] for r in args["rows"])
    want = sorted(
        json.loads(r[0])["p"]
        for r in await _direct(
            "select json_extract(attributes, '$.\"gen_ai.tool.call.arguments\"') from trace_spans "
            "where project_id = :p",
            p=A,
        )
    )
    assert patterns == want and len(want) == 5
    assert all(p.startswith(A) for p in patterns)


# ------------------------------------------------------------------------------------- FR-6


async def test_a_query_past_the_limit_is_stopped(seeded, monkeypatch):
    monkeypatch.setattr(config.settings, "aw_dashboard_query_timeout", 1)
    loop = asyncio.get_running_loop()
    started = loop.time()
    refused = await _refused(
        "with recursive c(x) as (select 1 union all select x + 1 from c) select count(*) from c"
    )
    assert refused.code == "timeout"
    assert "longer than 1 seconds" in refused.message
    assert loop.time() - started < 10


async def test_a_result_over_the_cap_is_cut_and_says_so(seeded):
    result = await run_query(
        A,
        "with recursive c(x) as (select 1 union all select x + 1 from c where x < 10050) select x from c",
    )
    assert config.settings.aw_dashboard_query_max_rows == 10000
    assert result["row_count"] == 10000 and len(result["rows"]) == 10000
    assert result["truncated"] is True
    assert result["rows"][-1] == [10000]


async def test_a_result_at_the_cap_is_not_marked_cut(seeded, monkeypatch):
    monkeypatch.setattr(config.settings, "aw_dashboard_query_max_rows", 5)
    result = await run_query(
        A,
        "with recursive c(x) as (select 1 union all select x + 1 from c where x < 5) select x from c",
    )
    assert result["row_count"] == 5 and result["truncated"] is False


# ------------------------------------------------------------------------------------- FR-7


async def test_the_reference_lists_only_what_answers(seeded):
    reference = query_reference()
    tables = reference["tables"]
    names = {t["name"] for t in tables}
    assert {
        "tasks",
        "runs",
        "agent_outputs",
        "trace_spans",
        "turn_usage",
        "projects",
        "messages",
    } <= names
    forbidden_tables = set(dashboard_query.NOT_QUERYABLE_TABLES)
    forbidden_columns = {c for _, c in dashboard_query.NOT_QUERYABLE_COLUMNS}
    assert not names & forbidden_tables
    for table in tables:
        assert table["meaning"]
        for column in table["columns"]:
            assert column["name"] not in forbidden_columns
            assert column["type"] and column["meaning"], (table["name"], column)
        columns = ", ".join(f'"{c["name"]}"' for c in table["columns"])
        await run_query(A, f'select {columns} from "{table["name"]}" limit 1')


def test_no_queryable_column_shares_a_never_queryable_name():
    """The refusal by name would refuse a legitimate column that shared one."""
    forbidden = set(dashboard_query._forbidden_names())
    for table in dashboard_query._exposed_tables():
        assert not set(table.columns) & forbidden, table.name


def test_the_reference_takes_meanings_from_the_models_comments():
    tables = {t["name"]: t for t in query_reference()["tables"]}
    spans = {c["name"]: c["meaning"] for c in tables["trace_spans"]["columns"]}
    assert "execute_tool" in spans["operation"]
    assert "span of an OpenTelemetry-shaped trace" in tables["trace_spans"]["meaning"]


# ------------------------------------------------------------------------------------ FR-14


async def test_the_loop_never_stalls_while_queries_run(seeded, monkeypatch):
    monkeypatch.setattr(config.settings, "aw_dashboard_query_timeout", 2)
    async with LagProbe() as probe:
        slow = asyncio.create_task(
            run_query(
                A,
                "with recursive c(x) as (select 1 union all select x + 1 from c) select count(*) from c",
            )
        )
        regex = asyncio.create_task(
            run_query(
                A,
                "with recursive c(x) as (select 1 union all select x + 1 from c where x < 300000) "
                "select count(*) from c where printf('span %d LEAK', x) regexp 'LEAK$'",
            )
        )
        regex_result = await regex
        with pytest.raises(QueryRefused) as stopped:
            await slow
    assert stopped.value.code == "timeout"
    assert regex_result["rows"] == [[300000]]
    assert probe.worst < STALL_LIMIT, f"the loop stalled {probe.worst * 1000:.0f} ms: {probe.why}"
