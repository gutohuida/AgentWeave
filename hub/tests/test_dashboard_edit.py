"""Editing a saved dashboard at the store and route seams (`change-a-dashboard-by-asking`, task
`edit-store-and-tools`: FR-1 to FR-9).

An agent edits through `PATCH /agent-actions/dashboards/{id}` with the version it read and a list of
operations; a whole replace (`POST /agent-actions/dashboards` with `dashboard_id`, or the
operator's PUT) is an edit too. Each keeps the version it replaced, so one undo restores it.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import Dashboard, DashboardVersion, Project
from hub.project_lifecycle import ProjectLifecycleService

from .test_dashboards import (
    AA,
    BROKEN,
    COUNT_BY_STATUS,
    OP,
    OTHER,
    P,
    _seed_tasks,
    _writer,
    events,
)
from .test_vault import _run_headers

__all__ = ["events"]  # the fixture, imported so this module's tests can ask for it

COUNT = "select count(*) as n from tasks"


def _four() -> List[Dict[str, Any]]:
    return [
        {"title": "Tasks by status", "query": COUNT_BY_STATUS, "kind": "bar"},
        {"title": "Broken", "query": BROKEN, "kind": "table"},
        {"title": "Task count", "query": COUNT, "kind": "number"},
        {"title": "Statuses", "query": COUNT_BY_STATUS, "kind": "table"},
    ]


async def _save(app, headers, name: str, panels: List[Dict[str, Any]]) -> Dict[str, Any]:
    saved = await app.post(
        AA, json={"name": name, "description": "the question", "panels": panels}, headers=headers
    )
    assert saved.status_code == 200, saved.text
    return _dashboard(saved.json())


def _dashboard(answer: Dict[str, Any]) -> Dict[str, Any]:
    """An agent's save or edit answer without what only its run adds (`panel_problems`, FR-9 of
    `dashboards-that-feel-alive-and-draw-right-the-first-time`): the dashboard a read answers."""
    return {k: v for k, v in answer.items() if k not in ("panel_problems", "next_step")}


async def _edit(app, headers, dash: Dict[str, Any], operations, base=None):
    return await app.patch(
        f"{AA}/{dash['id']}",
        json={
            "base_version": dash["version"] if base is None else base,
            "operations": operations,
        },
        headers=headers,
    )


async def _read(app, auth_headers, dash_id: str) -> Dict[str, Any]:
    answer = await app.get(f"{OP}/{dash_id}", headers=auth_headers)
    assert answer.status_code == 200, answer.text
    return answer.json()


async def _kept(where, value) -> int:
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count()).select_from(DashboardVersion).where(where == value)
        )


@pytest.mark.asyncio
async def test_an_edit_adds_a_panel_to_the_same_dashboard(app, auth_headers, events):
    """ac-edit-in-place: one dashboard, the same id, four panels, edited by that agent."""
    headers = await _writer("run-edit-1", "Analyst", 'Add a panel to the dashboard "Health".')
    dash = await _save(app, headers, "Health", _four()[:3])
    assert dash["version"] == 1 and dash["can_undo"] is False and dash["edited_by"] is None

    edited = await _edit(
        app,
        headers,
        dash,
        [{"op": "add_panel", "panel": {"title": "More", "query": COUNT, "kind": "number"}}],
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["id"] == dash["id"] and body["version"] == 2 and body["can_undo"] is True
    assert body["edited_by"] == "Analyst" and body["edited_at"]
    assert body["author"] == "Analyst" and body["created_at"] == dash["created_at"]
    assert body["panels"][:3] == dash["panels"]
    assert body["panels"][3]["id"].startswith("pnl-") and body["panels"][3]["title"] == "More"
    listed = (await app.get(OP, headers=auth_headers)).json()["dashboards"]
    assert [(d["id"], d["panel_count"], d["version"], d["can_undo"]) for d in listed] == [
        (dash["id"], 4, 2, True)
    ]
    assert (P, "dashboard_edited", {"id": dash["id"], "name": "Health", "version": 2}) in events


@pytest.mark.asyncio
async def test_changing_one_chart_kind_keeps_every_other_field(app, auth_headers):
    """ac-keep-the-rest, field by field."""
    headers = await _writer(
        "run-edit-2", "Analyst", "In the Four dashboard, make the third panel a table."
    )
    dash = await _save(app, headers, "Four", _four())
    target = dash["panels"][2]["id"]
    body = (
        await _edit(
            app, headers, dash, [{"op": "change_panel", "panel_id": target, "kind": "table"}]
        )
    ).json()
    body = _dashboard(body)
    after = await _read(app, auth_headers, dash["id"])
    assert after == body
    assert [p for p in after["panels"] if p["id"] != target] == [
        p for p in dash["panels"] if p["id"] != target
    ]
    assert after["panels"][2] == {**dash["panels"][2], "kind": "table"}
    assert (after["name"], after["description"]) == (dash["name"], dash["description"])


@pytest.mark.asyncio
async def test_every_operation_applies_in_order(app, auth_headers):
    headers = await _writer("run-edit-3", "Analyst", "Rework the Ops dashboard.")
    dash = await _save(app, headers, "Ops", _four())
    ids = [p["id"] for p in dash["panels"]]
    answer = await _edit(
        app,
        headers,
        dash,
        [
            {"op": "remove_panel", "panel_id": ids[1]},
            {"op": "move_panel", "panel_id": ids[3], "position": 0},
            {"op": "change_panel", "panel_id": ids[0], "title": "Renamed", "query": COUNT},
            {
                "op": "add_panel",
                "panel": {"title": "First", "query": COUNT, "kind": "number"},
                "position": 0,
            },
            {"op": "rename", "name": "Ops renamed"},
            {"op": "set_description", "description": "new question"},
        ],
    )
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert [p["id"] for p in body["panels"]][1:] == [ids[3], ids[0], ids[2]]
    assert body["panels"][0]["title"] == "First"
    assert body["panels"][2] == {**dash["panels"][0], "title": "Renamed", "query": COUNT}
    assert (body["name"], body["description"], body["version"]) == (
        "Ops renamed",
        "new question",
        2,
    )


@pytest.mark.asyncio
async def test_a_refused_operation_applies_nothing_and_names_itself(app, auth_headers):
    """ac-all-or-nothing: operation 1 (zero-based) refused, and a rename to a taken name."""
    headers = await _writer("run-edit-4", "Analyst", "Change the Atomic dashboard.")
    dash = await _save(app, headers, "Atomic", _four()[:2])
    await _save(app, headers, "Cost", _four()[:1])
    first = dash["panels"][0]["id"]

    for operations, index, reason in (
        (
            [
                {"op": "add_panel", "panel": {"title": "Runs", "query": COUNT, "kind": "number"}},
                {"op": "change_panel", "panel_id": first, "kind": "pie"},
            ],
            1,
            "invalid_chart_kind",
        ),
        ([{"op": "remove_panel", "panel_id": "pnl-000000000000"}], 0, "unknown_panel"),
        (
            [
                {"op": "set_description", "description": "x"},
                {"op": "change_panel", "panel_id": first, "title": " "},
            ],
            1,
            "invalid_panel",
        ),
        (
            [{"op": "change_panel", "panel_id": first, "query": "select * from api_keys"}],
            0,
            "not_queryable",
        ),
        ([{"op": "explode"}], 0, "unknown_operation"),
    ):
        refused = await _edit(app, headers, dash, operations)
        assert refused.status_code == 422, refused.text
        detail = refused.json()["detail"]
        assert detail["code"] == "operation_refused" and detail["message"]
        assert (detail["operation_index"], detail["reason"]) == (index, reason), detail
        assert await _read(app, auth_headers, dash["id"]) == dash

    taken = await _edit(app, headers, dash, [{"op": "rename", "name": "Cost"}])
    assert taken.status_code == 409 and taken.json()["detail"]["code"] == "dashboard_name_taken"
    assert await _read(app, auth_headers, dash["id"]) == dash
    assert await _kept(DashboardVersion.dashboard_id, dash["id"]) == 0


@pytest.mark.asyncio
async def test_a_stale_edit_or_replace_is_refused_with_the_current_dashboard(app, auth_headers):
    """ac-stale: two writes from the same base version."""
    headers = await _writer("run-edit-5", "Analyst", "Change the Stale dashboard.")
    dash = await _save(app, headers, "Stale", _four()[:2])
    newer = _dashboard(
        (
            await _edit(app, headers, dash, [{"op": "set_description", "description": "other"}])
        ).json()
    )
    assert newer["version"] == 2

    stale = await _edit(app, headers, dash, [{"op": "set_description", "description": "stale"}])
    assert stale.status_code == 409, stale.text
    detail = stale.json()["detail"]
    assert detail["code"] == "stale_version" and detail["message"]
    assert detail["current"] == newer
    replace = {"name": "Stale", "description": "replace", "panels": _four()[:1], "base_version": 1}
    by_agent = await app.post(AA, json={**replace, "dashboard_id": dash["id"]}, headers=headers)
    by_operator = await app.put(f"{OP}/{dash['id']}", json=replace, headers=auth_headers)
    for answer in (by_agent, by_operator):
        assert answer.status_code == 409, answer.text
        assert answer.json()["detail"]["code"] == "stale_version"
        assert answer.json()["detail"]["current"]["version"] == 2
    assert await _read(app, auth_headers, dash["id"]) == newer

    current = await _edit(app, headers, newer, [{"op": "set_description", "description": "now"}])
    assert current.status_code == 200 and current.json()["version"] == 3


@pytest.mark.asyncio
async def test_undo_restores_the_kept_version_and_is_itself_undone(app, auth_headers, events):
    """ac-undo and ac-undo-none at the routes, the operator's and the agent's."""
    headers = await _writer("run-edit-6", "Analyst", "Change, then undo, the Undo dashboard.")
    dash = await _save(app, headers, "Undo", _four()[:1])
    nothing = await app.post(f"{OP}/{dash['id']}/undo", headers=auth_headers)
    assert nothing.status_code == 409 and nothing.json()["detail"]["code"] == "nothing_to_undo"
    assert (await app.post(f"{AA}/{dash['id']}/undo", headers=headers)).status_code == 409
    assert await _read(app, auth_headers, dash["id"]) == dash

    edited = (
        await _edit(
            app,
            headers,
            dash,
            [{"op": "add_panel", "panel": {"title": "Runs", "query": COUNT, "kind": "number"}}],
        )
    ).json()
    undone = await app.post(f"{OP}/{dash['id']}/undo", headers=auth_headers)
    assert undone.status_code == 200, undone.text
    body = undone.json()
    assert body["panels"] == dash["panels"] and body["version"] == 3
    assert body["edited_by"] == "operator" and body["can_undo"] is True
    assert (P, "dashboard_edited", {"id": dash["id"], "name": "Undo", "version": 3}) in events

    again = await app.post(f"{AA}/{dash['id']}/undo", headers=headers)
    assert again.status_code == 200, again.text
    assert again.json()["panels"] == edited["panels"] and again.json()["version"] == 4
    assert again.json()["edited_by"] == "Analyst"
    assert await _kept(DashboardVersion.dashboard_id, dash["id"]) == 1


@pytest.mark.asyncio
async def test_a_whole_replace_keeps_what_it_replaced(app, auth_headers):
    headers = await _writer("run-edit-7", "Analyst", "Replace the Whole dashboard.")
    dash = await _save(app, headers, "Whole", _four()[:2])
    replaced = await app.post(
        AA,
        json={
            "name": "Whole",
            "description": "",
            "panels": _four()[2:],
            "dashboard_id": dash["id"],
        },
        headers=headers,
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["version"] == 2 and replaced.json()["can_undo"] is True
    undone = (await app.post(f"{OP}/{dash['id']}/undo", headers=auth_headers)).json()
    assert undone["panels"] == dash["panels"] and undone["description"] == dash["description"]


@pytest.mark.asyncio
async def test_the_agent_run_answers_what_the_screen_run_does(app, auth_headers):
    """ac-run-for-agent: the broken panel's error and the others' rows, as the screen's run."""
    await _seed_tasks()
    headers = await _run_headers("run-edit-8", "Analyst")
    dash = await _save(app, headers, "Broken", _four()[:3])
    screen = (await app.get(f"{OP}/{dash['id']}/run", headers=auth_headers)).json()
    agent = await app.get(f"{AA}/{dash['id']}/run", headers=headers)
    assert agent.status_code == 200, agent.text

    def shape(run):
        return [(p["id"], p["error"], p["warning"], p["columns"], p["rows"]) for p in run["panels"]]

    assert shape(agent.json()) == shape(screen)
    assert screen["panels"][1]["error"] and not screen["panels"][0]["error"]
    assert screen["panels"][2]["rows"] == [[4]]
    assert agent.json()["version"] == 1 and agent.json()["can_undo"] is False


