"""F612: adopting a hand-placed document indexes the requirements it declares.

A file the Hub never wrote has no `aw_identity`, and the index skips a requirement with no minted
identifier, so adoption answered 201 with `created: []` and the document read as asserting
nothing on every operator surface. Adoption now mints identifiers for exactly the requirements
that have none, through the Hub's own write, and says so (`minted`). A file whose requirements
all carry identity, like any corpus the Hub wrote, is still adopted without a byte changing.
"""

from __future__ import annotations

import json

import pytest

from ._spec_files import stored_text
from .test_spec_adoption_api import BASE, _adopt, _bytes, _document, _requirement, _write


def _hand_placed(requirements: list) -> str:
    payload = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": "Rounding rules",
        "requirements": requirements,
    }
    return stored_text(payload, phase="exploring")


@pytest.mark.asyncio
async def test_a_hand_placed_documents_requirements_are_minted_and_indexed(
    app, tmp_path, auth_headers
):
    path = "spec/changes/rounding-rules/spec.json"
    _write(tmp_path, path, _hand_placed([_requirement("one-decimal", "Totals SHALL round.")]))

    response = await _adopt(app, path, auth_headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["minted"] == ["FR-1"]

    listed = await app.get(f"{BASE}/spec/requirements", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    rows = [r for r in listed.json()["requirements"] if r["document_id"] == body["id"]]
    assert [r["identifier"] for r in rows] == ["FR-1"]

    stored = json.loads((tmp_path / path).read_text(encoding="utf-8"))
    assert stored["aw_identity"]["requirements"] == {"one-decimal": "FR-1"}


@pytest.mark.asyncio
async def test_a_document_that_carries_identity_is_adopted_unchanged(app, tmp_path, auth_headers):
    path = "spec/changes/kept/spec.json"
    before = _write(
        tmp_path,
        path,
        _document(
            title="Kept", kind="change-spec", status="exploring", requirements=[_requirement()]
        ),
    )

    response = await _adopt(app, path, auth_headers)
    assert response.status_code == 201, response.text
    assert response.json()["minted"] == []
    assert _bytes(tmp_path, path) == before
