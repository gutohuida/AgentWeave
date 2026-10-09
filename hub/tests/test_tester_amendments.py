"""`a-tester-drives-the-built-product-and-keeps-the-spec-true` (tester-amends slice, spdoc-622cf1b3b011).

A run testing a task of an approved document amends it; the builder cannot; every amendment is
recorded with its author and run and stays not reviewed until the operator marks it; an added task
joins the live flow; a change or removal of a criterion holds its requirement back from verified.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub import requirement_coverage
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, InboundQueueEntry, Loop, Run, SpecDocument, Task
from hub.spec_documents import parse_stored

from .test_spec_documents_api import PATH, _document
from .test_spec_documents_api import _submit as _submit_document

BASE = "/api/v1/projects/proj-test/project"
AMEND = "/api/v1/agent-actions/spec/documents/amend"
CANNOT = "/api/v1/agent-actions/spec/documents/cannot-satisfy"
FLOW = {"mode": "flow", "agent": "dev", "tester": "tess", "stop_when_queue_empties": True}


@pytest.fixture
async def author_headers():
    """The run that writes the document before approval (a spec turn, bound to nothing)."""
    return await _run("run-author", "scribe")


async def _run(run_id, agent, *, task_id=None, reviews=None):
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                task_id=task_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        if reviews:
            db.add(
                InboundQueueEntry(
                    id=f"entry-{run_id}",
                    project_id="proj-test",
                    agent=agent,
                    origin_type="operator",
                    content="test the task",
                    hop_depth=0,
                    state="delivered",
                    review_task_id=reviews,
                    delivered_in_run_id=run_id,
                )
            )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _agents(*names):
    async with async_session_factory() as db:
        for name in names:
            db.add(Agent(id=f"agt-{name}", project_id="proj-test", name=name, lifecycle="open"))
        await db.commit()


async def _approved(app, auth_headers, author_headers, **overrides):
    """An approved flow document with one task; returns that task's id."""
    await _agents("dev", "tess")
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    document = _document(**{"delivery": FLOW, **overrides})
    written = await _submit_document(app, author_headers, document)
    assert written.status_code == 200, written.text
    async with async_session_factory() as db:
        row = (await db.execute(select(SpecDocument).where(SpecDocument.path == PATH))).scalar_one()
        row.phase = "proposed"
        row.explore_closed_at = datetime.now(timezone.utc)
        await db.commit()
    approved = await app.post(
        f"{BASE}/documents/phase?path={PATH}&to=approved",
        json={"reason": "test", "approve_anyway": True},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text
    (task_id,) = approved.json()["tasks_created"]
    return task_id


async def _stored(tmp_path):
    return parse_stored((tmp_path / PATH).read_text(encoding="utf-8"))


async def _amendments(app, auth_headers):
    response = await app.get(f"{BASE}/documents/{PATH}/amendments", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["amendments"]


NEW_CRITERION = {
    "path": PATH,
    "op": "add_criterion",
    "requirement": "alpha",
    "criterion": "c-slow",
    "change": {
        "given": "a slow disk",
        "when": "it responds",
        "then": "within 200ms",
        "how_to_check": "time curl",
    },
    "reason": "drove it on a slow disk; nothing said what should happen",
    "how_to_check": "time curl /ping on a throttled disk",
}


# ---------------------------------------------------------------------------
# Who may amend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_builder_is_refused_and_the_tester_amends(
    app, auth_headers, author_headers, tmp_path
):
    task_id = await _approved(app, auth_headers, author_headers)
    builder = await _run("run-builder", "dev", task_id=task_id)
    tester = await _run("run-tester", "tess", reviews=task_id)
    before = await _stored(tmp_path)

    refused = await app.post(AMEND, json=NEW_CRITERION, headers=builder)
    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "amend_not_tester"
    assert await _stored(tmp_path) == before

    accepted = await app.post(AMEND, json=NEW_CRITERION, headers=tester)
    assert accepted.status_code == 201, accepted.text
    keys = [c["key"] for c in (await _stored(tmp_path))["acceptance_criteria"]]
    assert keys == ["c1", "c-slow"]


@pytest.mark.asyncio
async def test_testing_off_refuses_even_the_test_turn(app, auth_headers, author_headers):
    task_id = await _approved(app, auth_headers, author_headers, delivery={**FLOW, "tester": False})
    tester = await _run("run-tester", "tess", reviews=task_id)

    refused = await app.post(AMEND, json=NEW_CRITERION, headers=tester)

    assert refused.status_code == 403, refused.text
    assert refused.json()["detail"]["code"] == "amend_not_tester"


@pytest.mark.asyncio
async def test_a_document_not_approved_is_not_amended(app, auth_headers, author_headers):
    task_id = await _approved(app, auth_headers, author_headers)
    reopened = await app.post(
        f"{BASE}/documents/phase?path={PATH}&to=exploring",
        json={"reason": "t"},
        headers=auth_headers,
    )
    assert reopened.status_code == 200, reopened.text
    tester = await _run("run-tester", "tess", reviews=task_id)

    refused = await app.post(AMEND, json=NEW_CRITERION, headers=tester)

    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "amend_not_approved"


# ---------------------------------------------------------------------------
# The operations and the record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_amendment_names_only_what_the_document_holds_and_says_how_to_check(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)

    unknown = await app.post(AMEND, json={**NEW_CRITERION, "requirement": "omega"}, headers=tester)
    unchecked = await app.post(AMEND, json={**NEW_CRITERION, "how_to_check": ""}, headers=tester)

    assert unknown.status_code == 422 and unknown.json()["detail"]["field"] == "requirement"
    assert unchecked.status_code == 422 and unchecked.json()["detail"]["field"] == "how_to_check"
    assert await _amendments(app, auth_headers) == []


@pytest.mark.asyncio
async def test_an_added_task_joins_the_live_flow_at_once(
    app, auth_headers, author_headers, tmp_path
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)

    response = await app.post(
        AMEND,
        json={
            "path": PATH,
            "op": "add_task",
            "task": {
                "key": "fix-slow",
                "title": "Respond within 200ms on a slow disk",
                "description": "It took 900ms.",
                "requirements": ["alpha"],
            },
            "reason": "drove /ping on a throttled disk: 900ms",
            "how_to_check": "time curl /ping",
        },
        headers=tester,
    )

    assert response.status_code == 201, response.text
    created = response.json()["task_created"]
    async with async_session_factory() as db:
        task = await db.get(Task, created)
        loop = (await db.execute(select(Loop))).scalars().one()
    assert (task.spec_task_key, task.status, task.loop_id) == ("fix-slow", "pending", loop.id)
    assert [t["key"] for t in (await _stored(tmp_path))["tasks"]] == ["t1", "fix-slow"]


@pytest.mark.asyncio
async def test_each_amendment_records_author_and_run_and_is_not_reviewed(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)
    await app.post(AMEND, json=NEW_CRITERION, headers=tester)

    (amendment,) = await _amendments(app, auth_headers)

    assert amendment["op"] == "add_criterion" and amendment["target"] == "c-slow"
    assert (amendment["author"], amendment["run_id"]) == ("tess", "run-tester")
    assert amendment["reviewed"] is False and amendment["relaxing"] is False
    assert amendment["how_to_check"] == NEW_CRITERION["how_to_check"]
    assert amendment["identifier"] == "FR-1"


@pytest.mark.asyncio
async def test_the_operator_marks_reviewed_per_item_then_for_the_document(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)
    for key in ("c-a", "c-b", "c-c"):
        response = await app.post(AMEND, json={**NEW_CRITERION, "criterion": key}, headers=tester)
        assert response.status_code == 201, response.text
    first = (await _amendments(app, auth_headers))[0]["id"]

    one = await app.post(
        f"{BASE}/documents/{PATH}/amendments/review", json={"ids": [first]}, headers=auth_headers
    )
    assert one.status_code == 200, one.text
    assert [a["reviewed"] for a in one.json()["amendments"]] == [True, False, False]

    rest = await app.post(
        f"{BASE}/documents/{PATH}/amendments/review", json={}, headers=auth_headers
    )
    assert rest.status_code == 200, rest.text
    assert len(rest.json()["marked"]) == 2
    assert all(a["reviewed"] and a["reviewed_by"] == "operator" for a in rest.json()["amendments"])


@pytest.mark.asyncio
async def test_marking_an_amendment_the_document_does_not_hold_is_refused(
    app, auth_headers, author_headers
):
    await _approved(app, auth_headers, author_headers)

    response = await app.post(
        f"{BASE}/documents/{PATH}/amendments/review",
        json={"ids": ["amd-nope"]},
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Relaxing, and cannot satisfy
# ---------------------------------------------------------------------------


async def _coverage_state(identifier="FR-1"):
    async with async_session_factory() as db:
        report = await requirement_coverage.requirement_coverage(db, "proj-test")
    return next(c.state for c in report.requirements if c.identifier == identifier)


async def _accepted_evidence(app, auth_headers):
    recorded = await app.post(
        f"{BASE}/spec/evidence",
        json={
            "identifier": "FR-1",
            "summary": "measured",
            "kind": "test_result",
            "document": PATH,
        },
        headers=auth_headers,
    )
    assert recorded.status_code == 201, recorded.text
    decided = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted", "reason": "ok"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text


@pytest.mark.asyncio
async def test_a_changed_criterion_holds_its_requirement_until_reviewed(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)
    changed = await app.post(
        AMEND,
        json={
            "path": PATH,
            "op": "change_criterion",
            "criterion": "c1",
            "change": {"then": "eventually"},
            "reason": "200ms was never met",
            "how_to_check": "curl /ping",
        },
        headers=tester,
    )
    assert changed.status_code == 201, changed.text
    await _accepted_evidence(app, auth_headers)

    assert await _coverage_state() == requirement_coverage.AMENDMENT_UNREVIEWED
    reviewed = await app.post(
        f"{BASE}/documents/{PATH}/amendments/review", json={}, headers=auth_headers
    )
    assert reviewed.status_code == 200, reviewed.text
    assert await _coverage_state() == requirement_coverage.VERIFIED


@pytest.mark.asyncio
async def test_an_added_criterion_alone_never_holds_its_requirement(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)
    await app.post(AMEND, json=NEW_CRITERION, headers=tester)
    await _accepted_evidence(app, auth_headers)

    assert await _coverage_state() == requirement_coverage.VERIFIED


@pytest.mark.asyncio
async def test_the_builder_reports_a_criterion_it_cannot_satisfy(app, auth_headers, author_headers):
    task_id = await _approved(app, auth_headers, author_headers)
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        task.status, task.assignee = "in_progress", "dev"
        await db.commit()
    builder = await _run("run-builder", "dev", task_id=task_id)

    response = await app.post(
        CANNOT,
        json={
            "path": PATH,
            "criterion": "c1",
            "reason": "the disk is the bottleneck; 200ms is not reachable",
        },
        headers=builder,
    )

    assert response.status_code == 201, response.text
    assert response.json()["task_blocked"] is True
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
    assert task.status == "blocked" and "cannot satisfy criterion c1" in task.blocked_reason
    (amendment,) = await _amendments(app, auth_headers)
    assert (amendment["op"], amendment["author"], amendment["reviewed"]) == (
        "cannot_satisfy",
        "dev",
        False,
    )
    assert amendment["relaxing"] is True


@pytest.mark.asyncio
async def test_a_run_on_no_task_of_the_document_cannot_report(app, auth_headers, author_headers):
    await _approved(app, auth_headers, author_headers)
    stranger = await _run("run-stranger", "dev")

    response = await app.post(
        CANNOT, json={"path": PATH, "criterion": "c1", "reason": "x"}, headers=stranger
    )

    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# The approval gap and the documents view
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_reapproval_with_unreviewed_amendments_lists_the_gap(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)
    assert (await app.post(AMEND, json=NEW_CRITERION, headers=tester)).status_code == 201
    for to in ("exploring", "proposed"):
        async with async_session_factory() as db:
            row = (
                await db.execute(select(SpecDocument).where(SpecDocument.path == PATH))
            ).scalar_one()
            row.phase = to
            row.explore_closed_at = datetime.now(timezone.utc)
            await db.commit()

    response = await app.post(
        f"{BASE}/documents/phase?path={PATH}&to=approved",
        json={"reason": "t"},
        headers=auth_headers,
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "approval_warnings"
    assert "amendments_unreviewed" in [w["code"] for w in detail["warnings"]]


@pytest.mark.asyncio
async def test_the_documents_view_counts_the_amendments_not_reviewed(
    app, auth_headers, author_headers
):
    task_id = await _approved(app, auth_headers, author_headers)
    tester = await _run("run-tester", "tess", reviews=task_id)
    for key in ("c-a", "c-b"):
        await app.post(AMEND, json={**NEW_CRITERION, "criterion": key}, headers=tester)
    first = (await _amendments(app, auth_headers))[0]["id"]
    await app.post(
        f"{BASE}/documents/{PATH}/amendments/review", json={"ids": [first]}, headers=auth_headers
    )

    listed = await app.get(f"{BASE}/documents", headers=auth_headers)

    (view,) = [d for d in listed.json()["documents"] if d["path"] == PATH]
    assert view["amendments"] == {"total": 2, "unreviewed": 1}


# ---------------------------------------------------------------------------
# delivery.tester: staffing and the test briefing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_named_tester_reviews_before_the_default_reviewer_and_after_the_task_s_own(
    app, auth_headers, author_headers, monkeypatch
):
    from hub import project_workspace, review_turn

    # `review_turn` holds its own import of the resolver the app fixture patches on its module.
    monkeypatch.setattr(
        review_turn, "resolve_project_workspace", project_workspace.resolve_project_workspace
    )

    await _agents("rev")
    tasks = [
        {"key": "t1", "description": "Build it", "requirements": ["alpha"]},
        {"key": "t2", "description": "Doc it", "requirements": ["alpha"], "reviewer": "rev"},
    ]
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Demo"}, headers=auth_headers
    )
    assert created.status_code == 201
    await _agents("dev", "tess")
    written = await _submit_document(
        app, author_headers, _document(tasks=tasks, delivery={**FLOW, "reviewer": "rev"})
    )
    assert written.status_code == 200, written.text
    async with async_session_factory() as db:
        row = (await db.execute(select(SpecDocument).where(SpecDocument.path == PATH))).scalar_one()
        row.phase = "proposed"
        row.explore_closed_at = datetime.now(timezone.utc)
        await db.commit()
    approved = await app.post(
        f"{BASE}/documents/phase?path={PATH}&to=approved",
        json={"reason": "t", "approve_anyway": True},
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text

    async with async_session_factory() as db:
        rows = (await db.execute(select(Task).order_by(Task.spec_task_key))).scalars().all()
        resolved = {
            row.spec_task_key: (
                await review_turn.resolve_declared_reviewer(db, project_id="proj-test", task=row)
            ).agent
            for row in rows
        }
    assert resolved == {"t1": "tess", "t2": "rev"}


async def _duty(app, auth_headers, author_headers, delivery, monkeypatch):
    from hub import project_workspace, review_turn

    monkeypatch.setattr(
        review_turn, "resolve_project_workspace", project_workspace.resolve_project_workspace
    )

    task_id = await _approved(app, auth_headers, author_headers, delivery=delivery)
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        return "\n".join(await review_turn.test_duty_lines(db, task))


@pytest.mark.asyncio
async def test_a_flow_review_is_a_test_turn_by_default(
    app, auth_headers, author_headers, monkeypatch
):
    duty = await _duty(
        app,
        auth_headers,
        author_headers,
        {k: v for k, v in FLOW.items() if k != "tester"},
        monkeypatch,
    )

    assert "Drive the running product" in duty
    assert f'amend_spec_document(path="{PATH}"' in duty
    assert "side finding" in duty and "report_cannot_satisfy" in duty


@pytest.mark.asyncio
async def test_tester_false_leaves_a_plain_review(app, auth_headers, author_headers, monkeypatch):
    assert (
        await _duty(app, auth_headers, author_headers, {**FLOW, "tester": False}, monkeypatch) == ""
    )
