"""A fold carries the change's algorithms and criterion rewrites, and reaches a second capability (F753).

`spec/changes/a-fold-carries-algorithms-and-criterion-rewrites`: a fold appends the change's
algorithms (or replaces a named capability algorithm with one, or retires one), puts a change
criterion in place of a named capability criterion under the capability's key, and a change already
folded and archived can still be folded into a capability it is not yet in.
"""

import pytest

from hub.spec_documents import parse_stored
from tests.test_a_finished_change_is_folded_into_its_capability import (
    BASE,
    CAP,
    CAP2,
    CHANGE,
    _approved_change,
    _capability,
    _change,
    _create_capability,
    _digest,
    _finish_tasks,
    _state,
)

STEPS_OLD = ["Hover.", "Glow."]
STEPS_NEW = ["Hover.", "Wait 50ms.", "Glow."]

CAPABILITY = _capability()
CAPABILITY["acceptance_criteria"] = [
    {"key": "exist-c", "requirement": "widgets-exist", "given": "g", "when": "w", "then": "old"},
]
CAPABILITY["algorithms"] = [
    {"name": "Hover", "steps": STEPS_OLD},
    {"name": "Idle", "steps": ["Dim."]},
]

CHANGE_PAYLOAD = _change(
    algorithms=[{"name": "Hover", "steps": STEPS_NEW}, {"name": "Blink", "steps": ["Blink."]}]
)


async def _ready(app, auth_headers, capability=None):
    await _create_capability(app, auth_headers, payload=capability or CAPABILITY)
    await _approved_change(app, auth_headers, payload=CHANGE_PAYLOAD)
    await _finish_tasks()


async def _on_disk(tmp_path, path=CAP):
    return parse_stored((tmp_path / path).read_text(encoding="utf-8"))


async def _fold(app, auth_headers, **body):
    return await app.post(
        f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP, **body}, headers=auth_headers
    )


@pytest.mark.asyncio
async def test_a_fold_replaces_an_algorithm_appends_another_and_retires_a_third(
    app, auth_headers, tmp_path
):
    await _ready(app, auth_headers)

    response = await _fold(
        app,
        auth_headers,
        algorithms=[{"name": "Hover", "replaces": "Hover"}, {"name": "Blink"}],
        retire_algorithms=["Idle"],
    )

    assert response.status_code == 200, response.text
    algorithms = (await _on_disk(tmp_path))["algorithms"]
    assert algorithms == [
        {"name": "Hover", "steps": STEPS_NEW},
        {"name": "Blink", "steps": ["Blink."]},
    ]


@pytest.mark.asyncio
async def test_by_default_a_fold_carries_every_algorithm_of_the_change(app, auth_headers, tmp_path):
    await _ready(app, auth_headers, capability=_capability())

    response = await _fold(app, auth_headers)

    assert response.status_code == 200, response.text
    names = [a["name"] for a in (await _on_disk(tmp_path))["algorithms"]]
    assert names == ["Hover", "Blink"]


@pytest.mark.asyncio
async def test_a_fold_puts_a_change_criterion_in_place_of_a_capability_criterion(
    app, auth_headers, tmp_path
):
    await _ready(app, auth_headers)

    response = await _fold(
        app,
        auth_headers,
        requirements=[{"key": "glow"}],
        criteria=[{"key": "dim-c", "replaces": "exist-c"}],
        algorithms=[],
    )

    assert response.status_code == 200, response.text
    criteria = {c["key"]: c for c in (await _on_disk(tmp_path))["acceptance_criteria"]}
    # Under the capability's key, still demonstrating the capability's requirement, since the
    # change criterion's own requirement (`dim`) was not folded.
    assert criteria["exist-c"]["then"] == "it dims"
    assert criteria["exist-c"]["requirement"] == "widgets-exist"
    # Not folded a second time under a drafted key.
    assert not [k for k in criteria if k.endswith("dim-c")]


