"""`materialise()` turns a document's declared `depends_on`/`from` entries into edges.

`task-dependencies` section 4. The payload shape (section 1) and the completeness checks that gate
`propose()` (section 2) already exist; this is the layer that actually creates a `TaskDependency`
row once both ends of an edge exist, and resolves an imported entry to the task it names rather
than minting a second one (design D4).
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument, Task, TaskDependency, TaskDependencyReference
from hub.spec_lifecycle import Actor
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-tdep", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-tdep",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_tdep-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_tdep-secret"}


async def submit(app, run_headers, *, path, tasks, title="Dependency demo"):
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": title,
        "requirements": [ALPHA],
        "tasks": tasks,
    }
    saved = await app.post(SUBMIT, json={"path": path, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text


async def make_document(app, auth_headers, run_headers, *, path, tasks, title="Dependency demo"):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": title}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    await submit(app, run_headers, path=path, tasks=tasks, title=title)


async def approve(app, auth_headers, *, path):
    closed = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    assert closed.status_code in (200, 409), closed.text
    for phase in ("proposed", "approved"):
        moved = await app.post(
            f"{BASE}/documents/phase",
            params={"path": path, "to": phase},
            json={"reason": "looks right"},
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text
    return moved


async def reopen(app, auth_headers, *, path):
    moved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": "exploring"},
        json={"reason": "one more thing"},
        headers=auth_headers,
    )
    assert moved.status_code == 200, moved.text


async def tasks_by_key(project_id="proj-test"):
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(Task).where(
                        Task.project_id == project_id, Task.spec_task_key.is_not(None)
                    )
                )
            )
            .scalars()
            .all()
        )
    return {row.spec_task_key: row for row in rows}


async def edges():
    async with async_session_factory() as session:
        rows = (await session.execute(select(TaskDependency))).scalars().all()
    return {(row.task_id, row.depends_on_task_id) for row in rows}


async def dependency_references(task_id):
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(TaskDependencyReference).where(
                        TaskDependencyReference.task_id == task_id
                    )
                )
            )
            .scalars()
            .all()
        )
    return rows


PATH_LOCAL = "spec/changes/dep-local/spec.html"


@pytest.mark.asyncio
async def test_a_local_dependency_becomes_an_edge(app, auth_headers, author):
    declared = [
        {"key": "build-listing", "description": "Build the listing.", "requirements": ["alpha"]},
        {
            "key": "build-recording",
            "description": "Build the recording.",
            "requirements": ["alpha"],
            "depends_on": ["build-listing"],
        },
    ]
    await make_document(app, auth_headers, author, path=PATH_LOCAL, tasks=declared)
    await approve(app, auth_headers, path=PATH_LOCAL)

    by_key = await tasks_by_key()
    assert (
        by_key["build-recording"].id,
        by_key["build-listing"].id,
    ) in await edges()


@pytest.mark.asyncio
async def test_a_document_with_no_dependencies_materialises_no_edges(app, auth_headers, author):
    declared = [
        {"key": "solo", "description": "Stands alone.", "requirements": ["alpha"]},
    ]
    await make_document(app, auth_headers, author, path=PATH_LOCAL, tasks=declared)
    await approve(app, auth_headers, path=PATH_LOCAL)

    by_key = await tasks_by_key()
    assert not await dependency_references(by_key["solo"].id)
    all_edges = await edges()
    assert not any(pair[0] == by_key["solo"].id for pair in all_edges)


@pytest.mark.asyncio
async def test_re_approving_twice_creates_no_duplicate_edges(app, auth_headers, author):
    declared = [
        {"key": "build-listing", "description": "Build the listing.", "requirements": ["alpha"]},
        {
            "key": "build-recording",
            "description": "Build the recording.",
            "requirements": ["alpha"],
            "depends_on": ["build-listing"],
        },
    ]
    await make_document(app, auth_headers, author, path=PATH_LOCAL, tasks=declared)
    await approve(app, auth_headers, path=PATH_LOCAL)
    first_pass = await edges()

    await reopen(app, auth_headers, path=PATH_LOCAL)
    await submit(app, author, path=PATH_LOCAL, tasks=declared)
    await approve(app, auth_headers, path=PATH_LOCAL)

    assert await edges() == first_pass


@pytest.mark.asyncio
async def test_a_revision_adds_a_new_edge_to_an_existing_task_without_touching_it(
    app, auth_headers, author
):
    """4.4's decision: the document is the only writer of edges (D5), so a revision may add a new
    `depends_on` to a task an earlier approval already materialised — even though the task row
    itself is never touched (`test_work_already_under_way_is_left_alone`'s guarantee, unaffected).
    """
    declared = [
        {"key": "build-listing", "description": "Build the listing.", "requirements": ["alpha"]},
        {
            "key": "build-recording",
            "description": "Build the recording.",
            "requirements": ["alpha"],
        },
    ]
    await make_document(app, auth_headers, author, path=PATH_LOCAL, tasks=declared)
    await approve(app, auth_headers, path=PATH_LOCAL)
    assert not await edges()

    by_key = await tasks_by_key()
    listing_id, recording_id = by_key["build-listing"].id, by_key["build-recording"].id

    await reopen(app, auth_headers, path=PATH_LOCAL)
    revised = [
        declared[0],
        {**declared[1], "depends_on": ["build-listing"]},
    ]
    await submit(app, author, path=PATH_LOCAL, tasks=revised)
    response = await approve(app, auth_headers, path=PATH_LOCAL)
    # No new task — the edge is the only new fact.
    assert response.json()["tasks_created"] == []

    assert (recording_id, listing_id) in await edges()
    by_key_after = await tasks_by_key()
    assert by_key_after["build-listing"].id == listing_id
    assert by_key_after["build-recording"].id == recording_id


PATH_IMPORT_SOURCE = "spec/changes/dep-import-source/spec.html"
PATH_IMPORT_USER = "spec/changes/dep-import-user/spec.html"


@pytest.mark.asyncio
async def test_an_import_resolves_to_the_existing_task_without_creating_one(
    app, auth_headers, author
):
    await make_document(
        app,
        auth_headers,
        author,
        path=PATH_IMPORT_SOURCE,
        tasks=[{"key": "adopt-corpus", "description": "Adopt it.", "requirements": ["alpha"]}],
    )
    await approve(app, auth_headers, path=PATH_IMPORT_SOURCE)
    source_tasks = await tasks_by_key()
    source_task_id = source_tasks["adopt-corpus"].id

    declared = [
        {"key": "adopt-corpus", "from": {"document": PATH_IMPORT_SOURCE, "key": "adopt-corpus"}},
        {
            "key": "render-map",
            "description": "Render the map.",
            "requirements": ["alpha"],
            "depends_on": ["adopt-corpus"],
        },
    ]
    await make_document(app, auth_headers, author, path=PATH_IMPORT_USER, tasks=declared)
    response = await approve(app, auth_headers, path=PATH_IMPORT_USER)

    # Exactly one task created — the import entry never mints its own, so "adopt-corpus" still
    # resolves to the one Task row the source document created.
    assert len(response.json()["tasks_created"]) == 1
    by_key = await tasks_by_key()
    assert by_key["adopt-corpus"].id == source_task_id
    assert by_key["adopt-corpus"].spec_document_id == source_tasks["adopt-corpus"].spec_document_id

    render_map_id = by_key["render-map"].id
    assert (render_map_id, source_task_id) in await edges()
    assert not await dependency_references(render_map_id)


@pytest.mark.asyncio
async def test_an_unresolvable_import_is_preserved_and_reported_not_raised(
    app, auth_headers, author
):
    """The race D7 names: an import checked at `propose()` time can go stale by `approve()` time
    if the referenced document is reopened in between. `materialise()` must not raise — the
    approval stands, and the dangling reference is recorded rather than silently dropped."""
    await make_document(
        app,
        auth_headers,
        author,
        path=PATH_IMPORT_SOURCE,
        tasks=[{"key": "adopt-corpus", "description": "Adopt it.", "requirements": ["alpha"]}],
    )
    await approve(app, auth_headers, path=PATH_IMPORT_SOURCE)

    declared = [
        {"key": "adopt-corpus", "from": {"document": PATH_IMPORT_SOURCE, "key": "adopt-corpus"}},
        {
            "key": "render-map",
            "description": "Render the map.",
            "requirements": ["alpha"],
            "depends_on": ["adopt-corpus"],
        },
    ]
    await make_document(app, auth_headers, author, path=PATH_IMPORT_USER, tasks=declared)

    # Reach `proposed` while the import still resolves...
    closed = await app.post(
        f"{BASE}/documents/close-exploration",
        params={"path": PATH_IMPORT_USER},
        headers=auth_headers,
    )
    assert closed.status_code in (200, 409), closed.text
    proposed = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH_IMPORT_USER, "to": "proposed"},
        json={"reason": "looks right"},
        headers=auth_headers,
    )
    assert proposed.status_code == 200, proposed.text

    # ...then the source document is reopened, invalidating the import before approval.
    await reopen(app, auth_headers, path=PATH_IMPORT_SOURCE)

    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH_IMPORT_USER, "to": "approved"},
        json={"reason": "looks right"},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"
    assert len(approved.json()["tasks_created"]) == 1

    by_key = await tasks_by_key()
    render_map_id = by_key["render-map"].id
    assert not any(pair[0] == render_map_id for pair in await edges())
    references = await dependency_references(render_map_id)
    assert len(references) == 1
    assert references[0].reference == "adopt-corpus"
    assert references[0].reason == "document_not_approved"


@pytest.mark.asyncio
async def test_materialise_never_raises_for_a_malformed_import(app, auth_headers, author):
    """Direct unit-level check of `_resolve_import`'s defensive branch — a shape no validated
    payload can carry, reached only if a document's stored file was edited outside the Hub."""
    from hub import spec_tasks

    async with async_session_factory() as session:
        session.add(
            SpecDocument(
                id="doc-malformed",
                project_id="proj-test",
                path="spec/changes/dep-malformed/spec.html",
                title="Malformed",
                kind="change-spec",
                phase="proposed",
            )
        )
        await session.flush()
        created = await spec_tasks.materialise(
            session,
            (await session.execute(select(SpecDocument).where(SpecDocument.id == "doc-malformed")))
            .scalars()
            .first(),
            {
                "tasks": [
                    {
                        "key": "orphan",
                        "description": "Depends on nothing real.",
                        "requirements": [],
                        "depends_on": ["ghost-key"],
                    }
                ]
            },
            actor=Actor(kind="operator", name="operator"),
        )
        await session.commit()
        assert len(created) == 1
        orphan_id = created[0].id

    references = await dependency_references(orphan_id)
    assert len(references) == 1
    assert references[0].reference == "ghost-key"
    assert references[0].reason == "not_declared"


# ---------------------------------------------------------------------------
# Section 10.4 — the whole chain, end to end
#
# The gate itself (`test_dependency_gate.py`) and the HTTP wiring
# (`test_task_transitions_api.py`) are both covered against hand-built `TaskDependency` rows. This
# is the one path neither exercises: a document that DECLARES a three-hop chain, materialised for
# real through document approval, then walked hop by hop through the real operator PATCH route to
# confirm each gate opens on the prerequisite reaching APPROVED specifically — not merely
# `completed`, and not merely "the immediate prerequisite has started".
# ---------------------------------------------------------------------------

TASKS_BASE = "/api/v1/projects/proj-test/tasks"
PATH_CHAIN = "spec/changes/dep-chain/spec.html"


async def _patch_status(app, auth_headers, task_id, status):
    return await app.patch(f"{TASKS_BASE}/{task_id}", json={"status": status}, headers=auth_headers)


@pytest.mark.asyncio
async def test_the_whole_chain_gates_hop_by_hop_on_approved_not_completed(
    app, auth_headers, author
):
    declared = [
        {"key": "task-a", "description": "First.", "requirements": ["alpha"]},
        {
            "key": "task-b",
            "description": "Second.",
            "requirements": ["alpha"],
            "depends_on": ["task-a"],
        },
        {
            "key": "task-c",
            "description": "Third.",
            "requirements": ["alpha"],
            "depends_on": ["task-b"],
        },
    ]
    await make_document(app, auth_headers, author, path=PATH_CHAIN, tasks=declared)
    await approve(app, auth_headers, path=PATH_CHAIN)

    by_key = await tasks_by_key()
    a_id, b_id, c_id = by_key["task-a"].id, by_key["task-b"].id, by_key["task-c"].id

    # B cannot start while A is merely completed, not yet approved.
    for status in ("in_progress", "completed"):
        response = await _patch_status(app, auth_headers, a_id, status)
        assert response.status_code == 200, f"{status}: {response.text}"
    gated = await _patch_status(app, auth_headers, b_id, "in_progress")
    assert gated.status_code == 409, gated.text
    assert gated.json()["detail"]["code"] == "dependency_unmet"

    # C cannot start either -- it depends on B, which has not even been assigned yet.
    c_gated = await _patch_status(app, auth_headers, c_id, "in_progress")
    assert c_gated.status_code == 409, c_gated.text

    # A reaches approved -- B unblocks.
    for status in ("under_review", "approved"):
        response = await _patch_status(app, auth_headers, a_id, status)
        assert response.status_code == 200, f"{status}: {response.text}"
    unblocked = await _patch_status(app, auth_headers, b_id, "in_progress")
    assert unblocked.status_code == 200, unblocked.text

    # C is still gated -- B is only in_progress, not approved.
    still_gated = await _patch_status(app, auth_headers, c_id, "in_progress")
    assert still_gated.status_code == 409, still_gated.text

    # Walk B to approved -- C unblocks.
    for status in ("completed", "under_review", "approved"):
        response = await _patch_status(app, auth_headers, b_id, status)
        assert response.status_code == 200, f"{status}: {response.text}"
    final = await _patch_status(app, auth_headers, c_id, "in_progress")
    assert final.status_code == 200, final.text
