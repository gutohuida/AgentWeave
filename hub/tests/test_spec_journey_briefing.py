"""A spec is written one step at a time (step-journey, slice 1): the briefing half.

A turn on an exploring change document is told only its current step's duty, and one line naming
the journey; it records the size and moves the step through two agent tools that never refuse a
move for a missing output; `GET /agents/agent-context?spec_document=` shows that briefing.
"""

import pytest
from sqlalchemy import select, update

from hub import spec_journey
from hub.api.v1.agents import _render_hub_agent_context
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent

from .test_spec_documents_api import (
    PATH,
    _create,
    _document,
    _submit,
    run_headers,  # noqa: F401  (fixture)
)

PREVIEW = "/api/v1/projects/proj-test/agents/agent-context"
ACTIONS = "/api/v1/agent-actions/spec/documents"
ALL_STEPS = [
    "intake",
    "requirements",
    "acceptance",
    "requirements-and-acceptance",
    "approach",
    "tasks",
    "delivery",
]


async def _place(step=None, size=None):
    async with async_session_factory() as session:
        await session.execute(
            update(SpecDocument).where(SpecDocument.path == PATH).values(step=step, size=size)
        )
        await session.commit()


async def _row():
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()


async def _briefing(app, auth_headers, agent="claude-1"):
    response = await app.get(
        PREVIEW, params={"agent": agent, "spec_document": PATH}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()["context"]


def _markers(text):
    return [step for step in ALL_STEPS if spec_journey.marker(step) in text]


def _open_document_block(text):
    start = text.index("### Open specification document")
    end = text.find("\n### ", start + 1)
    return text[start : end if end != -1 else None]


# only-current (FR-3)
@pytest.mark.asyncio
@pytest.mark.parametrize("step", ALL_STEPS)
async def test_a_briefing_holds_its_own_step_and_no_other(app, auth_headers, tmp_path, step):
    await _create(app, auth_headers)
    await _place(step=step, size="small")

    text = await _briefing(app, auth_headers)

    assert _markers(text) == [step]
    (line,) = [ln for ln in text.splitlines() if ln.startswith("- Journey")]
    assert "intake → requirements-and-acceptance → tasks → delivery" in line.replace("**", "")


@pytest.mark.asyncio
async def test_an_unsized_document_is_briefed_with_the_large_journey(app, auth_headers, tmp_path):
    await _create(app, auth_headers)

    text = await _briefing(app, auth_headers)

    assert _markers(text) == ["intake"]
    (line,) = [ln for ln in text.splitlines() if ln.startswith("- Journey")]
    assert "approach" in line


@pytest.mark.asyncio
async def test_a_proposed_document_is_briefed_by_its_phase_not_its_step(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await app.post(
        "/api/v1/projects/proj-test/project/documents/propose",
        params={"path": PATH},
        headers=auth_headers,
    )

    text = await _briefing(app, auth_headers)

    assert _markers(text) == []
    assert "proposed and awaiting the operator" in text


# asks / size-told / acceptance-duty (FR-4, FR-7, FR-8)
@pytest.mark.parametrize("step", [s for s in ALL_STEPS if s != "delivery"])
def test_every_step_says_what_it_writes_and_asks_to_advance(step):
    text = spec_journey.duty(step)

    assert "`ask_user`" in text
    for choice in ("Continue here", "Continue in a fresh conversation", "Stop here"):
        assert choice in text
    assert "advance_spec_step" in text
    assert "submit_spec_document" in text or "`design`" in text


def test_intake_asks_one_question_at_a_time_and_records_the_size_before_advancing():
    text = spec_journey.duty("intake")

    assert "one question per `ask_user` call" in text
    assert text.index("set_spec_size") < text.index("advance_spec_step")
    assert "confirm the size with `ask_user`" in text


def test_acceptance_asks_how_and_who_per_must_and_tasks_starts_with_the_failing_drive():
    for step in ("acceptance", "requirements-and-acceptance"):
        text = spec_journey.duty(step)
        assert "every MUST requirement" in text
        assert "how_to_check" in text and "checked_by" in text
        assert "acceptance drive" in text
    assert "Task 1 writes the acceptance drive and records it failing" in spec_journey.duty("tasks")


# move-recorded (FR-5)
@pytest.mark.asyncio
async def test_advancing_never_refuses_and_names_what_the_step_left_empty(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _place(step="requirements", size="large")

    response = await app.post(f"{ACTIONS}/advance", json={"path": PATH}, headers=run_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["step"], body["previous_step"]) == ("acceptance", "requirements")
    assert "requirements" in body["missing"]
    assert spec_journey.marker("acceptance") in body["instructions"]
    assert (await _row()).step == "acceptance"
    async with async_session_factory() as session:
        event = (
            await session.execute(
                select(SpecDocumentEvent).where(SpecDocumentEvent.kind == "journey")
            )
        ).scalar_one()
    assert (event.run_id, event.actor) == ("run-spec-doc", "claude-1")


@pytest.mark.asyncio
async def test_advancing_to_a_named_step_and_past_the_end(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)

    named = await app.post(
        f"{ACTIONS}/advance", json={"path": PATH, "to": "tasks"}, headers=run_headers
    )
    assert named.status_code == 200, named.text
    assert named.json()["step"] == "tasks"

    await _place(step="delivery", size="fix")
    end = await app.post(f"{ACTIONS}/advance", json={"path": PATH}, headers=run_headers)
    assert end.status_code == 200, end.text
    assert end.json()["step"] == "delivery"
    assert "last step" in end.json()["message"]


@pytest.mark.asyncio
async def test_the_agent_records_the_size_with_its_reason(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)

    response = await app.post(
        f"{ACTIONS}/size",
        json={"path": PATH, "size": "small", "reason": "one route"},
        headers=run_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["journey"] == [
        "intake",
        "requirements-and-acceptance",
        "tasks",
        "delivery",
    ]
    assert (await _row()).size == "small"
    refused = await app.post(
        f"{ACTIONS}/size", json={"path": PATH, "size": "medium", "reason": ""}, headers=run_headers
    )
    assert refused.status_code == 422
    assert "small" in refused.text


# fresh (FR-6)
@pytest.mark.asyncio
async def test_any_conversation_with_any_agent_is_briefed_from_the_recorded_step(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await app.post(f"{ACTIONS}/advance", json={"path": PATH, "to": "tasks"}, headers=run_headers)

    assert _markers(await _briefing(app, auth_headers, agent="someone-else")) == ["tasks"]


# preview (FR-13)
@pytest.mark.asyncio
async def test_the_preview_is_the_block_a_turn_on_that_document_receives(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers)
    await _place(step="acceptance", size="large")

    preview = await _briefing(app, auth_headers)
    async with async_session_factory() as session:
        turn = await _render_hub_agent_context(
            agent="claude-1",
            project_id="proj-test",
            db=session,
            session_data=None,
            agent_row=None,
            spec_document=PATH,
            work_dir=str(tmp_path),
            isolated=True,
        )

    assert _open_document_block(preview) == _open_document_block(turn["context"])
    assert spec_journey.marker("acceptance") in _open_document_block(preview)


@pytest.mark.asyncio
async def test_a_roadmap_keeps_todays_exploring_duty(app, auth_headers, tmp_path):
    response = await app.post(
        "/api/v1/projects/proj-test/project/documents",
        json={"path": PATH, "title": "Plan", "kind": "roadmap"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text

    text = await _briefing(app, auth_headers)

    assert _markers(text) == []
    assert "Size it as a slice" in text
