"""The turn context says which specification procedure governs the open document.

Change `2026-08-13-the-hubs-procedure-outranks-an-installed-one`. Observed on a live run: the
document was attached to the first message, the phase block was in the delivered context file, and
the agent had demonstrably read it — and it still opened with *"I'm going to use the OpenSpec
proposal workflow"*. `~/.codex/skills/` held `openspec-propose`, whose description ("Use when the
user wants to quickly describe what they want to build") matched the operator's opening sentence.

The block said how to author a document. It never said which authority governed it.

**What these tests can show is delivery.** That the sentences are present, reach either runner, and
survive a project with no charter. Whether a model *obeys* them against a matching skill trigger is
not decidable here — it needs the skills restored and a live run, which is task 5.1.
"""

import pytest
from sqlalchemy import select

from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import Agent

BASE = "/api/v1/projects/proj-test/project"
PATH = "spec/changes/precedence/spec.html"


async def _register(app, auth_headers, name):
    response = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": name, "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


async def _create_document(app, auth_headers, path=PATH):
    response = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers
    )
    assert response.status_code == 201, response.text


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
async def test_the_context_says_which_procedure_governs(app, auth_headers, tmp_path):
    await _register(app, auth_headers, "speccer")
    await _create_document(app, auth_headers)

    context = await _render("speccer", PATH)

    assert "governs this document" in context
    assert "No other specification workflow" in context
    # The two cases that actually happened: a skill installed on the machine, and a workflow the
    # model has used before and reaches for from habit.
    assert "installed on this machine" in context
    assert "used before" in context


@pytest.mark.asyncio
async def test_it_tells_the_agent_to_raise_a_competing_workflow_rather_than_only_banning_it(
    app, auth_headers, tmp_path
):
    """An agent told only "do not" is holding a fact with nowhere to put it — and the tool it found
    belongs to the operator, who is the one who should decide about it."""
    await _register(app, auth_headers, "speccer")
    await _create_document(app, auth_headers)

    context = await _render("speccer", PATH)

    assert "say so to the operator" in context
    assert "Do not follow it" in context


@pytest.mark.asyncio
async def test_reading_a_competing_workflows_files_is_still_allowed(app, auth_headers, tmp_path):
    """A project may legitimately contain an `openspec/` directory that is real context about the
    project. The rule is about which authority governs the document, not which files may be read —
    an agent that refuses to look is worse than one that looked and stayed."""
    await _register(app, auth_headers, "speccer")
    await _create_document(app, auth_headers)

    context = await _render("speccer", PATH)

    assert "as context about the project is fine" in context


@pytest.mark.asyncio
async def test_it_names_no_product(app, auth_headers, tmp_path):
    """A blocklist dates the moment a different tool is installed, and implies the unnamed ones are
    acceptable. Asserted as an absence so a later edit cannot quietly turn this into one."""
    await _register(app, auth_headers, "speccer")
    await _create_document(app, auth_headers)

    context = await _render("speccer", PATH)

    lowered = context.lower()
    for product in ("openspec", "opsx", "aw-spec", "spec-kit"):
        assert product not in lowered, f"the floor should not name {product}"


@pytest.mark.asyncio
async def test_precedence_does_not_depend_on_a_charter(app, auth_headers, tmp_path):
    """The floor is code-owned. A project with no charter bound is the case most exposed — mechanism
    without judgement — so precedence carried by a charter would be missing exactly where it is
    needed most."""
    await _register(app, auth_headers, "uncharted")
    await _create_document(app, auth_headers)

    context = await _render("uncharted", PATH)

    # The section is always rendered; with nothing bound it says so. Asserting the absence of the
    # heading would have passed for the wrong reason the day the heading changed.
    assert "No charter is assigned to this agent." in context
    assert "No other specification workflow" in context


@pytest.mark.asyncio
async def test_a_turn_with_no_document_says_nothing_about_procedure(app, auth_headers, tmp_path):
    """The claim is about *this document*. Asserting procedural precedence on a turn that has
    nothing to do with specifications would be untrue and noise on every unrelated turn."""
    await _register(app, auth_headers, "speccer")
    await _create_document(app, auth_headers)

    context = await _render("speccer", None)

    assert "No other specification workflow" not in context
    assert "governs this document" not in context


@pytest.mark.asyncio
async def test_the_instruction_and_the_tool_list_agree_in_one_rendered_context(
    app, auth_headers, tmp_path
):
    """The failure was a contradiction inside a single context file.

    The phase block said *"Write the document with `submit_spec_document`"*; `## Your tools`
    enumerated a surface without it. The agent resolved it against the enumeration — the more
    specific claim, and the one that reads as an inventory — reported the capability as unavailable,
    and stopped after a complete interview.

    `test_tool_surface_matches_server.py` checks the surface against the server. This checks the two
    halves of what one agent actually reads, which is where they disagreed.
    """
    await _register(app, auth_headers, "speccer")
    await _create_document(app, auth_headers)

    context = await _render("speccer", PATH)

    assert "Write the document with `submit_spec_document`" in context
    tools = context.split("## Your tools", 1)[1].split("\n## ", 1)[0]
    assert "`submit_spec_document(" in tools, (
        "the phase block instructs a tool the tool list omits; "
        "an agent reading both concludes it does not have it"
    )


@pytest.mark.asyncio
async def test_both_runners_are_told_the_same_thing(app, auth_headers, bind_runner, tmp_path):
    """Runner-agnostic delivery is the premise the skills' deletion rested on, and the live failure
    was on Codex. The context file is what both runners consume, so this asserts rather than assumes
    that neither is left out."""
    await _register(app, auth_headers, "claude-side")
    await _register(app, auth_headers, "codex-side")
    await bind_runner("claude-side", cli="claude")
    await bind_runner("codex-side", cli="codex")
    await _create_document(app, auth_headers)

    for agent in ("claude-side", "codex-side"):
        context = await _render(agent, PATH)
        assert "No other specification workflow" in context, agent
