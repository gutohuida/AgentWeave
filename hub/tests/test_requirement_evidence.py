"""Evidence, who may accept it, and what stops it outliving the thing it demonstrated.

The rule under test is not "agents cannot verify". It is that **producing evidence is open and
accepting it is controlled** — the artifact is a fact, the claim about what it proves is not. So the
interesting assertions are the refusals: an agent accepting its own work, an agent nobody granted
anything, and evidence that quietly survives a rewording of the requirement it was accepted against.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, RequirementEvidence, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/evidence-demo/spec.html"

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
    return await _run("builder", "run-builder", "aw_run_builder-secret")


@pytest.fixture
async def verifier():
    return await _run("verifier", "run-verifier", "aw_run_verifier-secret")


async def _grant(agent: str):
    async with async_session_factory() as session:
        row = (
            (
                await session.execute(
                    select(Agent).where(Agent.project_id == "proj-test", Agent.name == agent)
                )
            )
            .scalars()
            .first()
        )
        row.can_accept_evidence = True
        await session.commit()


async def _document(app, auth_headers, run_headers, requirements=(ALPHA, BETA), path=PATH):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Evidence demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": path,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Evidence demo",
                "requirements": list(requirements),
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def _coverage(app, auth_headers, document=None):
    params = {"document": document} if document else None
    response = await app.get(f"{BASE}/spec/coverage", params=params, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


def _state(coverage, identifier):
    for entry in coverage["requirements"]:
        if entry["identifier"] == identifier:
            return entry["state"]
    raise AssertionError(f"{identifier} not in coverage")


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_evidence_awaits_review(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)

    response = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "99 tests pass"},
        headers=builder,
    )

    assert response.status_code == 201, response.text
    assert response.json()["review_state"] == "awaiting"
    assert _state(await _coverage(app, auth_headers), "FR-1") == "evidence_awaiting_review"


@pytest.mark.asyncio
async def test_evidence_carries_its_actor_run_and_digest(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)

    await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )

    async with async_session_factory() as session:
        row = (await session.execute(select(RequirementEvidence))).scalars().first()
    assert row.actor_kind == "agent"
    assert row.actor == "builder"
    assert row.run_id == "run-builder"
    assert row.digest


@pytest.mark.asyncio
async def test_an_agent_cannot_name_another_actor(app, auth_headers, builder, tmp_path):
    """Identity is the run credential's, never a value the request supplies."""
    await _document(app, auth_headers, builder)

    response = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "summary": "ran it", "actor": "operator"},
        headers=builder,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_operator_evidence_is_accepted_on_arrival(app, auth_headers, builder, tmp_path):
    """There is nobody else for it to await."""
    await _document(app, auth_headers, builder)

    response = await app.post(
        f"{BASE}/spec/evidence",
        json={"identifier": "FR-1", "kind": "manual_observation", "summary": "I watched it"},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
    assert response.json()["review_state"] == "accepted"
    assert _state(await _coverage(app, auth_headers), "FR-1") == "verified"


# ---------------------------------------------------------------------------
# Who may accept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_ungranted_agent_cannot_accept(app, auth_headers, builder, verifier, tmp_path):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )

    response = await app.post(
        f"{AGENT_EVIDENCE}/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=verifier,
    )

    assert response.status_code == 403
    assert "granted" in response.text


@pytest.mark.asyncio
async def test_a_granted_agent_may_accept_another_agents_evidence(
    app, auth_headers, builder, verifier, tmp_path
):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )
    await _grant("verifier")

    response = await app.post(
        f"{AGENT_EVIDENCE}/{recorded.json()['id']}/decision",
        json={"decision": "accepted", "reason": "I reran it"},
        headers=verifier,
    )

    assert response.status_code == 200, response.text
    assert response.json()["review_state"] == "accepted"
    assert _state(await _coverage(app, auth_headers), "FR-1") == "verified"


@pytest.mark.asyncio
async def test_an_agent_cannot_accept_its_own_evidence(app, auth_headers, builder, tmp_path):
    """Distinctness is on agent identity, not run identity: every turn an agent
    takes is a new run, so a run-based check is satisfied by an agent simply
    continuing its own work."""
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )
    await _grant("builder")

    response = await app.post(
        f"{AGENT_EVIDENCE}/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=builder,
    )

    assert response.status_code == 403
    assert "cannot accept evidence it produced" in response.text


