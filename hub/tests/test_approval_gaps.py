"""Approve lists what is missing (approval-warnings slice, task 2): gaps and refusals.

Proposal and approval find two kinds of thing. A refusal makes approval's own work wrong and nothing
passes it; a gap describes completeness, and the operator may approve over it. This file covers the
classification and the three new gaps; the routes that act on it are task 3. Change:
spec/changes/approve-lists-what-is-missing-and-can-approve-anyway (spdoc-9a9d313a4894). The
acceptance drive is `scripts/drive/d1012_approval_warnings.py`.
"""

import pytest
from sqlalchemy import select

from hub import project_workspace, spec_completeness, spec_service
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument
from hub.spec_completeness import approval_gaps, check, split
from hub.spec_payload import SCHEMA_VERSION, validate_payload

from .test_project_spec_steps import THREAT, _steps, _write
from .test_spec_documents_api import PATH, _create
from .test_spec_journey_briefing import _place


def _payload(**overrides):
    base = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "A change",
        "requirements": [{"key": "alpha", "statement": "It responds in 200ms", "modal": "MUST"}],
        "acceptance_criteria": [
            {
                "key": "c1",
                "requirement": "alpha",
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "a test",
                "checked_by": "agent",
            }
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "delivery": {"mode": "none"},
    }
    base.update(overrides)
    return validate_payload(base)


def _task(key, depends_on=()):
    return {
        "key": key,
        "description": key,
        "requirements": ["alpha"],
        "depends_on": list(depends_on),
    }


def _gaps(payload):
    return [*check(payload), *approval_gaps(payload)]


def test_a_complete_document_has_no_gap():
    assert _gaps(_payload()) == []


# should-not-gap (FR-2)
@pytest.mark.parametrize("modal", ["SHOULD", "MAY"])
def test_a_should_or_may_requirement_with_no_criterion_is_not_a_gap(modal):
    payload = _payload(
        requirements=[
            {"key": "alpha", "statement": "It responds in 200ms", "modal": "MUST"},
            {"key": "beta", "statement": "It logs the reply", "modal": modal},
        ],
        tasks=[{"key": "t1", "description": "Build it", "requirements": ["alpha", "beta"]}],
    )
    assert "requirement_without_criterion" not in {f.code for f in _gaps(payload)}


@pytest.mark.parametrize("modal", ["MUST", "SHALL"])
def test_a_must_or_shall_requirement_with_no_criterion_is_a_gap(modal):
    payload = _payload(
        requirements=[{"key": "alpha", "statement": "It responds in 200ms", "modal": modal}],
        acceptance_criteria=[],
    )
    found = [f for f in _gaps(payload) if f.code == "requirement_without_criterion"]
    assert [(f.where, "alpha" in f.message) for f in found] == [("requirements[0]", True)]


# criterion-check (FR-2)
def test_a_criterion_without_its_check_or_its_checker_is_a_gap_naming_it():
    criterion = {"requirement": "alpha", "given": "g", "when": "w", "then": "t"}
    payload = _payload(
        acceptance_criteria=[
            {**criterion, "key": "how-only", "how_to_check": "a test"},
            {**criterion, "key": "neither"},
            {**criterion, "key": "both", "how_to_check": "a test", "checked_by": "operator"},
        ]
    )
    found = [f for f in approval_gaps(payload) if f.code == "criterion_without_check"]
    assert [f.where for f in found] == ["acceptance_criteria[0]", "acceptance_criteria[1]"]
    assert "'how-only'" in found[0].message and "checked_by" in found[0].message
    assert "how_to_check" not in found[0].message
    assert "'neither'" in found[1].message
    assert "how_to_check" in found[1].message and "checked_by" in found[1].message


# drive-first (FR-2, D3). The change's criterion lists "build then drive (drive depends on build)"
# as the gap, but that shape is structurally the drive-first one with the keys swapped, and D3
# rejected reading names; the gap shapes FR-2 names are tested instead (F562).
def test_only_a_change_whose_first_task_is_not_the_drive_lacks_an_acceptance_drive():
    first_waits = _payload(tasks=[_task("drive", ["build"]), _task("build")])
    first_not_awaited = _payload(tasks=[_task("drive"), _task("build")])
    drive_then_build = _payload(tasks=[_task("drive"), _task("build", ["drive"])])
    single = _payload(tasks=[_task("only")])

    def codes(payload):
        return [f.code for f in approval_gaps(payload)]

    assert codes(first_waits) == ["no_acceptance_drive"]
    assert codes(first_not_awaited) == ["no_acceptance_drive"]
    assert codes(drive_then_build) == []
    assert codes(single) == []


def test_a_task_waiting_on_the_drive_through_another_task_still_counts():
    chained = _payload(tasks=[_task("drive"), _task("build", ["drive"]), _task("page", ["build"])])
    loose = _payload(tasks=[_task("drive"), _task("build", ["drive"]), _task("page")])
    assert [f.code for f in approval_gaps(chained)] == []
    assert [(f.code, f.where) for f in approval_gaps(loose)] == [
        ("no_acceptance_drive", "tasks[0]")
    ]


# refusals-stay (FR-3, D2)
def test_what_makes_approval_wrong_is_a_refusal_and_completeness_is_a_gap():
    payload = _payload(
        tasks=[
            {**_task("a", ["b"]), "estimate": "2d"},
            _task("b", ["a"]),
            _task("c", ["ghost"]),
        ],
        open_questions=[{"question": "Which port?", "resolved": False}],
        scope={"in_scope": ["x"], "non_goals": []},
    )
    refusals, gaps = split(check(payload))
    assert {f.code for f in refusals} == {
        "dependency_cycle",
        "depends_on_unresolved",
        "unknown_field",
    }
    assert {"unresolved_question", "non_goals_empty"} <= {f.code for f in gaps}
    assert not {f.code for f in gaps} & spec_completeness.REFUSAL_CODES


# skipped (FR-2), at the service seam: the route that answers with it is task 3
async def _findings(to_phase="approved"):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        workspace = await project_workspace.resolve_project_workspace(session, document.project_id)
        return await spec_service.phase_findings(session, workspace, document, to_phase)


@pytest.mark.asyncio
async def test_the_journey_steps_a_document_never_reached_are_a_gap_naming_them(
    app, auth_headers, tmp_path
):
    await _create(app, auth_headers)
    _write(tmp_path, _steps(THREAT))
    await _place(step="requirements", size="large")

    at_requirements = await _findings()
    skipped = [g for g in at_requirements.gaps if g["code"] == "steps_skipped"]
    assert len(skipped) == 1, at_requirements
    message = skipped[0]["message"]
    for step in ("threat-model", "acceptance", "approach", "tasks", "delivery"):
        assert step in message
    assert message.index("threat-model") < message.index("acceptance")
    assert not any(r["code"] == "steps_skipped" for r in at_requirements.refusals)

    await _place(step="delivery", size="large")
    assert "steps_skipped" not in {g["code"] for g in (await _findings()).gaps}


@pytest.mark.asyncio
async def test_a_document_with_no_step_has_no_skipped_steps(app, auth_headers, tmp_path):
    await _create(app, auth_headers)
    await _place(step=None, size=None)
    assert "steps_skipped" not in {g["code"] for g in (await _findings("proposed")).gaps}
