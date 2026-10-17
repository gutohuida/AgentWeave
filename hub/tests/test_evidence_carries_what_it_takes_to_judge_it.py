"""Evidence carries what it takes to judge it (`evidence-carries-what-it-takes-to-judge-it`, F673).

A piece used to be the builder's sentence and a path: no output, no requirement wording beside it,
no mark when a later piece replaced it, and no route for the diff its footprint names (vis-D5).
Real repository, real routes, as the gate tests do.
"""

import inspect

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run

from .test_approval_refuses_unaccepted_evidence import make_paths_footprint
from .test_task_integration import (
    AGENT_BRANCH,
    AGENT_EVIDENCE,
    BASE,
    PATH,
    TASKS,
    commit_on_branch,
    drive_to,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-worth-b", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-worth-b",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_worthb-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_worthb-secret"}


async def ready(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")


async def listed(app, auth_headers):
    response = await app.get(f"{BASE}/spec/evidence", headers=auth_headers)
    assert response.status_code == 200, response.text
    return {row["id"]: row for row in response.json()["evidence"]}


async def record(app, builder, **extra):
    body = {"identifier": "FR-1", "summary": "ran the tests", **extra}
    return await app.post(AGENT_EVIDENCE, json=body, headers=builder)


@pytest.mark.asyncio
async def test_a_piece_carries_its_command_output_tail_and_coverage(
    app, auth_headers, builder, tmp_path
):
    await ready(app, auth_headers, builder, tmp_path)
    task = await linked_task(app, auth_headers)
    output = "".join(f"line {n}\n" for n in range(900)) + "34 passed in 1.2s\n"
    assert len(output) > 6000

    recorded = await record(
        app, builder, task_id=task, command="npm test", output=output, covers="partial"
    )

    assert recorded.status_code == 201, recorded.text
    row = (await listed(app, auth_headers))[recorded.json()["id"]]
    assert row["command"] == "npm test"
    assert row["covers"] == "partial"
    assert row["output"].endswith("34 passed in 1.2s\n")
    assert len(row["output"]) <= 4100
    assert row["output"].startswith("[earlier output cut]"), row["output"][:60]


@pytest.mark.asyncio
async def test_an_unknown_coverage_is_refused_naming_the_permitted_ones(
    app, auth_headers, builder, tmp_path
):
    await ready(app, auth_headers, builder, tmp_path)
    task = await linked_task(app, auth_headers)

    refused = await record(app, builder, task_id=task, covers="mostly")

    assert refused.status_code == 422, refused.text
    assert "full" in refused.text and "partial" in refused.text


@pytest.mark.asyncio
async def test_a_piece_without_output_reads_null(app, auth_headers, builder, tmp_path):
    await ready(app, auth_headers, builder, tmp_path)
    task = await linked_task(app, auth_headers)
    recorded = await record(app, builder, task_id=task)
    row = (await listed(app, auth_headers))[recorded.json()["id"]]
    assert (row["command"], row["output"], row["covers"]) == (None, None, None)


@pytest.mark.asyncio
async def test_a_re_record_in_the_same_run_revises_the_output(app, auth_headers, builder, tmp_path):
    await ready(app, auth_headers, builder, tmp_path)
    task = await linked_task(app, auth_headers)
    first = await record(app, builder, task_id=task, command="npm test", output="1 failed\n")
    again = await record(app, builder, task_id=task, command="npm test", output="all passed\n")

    assert again.status_code == 200, again.text
    assert again.json()["id"] == first.json()["id"]
    row = (await listed(app, auth_headers))[first.json()["id"]]
    assert row["output"] == "all passed\n"


@pytest.mark.asyncio
async def test_a_piece_says_what_it_demonstrates_and_what_replaced_it(
    app, auth_headers, builder, tmp_path
):
    await ready(app, auth_headers, builder, tmp_path)
    task = await linked_task(app, auth_headers)
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    older = (await record(app, builder, task_id=task)).json()["id"]
    git(tmp_path, "checkout", "-q", "main")
    newer = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "summary": "checked by hand", "task_id": task},
        headers=auth_headers,
    )
    assert newer.status_code == 201, newer.text

    rows = await listed(app, auth_headers)
    for row in (rows[older], rows[newer.json()["id"]]):
        assert row["requirement"]["identifier"] == "FR-1"
        assert row["requirement"]["statement"] == "It lists what is due today"
        # FR-n repeats in every document; the piece names the one it is about (evidence browser).
        assert row["requirement"]["document"] == {"path": PATH, "title": "Integration demo"}
    assert rows[older]["superseded_by"] == newer.json()["id"]
    assert rows[newer.json()["id"]]["superseded_by"] is None