@pytest.mark.asyncio
async def test_an_agent_cannot_reach_another_projects_dashboard(app, auth_headers):
    """ac-edit-boundary at the routes."""
    await _seed_tasks()
    async with async_session_factory() as db:
        db.add(
            Dashboard(
                id="dash-0ther0000002",
                project_id=OTHER,
                name="Theirs",
                description="",
                panels=[],
                author="x",
            )
        )
        await db.commit()
    headers = await _writer(
        "run-edit-9", "Analyst", "Describe the History dashboard, and dash-0ther0000002."
    )
    theirs = {"id": "dash-0ther0000002", "version": 1}
    for answer in (
        await _edit(app, headers, theirs, [{"op": "set_description", "description": "from A"}]),
        await app.post(f"{AA}/{theirs['id']}/undo", headers=headers),
        await app.get(f"{AA}/{theirs['id']}/run", headers=headers),
        await app.post(f"{OP}/{theirs['id']}/undo", headers=auth_headers),
    ):
        assert answer.status_code == 404, answer.text
        assert answer.json()["detail"]["code"] == "dashboard_not_found"
    async with async_session_factory() as db:
        row = await db.get(Dashboard, theirs["id"])
        assert (row.description, row.version) == ("", 1)


async def _ask(app, headers) -> str:
    asked = await app.post(
        "/api/v1/agent-actions/questions",
        headers=headers,
        json={
            "question": "Which team health dashboard?",
            "header": "Which dashboard",
            "options": [{"label": "Team health North"}, {"label": "Team health South"}],
            "multi_select": False,
            "blocking": True,
        },
    )
    assert asked.status_code == 201, asked.text
    return asked.json()["id"]


