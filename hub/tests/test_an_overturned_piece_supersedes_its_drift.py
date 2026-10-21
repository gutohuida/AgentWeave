"""F759: overturning evidence to rejected supersedes the drift candidate raised on it.

A drift candidate asks whether the implementation moved away from what a piece of *accepted*
evidence demonstrated. `RequirementDrift` outranks `rejected` in the coverage precedence, so a
candidate left open on a piece the operator then rejected hid the rejection: the requirement read
"drifting" with no accepted piece, and the approval gate (which only sees `rejected`) let the task
through. The overturn is the answer to that question, so it closes the candidate.
"""

import pytest

from .test_a_reworded_requirement_supersedes_its_drift import _drift, _raise_candidate
from .test_requirement_drift import BASE, builder  # noqa: F401 - the fixture, used by name


@pytest.mark.asyncio
async def test_overturning_the_piece_supersedes_its_open_candidate(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    await _raise_candidate(app, auth_headers, builder, tmp_path)
    [candidate] = await _drift(app, auth_headers, "candidate")

    overturned = await app.post(
        f"{BASE}/spec/evidence/{candidate['evidence_id']}/overturn",
        json={"reason": "the demonstration was wrong"},
        headers=auth_headers,
    )
    assert overturned.status_code == 200, overturned.text
    assert overturned.json()["review_state"] == "rejected"

    assert await _drift(app, auth_headers, "candidate") == []
    assert [d["state"] for d in await _drift(app, auth_headers)] == ["superseded"]


@pytest.mark.asyncio
async def test_a_rejected_requirement_reads_rejected_not_drifting(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    await _raise_candidate(app, auth_headers, builder, tmp_path)
    [candidate] = await _drift(app, auth_headers, "candidate")
    await app.post(
        f"{BASE}/spec/evidence/{candidate['evidence_id']}/overturn",
        json={"reason": "the demonstration was wrong"},
        headers=auth_headers,
    )

    listed = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    states = [r["state"] for r in listed.json()["requirements"]]
    assert states == ["rejected"], listed.text


@pytest.mark.asyncio
async def test_the_approval_gate_refuses_a_task_whose_only_piece_was_overturned_after_drift(
    app, auth_headers, builder, tmp_path  # noqa: F811
):
    """The repro as the operator walks it: accept, drift, overturn, then approve the task."""
    from .test_task_integration import approve, linked_task

    await _raise_candidate(app, auth_headers, builder, tmp_path)
    task = await linked_task(app, auth_headers)
    [candidate] = await _drift(app, auth_headers, "candidate")
    overturned = await app.post(
        f"{BASE}/spec/evidence/{candidate['evidence_id']}/overturn",
        json={"reason": "the demonstration was wrong"},
        headers=auth_headers,
    )
    assert overturned.status_code == 200, overturned.text

    refused = await approve(app, auth_headers, task)

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert [b["state"] for b in detail["blocking"]] == ["rejected"], detail
