"""A fold can retire what the change supersedes in the capability (F533).

`spec/changes/a-fold-can-retire-what-the-change-supersedes`: the fold request names capability
requirements to retire (their criteria go with them) and individual criteria to retire, applied in
the same merge as the folded requirements; the draft lists what the capability holds.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentMerge
from hub.spec_documents import parse_stored
from tests.test_a_finished_change_is_folded_into_its_capability import (
    BASE,
    CAP,
    CHANGE,
    _approved_change,
    _capability,
    _create_capability,
    _digest,
    _finish_tasks,
)

CAPABILITY = _capability(
    requirements=[
        {"key": "widgets-exist", "statement": "A widget MUST exist.", "modal": "MUST"},
        {"key": "old-rule", "statement": "A widget MUST never glow.", "modal": "MUST"},
    ]
)
CAPABILITY["acceptance_criteria"] = [
    {"key": "exist-c", "requirement": "widgets-exist", "given": "g", "when": "w", "then": "dark"},
    {"key": "exist-d", "requirement": "widgets-exist", "given": "g", "when": "w", "then": "t"},
    {"key": "old-c", "requirement": "old-rule", "given": "g", "when": "w", "then": "never"},
]


async def _ready(app, auth_headers):
    await _create_capability(app, auth_headers, payload=CAPABILITY)
    await _approved_change(app, auth_headers)
    await _finish_tasks()


async def _capability_on_disk(tmp_path):
    return parse_stored((tmp_path / CAP).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_a_fold_retires_a_requirement_with_its_criteria_and_one_criterion(
    app, auth_headers, tmp_path
):
    await _ready(app, auth_headers)

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold",
        json={"into": CAP, "retire": ["old-rule"], "retire_criteria": ["exist-c"]},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    capability = await _capability_on_disk(tmp_path)
    keys = [r["key"] for r in capability["requirements"]]
    assert "old-rule" not in keys and "widgets-exist" in keys and "widgets-glow-glow" in keys
    criteria = {c["key"] for c in capability["acceptance_criteria"]}
    assert "old-c" not in criteria and "exist-c" not in criteria and "exist-d" in criteria
    async with async_session_factory() as session:
        change_id = (
            await session.execute(select(SpecDocument.id).where(SpecDocument.path == CHANGE))
        ).scalar_one()
        merges = (
            (
                await session.execute(
                    select(SpecDocumentMerge).where(
                        SpecDocumentMerge.change_document_id == change_id
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(merges) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, code",
    [
        ({"retire": ["ghost"]}, "fold_retire_unknown"),
        ({"retire_criteria": ["ghost-c"]}, "fold_retire_unknown"),
        (
            {"requirements": [{"key": "glow", "replaces": "old-rule"}], "retire": ["old-rule"]},
            "fold_retire_replaced",
        ),
    ],
)
async def test_a_refused_retirement_writes_nothing(app, auth_headers, tmp_path, body, code):
    await _ready(app, auth_headers)
    before = await _digest()

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP, **body}, headers=auth_headers
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == code
    assert await _digest() == before


@pytest.mark.asyncio
async def test_the_draft_lists_what_the_capability_holds_in_its_order(app, auth_headers, tmp_path):
    await _ready(app, auth_headers)

    response = await app.get(
        f"{BASE}/documents/{CHANGE}/fold-draft", params={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft["capability_requirements"] == [
        {"key": "widgets-exist", "statement": "A widget MUST exist."},
        {"key": "old-rule", "statement": "A widget MUST never glow."},
    ]
    assert [(c["key"], c["requirement"], c["then"]) for c in draft["capability_criteria"]] == [
        ("exist-c", "widgets-exist", "dark"),
        ("exist-d", "widgets-exist", "t"),
        ("old-c", "old-rule", "never"),
    ]