@pytest.mark.asyncio
async def test_a_replacing_criterion_follows_its_folded_requirement(app, auth_headers, tmp_path):
    await _ready(app, auth_headers)

    response = await _fold(
        app,
        auth_headers,
        requirements=[{"key": "glow", "replaces": "widgets-exist"}],
        criteria=[{"key": "glow-c", "replaces": "exist-c"}],
        algorithms=[],
    )

    assert response.status_code == 200, response.text
    criteria = {c["key"]: c for c in (await _on_disk(tmp_path))["acceptance_criteria"]}
    assert criteria["exist-c"]["then"] == "it glows"
    assert criteria["exist-c"]["requirement"] == "widgets-exist"
    assert not [k for k in criteria if k.endswith("glow-c")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, code",
    [
        ({"algorithms": [{"name": "Ghost"}]}, "fold_unknown_algorithm"),
        ({"algorithms": [{"name": "Hover"}]}, "fold_key_collision"),
        ({}, "fold_key_collision"),
        ({"algorithms": [{"name": "Blink", "replaces": "Ghost"}]}, "fold_replaces_unknown"),
        ({"algorithms": [], "retire_algorithms": ["Ghost"]}, "fold_retire_unknown"),
        (
            {
                "algorithms": [{"name": "Hover", "replaces": "Hover"}],
                "retire_algorithms": ["Hover"],
            },
            "fold_retire_replaced",
        ),
        ({"algorithms": [], "criteria": [{"key": "ghost", "replaces": "exist-c"}]}, None),
        ({"algorithms": [], "criteria": [{"key": "dim-c", "replaces": "ghost"}]}, None),
        (
            {
                "algorithms": [],
                "criteria": [{"key": "dim-c", "replaces": "exist-c"}],
                "retire_criteria": ["exist-c"],
            },
            "fold_retire_replaced",
        ),
    ],
)
async def test_a_refused_algorithm_or_criterion_fold_writes_nothing(
    app, auth_headers, tmp_path, body, code
):
    await _ready(app, auth_headers)
    before = await _digest()

    response = await _fold(app, auth_headers, **body)

    assert response.status_code == 409, response.text
    expected = code or (
        "fold_unknown_criterion"
        if body["criteria"][0]["key"] == "ghost"
        else "fold_replaces_unknown"
    )
    assert response.json()["detail"]["code"] == expected
    assert await _digest() == before
    assert await _state() == ("approved", 0)


@pytest.mark.asyncio
async def test_the_draft_lists_the_capability_algorithms_and_the_folded_ones(
    app, auth_headers, tmp_path
):
    await _ready(app, auth_headers, capability=_capability())

    response = await app.get(
        f"{BASE}/documents/{CHANGE}/fold-draft", params={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["capability_algorithms"] == []
    assert [a["name"] for a in body["algorithms"]] == ["Hover", "Blink"]
    assert [a["name"] for a in body["payload"]["algorithms"]] == ["Hover", "Blink"]


@pytest.mark.asyncio
async def test_a_folded_archived_change_is_folded_into_a_second_capability(
    app, auth_headers, tmp_path
):
    await _create_capability(app, auth_headers)
    await _create_capability(app, auth_headers, path=CAP2, payload=_capability(title="Gadgets"))
    await _approved_change(app, auth_headers)
    await _finish_tasks()
    first = await _fold(app, auth_headers, requirements=[{"key": "glow"}])
    assert first.status_code == 200, first.text
    assert first.json()["phase"] == "archived"

    draft = await app.get(
        f"{BASE}/documents/{CHANGE}/fold-draft", params={"into": CAP2}, headers=auth_headers
    )
    second = await app.post(
        f"{BASE}/documents/{CHANGE}/fold",
        json={"into": CAP2, "requirements": [{"key": "dim"}]},
        headers=auth_headers,
    )

    assert draft.status_code == 200, draft.text
    assert second.status_code == 200, second.text
    assert second.json()["phase"] == "archived"
    assert second.json()["archived"] is False
    assert second.json()["fold_state"]["capabilities"] == [CAP, CAP2]
    assert await _state() == ("archived", 2)
    keys = [r["key"] for r in (await _on_disk(tmp_path, CAP2))["requirements"]]
    assert "widgets-glow-dim" in keys


@pytest.mark.asyncio
async def test_a_folded_archived_change_is_not_folded_into_the_same_capability_again(
    app, auth_headers, tmp_path
):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    await _finish_tasks()
    first = await _fold(app, auth_headers, requirements=[{"key": "glow"}])
    assert first.status_code == 200, first.text
    before = await _digest()

    again = await _fold(app, auth_headers, requirements=[{"key": "dim"}])

    assert again.status_code == 409, again.text
    assert again.json()["detail"]["code"] == "fold_already_folded"
    assert await _digest() == before


@pytest.mark.asyncio
async def test_an_archived_change_that_was_never_folded_is_still_not_folded(
    app, auth_headers, tmp_path
):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    await _finish_tasks()
    archived = await app.post(
        f"{BASE}/documents/phase",
        params={"path": CHANGE, "to": "archived"},
        json={"no_capability_change": True, "reason": "it changed nothing"},
        headers=auth_headers,
    )
    assert archived.status_code == 200, archived.text

    response = await _fold(app, auth_headers)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "fold_change_not_approved"
