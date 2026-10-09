"""Approve lists what is missing and can approve anyway (approval-warnings slice, task 3).

The routes over the classification `test_approval_gaps.py` covers. Change:
spec/changes/approve-lists-what-is-missing-and-can-approve-anyway (spdoc-9a9d313a4894); the
acceptance drive is `scripts/drive/d1012_approval_warnings.py`.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent

from .test_project_spec_steps import THREAT, _steps, _write
from .test_spec_documents_api import (  # noqa: F401  (run_headers is a fixture)
    BASE,
    PATH,
    _create,
    _document,
    _submit,
    run_headers,
)
from .test_spec_journey_briefing import _place


def _checked(**overrides):
    """A document with no gap: its criterion carries a check and a checker."""
    criterion = {
        "key": "c1",
        "requirement": "alpha",
        "given": "g",
        "when": "w",
        "then": "t",
        "how_to_check": "a test",
        "checked_by": "agent",
    }
    return _document(acceptance_criteria=[criterion], **overrides)


async def _propose(app, auth_headers):
    return await app.post(f"{BASE}/documents/propose", params={"path": PATH}, headers=auth_headers)


async def _phase(app, auth_headers, to, **body):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": to},
        json={"reason": "", **body},
        headers=auth_headers,
    )


async def _phase_of():
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument.phase).where(SpecDocument.path == PATH))
        ).scalar_one()


async def _approval_events():
    async with async_session_factory() as session:
        rows = await session.execute(
            select(SpecDocumentEvent.detail).where(SpecDocumentEvent.kind == "phase")
        )
        return [d for d in rows.scalars() if d.get("to") == "approved"]


async def _listed(app, auth_headers):
    response = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert response.status_code == 200, response.text
    return next(d for d in response.json()["documents"] if d["path"] == PATH)


async def _proposed_with_a_gap(app, auth_headers, run_headers):  # noqa: F811
    """A proposed document whose criterion has no check, so approval has one gap to list."""
    await _create(app, auth_headers)
    await _submit(app, run_headers, _document())
    await _place(step="delivery", size="large")
    proposed = await _propose(app, auth_headers)
    assert proposed.json()["proposed"] is True, proposed.text
    return proposed.json()


# propose-lists
@pytest.mark.asyncio
async def test_propose_passes_a_gap_and_lists_it_under_warnings(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    body = await _proposed_with_a_gap(app, auth_headers, run_headers)

    assert body["phase"] == "proposed"
    assert body["blocking"] == []
    assert [w["code"] for w in body["warnings"]] == ["criterion_without_check"]


@pytest.mark.asyncio
async def test_propose_still_holds_a_refusal_and_lists_the_gaps_beside_it(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    cycle = [
        {"key": "a", "description": "a", "requirements": ["alpha"], "depends_on": ["b"]},
        {"key": "b", "description": "b", "requirements": ["alpha"], "depends_on": ["a"]},
    ]
    await _submit(app, run_headers, _document(tasks=cycle))

    body = (await _propose(app, auth_headers)).json()

    assert body["proposed"] is False and body["phase"] == "exploring"
    assert "dependency_cycle" in {b["code"] for b in body["blocking"]}
    assert "criterion_without_check" in {w["code"] for w in body["warnings"]}


# clean-and-reopen, anyway-400, refusal-holds
@pytest.mark.asyncio
async def test_approve_lists_the_gaps_and_stays_proposed_until_approve_anyway(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _proposed_with_a_gap(app, auth_headers, run_headers)

    refused = await _phase(app, auth_headers, "approved")

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "approval_warnings"
    assert [w["code"] for w in detail["warnings"]] == ["criterion_without_check"]
    assert "blocking" not in detail
    assert await _phase_of() == "proposed"
    assert await _approval_events() == []

    approved = await _phase(app, auth_headers, "approved", approve_anyway=True)

    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"
    assert len(approved.json()["tasks_created"]) == 1
    events = await _approval_events()
    assert [[w["code"] for w in e["warnings_overridden"]] for e in events] == [
        ["criterion_without_check"]
    ]
    listed = await _listed(app, auth_headers)
    assert [w["code"] for w in listed["approval_warnings_overridden"]] == [
        "criterion_without_check"
    ]


@pytest.mark.asyncio
async def test_a_clean_approval_records_that_it_overrode_nothing_and_a_reopen_forgets(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _checked())
    await _place(step="delivery", size="large")
    assert (await _propose(app, auth_headers)).json()["warnings"] == []

    approved = await _phase(app, auth_headers, "approved")

    assert approved.status_code == 200, approved.text
    assert [e["warnings_overridden"] for e in await _approval_events()] == [[]]
    assert (await _listed(app, auth_headers))["approval_warnings_overridden"] == []

    reopened = await _phase(app, auth_headers, "exploring")
    assert reopened.status_code == 200, reopened.text
    assert "approval_warnings_overridden" not in await _listed(app, auth_headers)


@pytest.mark.asyncio
async def test_approve_anyway_with_no_gap_still_records_an_empty_list(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    await _submit(app, run_headers, _checked())
    await _place(step="delivery", size="large")
    await _propose(app, auth_headers)

    approved = await _phase(app, auth_headers, "approved", approve_anyway=True)

    assert approved.status_code == 200, approved.text
    assert [e["warnings_overridden"] for e in await _approval_events()] == [[]]


@pytest.mark.asyncio
@pytest.mark.parametrize("to", ["proposed", "exploring", "archived"])
async def test_approve_anyway_on_any_other_move_is_a_400_before_anything_moves(
    app, auth_headers, run_headers, to, tmp_path  # noqa: F811
):
    await _proposed_with_a_gap(app, auth_headers, run_headers)

    response = await _phase(app, auth_headers, to, approve_anyway=True)

    assert response.status_code == 400, response.text
    assert "approve_anyway" in response.text
    assert await _phase_of() == "proposed"


@pytest.mark.asyncio
async def test_a_refusal_holds_against_approve_anyway(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _proposed_with_a_gap(app, auth_headers, run_headers)
    cycle = [
        {"key": "a", "description": "a", "requirements": ["alpha"], "depends_on": ["b"]},
        {"key": "b", "description": "b", "requirements": ["alpha"], "depends_on": ["a"]},
    ]
    assert (await _submit(app, run_headers, _document(tasks=cycle))).status_code == 200

    response = await _phase(app, auth_headers, "approved", approve_anyway=True)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "document_incomplete"
    assert "dependency_cycle" in {b["code"] for b in detail["blocking"]}
    assert await _phase_of() == "proposed"
    assert await _approval_events() == []


@pytest.mark.asyncio
async def test_skipped_journey_steps_are_listed_at_approval(
    app, auth_headers, run_headers, tmp_path  # noqa: F811
):
    await _create(app, auth_headers)
    _write(tmp_path, _steps(THREAT))
    await _submit(app, run_headers, _checked())
    await _place(step="requirements", size="large")
    await _propose(app, auth_headers)

    refused = await _phase(app, auth_headers, "approved")

    assert refused.status_code == 409, refused.text
    warnings = refused.json()["detail"]["warnings"]
    assert [w["code"] for w in warnings] == ["steps_skipped"]
    assert "threat-model" in warnings[0]["message"]
