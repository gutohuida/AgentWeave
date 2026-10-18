"""A decided piece of evidence is overturned only by the operator, with a reason (F692).

The sweep's granted tester accepted a piece its own review had rejected -- recorded against an
earlier wording of the requirement -- and got `accepted` back with no note and no refusal, while
the operator had no screen to reverse a decision at all. Operator decision 2026-10-18: agents decide
`awaiting` evidence only; the operator overturns with a required reason; evidence recorded for an
earlier wording is never accepted. Real routes on both planes, a real repository.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceReview, RequirementEvidence, Run, Task
from hub.spec_payload import SCHEMA_VERSION

from .test_approval_refuses_unaccepted_evidence import (
    a_task_with_awaiting_evidence,
    record_evidence,
)
from .test_task_integration import (
    ALPHA,
    BASE,
    PATH,
    SUBMIT,
    make_document,
    make_repo,
    set_main_branch,
)

AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
AGENT_TASKS = "/api/v1/agent-actions/tasks"
F692 = pytest.mark.xfail(strict=True, reason="F692: not built yet")


def _run(agent_id, name, run_id, secret, *, granted=False):
    return [
        Agent(id=agent_id, project_id="proj-test", name=name, can_accept_evidence=granted),
        Run(
            id=run_id,
            project_id="proj-test",
            agent=name,
            status="running",
            turn_depth=0,
            capability_token_hash=hash_run_token(secret),
        ),
    ]


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add_all(_run("ag-ovt-b", "builder", "run-ovt-b", "aw_run_ovtb-secret"))
        await session.commit()
    return {"Authorization": "Bearer aw_run_ovtb-secret"}


@pytest.fixture
async def granted():
    """A tester the operator granted `can_accept_evidence`: the sweep's overturning agent."""
    async with async_session_factory() as session:
        session.add_all(_run("ag-ovt-t", "tester", "run-ovt-t", "aw_run_ovtt-secret", granted=True))
        await session.commit()
    return {"Authorization": "Bearer aw_run_ovtt-secret"}


async def ready(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")


async def state_of(evidence_id):
    async with async_session_factory() as session:
        return (await session.get(RequirementEvidence, evidence_id)).review_state


async def reviews_of(evidence_id):
    async with async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(EvidenceReview)
                    .where(EvidenceReview.evidence_id == evidence_id)
                    .order_by(EvidenceReview.sequence)
                )
            )
            .scalars()
            .all()
        )
        return [(row.decision, row.actor_kind, row.reason) for row in rows]


async def decide(app, headers, evidence, decision, reason=""):
    return await app.post(
        f"{BASE}/spec/evidence/{evidence}/decision",
        json={"decision": decision, "reason": reason},
        headers=headers,
    )


async def overturn(app, headers, evidence, reason):
    return await app.post(
        f"{BASE}/spec/evidence/{evidence}/overturn", json={"reason": reason}, headers=headers
    )


@F692
@pytest.mark.asyncio
async def test_a_granted_agent_cannot_decide_a_decided_piece(
    app, auth_headers, builder, granted, tmp_path
):
    """R1: the sweep's repro. FAILS before: the agent's acceptance overturned the rejection."""
    await ready(app, auth_headers, builder, tmp_path)
    _task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    rejected = await decide(app, auth_headers, evidence, "rejected", "an empty commit")
    assert rejected.status_code == 200, rejected.text

    refused = await app.post(
        f"{AGENT_EVIDENCE}/{evidence}/decision",
        json={"decision": "accepted", "reason": "probe overturn"},
        headers=granted,
    )

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "already_decided", detail
    assert "rejected" in detail["message"] and "operator" in detail["message"], detail
    assert await state_of(evidence) == "rejected"
    assert [d for d, _k, _r in await reviews_of(evidence)] == ["rejected"]


