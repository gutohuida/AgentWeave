"""F706: evidence that says `covers: partial` alone made a requirement Verified.

Found on the 2026-10-18 sweep (group B): FR-2 and the capability's FR-4 read verified though the
only accepted current piece said `covers: partial`; `covers` was displayed, never weighed. Operator
decision (Tier 1, 2026-10-18): a requirement whose only accepted current evidence is partial reads
`in_progress`, with the reason "partial evidence only", so a `gate` document refuses approval until
some accepted piece says it covers the requirement fully (or does not say).

The acceptance drive: through the routes — record as the agent, accept as the operator, read
coverage, and approve under `gate`.
"""

import pytest

from .test_requirement_gate import (
    AGENT_EVIDENCE,
    BASE,
    _document,
    _linked_task,
    _set_rigor,
    _task_to,
    builder,  # noqa: F401  (fixture)
)


async def _record_and_accept(app, auth_headers, run_headers, covers):
    body = {"identifier": "FR-1", "summary": f"covers {covers}"}
    if covers is not None:
        body["covers"] = covers
    recorded = await app.post(AGENT_EVIDENCE, json=body, headers=run_headers)
    assert recorded.status_code == 201, recorded.text
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text


async def _coverage(app, auth_headers):
    response = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)
    assert response.status_code == 200, response.text
    return next(row for row in response.json()["requirements"] if row["identifier"] == "FR-1")


@pytest.mark.xfail(strict=True, reason="F706: partial-only evidence still reads verified")
@pytest.mark.asyncio
async def test_partial_evidence_alone_reads_in_progress_and_the_gate_refuses(
    app, auth_headers, builder  # noqa: F811
):
    await _document(app, auth_headers, builder)
    assert (await _set_rigor(app, auth_headers, "gate")).status_code == 200
    task = await _linked_task(app, auth_headers)

    await _record_and_accept(app, auth_headers, builder, "partial")
    row = await _coverage(app, auth_headers)
    assert row["state"] == "in_progress", row
    assert row["reason"] == "partial evidence only", row
    assert row["accepted_count"] == 1

    refused = await _task_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review", "approved"
    )
    assert refused.status_code == 409, refused.text
    message = refused.json()["detail"]["message"]
    assert "FR-1" in message and "partial" in message, message

    # A piece that covers it fully verifies it, and the same approval goes through.
    await _record_and_accept(app, auth_headers, builder, "full")
    row = await _coverage(app, auth_headers)
    assert row["state"] == "verified", row
    assert row["reason"] is None
    approved = await _task_to(app, auth_headers, task, "approved")
    assert approved.status_code == 200, approved.text


@pytest.mark.xfail(strict=True, reason="F706: partial-only evidence still reads verified")
@pytest.mark.asyncio
async def test_evidence_that_does_not_say_still_verifies(app, auth_headers, builder):  # noqa: F811
    """`covers` absent is not partial: every piece recorded before vis-D5 reads as it did."""
    await _document(app, auth_headers, builder)
    await _record_and_accept(app, auth_headers, builder, None)
    row = await _coverage(app, auth_headers)
    assert row["state"] == "verified", row
    assert row["reason"] is None
