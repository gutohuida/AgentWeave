"""A rejected or accepted evidence row names why, without a second request.

`review_state` on an evidence row said *what* happened but not *why* - a caller that lists
evidence and finds `review_state: rejected` had to make one more GET per row, to
`/spec/evidence/{id}/reviews`, to learn the reason. Same silent-signal shape as the
merge-outcome and rejected-evidence-on-task fixes closed elsewhere. This covers the
`latest_review` field `_evidence_view` now embeds on `list_evidence`, `requirement_detail`, and
the `decide_evidence` response itself.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/latest-review-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-lr", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-lr",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_lr-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_lr-secret"}


async def _document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": PATH, "title": "Latest review demo"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Latest review demo",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


@pytest.mark.asyncio
async def test_a_freshly_recorded_row_carries_no_review_yet(app, auth_headers, builder):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "ran it"},
        headers=builder,
    )
    assert recorded.status_code == 201, recorded.text

    listed = await app.get(f"{BASE}/spec/evidence", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    [row] = listed.json()["evidence"]
    assert row["latest_review"] is None


@pytest.mark.asyncio
async def test_decide_evidence_response_names_its_own_reason(app, auth_headers, builder):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "ran it"},
        headers=builder,
    )
    decided = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "rejected", "reason": "tests never actually exercise FR-1"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text
    review = decided.json()["latest_review"]
    assert review is not None
    assert review["decision"] == "rejected"
    assert review["reason"] == "tests never actually exercise FR-1"
    assert review["actor_kind"] == "operator"


@pytest.mark.asyncio
async def test_list_evidence_and_requirement_detail_carry_the_rejection_reason(
    app, auth_headers, builder
):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "ran it"},
        headers=builder,
    )
    await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "rejected", "reason": "tests never actually exercise FR-1"},
        headers=auth_headers,
    )

    listed = await app.get(f"{BASE}/spec/evidence", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    [row] = listed.json()["evidence"]
    assert row["review_state"] == "rejected"
    assert row["latest_review"]["reason"] == "tests never actually exercise FR-1"

    detail = await app.get(f"{BASE}/spec/requirements/FR-1", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    [evidence_row] = detail.json()["evidence"]
    assert evidence_row["latest_review"]["reason"] == "tests never actually exercise FR-1"


@pytest.mark.asyncio
async def test_a_later_acceptance_replaces_the_reason_shown(app, auth_headers, builder):
    """`latest_review` follows `review_state` - a later decision is what's shown, not the first."""
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "ran it"},
        headers=builder,
    )
    evidence_id = recorded.json()["id"]
    await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "rejected", "reason": "not enough"},
        headers=auth_headers,
    )
    await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted", "reason": "fixed and re-checked"},
        headers=auth_headers,
    )

    listed = await app.get(f"{BASE}/spec/evidence", headers=auth_headers)
    [row] = listed.json()["evidence"]
    assert row["review_state"] == "accepted"
    assert row["latest_review"]["decision"] == "accepted"
    assert row["latest_review"]["reason"] == "fixed and re-checked"
