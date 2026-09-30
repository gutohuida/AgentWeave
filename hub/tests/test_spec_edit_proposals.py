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
from hub.db.models import Run, SpecDocumentEvent, SpecEditProposal
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


@pytest.mark.asyncio
async def test_an_accept_keeps_the_reason_it_was_given_exactly_as_a_reject_does(
    app, auth_headers, run_headers
):
    """F209: the route declared a 2000-character `reason`, answered 200, and stored nothing.

    The record of *why* a spec change was let in is the half of the pair an auditor actually
    wants, and it was the half that was dropped. Asserted against a reject of a sibling proposal
    in the same document, because "the accept keeps it too" is the whole claim.
    """
    await _gate_document(app, auth_headers, run_headers)
    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    changed["summary"] = "Revised summary"
    await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    proposals = listing.json()["proposals"]
    accepted = next(p for p in proposals if p["unit_kind"] == "requirement")
    rejected = next(p for p in proposals if p["unit_kind"] == "metadata")

    accept = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{accepted['id']}/accept",
        json={"reason": "looks right, and the gate agrees"},
        headers=auth_headers,
    )
    assert accept.status_code == 200, accept.text
    reject = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{rejected['id']}/reject",
        json={"reason": "not now"},
        headers=auth_headers,
    )
    assert reject.status_code == 200, reject.text

    async with async_session_factory() as session:
        rows = {
            row.id: row
            for row in (
                await session.execute(
                    select(SpecEditProposal).where(
                        SpecEditProposal.id.in_([accepted["id"], rejected["id"]])
                    )
                )
            ).scalars()
        }
    assert rows[accepted["id"]].status == "accepted"
    assert rows[accepted["id"]].resolution_reason == "looks right, and the gate agrees"
    assert rows[rejected["id"]].resolution_reason == "not now"


@pytest.mark.asyncio
async def test_an_accept_with_no_reason_stores_an_empty_one_rather_than_failing(
    app, auth_headers, run_headers
):
    """The field defaults to `""`, and the UI sends no reason at all (`useAcceptSpecProposal`)."""
    await _gate_document(app, auth_headers, run_headers)
    changed = _document()
    changed["requirements"][0]["statement"] = "It responds within 100ms"
    await app.post(AGENT, json={"path": PATH, "document": changed}, headers=run_headers)

    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    proposal_id = listing.json()["proposals"][0]["id"]
    accept = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{proposal_id}/accept", json={}, headers=auth_headers
    )

    assert accept.status_code == 200, accept.text
    async with async_session_factory() as session:
        row = await session.get(SpecEditProposal, proposal_id)
    assert row.status == "accepted"
    assert row.resolution_reason == ""


# --- A pending proposal leaves the queue without a judgement (F213, F428, F431) ------------------
# `a-pending-proposal-can-be-withdrawn`, design D1-D7.


def _operator():
    from hub.spec_lifecycle import Actor

    return Actor(kind="operator", name="operator")


