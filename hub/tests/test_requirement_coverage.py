"""Coverage: one computation, one precedence, and never a state without its integration answer.

The failure this guards against is not a wrong badge. It is *two* badges — a document saying one
thing and a project total saying another, with nothing to say which is right. So one test asserts
there is exactly one implementation, and it is the most important test in this file.
"""

import inspect

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceFootprint, RequirementEvidence, Run, SpecRequirement
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/coverage-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-cov-builder", project_id="proj-test", name="cov-builder"))
        session.add(
            Run(
                id="run-cov",
                project_id="proj-test",
                agent="cov-builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_cov-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_cov-secret"}


async def _document(app, auth_headers, run_headers, requirements=(ALPHA, BETA)):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Coverage demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Coverage demo",
                "requirements": list(requirements),
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def _coverage(app, auth_headers, document=None):
    response = await app.get(
        f"{BASE}/spec/coverage",
        params={"document": document} if document else None,
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _entry(coverage, identifier):
    for entry in coverage["requirements"]:
        if entry["identifier"] == identifier:
            return entry
    raise AssertionError(f"{identifier} not in coverage")


# ---------------------------------------------------------------------------
# The precedence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_requirement_nothing_serves_is_unserved(app, auth_headers, builder, tmp_path):
    """The question the end-to-end run needed and could not ask."""
    await _document(app, auth_headers, builder)

    coverage = await _coverage(app, auth_headers)

    assert _entry(coverage, "FR-1")["state"] == "unserved"
    assert coverage["unserved"] == ["FR-1", "FR-2"]


@pytest.mark.asyncio
async def test_linked_but_unstarted_work_is_not_started(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)

    await app.post(
        TASKS, json={"title": "Build FR-1", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )

    assert _entry(await _coverage(app, auth_headers), "FR-1")["state"] == "not_started"


@pytest.mark.asyncio
async def test_work_under_way_is_in_progress(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build FR-1", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    task_id = created.json()["id"]

    await app.patch(f"{TASKS}/{task_id}", json={"status": "assigned"}, headers=auth_headers)
    await app.patch(f"{TASKS}/{task_id}", json={"status": "in_progress"}, headers=auth_headers)

    assert _entry(await _coverage(app, auth_headers), "FR-1")["state"] == "in_progress"


@pytest.mark.asyncio
async def test_completed_work_without_evidence_is_still_in_progress(
    app, auth_headers, builder, tmp_path
):
    """Coverage asks whether the requirement is demonstrated, and a completed task
    with nothing to show demonstrably has not demonstrated it."""
    await _document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build FR-1", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    task_id = created.json()["id"]
    for next_status in ("assigned", "in_progress", "completed"):
        await app.patch(f"{TASKS}/{task_id}", json={"status": next_status}, headers=auth_headers)

    assert _entry(await _coverage(app, auth_headers), "FR-1")["state"] == "in_progress"


@pytest.mark.asyncio
async def test_awaiting_review_outranks_the_work_that_produced_it(
    app, auth_headers, builder, tmp_path
):
    await _document(app, auth_headers, builder)
    await app.post(
        TASKS, json={"title": "Build FR-1", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )

    await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)

    assert _entry(await _coverage(app, auth_headers), "FR-1")["state"] == (
        "evidence_awaiting_review"
    )


@pytest.mark.asyncio
async def test_stale_outranks_awaiting_review(app, auth_headers, builder, tmp_path):
    """Two adjacent states, resolving in the stated order: evidence exists, none
    of it applies, and a pending review of the old wording does not change that."""
    await _document(app, auth_headers, builder)
    await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)

    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Coverage demo",
                "requirements": [{**ALPHA, "statement": "Something else entirely"}, BETA],
            },
        },
        headers=builder,
    )

    assert _entry(await _coverage(app, auth_headers), "FR-1")["state"] == "stale"


@pytest.mark.asyncio
async def test_drifting_outranks_verified(app, auth_headers, builder, tmp_path):
    from hub import requirement_evidence
    from hub.spec_lifecycle import Actor

    await _document(app, auth_headers, builder)
    recorded = await app.post(
        f"{BASE}/spec/evidence", json={"identifier": "FR-1"}, headers=auth_headers
    )
    assert _entry(await _coverage(app, auth_headers), "FR-1")["state"] == "verified"

    async with async_session_factory() as session:
        evidence = await session.get(RequirementEvidence, recorded.json()["id"])
        requirement = await session.get(SpecRequirement, evidence.requirement_id)
        session.add(
            __import__("hub.db.models", fromlist=["RequirementDrift"]).RequirementDrift(
                id="drift-test",
                project_id="proj-test",
                requirement_id=requirement.id,
                evidence_id=evidence.id,
                state="candidate",
                digest=requirement.digest,
            )
        )
        await session.commit()

    assert _entry(await _coverage(app, auth_headers), "FR-1")["state"] == "drifting"
    del requirement_evidence, Actor


