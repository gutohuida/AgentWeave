"""`a-change-is-reconciled-with-its-code-before-it-is-folded` (reconcile-and-measure, spdoc-61efd5e5f6a4).

An agent records a reconcile result for an approved change, which the fold state carries; the
operator asks an agent to reconcile; a change's defects are derived from what the Hub records, each
with the step that caught it, and the project reports them per change.
"""

from unittest.mock import AsyncMock

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Task

from .test_spec_documents_api import PATH
from .test_tester_amendments import AMEND, BASE, CANNOT, _approved, _run

RECONCILE = "/api/v1/agent-actions/spec/documents/reconcile"


@pytest.fixture
async def author_headers():
    """The run that writes the document before approval."""
    return await _run("run-author", "scribe")


def _gap(kind, requirement="alpha", where="app.py", summary="it does not"):
    gap = {"class": kind, "where": where, "summary": summary}
    if requirement:
        gap["requirement"] = requirement
    return gap


async def _spec(app, auth_headers):
    response = await app.get(f"{BASE}/spec?path={PATH}", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Recording a reconcile result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reconcile_result_is_checked_and_recorded_with_its_run(
    app, auth_headers, author_headers
):
    await _approved(app, auth_headers, author_headers)
    rex = await _run("run-rex", "rex")

    unknown = await app.post(
        RECONCILE, json={"path": PATH, "summary": "s", "gaps": [_gap("vague")]}, headers=rex
    )
    nameless = await app.post(
        RECONCILE,
        json={"path": PATH, "summary": "s", "gaps": [_gap("missing", requirement=None)]},
        headers=rex,
    )
    empty = await app.post(
        RECONCILE, json={"path": PATH, "summary": "nothing found", "gaps": []}, headers=rex
    )

    assert unknown.status_code == 422 and unknown.json()["detail"]["field"] == "gaps[0].class"
    assert (
        nameless.status_code == 422 and nameless.json()["detail"]["field"] == "gaps[0].requirement"
    )
    assert empty.status_code == 201, empty.text
    assert (empty.json()["author"], empty.json()["run_id"]) == ("rex", "run-rex")
    assert empty.json()["counts"] == {
        "missing": 0,
        "partial": 0,
        "contradicts": 0,
        "unrequested": 0,
    }


@pytest.mark.asyncio
async def test_an_exploring_change_is_not_reconciled(app, auth_headers, author_headers):
    await _approved(app, auth_headers, author_headers)
    await app.post(
        f"{BASE}/documents/phase?path={PATH}&to=exploring",
        json={"reason": "t"},
        headers=auth_headers,
    )
    rex = await _run("run-rex", "rex")

    response = await app.post(
        RECONCILE, json={"path": PATH, "summary": "s", "gaps": []}, headers=rex
    )

    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_the_fold_state_carries_the_latest_result_and_fold_is_not_refused(
    app, auth_headers, author_headers
):
    await _approved(app, auth_headers, author_headers)
    assert (await _spec(app, auth_headers))["fold_state"]["reconcile"] == {"state": "none"}
    rex = await _run("run-rex", "rex")
    await app.post(
        RECONCILE, json={"path": PATH, "summary": "first", "gaps": [_gap("partial")]}, headers=rex
    )
    await app.post(
        RECONCILE,
        json={
            "path": PATH,
            "summary": "second",
            "gaps": [
                _gap("missing", requirement="FR-1"),
                _gap("unrequested", requirement=None, where="/debug"),
            ],
        },
        headers=rex,
    )

    result = (await _spec(app, auth_headers))["fold_state"]["reconcile"]

    assert result["state"] == "recorded" and result["summary"] == "second"
    assert result["counts"] == {"missing": 1, "partial": 0, "contradicts": 0, "unrequested": 1}
    assert result["gaps"][0]["requirement"] == "alpha", "an FR identifier is stored as its key"


@pytest.mark.asyncio
async def test_asking_an_agent_to_reconcile_starts_its_turn_with_the_brief(
    app, auth_headers, author_headers, monkeypatch
):
    from hub.api.v1 import agent_trigger

    await _approved(app, auth_headers, author_headers)
    started = AsyncMock(
        return_value={
            "success": True,
            "message": "queued",
            "agent": "rex",
            "status": "queued",
            "conversation_id": "conv-1",
        }
    )
    monkeypatch.setattr(agent_trigger, "trigger_agent", started)

    response = await app.post(
        f"{BASE}/documents/{PATH}/reconcile", json={"agent": "rex"}, headers=auth_headers
    )

    assert response.status_code == 202, response.text
    request = started.await_args.args[0]
    assert request.agent == "rex" and request.spec_document == PATH
    for word in (PATH, "missing", "partial", "contradicts", "unrequested", "record_reconcile"):
        assert word in request.message


# ---------------------------------------------------------------------------
# Defects by step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_change_s_defects_are_derived_each_with_the_step_that_caught_it(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)
    added = await app.post(
        AMEND,
        json={
            "path": PATH,
            "op": "add_task",
            "task": {"key": "fix", "title": "Fix it", "requirements": ["alpha"]},
            "reason": "drove it: 900ms",
            "how_to_check": "time curl",
        },
        headers=tester,
    )
    assert added.status_code == 201, added.text
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        task.status, task.assignee = "in_progress", "dev"
        await db.commit()
    builder = await _run("run-builder", "dev", task_id=task_id)
    blocked = await app.post(
        CANNOT, json={"path": PATH, "criterion": "c1", "reason": "disk"}, headers=builder
    )
    assert blocked.status_code == 201, blocked.text
    for status in ("in_progress", "completed", "under_review", "revision_needed"):
        moved = await app.patch(
            f"/api/v1/projects/proj-test/tasks/{task_id}",
            json={"status": status},
            headers=auth_headers,
        )
        assert moved.status_code == 200, (status, moved.text)
    rex = await _run("run-rex", "rex")
    await app.post(
        RECONCILE,
        json={
            "path": PATH,
            "summary": "s",
            "gaps": [_gap("missing"), _gap("unrequested", requirement=None)],
        },
        headers=rex,
    )

    report = await app.get(f"{BASE}/spec/defects", headers=auth_headers)

    assert report.status_code == 200, report.text
    (change,) = report.json()["changes"]
    assert change["path"] == PATH
    assert change["by_step"] == {"test": 1, "build": 1, "review": 1, "reconcile": 1}


@pytest.mark.asyncio
async def test_the_operator_records_a_defect_at_a_step(app, auth_headers, author_headers):
    await _approved(app, auth_headers, author_headers)

    later = await app.post(
        f"{BASE}/documents/{PATH}/defects",
        json={"summary": "500 in production", "caught_by": "after-fold"},
        headers=auth_headers,
    )
    unknown = await app.post(
        f"{BASE}/documents/{PATH}/defects",
        json={"summary": "x", "caught_by": "astrology"},
        headers=auth_headers,
    )
    report = await app.get(f"{BASE}/spec/defects", headers=auth_headers)

    assert later.status_code == 201, later.text
    assert unknown.status_code == 422 and unknown.json()["detail"]["field"] == "caught_by"
    (change,) = report.json()["changes"]
    assert change["by_step"] == {"after-fold": 1}
    assert change["defects"][0]["summary"] == "500 in production"


@pytest.mark.asyncio
async def test_a_journey_step_is_a_step_a_defect_can_be_caught_at(
    app, auth_headers, author_headers
):
    await _approved(app, auth_headers, author_headers)

    response = await app.post(
        f"{BASE}/documents/{PATH}/defects",
        json={"summary": "the criterion was untestable", "caught_by": "acceptance"},
        headers=auth_headers,
    )

    assert response.status_code == 201, response.text
