"""F1124: a save's warnings carry the gaps Approve lists, and `ready_to_approve` follows them."""

import pytest

from .test_spec_documents_api import _create, _document, _submit
from .test_spec_documents_api import run_headers as run_headers  # noqa: F401  (the fixture)


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