async def a_piece_on_a_branch(app, auth_headers, builder, tmp_path):
    task = await linked_task(app, auth_headers)
    commit_on_branch(tmp_path, AGENT_BRANCH, "feature.py", "print('hi')\n")
    evidence = (await record(app, builder, task_id=task)).json()["id"]
    git(tmp_path, "checkout", "-q", "main")
    return task, evidence


@pytest.mark.asyncio
async def test_the_diff_of_an_unmerged_piece_shows_its_work(app, auth_headers, builder, tmp_path):
    await ready(app, auth_headers, builder, tmp_path)
    _task, evidence = await a_piece_on_a_branch(app, auth_headers, builder, tmp_path)

    diff = await app.get(f"{BASE}/spec/evidence/{evidence}/diff", headers=auth_headers)

    assert diff.status_code == 200, diff.text
    body = diff.json()
    assert [f["path"] for f in body["files"]] == ["feature.py"]
    assert "+print('hi')" in body["files"][0]["patch"]
    assert body["truncated"] is False


@pytest.mark.asyncio
async def test_the_diff_survives_the_merge(app, auth_headers, builder, tmp_path):
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence = await a_piece_on_a_branch(app, auth_headers, builder, tmp_path)
    (tmp_path / "README.md").write_text("main moved\n", encoding="utf-8")
    git(tmp_path, "commit", "-q", "-am", "main moves")
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review", "approved"
    )
    assert walked.status_code == 200, walked.text
    assert (tmp_path / "feature.py").exists() or "feature.py" in git(
        tmp_path, "ls-tree", "-r", "--name-only", "main"
    ).stdout

    diff = await app.get(f"{BASE}/spec/evidence/{evidence}/diff", headers=auth_headers)

    assert diff.status_code == 200, diff.text
    assert [f["path"] for f in diff.json()["files"]] == ["feature.py"]


@pytest.mark.asyncio
async def test_a_piece_with_no_commit_answers_why(app, auth_headers, builder, tmp_path):
    await ready(app, auth_headers, builder, tmp_path)
    _task, evidence = await a_piece_on_a_branch(app, auth_headers, builder, tmp_path)
    await make_paths_footprint(evidence)

    diff = await app.get(f"{BASE}/spec/evidence/{evidence}/diff", headers=auth_headers)

    assert diff.status_code == 200, diff.text
    assert diff.json()["files"] == []
    assert diff.json()["reason"]


@pytest.mark.asyncio
async def test_an_unknown_piece_has_no_diff(app, auth_headers):
    missing = await app.get(f"{BASE}/spec/evidence/ev-nope/diff", headers=auth_headers)
    assert missing.status_code == 404


def test_the_tool_describes_the_new_fields_and_the_verdict():
    from hub import mcp_server

    tool = getattr(mcp_server.record_evidence, "fn", mcp_server.record_evidence)
    params = inspect.signature(tool).parameters
    assert {"command", "output", "covers"} <= set(params)
    doc = inspect.getdoc(tool) or ""
    assert "verdict" in doc
    for name in ("command", "output", "covers"):
        assert f"{name}:" in doc


# Unused import guard: TASKS is part of the shared fixture vocabulary.
assert TASKS
