"""Work linked to the requirements it serves, and what happens to what does not resolve.

The failure this replaces is quiet: `Task.requirements` held `"FR-8 — initialize-members"`, a string
that looks like a reference and joins to nothing, so "does FR-8 have a task?" was unanswerable while
looking answered. The tests that matter here are therefore about refusal and preservation — a wrong
identifier must be stated rather than stored, and a value nobody can interpret must survive.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Run,
    SpecDocument,
    Task,
    TaskRequirementLink,
    TaskRequirementReference,
)
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/links-demo/spec.html"
OTHER = "spec/changes/links-other/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}


@pytest.fixture
async def run_headers():
    token = "aw_run_links-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-links",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _document(app, auth_headers, run_headers, requirements, path=PATH):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Links demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": path,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Links demo",
                "requirements": requirements,
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text
    return saved.json()


async def _create_task(app, auth_headers, **body):
    payload = {"title": "Build it"}
    payload.update(body)
    return await app.post(TASKS, json=payload, headers=auth_headers)


async def _links(task_id):
    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskRequirementLink).where(TaskRequirementLink.task_id == task_id)
        )
        return list(result.scalars().all())


async def _references(task_id):
    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskRequirementReference).where(TaskRequirementReference.task_id == task_id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Naming requirements
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_names_the_requirements_it_serves(app, auth_headers, run_headers, tmp_path):
    await _document(app, auth_headers, run_headers, [ALPHA, BETA])

    response = await _create_task(app, auth_headers, requirement_ids=["FR-1", "FR-2"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert [entry["identifier"] for entry in body["requirement_links"]] == ["FR-1", "FR-2"]
    assert len(await _links(body["id"])) == 2


@pytest.mark.asyncio
async def test_an_unknown_identifier_is_refused_and_nothing_is_created(
    app, auth_headers, run_headers, tmp_path
):
    """Stated, not silently dropped — and not stored either. A task on the board
    whose author believes it is linked is worse than a refusal."""
    await _document(app, auth_headers, run_headers, [ALPHA])

    response = await _create_task(app, auth_headers, requirement_ids=["FR-999"])

    assert response.status_code == 422
    assert "FR-999" in response.text
    async with async_session_factory() as session:
        tasks = (await session.execute(select(Task))).scalars().all()
    assert tasks == []


@pytest.mark.asyncio
async def test_a_malformed_identifier_is_refused(app, auth_headers, run_headers, tmp_path):
    await _document(app, auth_headers, run_headers, [ALPHA])

    response = await _create_task(app, auth_headers, requirement_ids=["the first one"])

    assert response.status_code == 422
    assert "the first one" in response.text


@pytest.mark.asyncio
async def test_a_partly_unknown_set_links_nothing(app, auth_headers, run_headers, tmp_path):
    """A task that silently serves two of the three requirements it named is a
    task whose author believes it serves three."""
    await _document(app, auth_headers, run_headers, [ALPHA, BETA])

    response = await _create_task(app, auth_headers, requirement_ids=["FR-1", "FR-42"])

    assert response.status_code == 422
    async with async_session_factory() as session:
        assert (await session.execute(select(TaskRequirementLink))).scalars().all() == []


@pytest.mark.asyncio
async def test_an_identifier_two_documents_declare_is_refused_as_ambiguous(
    app, auth_headers, run_headers, tmp_path
):
    """Identifiers are minted per document, so FR-1 exists in both. Choosing one
    would link work to a requirement nobody named."""
    await _document(app, auth_headers, run_headers, [ALPHA], path=PATH)
    await _document(app, auth_headers, run_headers, [BETA], path=OTHER)

    response = await _create_task(app, auth_headers, requirement_ids=["FR-1"])

    assert response.status_code == 422
    assert "more than one document" in response.text


@pytest.mark.asyncio
async def test_naming_the_document_resolves_the_ambiguity(app, auth_headers, run_headers, tmp_path):
    await _document(app, auth_headers, run_headers, [ALPHA], path=PATH)
    await _document(app, auth_headers, run_headers, [BETA], path=OTHER)

    response = await _create_task(app, auth_headers, requirement_ids=["FR-1"], spec_document=OTHER)

    assert response.status_code == 201, response.text
    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == OTHER)))
            .scalars()
            .first()
        )
    assert response.json()["requirement_links"][0]["document_id"] == document.id


# ---------------------------------------------------------------------------
# The free-text field, and what it leaves behind
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_legacy_reference_becomes_a_link(app, auth_headers, run_headers, tmp_path):
    """The shape a real agent wrote on 2026-08-13, unprompted."""
    await _document(app, auth_headers, run_headers, [ALPHA, BETA])

    response = await _create_task(
        app, auth_headers, requirements=["FR-1 — initialize-members", "FR-2 — local-single-ledger"]
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert [entry["identifier"] for entry in body["requirement_links"]] == ["FR-1", "FR-2"]
    # And the original is still there, so a mis-parse is re-derivable.
    assert body["requirements"] == ["FR-1 — initialize-members", "FR-2 — local-single-ledger"]


@pytest.mark.asyncio
async def test_an_uninterpretable_reference_is_kept_not_dropped(
    app, auth_headers, run_headers, tmp_path
):
    await _document(app, auth_headers, run_headers, [ALPHA])

    response = await _create_task(
        app, auth_headers, requirements=["something nobody can resolve", "FR-77 — gone"]
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["requirement_links"] == []
    kept = {entry["reference"]: entry["reason"] for entry in body["unresolved_requirements"]}
    # Both kept — that is the load-bearing property, and §2.4 forbids discarding either.
    #
    # The two reasons differ because the situations do. `FR-77` claimed to name a requirement and
    # did not resolve, which deserves attention. The prose never claimed to name one, and calling
    # that "unresolved" made every task on a real board look like it had three problems while
    # nothing was wrong — the agent had simply used a free-text field as free text.
    assert kept == {
        "something nobody can resolve": "not_a_reference",
        "FR-77 — gone": "unknown",
    }


@pytest.mark.asyncio
async def test_free_text_never_refuses_the_create(app, auth_headers, run_headers, tmp_path):
    """A free-text field that starts rejecting values breaks every caller that
    was using it as prose."""
    await _document(app, auth_headers, run_headers, [ALPHA])

    response = await _create_task(app, auth_headers, requirements=["FR-999 — not a thing"])

    assert response.status_code == 201


# ---------------------------------------------------------------------------
# What links survive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_links_survive_a_terminal_status(app, auth_headers, run_headers, tmp_path):
    """What work served a requirement is asked mostly about finished work."""
    await _document(app, auth_headers, run_headers, [ALPHA])
    created = await _create_task(app, auth_headers, requirement_ids=["FR-1"])
    task_id = created.json()["id"]

    for next_status in ("assigned", "in_progress", "completed", "under_review", "approved"):
        moved = await app.patch(
            f"{TASKS}/{task_id}", json={"status": next_status}, headers=auth_headers
        )
        assert moved.status_code == 200, moved.text

    assert len(await _links(task_id)) == 1
    assert [entry["identifier"] for entry in moved.json()["requirement_links"]] == ["FR-1"]


@pytest.mark.asyncio
async def test_a_link_carries_who_created_it(app, auth_headers, run_headers, tmp_path):
    await _document(app, auth_headers, run_headers, [ALPHA])

    created = await _create_task(app, auth_headers, requirement_ids=["FR-1"])

    links = await _links(created.json()["id"])
    assert links[0].actor_kind == "operator"


@pytest.mark.asyncio
async def test_an_agent_created_link_carries_its_run(app, auth_headers, run_headers, tmp_path):
    await _document(app, auth_headers, run_headers, [ALPHA])

    created = await app.post(
        "/api/v1/agent-actions/tasks",
        json={"title": "Agent's task", "requirement_ids": ["FR-1"]},
        headers=run_headers,
    )
    assert created.status_code in (200, 201), created.text

    links = await _links(created.json()["id"])
    assert links[0].actor_kind == "agent"
    assert links[0].run_id == "run-links"


@pytest.mark.asyncio
async def test_a_later_update_adds_links_without_removing_any(
    app, auth_headers, run_headers, tmp_path
):
    await _document(app, auth_headers, run_headers, [ALPHA, BETA])
    created = await _create_task(app, auth_headers, requirement_ids=["FR-1"])
    task_id = created.json()["id"]

    updated = await app.patch(
        f"{TASKS}/{task_id}", json={"requirement_ids": ["FR-2"]}, headers=auth_headers
    )

    assert updated.status_code == 200, updated.text
    assert [entry["identifier"] for entry in updated.json()["requirement_links"]] == [
        "FR-1",
        "FR-2",
    ]


@pytest.mark.asyncio
async def test_linking_the_same_requirement_twice_is_one_link(
    app, auth_headers, run_headers, tmp_path
):
    await _document(app, auth_headers, run_headers, [ALPHA])
    created = await _create_task(app, auth_headers, requirement_ids=["FR-1"])
    task_id = created.json()["id"]

    await app.patch(f"{TASKS}/{task_id}", json={"requirement_ids": ["FR-1"]}, headers=auth_headers)

    assert len(await _links(task_id)) == 1


# ---------------------------------------------------------------------------
# Which requirements have no work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unserved_lists_requirements_with_no_linked_work(
    app, auth_headers, run_headers, tmp_path
):
    """The question the end-to-end run needed and could not ask."""
    from hub import requirement_links

    await _document(app, auth_headers, run_headers, [ALPHA, BETA])
    await _create_task(app, auth_headers, requirement_ids=["FR-1"])

    async with async_session_factory() as session:
        rows = await requirement_links.unserved(session, "proj-test")

    assert [row.identifier for row in rows] == ["FR-2"]


@pytest.mark.asyncio
async def test_a_retired_requirement_is_not_unserved(app, auth_headers, run_headers, tmp_path):
    """A requirement nobody has to build any more is not unserved, it is over."""
    from hub import requirement_links

    await _document(app, auth_headers, run_headers, [ALPHA, BETA])
    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Links demo",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )

    async with async_session_factory() as session:
        rows = await requirement_links.unserved(session, "proj-test")

    assert [row.identifier for row in rows] == ["FR-1"]


# ---------------------------------------------------------------------------
# Reindex and backfill
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reference_resolves_once_the_index_knows_about_it(
    app, auth_headers, run_headers, tmp_path
):
    """A project whose documents predate the index converts nothing at migration
    time. Reindexing makes those identifiers real, and the backfill converts what
    then resolves — without ever having guessed in the meantime."""
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Links demo"}, headers=auth_headers
    )
    assert created.status_code == 201

    task = await _create_task(app, auth_headers, requirements=["FR-1 — initialize-members"])
    task_id = task.json()["id"]
    assert len(await _references(task_id)) == 1
    assert await _links(task_id) == []

    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Links demo",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )

    response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json()["references"]["converted"] == 1
    assert len(await _links(task_id)) == 1
    assert await _references(task_id) == []
