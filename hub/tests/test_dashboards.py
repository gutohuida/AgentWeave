"""Dashboards at the store and route seams (`ask-any-agent-for-a-dashboard-and-get-one-that-stays`,
task `dashboard-store-and-tools`: FR-1, FR-7, FR-9 to FR-13).

An agent saves through `/agent-actions/dashboards` on its run credential; the operator lists, runs
and deletes through `/projects/{project_id}/dashboards`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import Dashboard, Project, Task
from hub.project_lifecycle import ProjectLifecycleService
from hub.sse import sse_manager

from .test_vault import _run_headers

P = "proj-test"
OTHER = "proj-dashother01"
AA = "/api/v1/agent-actions/dashboards"
OP = f"/api/v1/projects/{P}/dashboards"

COUNT_BY_STATUS = "select status, count(*) as n from tasks group by status order by status"
BROKEN = "select no_such_column from tasks"


def _panels() -> List[Dict[str, Any]]:
    return [
        {"title": "Tasks by status", "query": COUNT_BY_STATUS, "kind": "bar"},
        {"title": "Broken", "query": BROKEN, "kind": "table"},
        {"title": "Task count", "query": "select count(*) from tasks", "kind": "number"},
    ]


@pytest.fixture
def events(monkeypatch) -> List[Tuple[str, str, Any]]:
    seen: List[Tuple[str, str, Any]] = []
    original = sse_manager.publish

    def publish(project_id: str, event_type: str, data: Any) -> None:
        seen.append((project_id, event_type, data))
        original(project_id, event_type, data)

    monkeypatch.setattr(sse_manager, "publish", publish)
    return seen


async def _seed_tasks() -> None:
    async with async_session_factory() as db:
        for n, status in enumerate(["pending", "pending", "approved", "in_progress"]):
            db.add(Task(id=f"task-dash{n:08d}", project_id=P, title=f"t{n}", status=status))
        db.add(Project(id=OTHER, name="Other"))
        db.add(Task(id="task-dashother001", project_id=OTHER, title="o", status="approved"))
        await db.commit()


@pytest.mark.asyncio
async def test_an_agent_saves_a_dashboard_with_a_broken_panel_and_it_is_listed(
    app, auth_headers, events
):
    """ac-save: three panels, one whose query names a missing column, saved and read back."""
    headers = await _run_headers("run-dash-1", "Builder")
    saved = await app.post(
        AA,
        json={"name": "Health", "description": "How is it going?", "panels": _panels()},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["id"].startswith("dash-") and len(body["id"]) == 17
    assert body["author"] == "Builder" and body["created_at"]
    assert [(p["title"], p["query"], p["kind"]) for p in body["panels"]] == [
        (p["title"], p["query"], p["kind"]) for p in _panels()
    ]
    assert all(p["id"].startswith("pnl-") for p in body["panels"])
    assert (P, "dashboard_saved", {"id": body["id"], "name": "Health"}) in events

    # Read back in a fresh request (and a fresh session): what survives a restart is the row.
    listed = (await app.get(OP, headers=auth_headers)).json()["dashboards"]
    assert [(d["name"], d["author"], d["panel_count"]) for d in listed] == [
        ("Health", "Builder", 3)
    ]
    assert listed[0]["created_at"]
    read = (await app.get(f"{OP}/{body['id']}", headers=auth_headers)).json()
    assert read["panels"] == body["panels"]
    agent_listed = (await app.get(AA, headers=headers)).json()["dashboards"]
    assert [d["id"] for d in agent_listed] == [body["id"]]
    agent_read = (await app.get(f"{AA}/{body['id']}", headers=headers)).json()
    assert agent_read["panels"][1]["query"] == BROKEN


@pytest.mark.asyncio
async def test_a_panel_naming_another_chart_kind_is_refused_and_nothing_is_saved(app, auth_headers):
    """ac-chart-kinds (save half): every kind of the fixed set saves; any other is refused."""
    headers = await _run_headers("run-dash-2", "Builder")
    every_kind = [
        {"title": kind, "query": "select 1", "kind": kind}
        for kind in ("number", "table", "bar", "stacked_bar", "line")
    ]
    ok = await app.post(
        AA, json={"name": "Kinds", "description": "", "panels": every_kind}, headers=headers
    )
    assert ok.status_code == 200, ok.text

    panels = _panels() + [{"title": "Pie", "query": "select 1", "kind": "pie"}]
    refused = await app.post(
        OP, json={"name": "Pies", "description": "", "panels": panels}, headers=auth_headers
    )
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "invalid_chart_kind" and detail["panel"] == 3
    assert "'pie'" in detail["message"]
    names = [d["name"] for d in (await app.get(OP, headers=auth_headers)).json()["dashboards"]]
    assert names == ["Kinds"]


@pytest.mark.asyncio
async def test_saving_refuses_a_never_queryable_name_without_running_anything(app, auth_headers):
    headers = await _run_headers("run-dash-3", "Builder")
    for query in (
        "select * from api_keys",
        "select r.capability_token_hash from runs r",
        "select x from (select working_directory as x from projects)",
    ):
        refused = await app.post(
            AA,
            json={
                "name": "Leak",
                "description": "",
                "panels": [{"title": "t", "query": query, "kind": "table"}],
            },
            headers=headers,
        )
        assert refused.status_code == 422, query
        assert refused.json()["detail"]["code"] == "not_queryable", refused.text
    async with async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Dashboard)) == 0


@pytest.mark.asyncio
async def test_a_name_is_unique_within_the_project(app, auth_headers):
    body = {"name": "Same", "description": "", "panels": _panels()}
    assert (await app.post(OP, json=body, headers=auth_headers)).status_code == 201
    taken = await app.post(OP, json=body, headers=auth_headers)
    assert taken.status_code == 409
    assert taken.json()["detail"]["code"] == "dashboard_name_taken"


@pytest.mark.asyncio
async def test_running_answers_each_panel_alone(app, auth_headers):
    """ac-panel-error: the missing column's error, the line's warning, and the working rows."""
    await _seed_tasks()
    panels = [
        {"title": "Missing column", "query": BROKEN, "kind": "table"},
        {"title": "Line of text", "query": "select title, status from tasks", "kind": "line"},
        {"title": "By status", "query": COUNT_BY_STATUS, "kind": "bar"},
    ]
    saved = await app.post(
        OP, json={"name": "Mixed", "description": "", "panels": panels}, headers=auth_headers
    )
    assert saved.status_code == 201, saved.text
    ran = await app.get(f"{OP}/{saved.json()['id']}/run", headers=auth_headers)
    assert ran.status_code == 200, ran.text
    body = ran.json()
    assert body["fetched_at"]
    missing, line, working = body["panels"]

    assert missing["error"]["code"] == "query_error"
    assert "no_such_column" in missing["error"]["message"]
    assert missing["rows"] == [] and missing["warning"] is None

    assert line["error"] is None
    assert line["warning"] and "numeric" in line["warning"]

    assert working["error"] is None and working["warning"] is None
    assert working["columns"] == ["status", "n"]
    # Only this project's tasks: OTHER's approved task is not counted.
    assert working["rows"] == [["approved", 1], ["in_progress", 1], ["pending", 2]]


@pytest.mark.asyncio
async def test_a_refresh_sees_rows_added_since_and_the_fetched_at_moves(app, auth_headers):
    await _seed_tasks()
    saved = await app.post(
        OP,
        json={
            "name": "Count",
            "description": "",
            "panels": [{"title": "n", "query": "select count(*) from tasks", "kind": "number"}],
        },
        headers=auth_headers,
    )
    url = f"{OP}/{saved.json()['id']}/run"
    first = (await app.get(url, headers=auth_headers)).json()
    async with async_session_factory() as db:
        db.add(Task(id="task-dashlate0001", project_id=P, title="late", status="pending"))
        await db.commit()
    second = (await app.get(url, headers=auth_headers)).json()
    assert first["panels"][0]["rows"] == [[4]] and second["panels"][0]["rows"] == [[5]]
    assert second["fetched_at"] > first["fetched_at"]


@pytest.mark.asyncio
async def test_the_operator_deletes_and_it_is_gone_from_both_lists(app, auth_headers, events):
    """ac-delete."""
    headers = await _run_headers("run-dash-4", "Builder")
    saved = (
        await app.post(
            AA, json={"name": "Doomed", "description": "", "panels": _panels()}, headers=headers
        )
    ).json()
    deleted = await app.delete(f"{OP}/{saved['id']}", headers=auth_headers)
    assert deleted.status_code == 204, deleted.text
    assert (P, "dashboard_deleted", {"id": saved["id"], "name": "Doomed"}) in events
    assert (await app.get(OP, headers=auth_headers)).json()["dashboards"] == []
    assert (await app.get(AA, headers=headers)).json()["dashboards"] == []
    assert (await app.get(f"{AA}/{saved['id']}", headers=headers)).status_code == 404
    assert (await app.delete(f"{OP}/{saved['id']}", headers=auth_headers)).status_code == 404


@pytest.mark.asyncio
async def test_agents_have_no_delete_route(app):
    headers = await _run_headers("run-dash-5", "Builder")
    saved = (
        await app.post(
            AA, json={"name": "Kept", "description": "", "panels": _panels()}, headers=headers
        )
    ).json()
    assert (await app.delete(f"{AA}/{saved['id']}", headers=headers)).status_code == 405


@pytest.mark.asyncio
async def test_another_projects_dashboard_is_not_found(app, auth_headers):
    await _seed_tasks()
    async with async_session_factory() as db:
        db.add(
            Dashboard(
                id="dash-0ther0000001",
                project_id=OTHER,
                name="Theirs",
                description="",
                panels=[],
                author="x",
            )
        )
        await db.commit()
    headers = await _run_headers("run-dash-6", "Builder")
    for method, url, kwargs in (
        ("get", f"{OP}/dash-0ther0000001", {}),
        ("get", f"{OP}/dash-0ther0000001/run", {}),
        ("delete", f"{OP}/dash-0ther0000001", {}),
        (
            "put",
            f"{OP}/dash-0ther0000001",
            {"json": {"name": "Mine", "description": "", "panels": _panels()}},
        ),
    ):
        answer = await getattr(app, method)(url, headers=auth_headers, **kwargs)
        assert answer.status_code == 404, (method, url, answer.text)
    assert (await app.get(f"{AA}/dash-0ther0000001", headers=headers)).status_code == 404
    replaced = await app.post(
        AA,
        json={
            "name": "Mine",
            "description": "",
            "panels": _panels(),
            "dashboard_id": "dash-0ther0000001",
        },
        headers=headers,
    )
    assert replaced.status_code == 404
    assert (await app.get(OP, headers=auth_headers)).json()["dashboards"] == []


@pytest.mark.asyncio
async def test_replacing_keeps_the_dashboard_and_its_panel_ids(app, auth_headers):
    headers = await _run_headers("run-dash-7", "Builder")
    saved = (
        await app.post(
            OP, json={"name": "V1", "description": "", "panels": _panels()}, headers=auth_headers
        )
    ).json()
    panels = [dict(p) for p in saved["panels"]]
    panels[0]["title"] = "Renamed"
    del panels[2]["id"]
    put = await app.put(
        f"{OP}/{saved['id']}",
        json={"name": "V2", "description": "now", "panels": panels},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["id"] == saved["id"] and body["name"] == "V2"
    assert [p["id"] for p in body["panels"][:2]] == [p["id"] for p in saved["panels"][:2]]
    assert body["panels"][2]["id"] != saved["panels"][2]["id"]
    assert body["panels"][0]["title"] == "Renamed"

    by_agent = await app.post(
        AA,
        json={
            "name": "V3",
            "description": "",
            "panels": body["panels"][:1],
            "dashboard_id": saved["id"],
        },
        headers=headers,
    )
    assert by_agent.status_code == 200, by_agent.text
    assert by_agent.json()["author"] == "Builder"
    assert by_agent.json()["created_at"] == saved["created_at"]
    listed = (await app.get(OP, headers=auth_headers)).json()["dashboards"]
    assert [(d["name"], d["panel_count"]) for d in listed] == [("V3", 1)]


@pytest.mark.asyncio
async def test_an_agent_runs_a_query_over_its_own_project(app):
    """ac-run-query through the agent's route: the count matches a hand-written one."""
    await _seed_tasks()
    headers = await _run_headers("run-dash-8", "Builder")
    ran = await app.post(f"{AA}/query", json={"sql": COUNT_BY_STATUS}, headers=headers)
    assert ran.status_code == 200, ran.text
    async with async_session_factory() as db:
        expected = [
            list(r)
            for r in (
                await db.execute(
                    select(Task.status, func.count())
                    .where(Task.project_id == P)
                    .group_by(Task.status)
                    .order_by(Task.status)
                )
            ).all()
        ]
    body = ran.json()
    assert body["columns"] == ["status", "n"] and body["rows"] == expected
    assert body["truncated"] is False

    refused = await app.post(f"{AA}/query", json={"sql": "select * from api_keys"}, headers=headers)
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "not_queryable"
    written = await app.post(f"{AA}/query", json={"sql": "delete from tasks"}, headers=headers)
    assert written.status_code == 422 and written.json()["detail"]["code"] == "read_only"


