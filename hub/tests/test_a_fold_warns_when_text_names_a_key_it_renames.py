"""A fold warns when the folded text names a change key the fold renames (F757).

The default fold prefixes each requirement key with the change's name. An algorithm step or a
rationale that names one of the change's own requirements by key was folded verbatim, so in the
capability it named a key that does not exist, and neither the draft nor the fold said so. Now both
report each such name; keeping the key (`as_key`) is the other way out and reports nothing.
"""

import pytest

from tests.test_a_finished_change_is_folded_into_its_capability import (
    BASE,
    CAP,
    CHANGE,
    _approved_change,
    _change,
    _create_capability,
    _finish_tasks,
)

PAYLOAD = _change(
    algorithms=[
        {
            "name": "Hover",
            "steps": ["Hover.", "Glow, as (*glow-on-hover*) says.", "Dim a glow once idle."],
        }
    ]
)
PAYLOAD["requirements"] = [
    {
        "key": "glow-on-hover",
        "statement": "A widget MUST glow when hovered.",
        "modal": "MUST",
        "rationale": "See `dim-when-idle` for the other half.",
    },
    {"key": "dim-when-idle", "statement": "A widget SHOULD dim when idle.", "modal": "SHOULD"},
]
for _criterion in PAYLOAD["acceptance_criteria"]:
    _criterion["requirement"] = {"glow": "glow-on-hover", "dim": "dim-when-idle"}.get(
        _criterion["requirement"], _criterion["requirement"]
    )
for _task in PAYLOAD.get("tasks") or []:
    _task["requirements"] = [
        {"glow": "glow-on-hover", "dim": "dim-when-idle"}.get(k, k)
        for k in _task.get("requirements", [])
    ]


def _dangling(warnings):
    return [w for w in warnings if w["code"] == "fold_renamed_key_named"]


async def _ready(app, auth_headers):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers, payload=PAYLOAD)
    await _finish_tasks()


@pytest.mark.asyncio
async def test_the_draft_names_each_renamed_key_the_text_still_uses(app, auth_headers):
    await _ready(app, auth_headers)

    response = await app.get(
        f"{BASE}/documents/{CHANGE}/fold-draft", params={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    found = _dangling(response.json()["warnings"])
    messages = " ".join(w["message"] for w in found)
    # The algorithm step, by key; the rationale, by key in backticks.
    assert "glow-on-hover" in messages and "dim-when-idle" in messages
    assert len(found) == 2
    assert "widgets-glow-glow-on-hover" in messages


@pytest.mark.asyncio
async def test_the_fold_reports_them_among_its_warnings(app, auth_headers):
    await _ready(app, auth_headers)

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    assert len(_dangling(response.json()["warnings"])) == 2


@pytest.mark.asyncio
async def test_keeping_the_key_reports_nothing(app, auth_headers):
    await _ready(app, auth_headers)

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold",
        json={
            "into": CAP,
            "requirements": [
                {"key": "glow-on-hover", "as_key": "glow-on-hover"},
                {"key": "dim-when-idle", "as_key": "dim-when-idle"},
            ],
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert _dangling(response.json()["warnings"]) == []


@pytest.mark.asyncio
async def test_a_word_in_prose_is_not_a_key_named(app, auth_headers):
    """The step "Dim a glow once idle." says `glow`, a plain word, and `glow` is no folded key."""
    await _ready(app, auth_headers)

    response = await app.get(
        f"{BASE}/documents/{CHANGE}/fold-draft", params={"into": CAP}, headers=auth_headers
    )

    assert all("`glow`" not in w["message"] for w in response.json()["warnings"])
