"""A fold reports the gaps it introduced, and the capability's older ones apart (F754).

Folding into a capability that already has a gap (here `widgets-exist`, a MUST with no criterion)
answered that gap among the fold's own warnings, so the change was blamed for it. The fold's
`warnings` now name only what the fold introduced; what the capability held before it is in
`standing_warnings`.
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

CHANGE_PAYLOAD = _change()
CHANGE_PAYLOAD["requirements"] = [
    *CHANGE_PAYLOAD["requirements"],
    {"key": "pulse", "statement": "A glowing widget MUST pulse.", "modal": "MUST"},
]
CHANGE_PAYLOAD["tasks"] = [
    {**task, "requirements": [*task.get("requirements", []), "pulse"]}
    for task in CHANGE_PAYLOAD.get("tasks") or []
]


def _naming(findings, key):
    return [
        f for f in findings if f["code"] == "requirement_without_criterion" and key in f["message"]
    ]


@pytest.mark.asyncio
async def test_a_fold_does_not_report_the_capabilitys_older_gap_as_its_own(app, auth_headers):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers, payload=CHANGE_PAYLOAD)
    await _finish_tasks()

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert _naming(body["warnings"], "widgets-exist") == []
    assert len(_naming(body["standing_warnings"], "widgets-exist")) == 1
    # The control: the requirement this fold brought in without a criterion is the fold's own.
    assert len(_naming(body["warnings"], "widgets-glow-pulse")) == 1
    assert _naming(body["standing_warnings"], "widgets-glow-pulse") == []
