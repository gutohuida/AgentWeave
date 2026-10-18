"""The reviewer's verdict decides the task's evidence (`the-reviewers-verdict-decides-the-tasks-evidence`).

F672: a reviewer judged the work right, its approval was refused because the task's evidence waited
on a decision only the operator or a granted agent could make, and the loop stalled on it. The
operator decided (vis-D1, vis-D4, 2026-10-17) that the verdict decides the evidence: approving a
task accepts the evidence recorded for it, sending it back rejects that evidence, and nothing waits
on the operator. These tests use a real repository and the real routes, as the gate tests do.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, EvidenceReview, RequirementEvidence, Run, Task
from hub.spec_lifecycle import Actor

from .test_approval_refuses_unaccepted_evidence import (
    a_task_with_awaiting_evidence,
    record_evidence,
)
from .test_task_integration import (
    AGENT_BRANCH,
    BASE,
    TASKS,
    commit_on_branch,
    commits_on,
    drive_to,
    git,
    linked_task,
    make_document,
    make_repo,
    set_main_branch,
)

AGENT_TASKS = "/api/v1/agent-actions/tasks"


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-verdict-b", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-verdict-b",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_verdictb-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_verdictb-secret"}


@pytest.fixture
async def reviewer():
    """An agent with no `can_accept_evidence` grant: the verdict alone decides."""
    async with async_session_factory() as session:
        session.add(Agent(id="ag-verdict-r", project_id="proj-test", name="reviewer"))
        session.add(
            Run(
                id="run-verdict-r",
                project_id="proj-test",
                agent="reviewer",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_verdictr-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_verdictr-secret"}


async def under_review(app, auth_headers, task):
    walked = await drive_to(
        app, auth_headers, task, "assigned", "in_progress", "completed", "under_review"
    )
    assert walked.status_code == 200, walked.text


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
        return [(row.decision, row.actor_kind, row.actor, row.reason) for row in rows]


async def state_of(evidence_id):
    async with async_session_factory() as session:
        return (await session.get(RequirementEvidence, evidence_id)).review_state


async def status_of(task_id):
    async with async_session_factory() as session:
        return (await session.get(Task, task_id)).status


async def ready(app, auth_headers, builder, tmp_path):
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")


@pytest.mark.asyncio
async def test_approving_accepts_the_tasks_evidence_and_merges(
    app, auth_headers, builder, reviewer, tmp_path
):
    """Criterion approve: the reviewer's approval accepts with its notes as the reason."""
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    await under_review(app, auth_headers, task)

    approved = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={"status": "approved", "notes": "feature.py prints hi; checked it"},
        headers=reviewer,
    )

    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert await state_of(evidence) == "accepted"
    assert await reviews_of(evidence) == [
        ("accepted", "agent", "reviewer", "feature.py prints hi; checked it")
    ]
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_approving_without_notes_names_the_approval(
    app, auth_headers, builder, reviewer, tmp_path
):
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    await under_review(app, auth_headers, task)

    approved = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )

    assert approved.status_code == 200, approved.text
    [(decision, _kind, actor, reason)] = await reviews_of(evidence)
    assert (decision, actor) == ("accepted", "reviewer")
    assert task in reason and "approv" in reason.lower(), reason


@pytest.mark.asyncio
async def test_the_operator_approving_accepts_too(app, auth_headers, builder, tmp_path):
    """One decision per task (vis-D2), whoever makes it."""
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    await under_review(app, auth_headers, task)

    approved = await app.patch(f"{TASKS}/{task}", json={"status": "approved"}, headers=auth_headers)

    assert approved.status_code == 200, approved.text
    assert [(d, k) for d, k, _a, _r in await reviews_of(evidence)] == [("accepted", "operator")]
    assert work in commits_on(tmp_path, "main")


@pytest.mark.asyncio
async def test_a_piece_the_acting_agent_recorded_is_left(app, auth_headers, builder, tmp_path):
    """Criterion self: nobody accepts their own evidence, verdict or not."""
    from hub import requirement_evidence

    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    async with async_session_factory() as session:
        decided = await requirement_evidence.decide_with_verdict(
            session,
            await session.get(Task, task),
            actor=Actor(kind="agent", name="builder", run_id="run-verdict-b"),
            decision=requirement_evidence.ACCEPTED,
            reason="",
        )
        await session.commit()
    assert decided == []
    assert await state_of(evidence) == "awaiting"


@pytest.mark.asyncio
async def test_another_tasks_piece_is_left(app, auth_headers, builder, tmp_path):
    """Criterion other-task: a second task serving the same requirement keeps its own evidence for
    its own reviewer."""
    from hub import requirement_evidence

    await ready(app, auth_headers, builder, tmp_path)
    task, _evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    other = await linked_task(app, auth_headers, title="The other one")
    commit_on_branch(tmp_path, AGENT_BRANCH, "other.py", "x = 1\n", create=False)
    foreign = await record_evidence(app, builder, task_id=other)
    git(tmp_path, "checkout", "-q", "main")

    async with async_session_factory() as session:
        decided = await requirement_evidence.decide_with_verdict(
            session,
            await session.get(Task, task),
            actor=Actor(kind="agent", name="reviewer", run_id="run-verdict-r"),
            decision=requirement_evidence.ACCEPTED,
            reason="ok",
        )
        await session.commit()
    assert foreign not in [row.evidence_id for row in decided]
    assert await state_of(foreign) == "awaiting"


