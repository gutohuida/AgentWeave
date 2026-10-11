"""A rejection of evidence is recorded with a reason, or not at all (F551, blank-reason part).

`EvidenceDecision.reason` defaults to `""` on both planes, and `requirement_evidence.decide` stored
it. A rejection is the only signal the author has about *what* to fix (the builder reads it back
through `list_evidence`), so a `rejected` review with nothing in it leaves the author with a retry
loop. Acceptance may stay silent: that one needs no corrective action.
"""

import pytest

from .test_requirement_evidence import AGENT_EVIDENCE, BASE, _document, _grant, _run


@pytest.fixture
async def builder():
    return await _run("builder", "run-builder", "aw_run_builder-secret")


@pytest.fixture
async def verifier():
    return await _run("verifier", "run-verifier", "aw_run_verifier-secret")


async def _evidence(app, auth_headers, builder):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    return recorded.json()["id"]


async def _reviews(app, auth_headers, evidence_id):
    response = await app.get(f"{BASE}/spec/evidence/{evidence_id}/reviews", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["reviews"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [{"decision": "rejected"}, {"decision": "rejected", "reason": "  \n"}]
)
async def test_the_operator_cannot_reject_without_a_reason(app, auth_headers, builder, body):
    evidence_id = await _evidence(app, auth_headers, builder)

    response = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision", json=body, headers=auth_headers
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "rejection_needs_reason"
    assert "reason" in detail["message"]
    assert await _reviews(app, auth_headers, evidence_id) == []


@pytest.mark.asyncio
async def test_a_granted_agent_cannot_reject_without_a_reason(app, auth_headers, builder, verifier):
    evidence_id = await _evidence(app, auth_headers, builder)
    await _grant("verifier")

    response = await app.post(
        f"{AGENT_EVIDENCE}/{evidence_id}/decision",
        json={"decision": "rejected", "reason": ""},
        headers=verifier,
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "rejection_needs_reason"
    assert await _reviews(app, auth_headers, evidence_id) == []


@pytest.mark.asyncio
async def test_acceptance_and_a_reasoned_rejection_are_unchanged(app, auth_headers, builder):
    evidence_id = await _evidence(app, auth_headers, builder)

    rejected = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "rejected", "reason": "the test cites the wrong file"},
        headers=auth_headers,
    )
    accepted = await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )

    assert rejected.status_code == 200, rejected.text
    assert accepted.status_code == 200, accepted.text
    assert [r["reason"] for r in await _reviews(app, auth_headers, evidence_id)] == [
        "the test cites the wrong file",
        "",
    ]
