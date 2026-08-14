"""Approving a document creates the work it declares.

The convention already existed and nothing consumed it. A payload carries `tasks` — a key, a
description, and the requirement keys each serves — `spec_payload` validates that those keys resolve,
and `spec_completeness` reads them to judge the decomposition. Then approval happened and the board
stayed empty.

From the run that found it: the authoring agent wrote six tasks into the document **and then created
three different ones by hand**, because the document's own were inert. Two decompositions, no
relationship between them, and the one that had been reviewed and approved was the one nobody worked
from.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/declared-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}

DECLARED = [
    {
        "key": "build-listing",
        "description": "Build the listing command. It shows what is due.",
        "requirements": ["alpha"],
    },
    {
        "key": "build-recording",
        "description": "Build the recording command.",
        "requirements": ["alpha", "beta"],
    },
]


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-dec", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-dec",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_dec-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_dec-secret"}


async def submit(app, run_headers, *, requirements=(ALPHA, BETA), tasks=DECLARED):
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Declared demo",
        "requirements": list(requirements),
    }
    if tasks is not None:
        document["tasks"] = list(tasks)
    saved = await app.post(SUBMIT, json={"path": PATH, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text


async def make_document(app, auth_headers, run_headers, **kwargs):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Declared demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    await submit(app, run_headers, **kwargs)


async def approve(app, auth_headers):
    closed = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    assert closed.status_code in (200, 409), closed.text
    for phase in ("proposed", "approved"):
        moved = await app.post(
            f"{BASE}/documents/phase",
            params={"path": PATH, "to": phase},
            json={"reason": "looks right"},
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text
    return moved


async def board(app, auth_headers):
    listed = await app.get(TASKS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return listed.json()


@pytest.mark.asyncio
async def test_approving_creates_the_declared_tasks_with_their_links(app, auth_headers, author):
    await make_document(app, auth_headers, author)
    assert await board(app, auth_headers) == []

    response = await approve(app, auth_headers)
    assert len(response.json()["tasks_created"]) == 2

    tasks = await board(app, auth_headers)
    assert len(tasks) == 2
    by_title = {task["title"]: task for task in tasks}

    listing = by_title["Build the listing command"]
    assert listing["status"] == "pending"
    # Who does the work is a roster decision, not something a specification dictates.
    assert listing["assignee"] is None
    assert [row["identifier"] for row in listing["requirement_links"]] == ["FR-1"]

    recording = by_title["Build the recording command"]
    assert sorted(row["identifier"] for row in recording["requirement_links"]) == ["FR-1", "FR-2"]


@pytest.mark.asyncio
async def test_re_approving_creates_no_duplicates(app, auth_headers, author):
    """Re-approving after a revision is what a revisable document earns. Duplicating the whole
    decomposition every time would make it something to avoid."""
    await make_document(app, auth_headers, author)
    await approve(app, auth_headers)
    assert len(await board(app, auth_headers)) == 2

    # Reopen, revise, approve again — with one new declared task.
    reopened = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "exploring"},
        json={"reason": "one more thing"},
        headers=auth_headers,
    )
    assert reopened.status_code == 200, reopened.text
    await submit(
        app,
        author,
        tasks=[
            *DECLARED,
            {"key": "build-export", "description": "Build the export.", "requirements": ["beta"]},
        ],
    )
    response = await approve(app, auth_headers)

    assert len(response.json()["tasks_created"]) == 1
    tasks = await board(app, auth_headers)
    assert len(tasks) == 3
    assert sorted(task["title"] for task in tasks) == [
        "Build the export",
        "Build the listing command",
        "Build the recording command",
    ]

    # And the declaration each task came from, which is what makes the second approval idempotent.
    from sqlalchemy import select

    from hub.db.models import Task

    async with async_session_factory() as session:
        keys = (
            (
                await session.execute(
                    select(Task.spec_task_key).where(Task.project_id == "proj-test")
                )
            )
            .scalars()
            .all()
        )
    assert sorted(keys) == ["build-export", "build-listing", "build-recording"]


@pytest.mark.asyncio
async def test_work_already_under_way_is_left_alone(app, auth_headers, author):
    """The document declares that work exists, not what has happened to it since.

    An approval that reset a task in progress, or reassigned it, would make re-approving a document
    something an operator learns to fear.
    """
    await make_document(app, auth_headers, author)
    await approve(app, auth_headers)

    tasks = await board(app, auth_headers)
    target = tasks[0]["id"]
    for status_name in ("assigned", "in_progress"):
        moved = await app.patch(
            f"{TASKS}/{target}", json={"status": status_name}, headers=auth_headers
        )
        assert moved.status_code == 200, moved.text
    renamed = await app.patch(
        f"{TASKS}/{target}", json={"assignee": "someone"}, headers=auth_headers
    )
    assert renamed.status_code == 200, renamed.text

    reopened = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "exploring"},
        json={"reason": "again"},
        headers=auth_headers,
    )
    assert reopened.status_code == 200, reopened.text
    await submit(app, author)
    await approve(app, auth_headers)

    after = {task["id"]: task for task in await board(app, auth_headers)}
    assert len(after) == 2
    assert after[target]["status"] == "in_progress"
    assert after[target]["assignee"] == "someone"


@pytest.mark.asyncio
async def test_a_document_declaring_no_tasks_creates_none(app, auth_headers, author):
    """A document approved for its requirements alone is a normal thing, not an error."""
    await make_document(app, auth_headers, author, tasks=None)
    response = await approve(app, auth_headers)

    assert response.status_code == 200
    assert response.json()["tasks_created"] == []
    assert await board(app, auth_headers) == []


@pytest.mark.asyncio
async def test_a_declared_task_naming_an_unknown_requirement_is_still_created(
    app, auth_headers, author
):
    """Preserved rather than dropped, and never a refusal.

    A declared task naming a requirement the index does not have is still work somebody asked for,
    and the unrecognised name is the evidence of what went wrong.
    """
    await make_document(app, auth_headers, author)

    # Reopen and declare a task naming a key the document does not carry. The payload validator
    # refuses that on submission, so write the state the Hub would reach after an external edit.
    from hub import spec_tasks
    from hub.db.models import SpecDocument
    from hub.spec_lifecycle import Actor

    async with async_session_factory() as session:
        from sqlalchemy import select

        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
        created = await spec_tasks.materialise(
            session,
            document,
            {
                "tasks": [
                    {
                        "key": "mystery",
                        "description": "Serve something nobody declared.",
                        "requirements": ["ghost"],
                    }
                ]
            },
            actor=Actor(kind="operator", name="operator"),
        )
        await session.commit()
        assert len(created) == 1

    tasks = {task["title"]: task for task in await board(app, auth_headers)}
    mystery = tasks["Serve something nobody declared"]
    assert mystery["requirement_links"] == []
    assert [row["reference"] for row in mystery["unresolved_requirements"]] == ["ghost"]


@pytest.mark.asyncio
async def test_a_failure_never_blocks_the_approval(app, auth_headers, author, monkeypatch):
    """Approval is the operator's decision about the specification.

    Failing it because the board could not be populated would leave the document unapproved — the
    one outcome nobody wanted — over a problem that has nothing to do with the decision.
    """
    await make_document(app, auth_headers, author)

    import hub.api.v1.spec as spec_module

    async def _explode(*args, **kwargs):
        raise RuntimeError("the board is on fire")

    monkeypatch.setattr(spec_module.spec_tasks, "materialise", _explode)

    response = await approve(app, auth_headers)
    assert response.status_code == 200
    assert response.json()["phase"] == "approved"
    assert response.json()["tasks_created"] == []


@pytest.mark.asyncio
async def test_a_declared_title_is_what_the_board_shows(app, auth_headers, author):
    """The decomposition approval produces was already good; the names were not.

    A description is a sentence written to be read in the document. Where the author says what to
    call the work, that is what a board should show — see `test_spec_declared_task_titles.py` for
    the derivation that covers a document which does not.
    """
    declared = [
        {
            "key": "verify-policy",
            "title": "Verify the fee policy",
            "description": (
                "Add automated examples covering the public API, strict input types, exception "
                "split, on-time and early return, Sunday exclusion, grace boundaries, charging, "
                "the cap with an uncapped day count, and invalid input."
            ),
            "requirements": ["alpha"],
        },
    ]
    await make_document(app, auth_headers, author, tasks=declared)
    await approve(app, auth_headers)

    tasks = await board(app, auth_headers)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Verify the fee policy"
    # The sentence is not lost — it is what the description is for.
    assert tasks[0]["description"].startswith("Add automated examples covering")


@pytest.mark.asyncio
async def test_a_task_declaring_no_title_gets_a_readable_one(app, auth_headers, author):
    declared = [
        {
            "key": "implement",
            "description": (
                "Implement the fixed Sunday exclusion together with the grace period, the daily "
                "rate, the monetary cap, the uncapped day count, and cent precision throughout."
            ),
            "requirements": ["alpha"],
        },
    ]
    await make_document(app, auth_headers, author, tasks=declared)
    await approve(app, auth_headers)

    title = (await board(app, auth_headers))[0]["title"]
    assert len(title) <= 81, title
    assert title.endswith("…")
    # And the word it stops on is whole.
    assert "Implement the fixed Sunday exclusion".startswith(title[:36])