@pytest.mark.asyncio
async def test_a_misspelled_decision_names_what_would_have_worked(
    app, auth_headers, builder, tmp_path
):
    """Measured live: `{"decision": "accept"}` answered `403 unknown decision 'accept'`, minutes
    after the trigger route refused a bad `permission_mode` by listing all four permitted values
    (`scripts/drive/FINDINGS.md`, F8).

    Two things were wrong. The message named nothing the caller could act on, which is the retry
    loop `spec_payload` exists to prevent; and 403 is an authorisation answer to a validation
    problem, so an agent reading the status code rather than the body concludes it lacks permission
    and stops trying.
    """
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )

    response = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accept"},
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "unknown_decision"
    assert "accepted" in detail["message"] and "rejected" in detail["message"]


@pytest.mark.asyncio
async def test_the_capability_refusals_are_still_403(app, auth_headers, builder, tmp_path):
    """The status override is per refusal, so widening it must not have flattened the two that
    genuinely are about authority."""
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )
    await _grant("builder")

    response = await app.post(
        f"{AGENT_EVIDENCE}/{recorded.json()['id']}/decision",
        json={"decision": "rejected"},
        headers=builder,
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "self_acceptance"


@pytest.mark.asyncio
async def test_with_no_granted_agent_the_operator_still_decides(
    app, auth_headers, builder, tmp_path
):
    """A supported way to work, not a degraded one — the operator knowingly takes
    the bottleneck."""
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )

    response = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert _state(await _coverage(app, auth_headers), "FR-1") == "verified"


@pytest.mark.asyncio
async def test_decisions_append_and_never_overwrite(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )
    evidence_id = recorded.json()["id"]

    await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "rejected", "reason": "the test was wrong"},
        headers=auth_headers,
    )
    await app.post(
        f"{BASE}/spec/evidence/{evidence_id}/decision",
        json={"decision": "accepted", "reason": "fixed and reran"},
        headers=auth_headers,
    )

    reviews = await app.get(f"{BASE}/spec/evidence/{evidence_id}/reviews", headers=auth_headers)
    assert [entry["decision"] for entry in reviews.json()["reviews"]] == ["rejected", "accepted"]


# ---------------------------------------------------------------------------
# Staleness — the whole reason for the digest pin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_goes_stale_when_the_requirement_is_reworded(
    app, auth_headers, builder, tmp_path
):
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran it"}, headers=builder
    )
    await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert _state(await _coverage(app, auth_headers), "FR-1") == "verified"

    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Evidence demo",
                "requirements": [
                    {**ALPHA, "statement": "It lists what is due this week"},
                    BETA,
                ],
            },
        },
        headers=builder,
    )

    assert _state(await _coverage(app, auth_headers), "FR-1") == "stale"


@pytest.mark.asyncio
async def test_evidence_for_a_retired_requirement_is_refused(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Evidence demo",
                "requirements": [ALPHA],
            },
        },
        headers=builder,
    )

    response = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-2", "summary": "ran it"}, headers=builder
    )

    assert response.status_code == 409
    assert "retired" in response.text


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_removed_artifact_leaves_its_record(app, auth_headers, builder, tmp_path):
    """That something was verified, by whom, and against which digest is the
    record. The artifact is its attachment."""
    from hub import requirement_evidence

    await _document(app, auth_headers, builder)
    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "locator": "evidence/FR-1/run.txt", "summary": "ran it"},
        headers=builder,
    )

    async with async_session_factory() as session:
        row = await session.get(RequirementEvidence, recorded.json()["id"])
        await requirement_evidence.mark_artifact_removed(session, row)
        await session.commit()

    listed = await app.get(f"{BASE}/spec/evidence", headers=auth_headers)
    entry = listed.json()["evidence"][0]
    assert entry["artifact_removed"] is True
    assert entry["locator"] == "evidence/FR-1/run.txt"


@pytest.mark.asyncio
async def test_retention_policy_is_the_projects_and_never_is_a_choice(app, auth_headers, tmp_path):
    response = await app.put(
        f"{BASE}/spec/evidence-retention", json={"policy": "never"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["policy"] == "never"

    refused = await app.put(
        f"{BASE}/spec/evidence-retention", json={"policy": "whenever"}, headers=auth_headers
    )
    assert refused.status_code == 422
