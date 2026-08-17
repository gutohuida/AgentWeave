"""F1-F3 — rigor gates whether an edit applies directly or becomes a proposal.

`openspec/changes/2026-08-17-authoring-rigor-and-scope`. At `contract`/`gate` rigor an agent's
submission no longer writes the live document — it is diffed and recorded as one pending,
individually acceptable `SpecEditProposal` per changed unit, until an operator accepts or rejects
it (design D1-D5).
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocumentEvent
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/demo/spec.html"


@pytest.fixture
async def run_headers():
    token = "aw_run_propose-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-propose",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _document(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Demo",
        "summary": "Original summary",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"},
            {"key": "beta", "statement": "It logs the request", "modal": "MUST"},
        ],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
    }
    payload.update(overrides)
    return payload


async def _gate_document(app, auth_headers, run_headers, path=PATH):
    await app.post(f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers)
    write = await app.post(AGENT, json={"path": path, "document": _document()}, headers=run_headers)
    assert write.status_code == 200, write.text
    rigor = await app.post(
        f"{BASE}/documents/{path}/rigor",
        json={"rigor": "gate"},
        headers=auth_headers,
    )
    assert rigor.status_code == 200, rigor.text
    return rigor.json()


@pytest.mark.asyncio
async def test_a_gate_rigor_submission_creates_proposals_instead_of_writing(
    app, auth_headers, run_headers
):
    await _gate_document(app, auth_headers, run_headers)

    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    changed["summary"] = "Revised summary"
    response = await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "identifiers" not in body
    assert len(body["proposals"]) == 2  # one requirement modify, one metadata modify
    kinds = {p["unit_kind"] for p in body["proposals"]}
    assert kinds == {"requirement", "metadata"}

    # The live document is untouched.
    content = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert "It responds within 200ms" in content.json()["content"]
    assert "It responds within 100ms" not in content.json()["content"]


@pytest.mark.asyncio
async def test_the_same_submission_against_a_sketch_document_still_applies_immediately(
    app, auth_headers, run_headers
):
    """Regression guard (design D1) — the one path that must not change."""
    path = "spec/changes/sketch-demo/spec.html"
    await app.post(f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers)
    await app.post(AGENT, json={"path": path, "document": _document()}, headers=run_headers)

    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    response = await app.post(AGENT, json={"path": path, "document": changed}, headers=run_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert "proposals" not in body
    assert "identifiers" in body

    content = await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)
    assert "It responds within 100ms" in content.json()["content"]


@pytest.mark.asyncio
async def test_an_unchanged_resubmission_creates_zero_proposals(app, auth_headers, run_headers):
    await _gate_document(app, auth_headers, run_headers)

    response = await app.post(
        AGENT, json={"path": PATH, "document": _document()}, headers=run_headers
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposals"] == []
    assert set(body["unchanged"]) == {"alpha", "beta", "metadata"}


@pytest.mark.asyncio
async def test_a_new_requirement_creates_an_add_proposal_positioned_after_its_neighbour(
    app, auth_headers, run_headers
):
    await _gate_document(app, auth_headers, run_headers)

    changed = _document()
    changed["requirements"].append(
        {"key": "gamma", "statement": "It retries once", "modal": "SHOULD"}
    )
    response = await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    assert response.status_code == 200, response.text
    proposals = response.json()["proposals"]
    assert len(proposals) == 1
    assert proposals[0]["change_kind"] == "add"
    assert proposals[0]["unit_key"] == "gamma"

    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    row = listing.json()["proposals"][0]
    assert row["position_after_key"] == "beta"


@pytest.mark.asyncio
async def test_accepting_one_proposal_leaves_a_sibling_pending_and_untouched(
    app, auth_headers, run_headers
):
    await _gate_document(app, auth_headers, run_headers)
    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    changed["summary"] = "Revised summary"
    await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    proposals = listing.json()["proposals"]
    requirement_proposal = next(p for p in proposals if p["unit_kind"] == "requirement")
    metadata_proposal = next(p for p in proposals if p["unit_kind"] == "metadata")

    accept = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{requirement_proposal['id']}/accept",
        json={},
        headers=auth_headers,
    )
    assert accept.status_code == 200, accept.text

    content = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert "It responds within 100ms" in content.json()["content"]
    assert "Revised summary" not in content.json()["content"]

    # Untouched, not auto-staled: D5 only detects staleness on an accept *attempt* against it,
    # tested separately below. Its status stays "pending" until someone acts on it.
    listing_after = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    remaining = {p["id"]: p["status"] for p in listing_after.json()["proposals"]}
    assert remaining[metadata_proposal["id"]] == "pending"


@pytest.mark.asyncio
async def test_accepting_a_second_proposal_against_the_same_digest_is_refused_as_stale(
    app, auth_headers, run_headers
):
    await _gate_document(app, auth_headers, run_headers)
    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    changed["summary"] = "Revised summary"
    await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    proposals = listing.json()["proposals"]
    requirement_proposal = next(p for p in proposals if p["unit_kind"] == "requirement")
    metadata_proposal = next(p for p in proposals if p["unit_kind"] == "metadata")

    await app.post(
        f"{BASE}/documents/{PATH}/proposals/{requirement_proposal['id']}/accept",
        json={},
        headers=auth_headers,
    )
    stale_attempt = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{metadata_proposal['id']}/accept",
        json={},
        headers=auth_headers,
    )

    assert stale_attempt.status_code == 409
    assert stale_attempt.json()["detail"]["code"] == "proposal_stale"


@pytest.mark.asyncio
async def test_a_rejected_proposal_leaves_the_document_exactly_as_it_was(
    app, auth_headers, run_headers
):
    await _gate_document(app, auth_headers, run_headers)
    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    before = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    proposal_id = listing.json()["proposals"][0]["id"]

    reject = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{proposal_id}/reject",
        json={"reason": "not now"},
        headers=auth_headers,
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["proposal"]["status"] == "rejected"

    after = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert before.json()["content"] == after.json()["content"]


@pytest.mark.asyncio
async def test_an_agent_cannot_accept_or_reject_its_own_proposal(app, auth_headers, run_headers):
    await _gate_document(app, auth_headers, run_headers)
    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    proposal_id = listing.json()["proposals"][0]["id"]

    # The agent-actions router carries no accept/reject route at all — there is no URL for an
    # agent to even attempt this against, which is the enforcement (design D4/route split).
    accept = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{proposal_id}/accept", json={}, headers=run_headers
    )
    assert accept.status_code in (401, 403)


@pytest.mark.asyncio
async def test_the_accepted_event_names_both_proposer_and_accepter(app, auth_headers, run_headers):
    await _gate_document(app, auth_headers, run_headers)
    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    proposal_id = listing.json()["proposals"][0]["id"]
    await app.post(
        f"{BASE}/documents/{PATH}/proposals/{proposal_id}/accept", json={}, headers=auth_headers
    )

    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(SpecDocumentEvent)
                    .where(SpecDocumentEvent.kind == "content")
                    .order_by(SpecDocumentEvent.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        latest = events[0]
        assert latest.actor == "operator"  # the accepter
        assert latest.detail["proposal_id"] == proposal_id
        assert latest.detail["proposer_actor_name"] == "claude-1"  # the proposer, one hop away
