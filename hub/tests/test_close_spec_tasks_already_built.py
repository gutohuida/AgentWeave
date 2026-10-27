"""Closing an approved change's tasks as already built (`every-task-can-always-be-moved-on`).

FR-5 `close-in-one-step` and FR-6 `evidence-awaits-review`, through the real routes and a real
repository: a four-task document whose work is already on main, closed in one operator action
naming that commit; then a reviewer -- an agent granted the decision -- accepts three tasks'
evidence and rejects one. On master 43301a6 the route does not exist (404), and the only ways to
close the four were a paid run each or deleting them by hand (src-28d4bff83265).
"""

import pytest
from sqlalchemy import func, select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument, Task
from hub.spec_payload import SCHEMA_VERSION

from ._spec_versions import content_version
from .test_task_integration import commit_on_branch, commits_on, git, make_repo, set_main_branch

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
TASKS = f"/api/v1/projects/{P}/tasks"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
AGENT_DECIDE = "/api/v1/agent-actions/spec/evidence/{id}/decision"
PATH = "spec/changes/built-already/spec.json"

KEYS = ("alpha", "beta", "gamma", "delta")


@pytest.fixture
async def author_headers():
    """The run that writes the document."""
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-author",
                project_id=P,
                agent="Architect",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_author-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_author-secret"}