@pytest.fixture
async def second_agent_headers():
    token = "aw_run_propose-other-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-propose-other",
                project_id="proj-test",
                agent="claude-2",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def _submit(app, headers, document):
    response = await app.post(AGENT, json={"path": PATH, "document": document}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _pending(app, auth_headers):
    listing = await app.get(f"{BASE}/documents/{PATH}/proposals", headers=auth_headers)
    assert listing.status_code == 200, listing.text
    return listing.json()["proposals"]


async def _stored(proposal_id):
    async with async_session_factory() as session:
        return await session.get(SpecEditProposal, proposal_id)


def _alpha(statement):
    changed = _document()
    changed["requirements"][0]["statement"] = statement
    return changed


@pytest.mark.asyncio
async def test_submitting_the_same_edit_twice_proposes_it_once(app, auth_headers, run_headers):
    """F213: 2 units submitted twice made 4 pending, with nothing to tell the pairs apart."""
    await _gate_document(app, auth_headers, run_headers)
    changed = _alpha("It responds within 100ms")
    changed["summary"] = "Revised summary"

    first = await _submit(app, run_headers, changed)
    second = await _submit(app, run_headers, changed)

    assert {p["id"] for p in await _pending(app, auth_headers)} == {
        p["id"] for p in first["proposals"]
    }
    assert second["proposals"] == []
    assert {p["id"] for p in second["already_pending"]} == {p["id"] for p in first["proposals"]}


@pytest.mark.asyncio
async def test_a_revision_supersedes_the_proposers_earlier_edit(app, auth_headers, run_headers):
    await _gate_document(app, auth_headers, run_headers)
    first = await _submit(app, run_headers, _alpha("It responds within 100ms"))
    second = await _submit(app, run_headers, _alpha("It responds within 50ms"))

    [old] = [p for p in first["proposals"] if p["unit_key"] == "alpha"]
    [new] = [p for p in second["proposals"] if p["unit_key"] == "alpha"]
    pending_alpha = [p for p in await _pending(app, auth_headers) if p["unit_key"] == "alpha"]
    assert [p["id"] for p in pending_alpha] == [new["id"]]
    row = await _stored(old["id"])
    assert row.status == "superseded"
    assert new["id"] in row.resolution_reason


@pytest.mark.asyncio
async def test_another_proposers_edit_is_an_alternative_not_a_revision(
    app, auth_headers, run_headers, second_agent_headers
):
    await _gate_document(app, auth_headers, run_headers)
    await _submit(app, run_headers, _alpha("It responds within 100ms"))
    await _submit(app, second_agent_headers, _alpha("It responds within 50ms"))

    pending_alpha = [p for p in await _pending(app, auth_headers) if p["unit_key"] == "alpha"]
    assert len(pending_alpha) == 2


@pytest.mark.asyncio
async def test_a_resubmission_after_an_accept_replaces_the_stale_in_waiting_sibling(
    app, auth_headers, run_headers
):
    await _gate_document(app, auth_headers, run_headers)
    changed = _alpha("It responds within 100ms")
    changed["summary"] = "Revised summary"
    first = await _submit(app, run_headers, changed)
    [alpha] = [p for p in first["proposals"] if p["unit_kind"] == "requirement"]
    [metadata] = [p for p in first["proposals"] if p["unit_kind"] == "metadata"]
    accepted = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{alpha['id']}/accept", json={}, headers=auth_headers
    )
    assert accepted.status_code == 200, accepted.text

    again = await _submit(app, run_headers, changed)

    assert again["already_pending"] == []
    assert (await _stored(metadata["id"])).status == "superseded"
    [fresh] = [p for p in await _pending(app, auth_headers) if p["unit_kind"] == "metadata"]
    assert fresh["id"] != metadata["id"]


@pytest.mark.asyncio
async def test_the_operator_can_withdraw_a_pending_proposal(app, auth_headers, run_headers):
    await _gate_document(app, auth_headers, run_headers)
    [proposal] = (await _submit(app, run_headers, _alpha("It responds within 100ms")))["proposals"]
    before = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)

    withdrawn = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{proposal['id']}/withdraw",
        json={"note": "a duplicate"},
        headers=auth_headers,
    )

    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["proposal"]["status"] == "withdrawn"
    assert withdrawn.json()["proposal"]["resolution_reason"] == "a duplicate"
    after = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert before.json()["content"] == after.json()["content"]
    assert await _pending(app, auth_headers) == []
    again = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{proposal['id']}/withdraw", headers=auth_headers
    )
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "proposal_not_pending"
    missing = await app.post(
        f"{BASE}/documents/{PATH}/proposals/spprop-nope/withdraw", headers=auth_headers
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_withdrawing_is_the_operators(app, auth_headers, run_headers):
    from hub import spec_service
    from hub.spec_lifecycle import Actor

    await _gate_document(app, auth_headers, run_headers)
    [proposal] = (await _submit(app, run_headers, _alpha("It responds within 100ms")))["proposals"]
    async with async_session_factory() as session:
        row = await session.get(SpecEditProposal, proposal["id"])
        with pytest.raises(spec_service.ProposalRefusedError) as refused:
            await spec_service.withdraw_proposal(
                session, row, actor=Actor(kind="agent", name="claude-1")
            )
    assert refused.value.code == "withdraw_is_the_operators"


@pytest.mark.asyncio
async def test_reject_and_withdraw_tell_every_view(app, auth_headers, run_headers, monkeypatch):
    await _gate_document(app, auth_headers, run_headers)
    changed = _alpha("It responds within 100ms")
    changed["summary"] = "Revised summary"
    first, second = (await _submit(app, run_headers, changed))["proposals"]
    events = []

    async def record(project_id, event, data):
        events.append((event, data.get("path")))

    monkeypatch.setattr("hub.api.v1.spec.sse_manager.broadcast", record)
    rejected = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{first['id']}/reject", json={}, headers=auth_headers
    )
    assert rejected.status_code == 200, rejected.text
    assert events == [("spec_updated", PATH)]
    withdrawn = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{second['id']}/withdraw", headers=auth_headers
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert events == [("spec_updated", PATH), ("spec_updated", PATH)]


