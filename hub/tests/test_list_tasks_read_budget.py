"""F523: `list_tasks` answers in a result that fits, the way `read_spec_document` does.

A real board's page (100 tasks, each with a description and notes) serialised to 80-180 KB, above the
size at which Claude Code spills a tool result to a `tool-results/` file outside the workspace that
the guard then refuses. A page over `spec_reading.READ_BUDGET_CHARS` is written to
`.agentweave/reads/` in the run's workspace with the path in the answer; where it cannot be, the
page is cut to fit and `has_more` says so.
"""

import json

import pytest

from hub import spec_reading
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run

TASKS = "/api/v1/agent-actions/tasks"
OPERATOR_TASKS = "/api/v1/projects/proj-test/tasks"
COUNT = 40


@pytest.fixture
async def agent_with_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    async with async_session_factory() as session:
        session.add(Agent(id="ag-lt", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-lt",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                workspace_dir=str(workspace),
                capability_token_hash=hash_run_token("aw_run_lt-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_lt-secret"}, workspace


async def _board(app, auth_headers, count=COUNT):
    for n in range(count):
        made = await app.post(
            OPERATOR_TASKS,
            json={"title": f"Task {n}", "description": f"d{n} " + "x" * 900},
            headers=auth_headers,
        )
        assert made.status_code == 201, made.text


@pytest.mark.asyncio
async def test_a_page_over_the_budget_is_written_into_the_workspace(
    app, auth_headers, agent_with_workspace
):
    headers, workspace = agent_with_workspace
    await _board(app, auth_headers)

    response = await app.get(TASKS, headers=headers)
    assert response.status_code == 200, response.text
    answer = response.json()

    assert len(json.dumps(answer)) <= spec_reading.READ_BUDGET_CHARS
    assert answer["total"] == COUNT
    assert answer["has_more"] is False
    assert answer["written_to"] == ".agentweave/reads/tasks.all.all.0.md"
    assert answer["written_to"] in answer["read_with"]
    assert len(answer["task_ids"]) == COUNT
    text = (workspace / answer["written_to"]).read_text(encoding="utf-8")
    assert max(len(line) for line in text.splitlines()) <= 200
    for n in range(COUNT):
        assert f"Task {n}" in text
    for task_id in answer["task_ids"]:
        assert task_id in text


@pytest.mark.asyncio
async def test_a_page_that_fits_is_answered_inline(app, auth_headers, agent_with_workspace):
    headers, workspace = agent_with_workspace
    await _board(app, auth_headers, count=3)

    answer = (await app.get(TASKS, headers=headers)).json()

    assert "written_to" not in answer
    assert len(answer["tasks"]) == 3
    assert not (workspace / ".agentweave" / "reads").exists()


@pytest.mark.asyncio
async def test_a_page_with_no_place_to_write_is_cut_to_fit_and_says_so(
    app, auth_headers, agent_with_workspace
):
    headers, workspace = agent_with_workspace
    (workspace / ".agentweave").mkdir()
    (workspace / ".agentweave" / "reads").write_text("not a directory", encoding="utf-8")
    await _board(app, auth_headers)

    answer = (await app.get(TASKS, headers=headers)).json()

    assert "written_to" not in answer
    assert len(json.dumps(answer)) <= spec_reading.READ_BUDGET_CHARS
    assert 0 < len(answer["tasks"]) < COUNT
    assert answer["total"] == COUNT
    assert answer["has_more"] is True
    # The cut page continues where it stopped: ask again with offset set to how many came back.
    rest = (await app.get(TASKS, params={"offset": len(answer["tasks"])}, headers=headers)).json()
    assert rest["tasks"][0]["title"] == f"Task {len(answer['tasks'])}"


@pytest.mark.asyncio
async def test_each_page_has_a_file_of_its_own(app, auth_headers, agent_with_workspace):
    headers, workspace = agent_with_workspace
    await _board(app, auth_headers)

    first = (await app.get(TASKS, params={"limit": 20}, headers=headers)).json()
    second = (await app.get(TASKS, params={"limit": 20, "offset": 20}, headers=headers)).json()

    assert first["has_more"] is True and second["has_more"] is False
    assert first["written_to"] == ".agentweave/reads/tasks.all.all.0.md"
    assert second["written_to"] == ".agentweave/reads/tasks.all.all.20.md"
    assert (workspace / first["written_to"]).exists() and (
        workspace / second["written_to"]
    ).exists()