@pytest.mark.asyncio
async def test_a_run_whose_question_has_no_answer_writes_no_dashboard(app, auth_headers):
    """ac-ambiguous (FR-2): the agent asked which dashboard and the operator declined, or did not
    answer yet. Every dashboard write of that run is refused, nothing changes and nothing is
    created; a later run, or the same run once answered, writes as before."""
    writer = await _writer("run-amb-0", "Analyst", "Rename Team health South.")
    north = await _save(app, writer, "Team health North", _four()[:2])
    south = await _save(app, writer, "Team health South", _four()[:2])
    await _edit(app, writer, south, [{"op": "rename", "name": "Team health South"}])
    south = await _read(app, auth_headers, south["id"])
    before = [await _read(app, auth_headers, d["id"]) for d in (north, south)]

    headers = await _run_headers("run-amb-1", "Asker")
    question = await _ask(app, headers)
    for outcome in ("open", "declined"):
        if outcome == "declined":
            declined = await app.post(
                f"/api/v1/projects/{P}/questions/{question}/decline", headers=auth_headers
            )
            assert declined.status_code == 200, declined.text
        add = [{"op": "add_panel", "panel": {"title": "M", "query": COUNT, "kind": "number"}}]
        attempts = [
            await _edit(app, headers, north, add),
            await app.post(f"{AA}/{south['id']}/undo", headers=headers),
            await app.post(
                AA,
                json={"name": "Team health", "description": "", "panels": _four()[:1]},
                headers=headers,
            ),
            await app.post(
                AA,
                json={
                    "name": "Team health North",
                    "panels": _four()[:1],
                    "dashboard_id": north["id"],
                    "base_version": north["version"],
                },
                headers=headers,
            ),
        ]
        for refused in attempts:
            assert refused.status_code == 409, (outcome, refused.text)
            detail = refused.json()["detail"]
            assert (detail["code"], detail["question_id"]) == ("question_unanswered", question)
        assert [await _read(app, auth_headers, d["id"]) for d in (north, south)] == before
        listed = (await app.get(OP, headers=auth_headers)).json()["dashboards"]
        assert sorted(d["id"] for d in listed) == sorted([north["id"], south["id"]])
        # Reading and running stay open: they are how the agent names the candidates.
        assert (await app.get(f"{AA}/{north['id']}", headers=headers)).status_code == 200

    answered_run = await _run_headers("run-amb-2", "Answered")
    asked = await _ask(app, answered_run)
    answered = await app.patch(
        f"/api/v1/projects/{P}/questions/{asked}",
        json={"answer": "Team health North", "labels": ["Team health North"]},
        headers=auth_headers,
    )
    assert answered.status_code == 200, answered.text
    edited = await _edit(app, answered_run, north, add)
    assert edited.status_code == 200, edited.text
    later = await _writer("run-amb-3", "Later", "Undo the last change to Team health South.")
    assert (await app.post(f"{AA}/{south['id']}/undo", headers=later)).status_code == 200


