"""Re-approving an amended document refreshes its open tasks (F535).

Reopening F532's approved document, retiring FR-3 and adding FR-5, then approving again changed no
task: the `backend` task kept its first title and its link to the retired FR-3, and FR-5 was served
by nothing until the operator linked it by hand. The rule was "a task that already exists is never
touched", which protected progress and assignment and froze the description of the work with them.

Now an open declared task follows the document (title, description, criteria, links to this
document's requirements); status, assignee, priority and other documents' links stay the board's; an
approved or rejected task stays as delivered; and the approval report says all of it.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/refresh-demo/spec.json"
OTHER = "spec/changes/other-demo/spec.json"


def _requirement(key):
    return {"key": key, "statement": f"It does {key}", "modal": "MUST"}


def _criterion(key, then="it is shown"):
    return {"key": f"c-{key}", "requirement": key, "given": "g", "when": "w", "then": then}


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-ref", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-ref",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_ref-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_ref-secret"}


async def submit(app, run_headers, keys, tasks, *, path=PATH, then="it is shown"):
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Refresh demo",
        "scope": {"in_scope": ["the demo"], "non_goals": ["everything else"]},
        "requirements": [_requirement(k) for k in keys],
        "acceptance_criteria": [_criterion(k, then) for k in keys],
        "tasks": tasks,
        "delivery": {"mode": "none"},
    }
    saved = await app.post(SUBMIT, json={"path": path, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text


async def create(app, auth_headers, path=PATH):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Refresh demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text


async def approve(app, auth_headers, path=PATH):
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    for phase in ("proposed", "approved"):
        moved = await app.post(
            f"{BASE}/documents/phase",
            params={"path": path, "to": phase},
            json={"reason": "looks right", "approve_anyway": phase == "approved"},
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text
    return moved.json()


async def reopen(app, auth_headers):
    moved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "exploring"},
        json={"reason": "amend"},
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text


async def task(app, auth_headers, task_id):
    got = await app.get(f"{TASKS}/{task_id}", headers=auth_headers)
    assert got.status_code == 200, got.text
    return got.json()


def links(view):
    return sorted((row["identifier"], row["document_id"]) for row in view["requirement_links"])


async def move(app, auth_headers, task_id, *statuses):
    for status_name in statuses:
        moved = await app.patch(
            f"{TASKS}/{task_id}", json={"status": status_name}, headers=auth_headers
        )
        assert moved.status_code == 200, moved.text


@pytest.mark.asyncio
async def test_an_open_task_follows_the_amended_document(app, auth_headers, author):
    """refresh-open: text and this document's links follow; progress, assignee, priority and the
    other document's link stay."""
    await create(app, auth_headers, OTHER)
    await submit(
        app,
        author,
        ["elsewhere"],
        [{"key": "x", "description": "x", "requirements": ["elsewhere"]}],
        path=OTHER,
    )

    await create(app, auth_headers)
    await submit(
        app,
        author,
        ["alpha", "beta"],
        [
            {"key": "t1", "title": "Old title", "description": "old", "requirements": ["alpha"]},
            {"key": "t2", "title": "Beta work", "description": "b", "requirements": ["beta"]},
        ],
    )
    first = await approve(app, auth_headers)
    ids = {row["key"]: row["id"] for row in first["approval_outcome"]["created"]}
    t1 = ids["t1"]

    await move(app, auth_headers, t1, "assigned", "in_progress")
    patched = await app.patch(
        f"{TASKS}/{t1}",
        json={
            "assignee": "someone",
            "priority": "high",
            "requirement_ids": ["FR-1"],
            "spec_document": OTHER,
        },
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    before = await task(app, auth_headers, t1)
    other_link = [pair for pair in links(before) if pair[1] != before["spec_document_id"]]
    assert len(other_link) == 1

    await reopen(app, auth_headers)
    # alpha retired, gamma added; t1 now serves beta and gamma.
    await submit(
        app,
        author,
        ["beta", "gamma"],
        [
            {
                "key": "t1",
                "title": "New title",
                "description": "new",
                "requirements": ["beta", "gamma"],
            },
            {"key": "t2", "title": "Beta work", "description": "b", "requirements": ["beta"]},
        ],
        then="it is refreshed",
    )
    second = await approve(app, auth_headers)
    assert second["tasks_created"] == []

    after = await task(app, auth_headers, t1)
    assert after["title"] == "New title"
    assert after["description"] == "new"
    assert after["acceptance_criteria"] == [
        "c-beta: Given g, when w, then it is refreshed",
        "c-gamma: Given g, when w, then it is refreshed",
    ]
    own = before["spec_document_id"]
    assert links(after) == sorted([("FR-2", own), ("FR-3", own), *other_link])
    assert (after["status"], after["assignee"], after["priority"]) == (
        "in_progress",
        "someone",
        "high",
    )


@pytest.mark.asyncio
async def test_approved_and_rejected_tasks_are_not_changed(app, auth_headers, author):
    """closed-unchanged: a closed task records what was asked when it was decided."""
    await create(app, auth_headers)
    await submit(
        app,
        author,
        ["alpha"],
        [
            {"key": "done", "title": "Done", "description": "d", "requirements": ["alpha"]},
            {"key": "no", "title": "Turned down", "description": "n", "requirements": ["alpha"]},
        ],
    )
    first = await approve(app, auth_headers)
    ids = {row["key"]: row["id"] for row in first["approval_outcome"]["created"]}
    await move(
        app, auth_headers, ids["done"], "in_progress", "completed", "under_review", "approved"
    )
    await move(app, auth_headers, ids["no"], "in_progress", "completed", "rejected")
    before = {key: await task(app, auth_headers, tid) for key, tid in ids.items()}

    await reopen(app, auth_headers)
    await submit(
        app,
        author,
        ["beta"],
        [
            {
                "key": "done",
                "title": "Done, renamed",
                "description": "d2",
                "requirements": ["beta"],
            },
            {
                "key": "no",
                "title": "Turned down, renamed",
                "description": "n2",
                "requirements": ["beta"],
            },
        ],
    )
    await approve(app, auth_headers)

    for key, tid in ids.items():
        after = await task(app, auth_headers, tid)
        for field in ("title", "description", "acceptance_criteria", "status"):
            assert after[field] == before[key][field], (key, field)
        assert links(after) == links(before[key]), key


@pytest.mark.asyncio
async def test_the_report_says_what_re_approval_did_and_did_not_change(app, auth_headers, author):
    """report-lists: refreshed with what changed, closed tasks linking a retired requirement, tasks
    no longer declared; an unchanged open task is not listed."""
    await create(app, auth_headers)
    await submit(
        app,
        author,
        ["alpha", "beta"],
        [
            {"key": "t1", "title": "Old title", "description": "d", "requirements": ["alpha"]},
            {"key": "t2", "title": "Closed", "description": "c", "requirements": ["alpha"]},
            {"key": "t3", "title": "Dropped", "description": "x", "requirements": ["beta"]},
            {"key": "t4", "title": "Same", "description": "s", "requirements": ["beta"]},
        ],
    )
    first = await approve(app, auth_headers)
    ids = {row["key"]: row["id"] for row in first["approval_outcome"]["created"]}
    await move(app, auth_headers, ids["t2"], "in_progress", "completed", "under_review", "approved")

    await reopen(app, auth_headers)
    await submit(
        app,
        author,
        ["beta", "gamma"],
        [
            {
                "key": "t1",
                "title": "New title",
                "description": "d",
                "requirements": ["beta", "gamma"],
            },
            {"key": "t2", "title": "Closed", "description": "c", "requirements": ["gamma"]},
            {"key": "t4", "title": "Same", "description": "s", "requirements": ["beta"]},
        ],
    )
    outcome = (await approve(app, auth_headers))["approval_outcome"]

    assert outcome["refreshed"] == [
        {
            "id": ids["t1"],
            "key": "t1",
            "title": "New title",
            "fields": ["title", "acceptance_criteria"],
            "linked": ["FR-2", "FR-3"],
            "unlinked": ["FR-1"],
        }
    ]
    assert outcome["closed_linking_retired"] == [
        {"id": ids["t2"], "key": "t2", "status": "approved", "requirements": ["FR-1"]}
    ]
    assert outcome["no_longer_declared"] == [{"id": ids["t3"], "key": "t3", "status": "pending"}]

    # Reported, never changed beyond the refresh rule.
    dropped = await task(app, auth_headers, ids["t3"])
    assert (dropped["title"], dropped["status"]) == ("Dropped", "pending")

    # The report is the stored record too: GET /spec serves the same.
    spec = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert spec.status_code == 200, spec.text
    assert spec.json()["approval_outcome"]["refreshed"] == outcome["refreshed"]
