"""`a-loops-history-records-its-creation-and-queue-additions` (F570), task `record`.

A loop's events gain `loop_created` and one `loop_tasks_added` per adding call, written in the
transaction that adds the rows. Each test reads the events the way the operator does, through
`GET /loops/{id}`, and the refusal case reads the table so "nothing recorded" cannot be hidden by
the detail's ten-event window.
"""

import pytest
from sqlalchemy import func, select

from hub.db.engine import async_session_factory
from hub.db.models import EventLog

from .test_a_document_says_how_it_will_be_built import (  # noqa: F401  (run_headers is a fixture)
    FLOW,
    _agent,
    _approve,
    _document,
    _proposed,
    run_headers,
)
from .test_spec_documents_api import PATH as DOC_PATH

BASE = "/api/v1/projects/proj-test"
JOBS = f"{BASE}/jobs"
KINDS = ("loop_created", "loop_tasks_added", "loop_tasks_adopted")


def _loop_body(**overrides) -> dict:
    body = {
        "name": "History Loop",
        "agent": "kimi",
        "message": "work the queue",
        "cron": "0 2 * * *",
        "purpose": "keep the history",
        "stop_when_queue_empties": True,
        "initial_tasks": [{"title": "First"}, {"title": "Second"}],
    }
    body.update(overrides)
    return body


async def _events(app, auth_headers, loop_id, kind=None):
    detail = await app.get(f"{BASE}/loops/{loop_id}", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    return [e for e in detail.json()["events"] if kind is None or e["event_type"] == kind]


async def _count_history_rows() -> int:
    async with async_session_factory() as session:
        return await session.scalar(
            select(func.count()).select_from(EventLog).where(EventLog.event_type.in_(KINDS))
        )


@pytest.mark.asyncio
async def test_a_job_that_opens_a_loop_records_its_creation_and_its_initial_tasks(
    app, auth_headers
):
    created = await app.post(JOBS, json=_loop_body(), headers=auth_headers)
    assert created.status_code == 201, created.text
    loop_id = created.json()["loop"]["id"]

    (made,) = await _events(app, auth_headers, loop_id, "loop_created")
    assert made["data"] == {
        "by": {"kind": "operator", "agent": None, "run_id": None},
        "door": "jobs",
        "agent": "kimi",
        "purpose": "keep the history",
        "document": None,
        "document_path": None,
    }
    assert made["agent"] is None

    (added,) = await _events(app, auth_headers, loop_id, "loop_tasks_added")
    assert added["data"]["source"] == "initial_tasks"
    assert added["data"]["by"]["kind"] == "operator"
    assert [t["title"] for t in added["data"]["tasks"]] == ["First", "Second"]
    assert all(t["id"].startswith("task-") for t in added["data"]["tasks"])


@pytest.mark.asyncio
async def test_a_task_created_with_the_loops_id_adds_one_entry(app, auth_headers):
    job = (await app.post(JOBS, json=_loop_body(), headers=auth_headers)).json()
    loop_id = job["loop"]["id"]

    task = await app.post(
        f"{BASE}/tasks",
        json={"title": "Third", "assignee": "kimi", "loop_id": loop_id},
        headers=auth_headers,
    )
    assert task.status_code == 201, task.text

    added = await _events(app, auth_headers, loop_id, "loop_tasks_added")
    assert sorted(e["data"]["source"] for e in added) == ["create_task", "initial_tasks"]
    (third,) = [e for e in added if e["data"]["source"] == "create_task"]
    assert third["data"]["tasks"] == [{"id": task.json()["id"], "title": "Third"}]
    assert third["data"]["by"]["kind"] == "operator"


@pytest.mark.asyncio
async def test_a_task_without_a_loop_records_nothing(app, auth_headers):
    task = await app.post(f"{BASE}/tasks", json={"title": "Loose"}, headers=auth_headers)
    assert task.status_code == 201, task.text
    assert await _count_history_rows() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second_task",
    [{"title": "Second", "requirement_ids": ["FR-99"]}, {"title": "Second", "id": "task-seed-1"}],
    ids=["unknown-requirement", "duplicate-id"],
)
async def test_a_refused_creation_leaves_no_history_row(app, auth_headers, second_task):
    body = _loop_body(initial_tasks=[{"title": "First", "id": "task-seed-1"}, second_task])
    if second_task.get("id"):
        body["initial_tasks"][1]["id"] = "task-seed-1"

    refused = await app.post(JOBS, json=body, headers=auth_headers)

    assert refused.status_code in (409, 422), refused.text
    assert await _count_history_rows() == 0


