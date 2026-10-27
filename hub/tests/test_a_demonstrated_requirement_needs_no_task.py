"""A requirement already demonstrated by accepted evidence needs no task to serve it (F752).

Recording work that was built with tests, not through tasks, gave a change with no `tasks[]`, so
every requirement raised `requirement_without_task` ("nothing implements it") and approval needed
"Approve anyway" every time. Accepted evidence at the requirement's current wording is the
strongest answer to "what implements it", so it counts as serving the requirement. Evidence for an
earlier wording, or evidence that says it covers only part of the requirement, does not: those
read `stale` and `in_progress` in coverage, never `verified`.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

from ._spec_versions import content_version

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/recorded-after-the-fact/spec.json"

CRITERION = {
    "key": "c1",
    "requirement": "alpha",
    "given": "g",
    "when": "w",
    "then": "t",
    "checked_by": "agent",
    "how_to_check": "pytest hub/tests/test_alpha.py",
}
SCOPE = {"in_scope": ["the thing"], "non_goals": ["the other thing"]}


@pytest.fixture
async def author():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-rec", project_id="proj-test", name="author"))
        session.add(
            Run(
                id="run-rec",
                project_id="proj-test",
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_rec-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_rec-secret"}


async def submit(app, run_headers, statement="It lists what is due today"):
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Recorded after the fact",
        "requirements": [{"key": "alpha", "statement": statement, "modal": "MUST"}],
        "acceptance_criteria": [CRITERION],
        "scope": SCOPE,
        "delivery": {"mode": "none"},
    }
    saved = await app.post(SUBMIT, json={"path": PATH, "document": document}, headers=run_headers)
    assert saved.status_code == 200, saved.text
    return saved.json()


async def make_document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": PATH, "title": "Recorded after the fact"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    await submit(app, run_headers)


async def record(app, auth_headers, **extra):
    recorded = await app.post(
        f"{BASE}/spec/evidence",
        json={
            "identifier": "FR-1",
            "document": PATH,
            "kind": "manual_observation",
            "summary": "built and tested before this change was written",
            **extra,
        },
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["review_state"] == "accepted"


async def check(app, auth_headers):
    closed = await app.post(
        f"{BASE}/documents/close-exploration", params={"path": PATH}, headers=auth_headers
    )
    assert closed.status_code == 200, closed.text
    checked = await app.post(f"{BASE}/documents/check", params={"path": PATH}, headers=auth_headers)
    assert checked.status_code == 200, checked.text
    return checked.json()


def codes(findings):
    return {finding["code"] for finding in findings}


async def phase(app, auth_headers, to):
    body = {"reason": "recording where it stands"}
    if to == "approved":
        body["content_version"] = await content_version(app, auth_headers, PATH)
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": to},
        json=body,
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_accepted_evidence_serves_a_requirement_no_task_names(app, auth_headers, author):
    await make_document(app, auth_headers, author)
    await record(app, auth_headers)

    body = await check(app, auth_headers)

    assert body["blocking"] == []
    assert "requirement_without_task" not in codes(body["warnings"]), body["warnings"]


@pytest.mark.asyncio
async def test_already_built_work_is_approved_without_approve_anyway(app, auth_headers, author):
    """The record-only path end to end, each step the one the previous answer named."""
    await make_document(app, auth_headers, author)
    await record(app, auth_headers)
    await check(app, auth_headers)

    refused = await phase(app, auth_headers, "approved")

    assert refused.status_code == 409, refused.text
    [gap] = refused.json()["detail"]["warnings"]
    assert gap["code"] == "steps_skipped"
    # Still exploring, so the journey moves directly: no send-it-back first.
    assert "to=exploring" not in gap["message"], gap["message"]
    journeyed = await app.post(
        f"{BASE}/documents/journey",
        params={"path": PATH},
        json={"step": "build"},
        headers=auth_headers,
    )
    assert journeyed.status_code == 200, journeyed.text
    assert (await check(app, auth_headers))["warnings"] == []
    approved = await phase(app, auth_headers, "approved")
    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"


@pytest.mark.asyncio
async def test_a_save_reports_the_same_as_a_check(app, auth_headers, author):
    """F703's rule: a write and a check of the same payload agree on what they report."""
    await make_document(app, auth_headers, author)
    await record(app, auth_headers)

    saved = await submit(app, author)

    assert "requirement_without_task" not in codes(saved["warnings"]), saved["warnings"]


@pytest.mark.asyncio
async def test_evidence_for_an_earlier_wording_does_not_serve(app, auth_headers, author):
    await make_document(app, auth_headers, author)
    await record(app, auth_headers)

    saved = await submit(app, author, statement="It lists what is due this week")

    assert "requirement_without_task" in codes(saved["warnings"]), saved["warnings"]
    body = await check(app, auth_headers)
    assert "requirement_without_task" in codes(body["warnings"]), body["warnings"]


@pytest.mark.asyncio
async def test_partial_evidence_does_not_serve(app, auth_headers, author):
    await make_document(app, auth_headers, author)
    await record(app, auth_headers, covers="partial")

    body = await check(app, auth_headers)

    assert "requirement_without_task" in codes(body["warnings"]), body["warnings"]


@pytest.mark.asyncio
async def test_the_gap_names_evidence_as_a_way_to_serve_it(app, auth_headers, author):
    await make_document(app, auth_headers, author)

    body = await check(app, auth_headers)

    [gap] = [w for w in body["warnings"] if w["code"] == "requirement_without_task"]
    assert "evidence" in gap["message"], gap["message"]
