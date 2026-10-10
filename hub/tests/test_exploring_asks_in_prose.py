"""An exploring turn asks its questions in its reply (change
`an-exploring-turn-asks-its-questions-in-its-reply`, F545, decision `overhaul-exploring-interview`).

The turn notice said interview in this reply and stop; the canonical context said ending without
`ask_user` is not a way to finish and that reply text reaches nobody; every journey step asked
through `ask_user`. Prose wins while exploring, and only while exploring: proposed and approved
turns keep F38's exit condition word for word.
"""

import pytest
from sqlalchemy import update

from hub import spec_journey
from hub.api.v1.agents import SPEC_PHASE_DUTIES
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument
from hub.launchability import spec_turn_notice

from .test_spec_documents_api import (
    PATH,
    _create,
    _document,
    _submit,
    run_headers,  # noqa: F401  (fixture)
)

PREVIEW = "/api/v1/projects/proj-test/agents/agent-context"
PROSE_RULE = "ask your questions in your reply"
PRECEDENCE = "overrides any charter or tool description"
FORBIDDEN = ("reach nobody", "not a way to finish")
F38 = (
    "- **Ending this turn without either submitting the document or calling "
    "`ask_user` is not a way to finish.** Questions written as ordinary reply text "
    "reach nobody: the turn ends, nothing is recorded, and the operator is not "
    "waiting for you. If you need an answer before you can write, ask for it with "
    "the tool."
)
BUILT_IN = [
    "intake",
    "requirements",
    "acceptance",
    "requirements-and-acceptance",
    "approach",
    "tasks",
    "delivery",
]


async def _set(**values):
    async with async_session_factory() as session:
        await session.execute(
            update(SpecDocument).where(SpecDocument.path == PATH).values(**values)
        )
        await session.commit()


async def _context(app, auth_headers):
    response = await app.get(
        PREVIEW, params={"agent": "claude-1", "spec_document": PATH}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()["context"]


def _asks_in_prose(text):
    lowered = text.lower()
    assert PROSE_RULE in lowered
    assert PRECEDENCE in lowered
    for sentence in FORBIDDEN:
        assert sentence not in lowered, sentence


# context-exploring (FR-1)
@pytest.mark.asyncio
@pytest.mark.parametrize("step", BUILT_IN + ["threat-model", None])
async def test_an_exploring_context_asks_in_the_reply_at_every_step(
    app, auth_headers, tmp_path, step
):
    """Every built-in step, a step the project does not have (briefed as removed), and an
    exploring change document with no step (the phase duty)."""
    await _create(app, auth_headers)
    await _set(step=step, size="large" if step else None)

    context = await _context(app, auth_headers)

    _asks_in_prose(context)
    if step is None:
        duty = SPEC_PHASE_DUTIES["exploring"]
    else:
        duty = spec_journey.duty(step) or spec_journey.removed(step, "large")
    assert duty in context, "the duty asserted on is the one the turn was given"
    assert "ask_user" not in duty


def test_the_exploring_turn_notice_asks_in_the_reply():
    for kind in (None, "change-spec", "roadmap"):
        _asks_in_prose(spec_turn_notice("exploring", kind=kind))


# steps (FR-2)
@pytest.mark.parametrize("step", BUILT_IN)
def test_every_step_asks_its_choices_in_the_reply(step):
    text = spec_journey.duty(step)

    assert "ask_user" not in text
    if step == "delivery":
        assert "Continue here" not in text
        return
    for choice in ("Continue here", "Continue in a fresh conversation", "Stop here"):
        assert choice in text
    assert "advance_spec_step" in text
    assert "in your reply" in text


def test_intake_asks_the_size_in_the_reply_and_records_it():
    text = spec_journey.duty("intake")

    for size in ("`fix`", "`small`", "`large`"):
        assert size in text
    assert "set_spec_size" in text
    assert text.index("set_spec_size") < text.index("advance_spec_step")


def test_a_removed_step_asks_where_to_resume_in_the_reply():
    text = spec_journey.removed("threat-model", "large")

    assert "ask_user" not in text
    assert "in your reply" in text
    assert "advance_spec_step(path, to=" in text


# other-phases (FR-3)
@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["proposed", "approved"])
async def test_other_phases_keep_the_exit_condition_word_for_word(
    app, auth_headers, run_headers, tmp_path, phase  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await _set(phase=phase, step=None)

    context = await _context(app, auth_headers)

    assert F38 in context
    assert PRECEDENCE not in context.lower()
