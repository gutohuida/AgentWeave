"""The exploring floor asks for a conversation, not a form.

Change `2026-08-13-the-interview-is-a-conversation`. The charter has always said *"Never run this as
a questionnaire"*, and the agent ran one anyway: nine questions across three `ask_user` calls, every
one multiple-choice, no open question and no sketch. The charter is optional and the floor is not,
and the floor said *"use `ask_user` for anything that changes scope"* — which during an exploration
is everything. A tool that requires two to eight options per question cannot produce a conversation,
so the binding guidance and the available mechanism agreed with each other and outvoted the craft.

These tests cover the wording being delivered and no longer self-contradictory. Whether an agent
interviews conversationally *because* of it is human-only verification.
"""

import pytest
from sqlalchemy import select, update

from hub.api.v1.agents import SPEC_PHASE_DUTIES, _render_hub_agent_context, _tool_surface_lines
from hub.db.engine import async_session_factory
from hub.db.models import Agent, SpecDocument

BASE = "/api/v1/projects/proj-test/project"
PATH = "spec/changes/interview/spec.json"


async def _create_document(app, auth_headers):
    response = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Demo"}, headers=auth_headers
    )
    assert response.status_code == 201, response.text


async def _render(agent_name):
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
            spec_document=PATH,
        )
    return rendered["context"]


def test_the_floor_no_longer_routes_every_scope_question_through_the_tool():
    """The sentence that produced the questionnaire, asserted gone.

    Pinned as an absence because the failure was not a missing instruction — the charter had the
    right instruction — but a binding one pointing the other way.
    """
    exploring = SPEC_PHASE_DUTIES["exploring"]
    assert "anything that changes scope" not in exploring


def test_the_floor_asks_for_the_interview_in_the_reply():
    exploring = SPEC_PHASE_DUTIES["exploring"]
    assert "Interview in your reply" in exploring
    assert "composer" in exploring


def test_the_floor_names_no_blocking_tool():
    """The genuine-fork allowance went with F545 (`night-1010-5`): an exploring turn asks in its
    reply and nothing tells it to use `ask_user` (`test_exploring_asks_in_prose.py`)."""
    exploring = SPEC_PHASE_DUTIES["exploring"]
    assert "ask_user" not in exploring


def test_the_floor_invites_a_sketch():
    """In the floor rather than the charter: a charter is optional by decision, so a project with
    none bound would otherwise get a wall of prose."""
    assert "Sketch when it makes something easier to see" in SPEC_PHASE_DUTIES["exploring"]


def test_the_obligation_to_interview_is_unchanged():
    """This change would be a regression if it read as permission to ask less. Only the medium
    changes."""
    exploring = SPEC_PHASE_DUTIES["exploring"]
    assert "Interview before writing" in exploring
    assert "Ground what you claim in the codebase" in exploring
    assert "Do not implement anything" in exploring


def test_ask_user_is_described_as_a_decision_tool():
    """Left alone, "there is no way to ask without options" reads as a fact about asking rather
    than about this tool — which is exactly how it was read."""
    text = "\n".join(_tool_surface_lines())
    entry = text.split("`ask_user(questions, blocking=True)`", 1)[1].split("\n- `", 1)[0]
    assert "decision" in entry.lower()
    assert "blocks your turn" in entry
    assert "belongs in your reply" in entry


@pytest.mark.asyncio
async def test_a_charterless_exploring_turn_gets_all_of_it(app, auth_headers, tmp_path, add_agent):
    """The floor is what always ships. Everything load-bearing has to survive here or it is
    load-bearing only when someone remembers to bind a charter.

    A roadmap: since step-journey a change document is briefed one step at a time instead
    (`test_spec_journey_briefing.py`), and the roadmap keeps this floor."""
    await add_agent("uncharted")
    await _create_roadmap_document(app, auth_headers, PATH)

    context = await _render("uncharted")

    assert "No charter is assigned to this agent." in context
    assert "Interview in your reply" in context
    assert "Sketch when it makes something easier to see" in context
    assert "ask your questions in your reply" in context.lower()


# ---------------------------------------------------------------------------
# D2: the delivery question and the open-agents roster, change-spec only
# (change `a-document-says-how-it-will-be-built-and-approval-starts-it`)
# ---------------------------------------------------------------------------

ROADMAP_PATH = "spec/changes/interview-roadmap/spec.json"


async def _create_roadmap_document(app, auth_headers, path):
    response = await app.post(
        f"{BASE}/documents",
        json={"path": path, "title": "Demo roadmap", "kind": "roadmap"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text


async def _render_at(agent_name, path):
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
            spec_document=path,
        )
    return rendered["context"]


@pytest.mark.asyncio
async def test_change_spec_exploring_is_asked_how_it_will_be_built(app, auth_headers, add_agent):
    """D2, Opus notes 5 and 7: the interview line, and the two phrases the review added.

    Since step-journey the question is the delivery step's, so the document is placed there."""
    await add_agent("solo")
    await _create_document(app, auth_headers)
    async with async_session_factory() as db:
        await db.execute(
            update(SpecDocument).where(SpecDocument.path == PATH).values(step="delivery")
        )
        await db.commit()

    context = await _render("solo")
    block = context.split("### Open specification document", 1)[1]

    assert "[step: delivery]" in block
    assert "say how it will be built" in block
    assert "when there is another agent" in block
    assert "every later submission" in block
    assert "'No flow' is a valid answer" in block


@pytest.mark.asyncio
async def test_roadmap_exploring_is_not_asked_about_delivery(app, auth_headers, add_agent):
    """D4 requires `delivery` of change-spec documents only, so no other kind is asked."""
    await add_agent("roadmapper")
    await _create_roadmap_document(app, auth_headers, ROADMAP_PATH)

    context = await _render_at("roadmapper", ROADMAP_PATH)

    assert "ask how it will be built" not in context
    assert "Open agents on this project" not in context


@pytest.mark.asyncio
async def test_single_agent_project_lists_open_agents_with_no_team_heading(
    app, auth_headers, add_agent
):
    """The roster line is built from `roster` regardless of team size, but `### Team` still
    prints only when there are peers
    (`test_agents.py::test_single_agent_project_gets_no_team_section`)."""
    await add_agent("solo")
    await _create_document(app, auth_headers)

    context = await _render("solo")

    assert "Open agents on this project: solo." in context
    assert "### Team" not in context