def test_a_request_names_a_dashboard_by_its_id_or_its_whole_name():
    from hub.api.v1.dashboards import named_dashboards

    boards = [
        ("dash-000000000001", "Team health North"),
        ("dash-000000000002", "Team health South"),
        ("dash-000000000003", "Weekly"),
        ("dash-000000000004", "Weekly delivery"),
        ("dash-000000000005", "Cost"),
    ]
    assert named_dashboards("Add a panel to the team health dashboard.", boards) == []
    assert named_dashboards("Add a panel to the dashboard.", boards) == []
    assert named_dashboards("Add a panel to the Inventory dashboard.", boards) == []
    assert named_dashboards("Add it to team HEALTH south, please", boards) == ["dash-000000000002"]
    assert named_dashboards('Change the dashboard "X" (dash-000000000001): more', boards) == [
        "dash-000000000001"
    ]
    # A name met only inside a longer one is not named; met on its own as well, it is.
    assert named_dashboards("Fix Weekly delivery.", boards) == ["dash-000000000004"]
    assert named_dashboards("Copy Weekly delivery into Weekly.", boards) == [
        "dash-000000000003",
        "dash-000000000004",
    ]
    # Whole words only: "Costs" is not "Cost".
    assert named_dashboards("Costs went up.", boards) == []