@pytest.mark.asyncio
async def test_an_accept_refused_as_stale_tells_every_view(
    app, auth_headers, run_headers, monkeypatch
):
    """F431: the refusal commits the row's move to `stale`; the list must drop it everywhere."""
    await _gate_document(app, auth_headers, run_headers)
    changed = _alpha("It responds within 100ms")
    changed["summary"] = "Revised summary"
    proposals = (await _submit(app, run_headers, changed))["proposals"]
    [alpha] = [p for p in proposals if p["unit_kind"] == "requirement"]
    [metadata] = [p for p in proposals if p["unit_kind"] == "metadata"]
    await app.post(
        f"{BASE}/documents/{PATH}/proposals/{alpha['id']}/accept", json={}, headers=auth_headers
    )
    events = []

    async def record(project_id, event, data):
        events.append((event, data.get("path")))

    monkeypatch.setattr("hub.api.v1.spec.sse_manager.broadcast", record)
    stale = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{metadata['id']}/accept", json={}, headers=auth_headers
    )

    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "proposal_stale"
    assert events == [("spec_updated", PATH)]
    assert (await _stored(metadata["id"])).status == "stale"


@pytest.mark.asyncio
async def test_a_unit_put_back_as_stored_retracts_its_removal(app, auth_headers, run_headers):
    """Without this, v1's `remove beta` stays pending after v2 restores beta, and accepting it
    deletes a requirement its proposer brought back."""
    await _gate_document(app, auth_headers, run_headers)
    without_beta = _document()
    without_beta["requirements"] = without_beta["requirements"][:1]
    [removal] = (await _submit(app, run_headers, without_beta))["proposals"]
    assert removal["change_kind"] == "remove"

    restored = await _submit(app, run_headers, _document())

    assert restored["proposals"] == []
    row = await _stored(removal["id"])
    assert row.status == "superseded"
    assert "leaves this unit as stored" in row.resolution_reason
    assert await _pending(app, auth_headers) == []
    accept = await app.post(
        f"{BASE}/documents/{PATH}/proposals/{removal['id']}/accept", json={}, headers=auth_headers
    )
    assert accept.status_code == 409
    assert accept.json()["detail"]["code"] == "proposal_not_pending"
    content = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert "It logs the request" in content.json()["content"]


@pytest.mark.asyncio
async def test_a_unit_dropped_from_the_next_submission_is_retracted(
    app, auth_headers, run_headers, second_agent_headers
):
    await _gate_document(app, auth_headers, run_headers)
    with_gamma = _document()
    with_gamma["requirements"].append({"key": "gamma", "statement": "It is new", "modal": "MUST"})
    [added] = (await _submit(app, run_headers, with_gamma))["proposals"]
    [other] = (await _submit(app, second_agent_headers, with_gamma))["proposals"]

    await _submit(app, run_headers, _document())
    assert (await _stored(added["id"])).status == "superseded"
    assert (await _stored(other["id"])).status == "pending"

    summary = _document(summary="A new summary")
    [metadata] = (await _submit(app, run_headers, summary))["proposals"]
    await _submit(app, run_headers, _document())
    assert (await _stored(metadata["id"])).status == "superseded"