@pytest.mark.asyncio
async def test_a_refused_approval_keeps_no_acceptance(
    app, auth_headers, builder, reviewer, tmp_path
):
    """Criterion rollback: the work conflicts with main, so approval is refused for the conflict and
    the evidence is still awaiting, with no review row."""
    await ready(app, auth_headers, builder, tmp_path)
    task = await linked_task(app, auth_headers)
    commit_on_branch(tmp_path, AGENT_BRANCH, "README.md", "the branch says this\n")
    evidence = await record_evidence(app, builder, task_id=task)
    git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "README.md").write_text("main says something else\n", encoding="utf-8")
    git(tmp_path, "commit", "-q", "-am", "main moves")
    await under_review(app, auth_headers, task)

    refused = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )

    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "gate_unsatisfied", detail
    assert not detail.get("unaccepted"), detail
    assert detail.get("unmergeable"), detail
    assert await state_of(evidence) == "awaiting"
    assert await reviews_of(evidence) == []
    assert await status_of(task) == "under_review"


@pytest.mark.asyncio
async def test_sending_back_rejects_the_tasks_evidence(
    app, auth_headers, builder, reviewer, tmp_path
):
    """Criterion sendback: the notes are the author's signal of what to fix."""
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    await under_review(app, auth_headers, task)

    sent = await app.patch(
        f"{AGENT_TASKS}/{task}",
        json={"status": "revision_needed", "notes": "feature.py prints the wrong word"},
        headers=reviewer,
    )

    assert sent.status_code == 200, sent.text
    assert await reviews_of(evidence) == [
        ("rejected", "agent", "reviewer", "feature.py prints the wrong word")
    ]


@pytest.mark.asyncio
async def test_sending_back_without_notes_still_gives_a_reason(
    app, auth_headers, builder, reviewer, tmp_path
):
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    await under_review(app, auth_headers, task)

    sent = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "revision_needed"}, headers=reviewer
    )

    assert sent.status_code == 200, sent.text
    [(decision, _kind, actor, reason)] = await reviews_of(evidence)
    assert (decision, actor) == ("rejected", "reviewer")
    assert reason.strip(), reason


@pytest.mark.asyncio
async def test_no_operator_hold_for_the_tasks_own_evidence(app, auth_headers, builder, tmp_path):
    """Criterion hold: neither the hold nor the briefing hands the task's own evidence to the
    operator, and the briefing says the verdict decides it."""
    from hub import requirement_gate, review_turn

    await ready(app, auth_headers, builder, tmp_path)
    task, _evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    await under_review(app, auth_headers, task)

    async with async_session_factory() as session:
        row = await session.get(Task, task)
        hold = await requirement_gate.approval_held_for_operator(session, row, candidate="reviewer")
        sentence = await review_turn.verdict_evidence_sentence(session, row, may_decide=False)

    assert hold is None, hold
    assert sentence is not None
    assert "operator's" not in sentence, sentence
    assert "verdict decides" in sentence, sentence


@pytest.mark.asyncio
async def test_the_operator_rejecting_an_accepted_piece_reopens_the_task(
    app, auth_headers, builder, reviewer, tmp_path
):
    """Criterion overturn: the operator leaves the gate and keeps the last word."""
    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, _work = await a_task_with_awaiting_evidence(
        app, auth_headers, builder, tmp_path
    )
    await under_review(app, auth_headers, task)
    approved = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )
    assert approved.status_code == 200, approved.text

    rejected = await app.post(
        f"{BASE}/spec/evidence/{evidence}/decision",
        json={"decision": "rejected", "reason": "this does not show the overdue list"},
        headers=auth_headers,
    )

    assert rejected.status_code == 200, rejected.text
    assert await state_of(evidence) == "rejected"
    assert await status_of(task) == "revision_needed"


@pytest.mark.asyncio
async def test_approval_with_checks_starts_a_run_on_the_evidence_the_verdict_accepts(
    app, auth_headers, builder, reviewer, tmp_path
):
    """F680: the verdict accepts the evidence inside the PATCH transaction, then the gate finds no
    check result and schedules a run. That run must check the work the verdict just accepted; read
    from its own session it saw no accepted evidence, started nothing, and the 409 rolled the
    acceptance back -- so "checks are still running" while no run existed, on every retry."""
    from hub import project_checks

    from .test_project_checks_run import PASS, _project, _runs

    await ready(app, auth_headers, builder, tmp_path)
    task, evidence, work = await a_task_with_awaiting_evidence(app, auth_headers, builder, tmp_path)
    await _project([PASS])
    await under_review(app, auth_headers, task)

    refused = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["checks"][0]["state"] == "running"
    await project_checks.drain()
    runs = await _runs(task)
    assert [r.state for r in runs] == ["passed"], [(r.state, r.error) for r in runs]
    assert runs[0].target_shas == [work]

    approved = await app.patch(
        f"{AGENT_TASKS}/{task}", json={"status": "approved"}, headers=reviewer
    )
    assert approved.status_code == 200, approved.text
    assert await state_of(evidence) == "accepted"
    assert work in commits_on(tmp_path, "main")