async def _everything(app, auth_headers) -> List[Dict[str, Any]]:
    listed = (await app.get(OP, headers=auth_headers)).json()["dashboards"]
    return [await _read(app, auth_headers, d["id"]) for d in listed]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_text",
    [
        "Add a panel counting runs to the team health dashboard.",
        "Add a panel counting runs to the Inventory dashboard.",
        "Add a panel counting runs to the dashboard.",
    ],
)
async def test_a_write_to_a_dashboard_the_request_did_not_name_lands_nowhere(
    app, auth_headers, request_text
):
    """ac-ambiguous (FR-2), held by the Hub whatever the agent does: two names both fit, or none,
    or no name at all. The agent asked nothing and guessed; every write is refused, nothing
    changes and nothing is created -- not even a new dashboard saved after the refusal."""
    seeder = await _writer("run-unnamed-0", "Seeder", "")
    north = await _save(app, seeder, "Team health North", _four()[:1])
    await _save(app, seeder, "Team health South", _four()[:1])
    before = await _everything(app, auth_headers)

    headers = await _writer("run-unnamed-1", "Guesser", request_text)
    add = [{"op": "add_panel", "panel": {"title": "Runs", "query": COUNT, "kind": "number"}}]
    whole = {"name": "Team health North", "panels": _four()[:2], "dashboard_id": north["id"]}
    attempts = [
        await _edit(app, headers, north, add),
        await app.post(AA, json=whole, headers=headers),
        await app.post(f"{AA}/{north['id']}/undo", headers=headers),
        await app.post(AA, json={"name": "Team health", "panels": _four()[:1]}, headers=headers),
    ]
    for refused in attempts:
        assert refused.status_code == 409, refused.text
        detail = refused.json()["detail"]
        assert (detail["code"], detail["named"]) == ("dashboard_not_named", [])
        assert "ask_user" in detail["message"] or "Ask the operator" in detail["message"]
    assert await _everything(app, auth_headers) == before


