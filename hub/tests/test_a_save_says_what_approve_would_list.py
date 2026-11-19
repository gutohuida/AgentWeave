"""F1124: a save's warnings carry the gaps Approve lists, and `ready_to_approve` follows them."""

import pytest

from ._spec_confirmations import submit_confirmed
from .test_spec_documents_api import PATH, _create, _document
from .test_spec_documents_api import _submit as _submit_once
from .test_spec_documents_api import run_headers as run_headers  # noqa: F401  (the fixture)


async def _submit(app, run_headers, document):  # noqa: F811
    """Saved with its criteria confirmed, so the save lists only what this file is about."""
    return await submit_confirmed(_submit_once, app, run_headers, document, PATH)


@pytest.mark.asyncio
async def test_a_criterion_with_no_check_is_a_warning_and_not_ready(app, auth_headers, run_headers):
    await _create(app, auth_headers)

    response = await _submit(app, run_headers, _document())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["blocking"] == []
    assert "criterion_without_check" in {w["code"] for w in body["warnings"]}
    assert body["ready_to_approve"] is False


@pytest.mark.asyncio
async def test_a_criterion_with_its_check_is_ready(app, auth_headers, run_headers):
    await _create(app, auth_headers)
    await _place_at_the_end()
    criteria = [
        {
            "key": "c1",
            "requirement": "alpha",
            "given": "g",
            "when": "w",
            "then": "t",
            "how_to_check": "a test",
            "checked_by": "agent",
        }
    ]

    response = await _submit(app, run_headers, _document(acceptance_criteria=criteria))

    body = response.json()
    assert "criterion_without_check" not in {w["code"] for w in body["warnings"]}
    assert body["ready_to_approve"] is True


def _ready_criteria():
    return [
        {
            "key": "c1",
            "requirement": "alpha",
            "given": "g",
            "when": "w",
            "then": "t",
            "how_to_check": "a test",
            "checked_by": "agent",
        }
    ]


@pytest.mark.asyncio
async def test_an_unresolved_question_is_not_ready_until_it_is_resolved(
    app, auth_headers, run_headers
):
    """AW-125: the warning said `unresolved_question` while `ready_to_approve` said true."""
    await _create(app, auth_headers)
    await _place_at_the_end()

    open_q = await _submit(
        app,
        run_headers,
        _document(
            acceptance_criteria=_ready_criteria(),
            open_questions=[{"question": "which one?", "resolved": False}],
        ),
    )
    body = open_q.json()
    assert body["blocking"] == []
    assert "unresolved_question" in {w["code"] for w in body["warnings"]}
    assert body["ready_to_approve"] is False

    answered = await _submit(
        app,
        run_headers,
        _document(
            acceptance_criteria=_ready_criteria(),
            open_questions=[{"question": "which one?", "resolved": True}],
        ),
    )
    assert answered.json()["ready_to_approve"] is True


async def _place_at_the_end():
    """The document's step is the journey's last, so `steps_skipped` does not colour what this
    test asks (a save moving the step by content is the steps slice)."""
    from .test_spec_journey_briefing import _place

    await _place(step="build", size="large")
