"""A turn bound to a task names the specification that task implements.

`read_spec_document` documents its argument as "the path, as given in your turn context". For a run
triggered on a **task** the context gave no path and no document id, so the tool it advertised could
not be called. From the run that found it:

    I tried read_spec_document on several guessed paths (spec/late-fees.html,
    spec/late-fee-calculator.html, …) and all 404. document_id in the task ledger is
    spdoc-d5632909 but that's not an accepted path.

It happened twice in one run, in two separate conversations — the second time blocking evidence
entirely — and the agents worked around it by messaging each other for the path.

The wording matters as much as the presence. The block that already existed says the operator is
*viewing* a document and to treat it as context "not as an instruction to act on it", which is
exactly backwards for a task run, where the document is the instruction.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument, Task
from hub.run_task_binding import spec_document_for_task
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
CONTEXT = "/api/v1/projects/proj-test/agents/agent-context"
PATH = "spec/changes/task-context/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-tc", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-tc",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_tc-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_tc-secret"}


async def _document(app, auth_headers, run_headers, tasks=None):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Task context"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Task context",
        "requirements": [ALPHA],
    }
    if tasks is not None:
        document["tasks"] = tasks
    saved = await app.post(SUBMIT, json={"path": PATH, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text


async def _task_row(task_id: str) -> Task:
    async with async_session_factory() as session:
        return await session.get(Task, task_id)


@pytest.mark.asyncio
async def test_a_task_created_against_requirements_records_their_document(
    app, auth_headers, author
):
    """`spec_document_id` was written only by `spec_tasks.materialise`.

    So the link reached tasks a document *declared* and no others — an agent that decomposed its
    own work got nothing, which is most of the tasks on a real board.
    """
    await _document(app, auth_headers, author)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    assert created.json()["spec_document_id"] is not None
    row = await _task_row(created.json()["id"])
    assert row.spec_document_id is not None


@pytest.mark.asyncio
async def test_a_task_naming_no_requirements_records_no_document(app, auth_headers, author):
    """Guessing which document unrelated work is against is worse than leaving the agent to ask."""
    await _document(app, auth_headers, author)
    created = await app.post(TASKS, json={"title": "Something else"}, headers=auth_headers)
    assert created.status_code == 201, created.text
    assert created.json()["spec_document_id"] is None


@pytest.mark.asyncio
async def test_the_path_is_resolved_from_the_task(app, auth_headers, author):
    """The id names nothing an agent has seen; the path is what the read tool accepts."""
    await _document(app, auth_headers, author)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    row = await _task_row(created.json()["id"])

    async with async_session_factory() as session:
        assert await spec_document_for_task(session, row) == PATH
        assert await spec_document_for_task(session, None) is None


@pytest.mark.asyncio
async def test_a_task_pointing_at_a_vanished_document_resolves_to_nothing(
    app, auth_headers, author
):
    """A dangling id must not fail the turn — it just contributes no line."""
    await _document(app, auth_headers, author)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    async with async_session_factory() as session:
        row = await session.get(Task, created.json()["id"])
        row.spec_document_id = "spdoc-gone"
        await session.commit()
        assert await spec_document_for_task(session, row) is None


@pytest.mark.asyncio
async def test_the_declared_task_link_still_holds(app, auth_headers, author):
    """The path this always covered, so widening it did not narrow anything."""
    declared = [
        {
            "key": "build-listing",
            "title": "Build the listing",
            "description": "Build the listing command.",
            "requirements": ["alpha"],
        }
    ]
    await _document(app, auth_headers, author, tasks=declared)
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

    listed = await app.get(TASKS, headers=auth_headers)
    task = listed.json()[0]
    assert task["spec_task_key"] == "build-listing"
    assert task["spec_document_id"] is not None

    async with async_session_factory() as session:
        row = await session.get(Task, task["id"])
        assert await spec_document_for_task(session, row) == PATH


@pytest.mark.asyncio
async def test_the_document_row_is_the_one_the_requirements_belong_to(app, auth_headers, author):
    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
        assert document is None, "the fixture starts clean"

    await _document(app, auth_headers, author)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
    assert created.json()["spec_document_id"] == document.id


async def _render(document=None, task_document=None, task_id=None):
    """The canonical context, rendered directly.

    The trigger route is not reachable here without spawning a runner, and what is under test is
    the text the agent reads, which this is.
    """
    from hub.api.v1.agents import _get_session_data, _render_hub_agent_context

    async with async_session_factory() as session:
        agent_row = (
            (
                await session.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == "builder")
                )
            )
            .scalars()
            .first()
        )
        rendered = await _render_hub_agent_context(
            agent="builder",
            project_id="proj-test",
            db=session,
            session_data=await _get_session_data("proj-test", session),
            agent_row=agent_row,
            spec_document=document,
            task_spec_document=task_document,
            task_id=task_id,
        )
    return rendered["context"]


@pytest.mark.asyncio
async def test_the_context_names_the_document_the_task_implements(app, auth_headers, author):
    await _document(app, auth_headers, author)
    context = await _render(task_document=PATH, task_id="task-1")

    assert "The specification this task implements" in context
    assert PATH in context
    assert f"read_spec_document('{PATH}')" in context
    assert "task-1" in context


@pytest.mark.asyncio
async def test_the_framing_is_to_implement_not_to_observe(app, auth_headers, author):
    """The existing block says the operator is *viewing* a document and to treat it as context
    "not as an instruction to act on it" — exactly backwards where the document is the work."""
    await _document(app, auth_headers, author)
    context = await _render(task_document=PATH, task_id="task-1")

    block = context.split("### The specification this task implements", 1)[1]
    block = block.split("###", 1)[0]
    assert "operator is viewing" not in block
    assert "not as an instruction to act on it" not in block


@pytest.mark.asyncio
async def test_one_statement_when_both_would_name_the_same_document(app, auth_headers, author):
    """Saying the same thing twice in two framings invites the agent to pick the weaker one."""
    await _document(app, auth_headers, author)
    context = await _render(document=PATH, task_document=PATH, task_id="task-1")

    assert context.count(PATH) >= 1
    assert "### The specification this task implements" not in context
    assert "### Open specification document" in context


@pytest.mark.asyncio
async def test_both_render_when_they_name_different_documents(app, auth_headers, author):
    """The operator reading one document while the task implements another is a real state, and
    collapsing it would hide whichever one it dropped."""
    await _document(app, auth_headers, author)
    other = "spec/changes/something-else/spec.html"
    context = await _render(document=other, task_document=PATH, task_id="task-1")

    assert "### The specification this task implements" in context
    assert PATH in context


@pytest.mark.asyncio
async def test_no_block_without_a_task_document(app, auth_headers, author):
    await _document(app, auth_headers, author)
    context = await _render()
    assert "### The specification this task implements" not in context


@pytest.mark.asyncio
async def test_a_task_derived_document_does_not_start_an_authoring_turn(app, auth_headers, author):
    """`spec_turn_notice` prepends "SPECIFICATION TURN — this overrides any other specification
    workflow you know", which is authoring instruction.

    Handing that to an implementer tells it to write a document instead of implement one. The
    notice is driven by the operator's *open* document, and the task-derived path must not reach
    it.
    """
    from hub.launchability import spec_turn_notice

    await _document(app, auth_headers, author)
    context = await _render(task_document=PATH, task_id="task-1")

    assert "SPECIFICATION TURN" not in context
    # And the notice itself is unchanged for the path that should produce it.
    assert spec_turn_notice(None) is None