# ---------------------------------------------------------------------------
# Integration, which no surface may omit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_coverage_entry_carries_an_integration_answer(
    app, auth_headers, builder, tmp_path
):
    await _document(app, auth_headers, builder)
    await app.post(f"{BASE}/spec/evidence", json={"identifier": "FR-1"}, headers=auth_headers)

    coverage = await _coverage(app, auth_headers)

    assert coverage["requirements"]
    assert all("integration" in entry for entry in coverage["requirements"])
    assert "integration" in coverage


@pytest.mark.asyncio
async def test_verified_work_that_has_not_landed_says_so(app, auth_headers, builder, tmp_path):
    """`verified` alone would be true of the branch and false of the product."""
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        f"{BASE}/spec/evidence", json={"identifier": "FR-1"}, headers=auth_headers
    )

    async with async_session_factory() as session:
        footprint = (
            (
                await session.execute(
                    select(EvidenceFootprint).where(
                        EvidenceFootprint.evidence_id == recorded.json()["id"]
                    )
                )
            )
            .scalars()
            .first()
        )
        footprint.reachable_from_main = False
        await session.commit()

    entry = _entry(await _coverage(app, auth_headers), "FR-1")
    assert entry["state"] == "verified"
    assert entry["integration"] == "not_integrated"


@pytest.mark.asyncio
async def test_a_project_with_no_main_branch_reports_unknown_not_unintegrated(
    app, auth_headers, builder, tmp_path
):
    """Reporting "not integrated" for a project that simply does not use a main
    branch would be an accusation about a choice."""
    await _document(app, auth_headers, builder)
    recorded = await app.post(
        f"{BASE}/spec/evidence", json={"identifier": "FR-1"}, headers=auth_headers
    )

    async with async_session_factory() as session:
        footprint = (
            (
                await session.execute(
                    select(EvidenceFootprint).where(
                        EvidenceFootprint.evidence_id == recorded.json()["id"]
                    )
                )
            )
            .scalars()
            .first()
        )
        assert footprint is not None
        footprint.reachable_from_main = None
        await session.commit()

    assert _entry(await _coverage(app, auth_headers), "FR-1")["integration"] == "unknown"


# ---------------------------------------------------------------------------
# One computation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_document_and_the_project_agree(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    await app.post(f"{BASE}/spec/evidence", json={"identifier": "FR-1"}, headers=auth_headers)

    whole = await _coverage(app, auth_headers)
    just_this = await _coverage(app, auth_headers, document=PATH)

    assert whole["requirements"] == just_this["requirements"]
    assert whole["totals"] == just_this["totals"]


def test_there_is_exactly_one_implementation_of_the_precedence():
    """A second one is the failure mode this phase exists to prevent. Both
    rollups must call `requirement_coverage`, not restate it."""
    from hub import requirement_coverage

    document_source = inspect.getsource(requirement_coverage.document_coverage)
    project_source = inspect.getsource(requirement_coverage.project_coverage)

    for source in (document_source, project_source):
        assert "requirement_coverage(" in source
        # No rollup may reach the precedence itself.
        assert "_state(" not in source
        assert requirement_coverage.DRIFTING not in source

    # And every state in the precedence is reachable from the one function that decides.
    state_source = inspect.getsource(requirement_coverage._state)
    names = {
        value: name
        for name, value in vars(requirement_coverage).items()
        if isinstance(value, str) and value in requirement_coverage.PRECEDENCE
    }
    for state in requirement_coverage.PRECEDENCE:
        assert names[state] in state_source, f"{state} is unreachable from _state"


def test_the_precedence_is_the_one_the_specification_states():
    from hub import requirement_coverage

    assert requirement_coverage.PRECEDENCE == (
        "drifting",
        "stale",
        "evidence_awaiting_review",
        "verified",
        "in_progress",
        "not_started",
        "unserved",
    )


# ---------------------------------------------------------------------------
# Diagnostics, which are not coverage states
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_broken_requirement_is_a_diagnostic_not_unserved(
    app, auth_headers, builder, tmp_path
):
    """It is not unserved; it is broken, and a gate has to refuse on it separately."""
    await _document(app, auth_headers, builder)

    async with async_session_factory() as session:
        row = (
            (
                await session.execute(
                    select(SpecRequirement).where(SpecRequirement.identifier == "FR-2")
                )
            )
            .scalars()
            .first()
        )
        row.digest = ""
        await session.commit()

    coverage = await _coverage(app, auth_headers)

    assert [entry["identifier"] for entry in coverage["requirements"]] == ["FR-1"]
    assert coverage["diagnostics"][0]["identifier"] == "FR-2"
    assert "digest" in coverage["diagnostics"][0]["problem"]
