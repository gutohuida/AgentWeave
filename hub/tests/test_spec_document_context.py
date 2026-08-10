"""The specification document the operator has open reaches the agent's turn context.

Change `2026-08-10-one-chat-surface`, tasks 2.1-2.3. The requirement being covered is
"The agent is told which document the operator is viewing": when a document is open the
canonical context names it, when none is open the context names none, and the operator's
message is never rewritten to carry it.
"""

import pytest
from sqlalchemy import select

from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import Agent, InboundQueueEntry

SPEC_PATH = "spec/a1-probe.html"
SPEC_HTML = "<html><body><h1>A1 probe</h1></body></html>"


async def _register(app, auth_headers, name):
    response = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": name, "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _sync_spec(app, auth_headers, path=SPEC_PATH, content=SPEC_HTML):
    response = await app.post(
        "/api/v1/projects/proj-test/project/specs/sync",
        json={"path": path, "content": content},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _render(agent_name, spec_document):
    async with async_session_factory() as db:
        agent_row = (
            (
                await db.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == agent_name)
                )
            )
            .scalars()
            .first()
        )
        rendered = await _render_hub_agent_context(
            agent=agent_name,
            project_id="proj-test",
            db=db,
            session_data=None,
            agent_row=agent_row,
            work_dir="/tmp/project",
            spec_document=spec_document,
        )
    return rendered["context"]


@pytest.mark.asyncio
async def test_context_names_the_open_document(app, auth_headers):
    await _register(app, auth_headers, "speccer")
    await _sync_spec(app, auth_headers)

    context = await _render("speccer", SPEC_PATH)

    assert "### Open specification document" in context
    assert f"`{SPEC_PATH}`" in context
    # Stated as context, not as a task. An agent that reads this must not go and start
    # editing the document because the operator happened to be looking at it.
    assert "not as an instruction" in context


@pytest.mark.asyncio
async def test_context_names_no_document_when_none_is_open(app, auth_headers):
    await _register(app, auth_headers, "speccer")
    await _sync_spec(app, auth_headers)

    context = await _render("speccer", None)

    assert "### Open specification document" not in context
    assert SPEC_PATH not in context


@pytest.mark.asyncio
async def test_context_omits_a_document_this_project_does_not_have(app, auth_headers):
    """A stale client path is not a document the operator can be looking at."""
    await _register(app, auth_headers, "speccer")
    await _sync_spec(app, auth_headers)

    context = await _render("speccer", "spec/deleted-yesterday.html")

    assert "### Open specification document" not in context
    assert "deleted-yesterday" not in context


@pytest.mark.asyncio
async def test_both_runners_are_told_the_same_thing(app, auth_headers, bind_runner):
    """The document reaches the agent through the canonical context file, which both
    runners consume — so there is nothing runner-specific to get right, and this asserts
    that rather than assuming it."""
    await _register(app, auth_headers, "claude-side")
    await _register(app, auth_headers, "codex-side")
    await bind_runner("claude-side", cli="claude")
    await bind_runner("codex-side", cli="codex")
    await _sync_spec(app, auth_headers)

    claude_context = await _render("claude-side", SPEC_PATH)
    codex_context = await _render("codex-side", SPEC_PATH)

    def document_block(context):
        lines = context.splitlines()
        start = lines.index("### Open specification document")
        end = lines.index("### Team")
        return lines[start:end]

    assert document_block(claude_context) == document_block(codex_context)
    assert f"`{SPEC_PATH}`" in "\n".join(document_block(claude_context))


@pytest.mark.asyncio
async def test_trigger_stores_the_document_on_the_queued_entry_not_in_the_message(
    app, auth_headers, bind_runner
):
    """The message is the durable record of what the operator said. Re-reading the
    conversation must not show them saying something they did not."""
    await _register(app, auth_headers, "speccer")
    await bind_runner("speccer", cli="claude")
    await _sync_spec(app, auth_headers)

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={
            "agent": "speccer",
            "message": "why does this say that?",
            "spec_document": SPEC_PATH,
        },
        headers=auth_headers,
    )
    assert response.status_code in (200, 409), response.text

    async with async_session_factory() as db:
        entry = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.project_id == "proj-test",
                        InboundQueueEntry.agent == "speccer",
                    )
                )
            )
            .scalars()
            .first()
        )
        assert entry is not None
        assert entry.spec_document == SPEC_PATH
        assert entry.content == "why does this say that?"
        assert SPEC_PATH not in entry.content


@pytest.mark.asyncio
async def test_trigger_refuses_an_unsafe_document_path(app, auth_headers, bind_runner):
    await _register(app, auth_headers, "speccer")
    await bind_runner("speccer", cli="claude")

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={
            "agent": "speccer",
            "message": "hello",
            "spec_document": "../../etc/passwd",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_trigger_without_a_document_leaves_the_entry_blank(app, auth_headers, bind_runner):
    await _register(app, auth_headers, "speccer")
    await bind_runner("speccer", cli="claude")

    response = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "speccer", "message": "hello"},
        headers=auth_headers,
    )
    assert response.status_code in (200, 409), response.text

    async with async_session_factory() as db:
        entry = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.project_id == "proj-test",
                        InboundQueueEntry.agent == "speccer",
                    )
                )
            )
            .scalars()
            .first()
        )
        assert entry is not None
        assert entry.spec_document is None