@pytest.mark.asyncio
async def test_a_decided_proposal_cannot_be_decided_again_by_a_stale_copy(
    app, auth_headers, run_headers
):
    """D7: every move out of `pending` is a conditional UPDATE. An attribute write on a row loaded
    before another request decided it turned `accepted` into `rejected`."""
    from hub import spec_service

    await _gate_document(app, auth_headers, run_headers)
    for decide in ("reject", "withdraw"):
        [proposal] = (await _submit(app, run_headers, _alpha(f"It responds within {decide}")))[
            "proposals"
        ]
        async with async_session_factory() as s1:
            held = await s1.get(SpecEditProposal, proposal["id"])
            assert held.status == "pending"
            await s1.commit()  # no transaction held across the other request
            accepted = await app.post(
                f"{BASE}/documents/{PATH}/proposals/{proposal['id']}/accept",
                json={},
                headers=auth_headers,
            )
            assert accepted.status_code == 200, accepted.text
            with pytest.raises(spec_service.ProposalRefusedError) as refused:
                if decide == "reject":
                    await spec_service.reject_proposal(s1, held, actor=_operator())
                else:
                    await spec_service.withdraw_proposal(s1, held, actor=_operator())
            await s1.commit()
        assert refused.value.code == "proposal_not_pending"
        assert (await _stored(proposal["id"])).status == "accepted"


@pytest.mark.asyncio
async def test_a_supersede_never_overwrites_a_decision(app, auth_headers, run_headers):
    from hub import spec_service
    from hub.db.models import SpecDocument
    from hub.spec_lifecycle import Actor
    from hub.spec_payload import validate_payload

    await _gate_document(app, auth_headers, run_headers)
    [proposal] = (await _submit(app, run_headers, _alpha("It responds within 100ms")))["proposals"]
    async with async_session_factory() as s1:
        held = await s1.get(SpecEditProposal, proposal["id"])
        assert held.status == "pending"
        await s1.commit()
        accepted = await app.post(
            f"{BASE}/documents/{PATH}/proposals/{proposal['id']}/accept",
            json={},
            headers=auth_headers,
        )
        assert accepted.status_code == 200, accepted.text
        document = (
            await s1.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        await s1.refresh(document)
        stored = _alpha("It responds within 100ms")
        await spec_service.propose_edit(
            s1,
            document,
            validate_payload(_alpha("It responds within 10ms")),
            stored,
            actor=Actor(kind="agent", name="claude-1", run_id="run-propose"),
        )
        await s1.commit()
    assert (await _stored(proposal["id"])).status == "accepted"


@pytest.mark.asyncio
async def test_an_accept_loses_to_a_withdraw_and_writes_nothing(app, auth_headers, run_headers):
    from hub import project_workspace, spec_service
    from hub.db.models import SpecDocument

    await _gate_document(app, auth_headers, run_headers)
    [proposal] = (await _submit(app, run_headers, _alpha("It responds within 100ms")))["proposals"]
    before = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    async with async_session_factory() as s1:
        held = await s1.get(SpecEditProposal, proposal["id"])
        document = (
            await s1.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        await s1.commit()
        withdrawn = await app.post(
            f"{BASE}/documents/{PATH}/proposals/{proposal['id']}/withdraw", headers=auth_headers
        )
        assert withdrawn.status_code == 200, withdrawn.text
        workspace = await project_workspace.resolve_project_workspace(s1, "proj-test")
        with pytest.raises(spec_service.ProposalRefusedError) as refused:
            await spec_service.accept_proposal(s1, workspace, document, held, actor=_operator())
        await s1.rollback()
    assert refused.value.code == "proposal_not_pending"
    after = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    assert before.json()["content"] == after.json()["content"]


@pytest.mark.asyncio
async def test_a_listed_proposal_carries_the_digest_it_was_made_against(
    app, auth_headers, run_headers
):
    await _gate_document(app, auth_headers, run_headers)
    [proposal] = (await _submit(app, run_headers, _alpha("It responds within 100ms")))["proposals"]

    [listed] = await _pending(app, auth_headers)

    assert listed["expected_digest"] == (await _stored(proposal["id"])).expected_digest
