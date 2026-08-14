"""The evidence loop, reachable by the agents that are supposed to drive it.

Both routes existed and nothing could call them. `requirement_evidence.may_accept` gates acceptance
on `Agent.can_accept_evidence`, a column with no schema, no route and no control — so it refused
every agent in every project, and a capability enforced everywhere and grantable nowhere is a
refusal of everyone.

From the run that found it: approving a task reported

    skipped: no accepted evidence names a commit, so there is nothing to merge

and finishing the loop took a run credential minted straight into the database and a `curl`. An
operator cannot do that.

The listing route is here for the same reason. Deciding names a specific piece of evidence, so an
agent with no way to discover what exists has nothing to act on and the grant is decorative.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
SUBMIT = "/api/v1/agent-actions/spec/documents"
EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/agent-evidence/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}


async def _run(agent: str, run_id: str, token: str):
    async with async_session_factory() as session:
        existing = (
            (
                await session.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == agent)
                )
            )
            .scalars()
            .first()
        )
        if existing is None:
            session.add(Agent(id=f"ag-{agent}", project_id="proj-test", name=agent))
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def builder():
    return await _run("builder", "run-ev-builder", "aw_run_ev-builder")


@pytest.fixture
async def reviewer():
    return await _run("reviewer", "run-ev-reviewer", "aw_run_ev-reviewer")


async def _grant(app, auth_headers, agent: str, enabled: bool = True):
    """Through the operator's own route, which is the only way it can be conferred."""
    patched = await app.patch(
        f"/api/v1/projects/proj-test/agents/{agent}",
        json={"can_accept_evidence": enabled},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Agent evidence"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Agent evidence",
                "requirements": [ALPHA, BETA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def _record(app, headers, identifier="FR-1", summary="18 tests pass"):
    response = await app.post(
        EVIDENCE, json={"identifier": identifier, "summary": summary}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_an_agent_records_evidence_and_it_awaits_a_decision(app, auth_headers, builder):
    await _document(app, auth_headers, builder)
    recorded = await _record(app, builder)

    assert recorded["identifier"] == "FR-1"
    assert recorded["review_state"] == "awaiting"


@pytest.mark.asyncio
async def test_an_agent_can_read_the_evidence_it_is_asked_to_judge(
    app, auth_headers, builder, reviewer
):
    await _document(app, auth_headers, builder)
    await _record(app, builder)

    listed = await app.get(EVIDENCE, headers=reviewer)
    assert listed.status_code == 200, listed.text
    rows = listed.json()["evidence"]
    assert len(rows) == 1

    row = rows[0]
    # The identifier it reasons in, not the database id of the requirement.
    assert row["identifier"] == "FR-1"
    assert row["summary"] == "18 tests pass"
    assert row["review_state"] == "awaiting"
    # Who produced it: without this a reviewer cannot tell which rows it may decide, and learns
    # the self-acceptance rule by being refused once per row.
    assert row["actor_kind"] == "agent"
    assert row["actor"] == "builder"
    # And what the evidence is about, which is how it can be judged responsibly at all.
    assert "footprint" in row


@pytest.mark.asyncio
async def test_reading_can_be_narrowed_to_what_is_awaiting(app, auth_headers, builder, reviewer):
    await _document(app, auth_headers, builder)
    first = await _record(app, builder, identifier="FR-1")
    await _record(app, builder, identifier="FR-2", summary="also verified")
    await _grant(app, auth_headers, "reviewer")

    decided = await app.post(
        f"{EVIDENCE}/{first['id']}/decision",
        json={"decision": "accepted", "reason": "the transcript shows the run"},
        headers=reviewer,
    )
    assert decided.status_code == 200, decided.text

    awaiting = await app.get(EVIDENCE, params={"review_state": "awaiting"}, headers=reviewer)
    assert [row["identifier"] for row in awaiting.json()["evidence"]] == ["FR-2"]

    by_requirement = await app.get(EVIDENCE, params={"identifier": "FR-1"}, headers=reviewer)
    assert [row["identifier"] for row in by_requirement.json()["evidence"]] == ["FR-1"]


@pytest.mark.asyncio
async def test_an_ungranted_agent_is_refused(app, auth_headers, builder, reviewer):
    await _document(app, auth_headers, builder)
    recorded = await _record(app, builder)

    refused = await app.post(
        f"{EVIDENCE}/{recorded['id']}/decision", json={"decision": "accepted"}, headers=reviewer
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "acceptance_not_granted"


@pytest.mark.asyncio
async def test_a_granted_agent_accepts_another_agents_evidence(
    app, auth_headers, builder, reviewer
):
    """The whole point: accepted evidence is what lets approval merge."""
    await _document(app, auth_headers, builder)
    recorded = await _record(app, builder)
    await _grant(app, auth_headers, "reviewer")

    decided = await app.post(
        f"{EVIDENCE}/{recorded['id']}/decision",
        json={"decision": "accepted", "reason": "reproduced the run myself"},
        headers=reviewer,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["review_state"] == "accepted"


@pytest.mark.asyncio
async def test_a_granted_agent_still_cannot_accept_its_own(app, auth_headers, builder):
    await _document(app, auth_headers, builder)
    recorded = await _record(app, builder)
    await _grant(app, auth_headers, "builder")

    refused = await app.post(
        f"{EVIDENCE}/{recorded['id']}/decision", json={"decision": "accepted"}, headers=builder
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "self_acceptance"


@pytest.mark.asyncio
async def test_rejection_is_available_too(app, auth_headers, builder, reviewer):
    """A surface that can only accept makes rejection unreachable while HTTP allows it."""
    await _document(app, auth_headers, builder)
    recorded = await _record(app, builder)
    await _grant(app, auth_headers, "reviewer")

    decided = await app.post(
        f"{EVIDENCE}/{recorded['id']}/decision",
        json={"decision": "rejected", "reason": "the tests it cites do not cover FR-1"},
        headers=reviewer,
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["review_state"] == "rejected"


@pytest.mark.asyncio
async def test_a_withdrawn_grant_takes_effect(app, auth_headers, builder, reviewer):
    await _document(app, auth_headers, builder)
    first = await _record(app, builder, identifier="FR-1")
    second = await _record(app, builder, identifier="FR-2")
    await _grant(app, auth_headers, "reviewer")
    allowed = await app.post(
        f"{EVIDENCE}/{first['id']}/decision", json={"decision": "accepted"}, headers=reviewer
    )
    assert allowed.status_code == 200, allowed.text

    await _grant(app, auth_headers, "reviewer", enabled=False)
    refused = await app.post(
        f"{EVIDENCE}/{second['id']}/decision", json={"decision": "accepted"}, headers=reviewer
    )
    assert refused.status_code == 403, refused.text


@pytest.mark.asyncio
async def test_an_unknown_decision_is_refused(app, auth_headers, builder, reviewer):
    await _document(app, auth_headers, builder)
    recorded = await _record(app, builder)
    await _grant(app, auth_headers, "reviewer")

    refused = await app.post(
        f"{EVIDENCE}/{recorded['id']}/decision", json={"decision": "accept"}, headers=reviewer
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "unknown_decision"


@pytest.mark.asyncio
async def test_evidence_from_another_project_is_not_found(app, auth_headers, builder, reviewer):
    await _document(app, auth_headers, builder)
    await _grant(app, auth_headers, "reviewer")

    missing = await app.post(
        f"{EVIDENCE}/ev-nonexistent/decision", json={"decision": "accepted"}, headers=reviewer
    )
    assert missing.status_code == 404, missing.text


@pytest.mark.asyncio
async def test_reading_is_scoped_to_the_agents_own_project(app, auth_headers, builder):
    """`actor.project_id` comes from the run credential and is never taken from the request."""
    await _document(app, auth_headers, builder)
    await _record(app, builder)

    listed = await app.get(EVIDENCE, headers=builder)
    assert listed.status_code == 200, listed.text
    assert all(row["actor"] == "builder" for row in listed.json()["evidence"])


@pytest.mark.asyncio
async def test_the_routes_refuse_an_unbound_caller(app, auth_headers, builder):
    await _document(app, auth_headers, builder)

    for response in (
        await app.get(EVIDENCE),
        await app.post(EVIDENCE, json={"identifier": "FR-1"}),
    ):
        assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_agents_drive_a_requirement_from_recorded_to_accepted(
    app, auth_headers, builder, reviewer
):
    """The chain the whole change exists for, with no operator HTTP call in the middle.

    From the run that found this: approving a task reported `skipped: no accepted evidence names a
    commit`, and finishing the loop took a run credential minted into the database and a `curl`.

    **The task must carry requirement links.** `task_integration` joins evidence to a task through
    `TaskRequirementLink`, not through `RequirementEvidence.task_id`, so a task created without
    `requirement_ids` still reports nothing to merge — and a verification that misses this reads as
    "the fix failed" when the fix is fine.
    """
    await _document(app, auth_headers, builder)

    created = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Build the listing", "requirement_ids": ["FR-1"]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert [row["identifier"] for row in created.json()["requirement_links"]] == ["FR-1"]

    # The builder records against the requirement its task is linked to...
    recorded = await app.post(
        EVIDENCE,
        json={"identifier": "FR-1", "summary": "18 tests pass", "task_id": task_id},
        headers=builder,
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["review_state"] == "awaiting"

    # ...the reviewer finds it without being told an id...
    await _grant(app, auth_headers, "reviewer")
    awaiting = await app.get(EVIDENCE, params={"review_state": "awaiting"}, headers=reviewer)
    rows = awaiting.json()["evidence"]
    assert [row["actor"] for row in rows] == ["builder"]

    # ...and accepts it.
    decided = await app.post(
        f"{EVIDENCE}/{rows[0]['id']}/decision",
        json={"decision": "accepted", "reason": "ran the suite against the branch"},
        headers=reviewer,
    )
    assert decided.status_code == 200, decided.text

    coverage = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)
    assert coverage.status_code == 200, coverage.text
    alpha = next(row for row in coverage.json()["requirements"] if row["identifier"] == "FR-1")
    assert alpha["state"] == "verified"
    assert alpha["accepted_count"] == 1