@pytest.fixture
async def reviewer_headers():
    """QA, granted the decision on evidence, deciding from its own run."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-qa", project_id=P, name="QA", can_accept_evidence=True))
        session.add(
            Run(
                id="run-qa",
                project_id=P,
                agent="QA",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_qa-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_qa-secret"}


def _document():
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Built already",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": key, "statement": f"It does {key}", "modal": "MUST"} for key in KEYS
        ],
        "acceptance_criteria": [
            {"key": f"c-{key}", "requirement": key, "given": "g", "when": "w", "then": "t"}
            for key in KEYS
        ],
        # A chain, so the walk has to pass a prerequisite that is not approved yet.
        "tasks": [
            {
                "key": f"t-{key}",
                "description": f"Build {key}",
                "requirements": [key],
                "depends_on": [f"t-{KEYS[i - 1]}"] if i else [],
            }
            for i, key in enumerate(KEYS)
        ],
        "delivery": {"mode": "none"},
    }


async def _approved_document(app, auth_headers, author_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Built already"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        AGENT_DOCS, json={"path": PATH, "document": _document()}, headers=author_headers
    )
    assert saved.status_code == 200, saved.text
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/check", params={"path": PATH}, headers=auth_headers)
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={
            "content_version": await content_version(app, auth_headers, PATH),
            "reason": "",
            "approve_anyway": True,
        },
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text


async def _tasks():
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        rows = await session.execute(
            select(Task).where(Task.spec_document_id == document.id).order_by(Task.title)
        )
        return {task.title: task for task in rows.scalars().all()}


async def _run_count():
    async with async_session_factory() as session:
        return (await session.execute(select(func.count()).select_from(Run))).scalar_one()


async def _closed(app, auth_headers, author_headers, root):
    make_repo(root)
    await _approved_document(app, auth_headers, author_headers)
    work = commit_on_branch(root, "feature", "built.py", "x = 1\n")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--ff-only", "feature")
    assert work in commits_on(root, "main")
    await set_main_branch("main")
    tasks = await _tasks()
    assert len(tasks) == 4 and {t.status for t in tasks.values()} == {"pending"}
    runs_before = await _run_count()

    closed = await app.post(
        f"{BASE}/documents/{PATH}/close-already-built",
        json={"commits": [work[:12]]},
        headers=auth_headers,
    )
    assert closed.status_code == 200, closed.text
    return work, closed.json(), runs_before


@pytest.mark.asyncio
async def test_close_in_one_step(app, auth_headers, author_headers, tmp_path):
    work, body, runs_before = await _closed(app, auth_headers, author_headers, tmp_path)

    assert body["commits"] == [work]
    tasks = await _tasks()
    statuses = {task.status for task in tasks.values()}
    assert not statuses & {"pending", "in_progress"}, statuses
    assert statuses == {"under_review"}
    assert {task.assignee for task in tasks.values()} == {None}
    assert await _run_count() == runs_before, "closing as already built started a run"


@pytest.mark.asyncio
async def test_evidence_awaits_review(
    app, auth_headers, author_headers, reviewer_headers, tmp_path
):
    work, body, _ = await _closed(app, auth_headers, author_headers, tmp_path)

    listed = await app.get(f"{BASE}/spec/evidence", params={"document": PATH}, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    rows = listed.json()["evidence"]
    by_identifier = {row["requirement"]["identifier"]: row for row in rows}
    assert sorted(by_identifier) == ["FR-1", "FR-2", "FR-3", "FR-4"], rows
    for row in rows:
        assert row["review_state"] == "awaiting", row
        assert work in row["locator"], row
        assert row["footprint"]["commit_sha"] == work, row

    tasks = await _tasks()
    by_task = {row["task_id"]: row for row in rows}
    accept = [tasks[f"Build {key}"].id for key in KEYS[:3]]
    reject = tasks["Build delta"].id
    # Out of dependency order, so approval cannot lean on a prerequisite being approved first.
    for task_id in reversed(accept):
        decided = await app.post(
            AGENT_DECIDE.format(id=by_task[task_id]["id"]),
            json={"decision": "accepted"},
            headers=reviewer_headers,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json().get("approved_task") == task_id
    refused = await app.post(
        AGENT_DECIDE.format(id=by_task[reject]["id"]),
        json={"decision": "rejected", "reason": "delta is not on main"},
        headers=reviewer_headers,
    )
    assert refused.status_code == 200, refused.text
    assert "approved_task" not in refused.json()

    tasks = await _tasks()
    assert [tasks[f"Build {key}"].status for key in KEYS] == [
        "approved",
        "approved",
        "approved",
        "under_review",
    ]
    for key in KEYS:
        task_id = tasks[f"Build {key}"].id
        history = await app.get(f"{TASKS}/{task_id}/transitions", headers=auth_headers)
        assert history.status_code == 200, history.text
        notes = [row["note"] for row in history.json()["transitions"]]
        assert [row["to_status"] for row in history.json()["transitions"]][:3] == [
            "in_progress",
            "completed",
            "under_review",
        ]
        assert all(note and "already built" in note and work[:12] in note for note in notes), notes
        if key != "delta":
            assert history.json()["transitions"][-1]["to_status"] == "approved"
            assert "accepted by QA" in notes[-1]


@pytest.mark.asyncio
async def test_a_commit_not_on_main_is_refused_and_changes_nothing(
    app, auth_headers, author_headers, tmp_path
):
    make_repo(tmp_path)
    await _approved_document(app, auth_headers, author_headers)
    stray = commit_on_branch(tmp_path, "elsewhere", "stray.py", "y = 2\n")
    git(tmp_path, "checkout", "-q", "main")
    await set_main_branch("main")

    refused = await app.post(
        f"{BASE}/documents/{PATH}/close-already-built",
        json={"commits": [stray]},
        headers=auth_headers,
    )

    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"]["code"] == "commit_not_on_main"
    assert {task.status for task in (await _tasks()).values()} == {"pending"}


@pytest.mark.asyncio
async def test_only_an_approved_change_is_closed(app, auth_headers, author_headers, tmp_path):
    make_repo(tmp_path)
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Built already"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    head = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    await set_main_branch("main")

    refused = await app.post(
        f"{BASE}/documents/{PATH}/close-already-built",
        json={"commits": [head]},
        headers=auth_headers,
    )

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "not_approved"


@pytest.mark.asyncio
async def test_the_operators_acceptance_approves_too(app, auth_headers, author_headers, tmp_path):
    work, body, _ = await _closed(app, auth_headers, author_headers, tmp_path)
    first = body["tasks"][0]

    decided = await app.post(
        f"{BASE}/spec/evidence/{first['evidence'][0]}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )

    assert decided.status_code == 200, decided.text
    assert decided.json()["approved_task"] == first["id"]
    async with async_session_factory() as session:
        assert (await session.get(Task, first["id"])).status == "approved"
    history = (await app.get(f"{TASKS}/{first['id']}/transitions", headers=auth_headers)).json()
    assert "accepted by the operator" in history["transitions"][-1]["note"]
