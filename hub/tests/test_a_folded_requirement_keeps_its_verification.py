"""F593: a folded requirement keeps the verification it earned; history is not counted twice.

Change `a-folded-requirement-keeps-its-verification`. A capability requirement with no evidence of
its own takes its coverage from the same-digest requirement of a change merged into it, and names
it; the project's rollup leaves archived documents out. The live check is
`scripts/drive/d1015_f593_fold_keeps_verification.py`.
"""

from datetime import datetime, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import (
    RequirementEvidence,
    SpecDocument,
    SpecDocumentMerge,
    SpecRequirement,
)
from hub.requirement_coverage import requirement_coverage

P = "proj-test"
SAME = "a" * 64
REWORDED = "b" * 64
OLD_WORDS = "c" * 64


async def _seed(*, own_evidence: bool = False) -> None:
    now = datetime.now(timezone.utc)
    async with async_session_factory() as session:
        session.add_all(
            [
                SpecDocument(
                    id="doc-cap",
                    project_id=P,
                    path="spec/capabilities/calc/spec.json",
                    title="Calc",
                    phase="current",
                    kind="capability",
                ),
                SpecDocument(
                    id="doc-chg",
                    project_id=P,
                    path="spec/changes/sub/spec.json",
                    title="Sub",
                    phase="archived",
                    kind="change-spec",
                ),
                SpecDocumentMerge(
                    id="merge-1",
                    project_id=P,
                    capability_document_id="doc-cap",
                    change_document_id="doc-chg",
                    actor_kind="operator",
                    actor="operator",
                ),
                SpecRequirement(
                    id="req-chg-1",
                    project_id=P,
                    document_id="doc-chg",
                    identifier="FR-1",
                    key="subtract",
                    digest=SAME,
                ),
                SpecRequirement(
                    id="req-chg-2",
                    project_id=P,
                    document_id="doc-chg",
                    identifier="FR-2",
                    key="help",
                    digest=OLD_WORDS,
                ),
                SpecRequirement(
                    id="req-cap-4",
                    project_id=P,
                    document_id="doc-cap",
                    identifier="FR-4",
                    key="sub-subtract",
                    digest=SAME,
                ),
                SpecRequirement(
                    id="req-cap-5",
                    project_id=P,
                    document_id="doc-cap",
                    identifier="FR-5",
                    key="sub-help",
                    digest=REWORDED,
                ),
            ]
        )
        for req, digest in (("req-chg-1", SAME), ("req-chg-2", OLD_WORDS)):
            session.add(
                RequirementEvidence(
                    id=f"ev-{req}",
                    project_id=P,
                    requirement_id=req,
                    digest=digest,
                    kind="manual_observation",
                    actor_kind="operator",
                    actor="operator",
                    summary="seen",
                    produced_at=now,
                    review_state="accepted",
                )
            )
        if own_evidence:
            session.add(
                RequirementEvidence(
                    id="ev-cap-own",
                    project_id=P,
                    requirement_id="req-cap-4",
                    digest=SAME,
                    kind="manual_observation",
                    actor_kind="operator",
                    actor="operator",
                    summary="re-checked",
                    produced_at=now,
                    review_state="awaiting",
                )
            )
        await session.commit()


def _by_identifier(report, document_id):
    return {r.identifier: r for r in report.requirements if r.document_id == document_id}


@pytest.mark.asyncio
async def test_an_unchanged_folded_requirement_is_served_by_the_change_and_names_it(app):
    await _seed()
    async with async_session_factory() as session:
        report = await requirement_coverage(session, P)
    capability = _by_identifier(report, "doc-cap")
    assert capability["FR-4"].state == "verified"
    assert capability["FR-4"].served_by == {
        "requirement_id": "req-chg-1",
        "identifier": "FR-1",
        "document_id": "doc-chg",
        # So the app can say which change serves it and read that change's evidence (F593).
        "document_path": "spec/changes/sub/spec.json",
    }
    assert capability["FR-4"].to_dict()["served_by"]["identifier"] == "FR-1"


@pytest.mark.asyncio
async def test_a_reworded_folded_requirement_inherits_nothing(app):
    await _seed()
    async with async_session_factory() as session:
        report = await requirement_coverage(session, P)
    capability = _by_identifier(report, "doc-cap")
    assert capability["FR-5"].state == "unserved"
    assert capability["FR-5"].served_by is None


@pytest.mark.asyncio
async def test_a_requirement_with_its_own_evidence_keeps_its_own(app):
    await _seed(own_evidence=True)
    async with async_session_factory() as session:
        report = await requirement_coverage(session, P)
    capability = _by_identifier(report, "doc-cap")
    assert capability["FR-4"].state == "evidence_awaiting_review"
    assert capability["FR-4"].served_by is None


@pytest.mark.asyncio
async def test_the_project_rollup_leaves_archived_documents_out_and_the_document_keeps_them(app):
    await _seed()
    async with async_session_factory() as session:
        project = await requirement_coverage(session, P)
        history = await requirement_coverage(session, P, document_id="doc-chg")
    assert not any(r.document_id == "doc-chg" for r in project.requirements)
    assert project.totals["verified"] == 1
    assert {r.identifier for r in history.requirements} == {"FR-1", "FR-2"}


async def _drift_on_the_change() -> None:
    from hub.db.models import RequirementDrift

    async with async_session_factory() as session:
        session.add(
            RequirementDrift(
                id="drift-folded",
                project_id=P,
                requirement_id="req-chg-1",
                evidence_id="ev-req-chg-1",
                state="candidate",
                observed={"src/core.py": {"was": "aaaaaaa", "now": "bbbbbbb"}},
                digest=SAME,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_drift_on_the_serving_change_reaches_the_capability(app, auth_headers):
    """F690: verification was carried across the fold, drift was not. The capability's FR-4 read
    verified with "nothing to answer" while the archived change held the open candidate."""
    await _seed()
    await _drift_on_the_change()

    async with async_session_factory() as session:
        capability = _by_identifier(
            await requirement_coverage(session, P, document_id="doc-cap"), "doc-cap"
        )
    assert capability["FR-4"].state == "drifting"
    # A requirement the drifting evidence does not serve is untouched.
    assert capability["FR-5"].state == "unserved"

    response = await app.get(
        "/api/v1/projects/proj-test/project/spec/drift",
        params={"document": "spec/capabilities/calc/spec.json", "state": "candidate"},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    [row] = response.json()["drift"]
    assert row["id"] == "drift-folded"
    assert row["requirement"]["identifier"] == "FR-1"
    assert row["serves"] == {"identifier": "FR-4", "document": "spec/capabilities/calc/spec.json"}

    on_the_change = await app.get(
        "/api/v1/projects/proj-test/project/spec/drift",
        params={"document": "spec/changes/sub/spec.json"},
        headers=auth_headers,
    )
    [own] = on_the_change.json()["drift"]
    assert own["id"] == "drift-folded" and own["serves"] is None
