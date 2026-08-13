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
from sqlalchemy import select

from hub.api.v1.agents import SPEC_PHASE_DUTIES, _render_hub_agent_context, _tool_surface_lines
from hub.db.engine import async_session_factory
from hub.db.models import Agent

BASE = "/api/v1/projects/proj-test/project"
PATH = "spec/changes/interview/spec.html"


async def _register(app, auth_headers, name):
    response = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": name, "contact_mode": "poll"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text


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


def test_the_floor_reserves_the_blocking_tool_for_a_fork():
    exploring = SPEC_PHASE_DUTIES["exploring"]
    assert "only for a genuine fork" in exploring
    # The cost is stated where the choice is made, not only in the tool's own description.
    assert "blocks your turn" in exploring


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
    entry = text.split("`ask_user(questions)`", 1)[1].split("\n- `", 1)[0]
    assert "decision" in entry.lower()
    assert "blocks your turn" in entry
    assert "belongs in your reply" in entry


@pytest.mark.asyncio
async def test_a_charterless_exploring_turn_gets_all_of_it(app, auth_headers, tmp_path):
    """The floor is what always ships. Everything load-bearing has to survive here or it is
    load-bearing only when someone remembers to bind a charter."""
    await _register(app, auth_headers, "uncharted")
    await _create_document(app, auth_headers)

    context = await _render("uncharted")

    assert "No charter is assigned to this agent." in context
    assert "Interview in your reply" in context
    assert "Sketch when it makes something easier to see" in context
    assert "only for a genuine fork" in context
