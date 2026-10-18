"""The operator answers a cannot-satisfy report, and the answer does something (F700).

A builder reports a criterion it cannot meet; its task blocks. The operator's only response used to
be "Mark reviewed", which left the criterion unchanged and the task blocked. Now there are three:
amend the criterion, accept the report, reject it -- each with its consequence. Real routes on the
agent plane (the report) and the operator plane (the answer).
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Task

from .test_spec_documents_api import PATH
from .test_tester_amendments import BASE, CANNOT, _amendments, _approved, _run, _stored


@pytest.fixture
async def author_headers():
    return await _run("run-author", "scribe")


async def reported(app, auth_headers, author_headers):
    """An approved document whose builder reported c1; returns (task id, report id)."""
    task_id = await _approved(app, auth_headers, author_headers)
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        task.status, task.assignee = "in_progress", "dev"
        await db.commit()
    builder = await _run("run-builder", "dev", task_id=task_id)
    report = await app.post(
        CANNOT,
        json={"path": PATH, "criterion": "c1", "reason": "the disk is the bottleneck"},
        headers=builder,
    )
    assert report.status_code == 201, report.text
    assert report.json()["task_blocked"] is True
    # The builder's turn has ended by the time the operator answers.
    from hub.db.models import Run

    async with async_session_factory() as db:
        (await db.get(Run, "run-builder")).status = "completed"
        await db.commit()
    return task_id, report.json()["id"]


async def respond(app, auth_headers, report_id, body):
    return await app.post(
        f"{BASE}/documents/{PATH}/amendments/{report_id}/respond", json=body, headers=auth_headers
    )


async def status_of(task_id):
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        return task.status, task.blocked_reason


async def entries_for(agent):
    async with async_session_factory() as db:
        rows = await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent, InboundQueueEntry.origin_type == "operator")
            .order_by(InboundQueueEntry.arrived_at)
        )
        return [row.content for row in rows.scalars().all()]


def row(amendments, amendment_id):
    return next(a for a in amendments if a["id"] == amendment_id)


@pytest.mark.asyncio
async def test_amending_changes_the_criterion_and_unblocks_the_task(
    app, auth_headers, author_headers, tmp_path
):
    task_id, report_id = await reported(app, auth_headers, author_headers)

    answered = await respond(
        app,
        auth_headers,
        report_id,
        {"response": "amend", "reason": "2s is what we need", "change": {"then": "within 2s"}},
    )

    assert answered.status_code == 200, answered.text
    c1 = next(c for c in (await _stored(tmp_path))["acceptance_criteria"] if c["key"] == "c1")
    assert c1["then"] == "within 2s"
    assert await status_of(task_id) == ("in_progress", None)
    amendments = await _amendments(app, auth_headers)
    report = row(amendments, report_id)
    assert report["reviewed"] is True and report["response"] == "amended", report
    produced = row(amendments, report["answered_by"])
    assert (produced["op"], produced["author"], produced["reviewed"]) == (
        "change_criterion",
        "operator",
        True,
    )
    assert produced["responds_to"] == report_id
    [note] = await entries_for("dev")
    assert "c1" in note and "within 2s" in note, note


@pytest.mark.asyncio
async def test_accepting_unblocks_the_task_and_keeps_the_criterion(
    app, auth_headers, author_headers, tmp_path
):
    task_id, report_id = await reported(app, auth_headers, author_headers)
    before = next(c for c in (await _stored(tmp_path))["acceptance_criteria"] if c["key"] == "c1")

    answered = await respond(app, auth_headers, report_id, {"response": "accept", "reason": ""})

    assert answered.status_code == 200, answered.text
    after = next(c for c in (await _stored(tmp_path))["acceptance_criteria"] if c["key"] == "c1")
    assert after == before
    assert await status_of(task_id) == ("in_progress", None)
    report = row(await _amendments(app, auth_headers), report_id)
    assert report["reviewed"] is True and report["response"] == "accepted", report
    [note] = await entries_for("dev")
    assert "c1" in note and "accepted" in note, note


@pytest.mark.asyncio
async def test_rejecting_keeps_the_task_blocked_and_sends_the_reason_to_the_reporter(
    app, auth_headers, author_headers
):
    task_id, report_id = await reported(app, auth_headers, author_headers)

    blank = await respond(app, auth_headers, report_id, {"response": "reject", "reason": " "})
    assert blank.status_code == 422, blank.text
    assert blank.json()["detail"]["code"] == "response_needs_reason"

    answered = await respond(
        app, auth_headers, report_id, {"response": "reject", "reason": "cache the index; it fits"}
    )

    assert answered.status_code == 200, answered.text
    status, reason = await status_of(task_id)
    assert status == "blocked" and "c1" in reason
    report = row(await _amendments(app, auth_headers), report_id)
    assert report["reviewed"] is True and report["response"] == "rejected", report
    [note] = await entries_for("dev")
    assert "c1" in note and "cache the index; it fits" in note, note


@pytest.mark.asyncio
async def test_mark_reviewed_does_not_answer_a_report(app, auth_headers, author_headers):
    task_id, report_id = await reported(app, auth_headers, author_headers)

    named = await app.post(
        f"{BASE}/documents/{PATH}/amendments/review",
        json={"ids": [report_id]},
        headers=auth_headers,
    )
    assert named.status_code == 409, named.text
    assert named.json()["detail"]["code"] == "report_needs_response"
    assert "respond" in named.json()["detail"]["message"]

    whole = await app.post(
        f"{BASE}/documents/{PATH}/amendments/review", json={}, headers=auth_headers
    )
    assert whole.status_code == 200, whole.text
    assert row(await _amendments(app, auth_headers), report_id)["reviewed"] is False
    assert (await status_of(task_id))[0] == "blocked"


@pytest.mark.asyncio
async def test_a_report_is_answered_once(app, auth_headers, author_headers):
    _task_id, report_id = await reported(app, auth_headers, author_headers)
    assert (
        await respond(app, auth_headers, report_id, {"response": "accept", "reason": ""})
    ).status_code == 200

    again = await respond(app, auth_headers, report_id, {"response": "reject", "reason": "no"})

    assert again.status_code == 409, again.text
    assert again.json()["detail"]["code"] == "report_answered"
