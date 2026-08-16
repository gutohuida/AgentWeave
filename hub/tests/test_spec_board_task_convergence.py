"""A real board task and the document's own declared decomposition, converging instead of
duplicating.

Found live in `aw-loop10` (`2026-08-15-spec-flow-findings.md`): an operator who hand-created board
tasks with the right `requirement_ids` before proposing got `requirement_without_task` from
`propose` anyway, because `spec_completeness.check()`'s `tasked` set came only from the document's
own embedded `tasks[]` — never from the real `Task`/`TaskRequirementLink` rows the board and `/tasks`
API read and write. Once an agent was asked to declare `tasks[]` too (to clear that refusal),
approving materialised a *second* set of tasks for the identical requirements: five tasks on the
board for one decomposition, nothing reconciling the two.

`board_served` (`spec_completeness.check`) and the hand-made-requirement skip in
`spec_tasks.materialise` are the two halves of the fix. Both key off `Task.spec_task_key IS NULL` —
the signal that a task was created independently of any document's own decomposition, since neither
`TaskCreate` nor `TaskUpdate` exposes that column for a caller to set.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/board-convergence-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
CRITERION = {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
SCOPE = {"in_scope": ["the thing"], "non_goals": ["the other thing"]}


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-conv", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-conv",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_conv-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_conv-secret"}


async def submit(app, run_headers, *, tasks=None):
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Board convergence demo",
        "requirements": [ALPHA],
        "acceptance_criteria": [CRITERION],
        "scope": SCOPE,
    }
    if tasks is not None:
        document["tasks"] = tasks
    saved = await app.post(SUBMIT, json={"path": PATH, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text


async def make_document(app, auth_headers, run_headers, *, tasks=None):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": PATH, "title": "Board convergence demo"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    await submit(app, run_headers, tasks=tasks)


async def close_and_propose(app, auth_headers):
    closed = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    assert closed.status_code == 200, closed.text
    return await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)


async def board(app, auth_headers):
    listed = await app.get(TASKS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()


@pytest.mark.asyncio
async def test_a_hand_made_task_satisfies_propose_without_a_declared_task(
    app, auth_headers, author
):
    """The document declares no `tasks[]` at all; a real board task covers the only requirement."""
    await make_document(app, auth_headers, author, tasks=None)

    created = await app.post(
        TASKS, json={"title": "Build it by hand", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    proposed = await close_and_propose(app, auth_headers)
    assert proposed.status_code == 200, proposed.text
    body = proposed.json()
    assert body["blocking"] == [], body["blocking"]
    assert body["phase"] == "proposed"


@pytest.mark.asyncio
async def test_propose_still_refuses_when_nothing_covers_the_requirement(app, auth_headers, author):
    """Same document, no hand-made task and no declared task: the gate still works."""
    await make_document(app, auth_headers, author, tasks=None)

    proposed = await close_and_propose(app, auth_headers)
    assert proposed.status_code == 200, proposed.text
    codes = {finding["code"] for finding in proposed.json()["blocking"]}
    assert "requirement_without_task" in codes


@pytest.mark.asyncio
async def test_approving_does_not_duplicate_a_requirement_a_hand_made_task_already_covers(
    app, auth_headers, author
):
    """The exact `aw-loop10` reproduction: a hand-made task exists first, the document also declares
    its own task for the same requirement, and approval must not mint a second one."""
    declared = [
        {
            "key": "build-it",
            "description": "Build it, declared in the document.",
            "requirements": ["alpha"],
        }
    ]
    await make_document(app, auth_headers, author, tasks=declared)

    hand_made = await app.post(
        TASKS, json={"title": "Build it by hand", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert hand_made.status_code == 201, hand_made.text
    hand_made_id = hand_made.json()["id"]
    assert len(await board(app, auth_headers)) == 1

    proposed = await close_and_propose(app, auth_headers)
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["blocking"] == [], proposed.json()["blocking"]

    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={"reason": "the hand-made task already covers this"},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["tasks_created"] == []

    tasks = await board(app, auth_headers)
    assert len(tasks) == 1
    assert tasks[0]["id"] == hand_made_id