@pytest.mark.asyncio
async def test_a_request_naming_the_second_dashboard_changes_only_the_second(app, auth_headers):
    """ac-by-name (FR-2) at the guard: the dashboard the request named is written, the other is
    refused, and the answer to a question the run asked names one as well."""
    seeder = await _writer("run-named-0", "Seeder", "")
    cost = await _save(app, seeder, "Cost watch", _four()[:1])
    review = await _save(app, seeder, "Review load", _four()[:1])
    headers = await _writer(
        "run-named-1", "Analyst", 'In the dashboard "Review load", add an "Open tasks" panel.'
    )
    add = [{"op": "add_panel", "panel": {"title": "Open", "query": COUNT, "kind": "number"}}]
    refused = await _edit(app, headers, cost, add)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["named"] == [review["id"]]
    assert await _read(app, auth_headers, cost["id"]) == cost
    edited = await _edit(app, headers, review, add)
    assert edited.status_code == 200, edited.text

    asker = await _writer("run-named-2", "Asker", "Add a panel to the dashboard.")
    assert (await _edit(app, asker, cost, add)).status_code == 409
    nothing_new = await app.post(AA, json={"name": "Fresh", "panels": _four()[:1]}, headers=asker)
    assert nothing_new.status_code == 409, nothing_new.text
    asked = await app.post(
        "/api/v1/agent-actions/questions",
        headers=asker,
        json={
            "question": "Which dashboard?",
            "header": "Which dashboard",
            "options": [{"label": "Cost watch"}, {"label": "Review load"}],
            "multi_select": False,
            "blocking": True,
        },
    )
    assert asked.status_code == 201, asked.text
    answered = await app.patch(
        f"/api/v1/projects/{P}/questions/{asked.json()['id']}",
        json={"answer": "Cost watch", "labels": ["Cost watch"]},
        headers=auth_headers,
    )
    assert answered.status_code == 200, answered.text
    assert (await _edit(app, asker, cost, add)).status_code == 200
    # Answered after the refusal, the run may save a new dashboard again.
    fresh = await app.post(AA, json={"name": "Fresh", "panels": _four()[:1]}, headers=asker)
    assert fresh.status_code == 200, fresh.text


@pytest.mark.asyncio
async def test_deleting_a_dashboard_or_its_project_removes_its_kept_version(app, auth_headers):
    """ac-history-delete."""
    headers = await _writer("run-edit-10", "Analyst", "Describe the History dashboard.")
    dash = await _save(app, headers, "History", _four()[:1])
    await _edit(app, headers, dash, [{"op": "set_description", "description": "kept"}])
    assert await _kept(DashboardVersion.dashboard_id, dash["id"]) == 1
    assert (await app.delete(f"{OP}/{dash['id']}", headers=auth_headers)).status_code == 204
    assert await _kept(DashboardVersion.dashboard_id, dash["id"]) == 0

    async with async_session_factory() as db:
        db.add(Project(id="proj-dashvictim2", name="Victim"))
        await db.flush()
        db.add(
            Dashboard(
                id="dash-v1ctim000002",
                project_id="proj-dashvictim2",
                name="Gone",
                panels=[],
                author="x",
            )
        )
        db.add(
            DashboardVersion(
                dashboard_id="dash-v1ctim000002",
                project_id="proj-dashvictim2",
                version=1,
                name="Gone",
                description="",
                panels=[],
            )
        )
        await db.commit()
    async with async_session_factory() as db:
        await ProjectLifecycleService(db).delete("proj-dashvictim2")
    assert await _kept(DashboardVersion.project_id, "proj-dashvictim2") == 0


def test_the_edit_tools_are_on_every_runners_surface():
    from hub import mcp_server
    from hub.api.v1.agents import _operations
    from hub.copilot_acp import HUB_MCP_TOOLS

    for tool in ("edit_dashboard", "undo_dashboard", "run_dashboard"):
        assert tool in mcp_server._CALLABLE_TOOLS and tool in HUB_MCP_TOOLS
        assert any(op.tool == tool for op in _operations())
    assert "base_version" in next(op for op in _operations() if op.tool == "save_dashboard").fields
    assert "delete_dashboard" not in mcp_server._CALLABLE_TOOLS