@pytest.mark.asyncio
async def test_a_job_that_is_not_a_loop_records_nothing(app, auth_headers):
    plain = _loop_body()
    for key in ("purpose", "stop_when_queue_empties", "initial_tasks"):
        plain.pop(key)
    created = await app.post(JOBS, json=plain, headers=auth_headers)
    assert created.status_code == 201, created.text
    assert created.json()["loop"] is None
    assert await _count_history_rows() == 0


@pytest.mark.asyncio
async def test_approving_a_document_records_the_flow_it_starts(
    app, auth_headers, run_headers  # noqa: F811
):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))

    approved = await _approve(app, auth_headers)

    loops = (await app.get(f"{BASE}/loops", headers=auth_headers)).json()
    (flow,) = loops
    (made,) = await _events(app, auth_headers, flow["id"], "loop_created")
    assert made["data"]["door"] == "approval"
    assert made["data"]["by"]["kind"] == "operator"
    assert made["data"]["agent"] == "dev"
    assert made["data"]["document"] == flow["spec_document_id"]
    assert made["data"]["document_path"] == DOC_PATH
    (added,) = await _events(app, auth_headers, flow["id"], "loop_tasks_added")
    assert added["data"]["source"] == "flow_built"
    assert [t["id"] for t in added["data"]["tasks"]] == sorted(approved["tasks_created"])


@pytest.mark.asyncio
async def test_approving_a_document_whose_loop_exists_records_the_materialised_tasks(
    app, auth_headers, run_headers  # noqa: F811
):
    """The loop is created first and claims the document; approval then materialises into it."""
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    job = await app.post(
        JOBS,
        json=_loop_body(agent="dev", spec_document_id=DOC_PATH, initial_tasks=None),
        headers=auth_headers,
    )
    assert job.status_code == 201, job.text
    loop_id = job.json()["loop"]["id"]
    assert await _events(app, auth_headers, loop_id, "loop_tasks_added") == []

    approved = await _approve(app, auth_headers)

    (added,) = await _events(app, auth_headers, loop_id, "loop_tasks_added")
    assert added["data"]["source"] == "document"
    assert [t["id"] for t in added["data"]["tasks"]] == approved["tasks_created"]


@pytest.mark.asyncio
async def test_a_move_out_of_an_archived_loop_is_adopted_not_added(
    app, auth_headers, run_headers  # noqa: F811
):
    await _agent("dev")
    await _proposed(app, auth_headers, run_headers, _document(delivery=FLOW))
    await _approve(app, auth_headers)
    (old,) = (await app.get(f"{BASE}/loops", headers=auth_headers)).json()
    detail = (await app.get(f"{BASE}/loops/{old['id']}", headers=auth_headers)).json()
    archived = await app.post(f"{JOBS}/{detail['job_id']}/archive", headers=auth_headers)
    assert archived.status_code == 200, archived.text

    job = await app.post(
        JOBS,
        json=_loop_body(agent="dev", spec_document_id=DOC_PATH, initial_tasks=None),
        headers=auth_headers,
    )
    assert job.status_code == 201, job.text
    new_id = job.json()["loop"]["id"]

    for loop_id in (old["id"], new_id):
        assert len(await _events(app, auth_headers, loop_id, "loop_tasks_adopted")) == 1
    assert len(await _events(app, auth_headers, new_id, "loop_tasks_added")) == 0
    # The old loop's one addition is its own flow-build, from before it was archived.
    assert len(await _events(app, auth_headers, old["id"], "loop_tasks_added")) == 1
