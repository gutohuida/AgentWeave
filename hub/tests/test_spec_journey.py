"""A spec is written one step at a time (step-journey, slice 1): the model half.

A change document records its journey step and size; the journey follows the size; proposing no
longer waits for the operator to mark exploration complete; a criterion may say how it is checked
and by whom. The acceptance drive is `scripts/drive/d1009_step_journey.py`.
"""

import pytest
from sqlalchemy import select

from hub import spec_journey, spec_lifecycle
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent
from hub.spec_payload import (
    PayloadError,
    embed_payload,
    extract_payload,
    payload_to_dict,
    validate_payload,
)

from .test_spec_documents_api import (
    BASE,
    PATH,
    _create,
    _document,
    _submit,
    run_headers,  # noqa: F401  (fixture)
)

OPERATOR = spec_lifecycle.Actor(kind="operator", name="operator")


async def _row(path=PATH):
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()


# new-doc-intake (FR-1)
@pytest.mark.asyncio
async def test_a_new_change_document_starts_at_intake_with_no_size(app, auth_headers, tmp_path):
    created = await _create(app, auth_headers)

    assert created["step"] == "intake"
    assert created["size"] is None
    listed = await app.get(f"{BASE}/documents", headers=auth_headers)
    (view,) = [d for d in listed.json()["documents"] if d["path"] == PATH]
    assert (view["step"], view["size"]) == ("intake", None)


@pytest.mark.asyncio
async def test_a_roadmap_has_no_step(app, auth_headers, tmp_path):
    path = "spec/changes/plan/spec.html"
    response = await app.post(
        f"{BASE}/documents",
        json={"path": path, "title": "Plan", "kind": "roadmap"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["step"] is None


# journeys (FR-2)
@pytest.mark.parametrize(
    ("size", "steps"),
    [
        (None, ["intake", "requirements", "acceptance", "approach", "tasks", "delivery"]),
        ("large", ["intake", "requirements", "acceptance", "approach", "tasks", "delivery"]),
        ("small", ["intake", "requirements-and-acceptance", "tasks", "delivery"]),
        ("fix", ["intake", "tasks", "delivery"]),
    ],
)
def test_the_journey_follows_the_size(size, steps):
    assert spec_journey.journey(size) == steps


def test_next_step_walks_the_journey_and_stops_at_its_end():
    assert spec_journey.next_step("small", "intake") == "requirements-and-acceptance"
    assert spec_journey.next_step("fix", "intake") == "tasks"
    assert spec_journey.next_step("large", "delivery") is None
    # A step the size's journey does not hold (the size changed under it) moves to the journey's
    # first step after the step's place in the full order, never backwards.
    assert spec_journey.next_step("fix", "requirements") == "tasks"
    assert spec_journey.next_step("small", "acceptance") == "tasks"


@pytest.mark.asyncio
async def test_moving_and_sizing_are_recorded_with_the_run(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    agent = spec_lifecycle.Actor(kind="agent", name="claude-1", run_id="run-spec-doc")
    async with async_session_factory() as session:
        document = await spec_lifecycle.get_document(session, "proj-test", PATH)
        await spec_journey.set_size(session, document, "small", actor=agent, reason="one route")
        await spec_journey.set_step(session, document, "requirements-and-acceptance", actor=agent)
        await session.commit()

    row = await _row()
    assert (row.size, row.step) == ("small", "requirements-and-acceptance")
    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(SpecDocumentEvent)
                    .where(
                        SpecDocumentEvent.document_id == row.id, SpecDocumentEvent.kind == "journey"
                    )
                    .order_by(SpecDocumentEvent.created_at)
                )
            )
            .scalars()
            .all()
        )
    assert [e.detail for e in events] == [
        {"size": {"from": None, "to": "small"}, "reason": "one route"},
        {"step": {"from": "intake", "to": "requirements-and-acceptance"}},
    ]
    assert {e.run_id for e in events} == {"run-spec-doc"}


@pytest.mark.asyncio
async def test_an_unknown_step_or_size_is_refused_naming_the_choices(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    async with async_session_factory() as session:
        document = await spec_lifecycle.get_document(session, "proj-test", PATH)
        with pytest.raises(spec_journey.JourneyError, match="intake"):
            await spec_journey.set_step(session, document, "design", actor=OPERATOR)
        with pytest.raises(spec_journey.JourneyError, match="small"):
            await spec_journey.set_size(session, document, "medium", actor=OPERATOR)


# no-close (FR-11)
@pytest.mark.asyncio
async def test_a_complete_document_proposes_without_exploration_being_closed(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    submitted = await _submit(app, run_headers, _document())
    assert submitted.status_code == 200, submitted.text

    proposed = await app.post(
        f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers
    )

    assert proposed.status_code == 200, proposed.text
    assert (await _row()).phase == "proposed"


# fields-optional (FR-9)
def _with_criterion(**extra):
    payload = _document()
    payload["acceptance_criteria"][0].update(extra)
    return payload


def test_a_criterion_may_say_how_it_is_checked_and_by_whom_and_it_round_trips():
    raw = _with_criterion(how_to_check="curl /ping and read the body", checked_by="agent")

    stored = payload_to_dict(validate_payload(raw))
    back = extract_payload(embed_payload(stored))

    (criterion,) = back["acceptance_criteria"]
    assert criterion["how_to_check"] == "curl /ping and read the body"
    assert criterion["checked_by"] == "agent"


def test_a_criterion_without_them_stores_exactly_as_before():
    stored = payload_to_dict(validate_payload(_document()))

    assert set(stored["acceptance_criteria"][0]) == {"key", "requirement", "given", "when", "then"}


def test_checked_by_other_than_agent_or_operator_is_refused_naming_the_field():
    with pytest.raises(PayloadError) as refused:
        validate_payload(_with_criterion(checked_by="robot"))

    assert "checked_by" in refused.value.field