@pytest.mark.asyncio
async def test_every_table_in_the_agents_reference_answers(app, auth_headers):
    """ac-reference through the agent's route, the dashboards table included."""
    from hub.dashboard_query import NOT_QUERYABLE_COLUMNS, NOT_QUERYABLE_TABLES

    headers = await _run_headers("run-dash-9", "Builder")
    reference = (await app.get(f"{AA}/query-reference", headers=headers)).json()
    assert reference == (await app.get(f"{OP}/query-reference", headers=auth_headers)).json()
    tables = {t["name"]: t for t in reference["tables"]}
    assert "dashboards" in tables
    for name in NOT_QUERYABLE_TABLES:
        assert name not in tables
    for table, column in NOT_QUERYABLE_COLUMNS:
        if table in tables:
            assert column not in {c["name"] for c in tables[table]["columns"]}
    for name in tables:
        answer = await app.post(
            f"{AA}/query", json={"sql": f'select * from "{name}" limit 1'}, headers=headers
        )
        assert answer.status_code == 200, (name, answer.text)


@pytest.mark.asyncio
async def test_deleting_the_project_removes_its_dashboards(app):
    """ac-project-delete: the generic project sweep reaches the table with no code of its own."""
    async with async_session_factory() as db:
        db.add(Project(id="proj-dashvictim", name="Victim"))
        await db.flush()
        db.add(
            Dashboard(
                id="dash-v1ctim000001",
                project_id="proj-dashvictim",
                name="Gone",
                description="",
                panels=_panels(),
                author="x",
            )
        )
        await db.commit()
    async with async_session_factory() as db:
        await ProjectLifecycleService(db).delete("proj-dashvictim")
    async with async_session_factory() as db:
        remaining = await db.scalar(
            select(func.count())
            .select_from(Dashboard)
            .where(Dashboard.project_id == "proj-dashvictim")
        )
    assert remaining == 0


def test_the_tools_are_on_every_runners_surface():
    from hub import mcp_server
    from hub.api.v1.agents import _operations
    from hub.copilot_acp import HUB_MCP_TOOLS

    for tool in (
        "dashboard_query_reference",
        "run_dashboard_query",
        "save_dashboard",
        "list_dashboards",
        "read_dashboard",
    ):
        assert tool in mcp_server._CALLABLE_TOOLS and tool in HUB_MCP_TOOLS
        assert any(op.tool == tool for op in _operations())
    assert "delete_dashboard" not in mcp_server._CALLABLE_TOOLS