@pytest.mark.asyncio
async def test_a_granted_agent_still_decides_an_awaiting_piece(
    app, auth_headers, builder, granted, tmp_path
):
    """R1 control: the grant still does what it was for."""
    await ready(app, auth_headers, builder, tmp_path)
    _task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    accepted = await app.post(
        f"{AGENT_EVIDENCE}/{evidence}/decision",
        json={"decision": "accepted", "reason": "ran it"},
        headers=granted,
    )
    assert accepted.status_code == 200, accepted.text
    assert await state_of(evidence) == "accepted"


@F692
@pytest.mark.asyncio
async def test_the_operator_overturns_only_with_a_reason(app, auth_headers, builder, tmp_path):
    """R2. FAILS before: there was no overturn route."""
    await ready(app, auth_headers, builder, tmp_path)
    _task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    assert (await decide(app, auth_headers, evidence, "rejected", "wrong file")).status_code == 200

    blank = await overturn(app, auth_headers, evidence, "  ")
    assert blank.status_code == 422, blank.text
    assert blank.json()["detail"]["code"] == "overturn_needs_reason"
    assert await state_of(evidence) == "rejected"

    done = await overturn(app, auth_headers, evidence, "the file was right; I misread it")

    assert done.status_code == 200, done.text
    body = done.json()
    assert body["review_state"] == "accepted"
    assert body["overturned"] == {"from": "rejected"}
    assert await reviews_of(evidence) == [
        ("rejected", "operator", "wrong file"),
        ("accepted", "operator", "the file was right; I misread it"),
    ]


@F692
@pytest.mark.asyncio
async def test_overturning_an_accepted_piece_reopens_the_approved_task(
    app, auth_headers, builder, tmp_path
):
    """R2: an overturn has a first decision's consequences."""
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    from .test_task_integration import TASKS, drive_to

    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text
    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)
    assert approved.status_code == 200, approved.text
    assert await state_of(evidence) == "accepted"

    done = await overturn(app, auth_headers, evidence, "it does not show the overdue list")

    assert done.status_code == 200, done.text
    assert done.json()["overturned"] == {"from": "accepted"}
    assert done.json()["task_reopen"] == {"task": task, "reopened": True}
    async with async_session_factory() as session:
        assert (await session.get(Task, task)).status == "revision_needed"


@F692
@pytest.mark.asyncio
async def test_overturning_an_awaiting_piece_is_refused(app, auth_headers, builder, tmp_path):
    await ready(app, auth_headers, builder, tmp_path)
    _task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    refused = await overturn(app, auth_headers, evidence, "a reason")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "not_decided"
    assert await state_of(evidence) == "awaiting"


@F692
@pytest.mark.asyncio
async def test_the_same_decision_again_is_refused(app, auth_headers, builder, tmp_path):
    """R2: a decided piece is decided; the operator's plain route needs a reason to reverse it."""
    await ready(app, auth_headers, builder, tmp_path)
    _task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    assert (await decide(app, auth_headers, evidence, "accepted")).status_code == 200

    again = await decide(app, auth_headers, evidence, "accepted")
    assert again.status_code == 409, again.text
    assert again.json()["detail"]["code"] == "already_decided"

    blank = await decide(app, auth_headers, evidence, "rejected", "")
    assert blank.status_code == 422, blank.text
    assert [d for d, _k, _r in await reviews_of(evidence)] == ["accepted"]


@F692
@pytest.mark.asyncio
async def test_evidence_for_an_earlier_wording_cannot_be_accepted(
    app, auth_headers, builder, tmp_path
):
    """R3. FAILS before: the stale piece was accepted."""
    await ready(app, auth_headers, builder, tmp_path)
    evidence = await record_evidence(app, builder)
    reworded = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Integration demo",
                "requirements": [{**ALPHA, "statement": "It lists what is due this week"}],
            },
        },
        headers=builder,
    )
    assert reworded.status_code == 200, reworded.text

    refused = await decide(app, auth_headers, evidence, "accepted")

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "evidence_stale", detail
    assert "reworded" in detail["message"], detail
    assert await state_of(evidence) == "awaiting"
    # Rejecting it stays possible: it is the author's signal.
    assert (await decide(app, auth_headers, evidence, "rejected", "old wording")).status_code == 200
