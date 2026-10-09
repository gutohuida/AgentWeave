"""F510 — a review turn reviews what approval would merge, and the branch tip is that where
evidence does not govern the merge. Written before the fix; the evidence-free legs fail today with
`409 ... has no recorded evidence`, because `commit_for_task_review` reads evidence alone.

Real git repository and the real `ensure_review_checkout` throughout (the suite stubs it otherwise):
"the checkout is at the branch tip" is read off the checkout, not off the context that claims it.
"""

import subprocess

import pytest

from hub import task_integration, worktrees
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EvidenceFootprint,
    Loop,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Task,
)
from hub.inbound_queue import new_entry
from hub.review_turn import ReviewTurnRefused, prepare_review_turn
from hub.scheduler import decide_firing
from hub.turn_scheduler import other_input_would_have_run_elsewhere

from .test_a_flow_names_what_it_cannot_staff import _roster
from .test_a_loop_does_not_staff_its_own_review import _completed_by
from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

#: Captured at import, before `conftest`'s autouse fixture stubs it.
_REAL_ENSURE_REVIEW_CHECKOUT = worktrees.ensure_review_checkout

ROUTE = "/api/v1/projects/proj-test/agent/trigger"
WORKER = "f510-worker"
REVIEWER = "f510-reviewer"
NO_EVIDENCE_WORDS = "no recorded evidence"


async def _loop(*, work_needs_evidence, document=False, suffix="a"):
    async with async_session_factory() as db:
        db.add(
            AIJob(
                id=f"job-f510-{suffix}",
                project_id="proj-test",
                name=f"f510 {suffix}",
                agent=WORKER,
                message="work",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await db.flush()
        if document:
            db.add(
                SpecDocument(
                    id=f"doc-f510-{suffix}",
                    project_id="proj-test",
                    path=f"spec/f510-{suffix}.json",
                    title="Doc",
                    phase="current",
                    kind="capability",
                )
            )
            await db.flush()
        db.add(
            Loop(
                id=f"loop-f510-{suffix}",
                project_id="proj-test",
                job_id=f"job-f510-{suffix}",
                purpose="work",
                work_needs_evidence=work_needs_evidence,
                spec_document_id=f"doc-f510-{suffix}" if document else None,
            )
        )
        await db.commit()
    return f"loop-f510-{suffix}"


async def _task(task_id, *, loop_id, status="completed"):
    async with async_session_factory() as db:
        db.add(
            Task(
                id=task_id,
                project_id="proj-test",
                loop_id=loop_id,
                title=f"t {task_id}",
                status=status,
                assignee=WORKER,
            )
        )
        await db.commit()
    return task_id


async def _evidence(task_id, sha):
    async with async_session_factory() as db:
        db.add(
            SpecRequirement(
                id=f"req-f510-{task_id}",
                project_id="proj-test",
                document_id=f"doc-f510-{task_id}",
                identifier="FR-1",
                key="fr-1",
                digest="d" * 64,
            )
        )
        db.add(
            RequirementEvidence(
                id=f"ev-f510-{task_id}",
                project_id="proj-test",
                requirement_id=f"req-f510-{task_id}",
                task_id=task_id,
                digest="d" * 64,
                kind="artifact_diff",
                actor_kind="operator",
                actor="operator-x",
                summary="did it",
                review_state="awaiting",
            )
        )
        db.add(
            EvidenceFootprint(
                id=f"fp-f510-{task_id}",
                project_id="proj-test",
                evidence_id=f"ev-f510-{task_id}",
                kind="git",
                commit_sha=sha,
                branch="main",
            )
        )
        await db.commit()


async def _repo(tmp_path, bind_project_workspace, monkeypatch):
    make_repo(tmp_path)
    await set_main_branch("main")
    await bind_project_workspace(tmp_path)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    return tmp_path


def _branch_work(repo, task_id):
    """One commit on the task's own branch; returns its sha. Main is left checked out."""
    tip = commit_on_branch(repo, worktrees.task_branch_name(task_id), "feature.py", "x = 1\n")
    git(repo, "checkout", "-q", "main")
    return tip


async def _request_review(app, auth_headers, bind_runner, task_id):
    """The reviewer is busy, so the route queues rather than starting a real runner — the 409 this
    pins comes from the route's own eligibility check, which runs before either."""
    await _roster(app, auth_headers, bind_runner, REVIEWER)
    async with async_session_factory() as db:
        db.add(Run(id="run-f510-busy", project_id="proj-test", agent=REVIEWER, status="running"))
        await db.commit()
    return await app.post(
        ROUTE,
        json={"agent": REVIEWER, "message": f"review {task_id}", "review_task_id": task_id},
        headers=auth_headers,
    )


async def _prepare(repo, task_id):
    async with async_session_factory() as db:
        return await prepare_review_turn(
            db,
            project_id="proj-test",
            reviewer=REVIEWER,
            task_id=task_id,
            repo_root=repo,
        )


def _head_of(path):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


async def test_dispatch_evidence_free_loop_task(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    loop_id = await _loop(work_needs_evidence=False)
    task_id = await _task("task-f510000000a1", loop_id=loop_id)
    tip = _branch_work(repo, task_id)

    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        merge = await task_integration.merge_targets(db, task, repo)
    assert [t.commit_sha for t in merge] == [tip], "the fixture must name the merge source"

    response = await _request_review(app, auth_headers, bind_runner, task_id)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
    assert response.json()["queue_entry_id"]


async def test_checkout_at_branch_tip(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    loop_id = await _loop(work_needs_evidence=False)
    task_id = await _task("task-f510000000a2", loop_id=loop_id)
    tip = _branch_work(repo, task_id)

    context = await _prepare(repo, task_id)

    assert context.commit_sha == tip
    assert _head_of(context.workspace) == tip


async def test_undeclared_loop_no_link(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    loop_id = await _loop(work_needs_evidence=None)
    task_id = await _task("task-f510000000a3", loop_id=loop_id)
    tip = _branch_work(repo, task_id)

    async with async_session_factory() as db:
        assert not await task_integration.evidence_governs(db, await db.get(Task, task_id))
    context = await _prepare(repo, task_id)

    assert context.commit_sha == tip
    assert _head_of(context.workspace) == tip


async def test_ordinary_task_with_evidence(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    task_id = await _task("task-f510000000a4", loop_id=None)
    c = _head_of(repo)
    await _evidence(task_id, c)
    # A branch that differs from C: the target is the evidence, not the branch.
    _branch_work(repo, task_id)

    context = await _prepare(repo, task_id)
    assert context.commit_sha == c


async def test_ordinary_task_without_evidence_is_refused_as_today(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    task_id = await _task("task-f510000000a5", loop_id=None)
    _branch_work(repo, task_id)

    response = await _request_review(app, auth_headers, bind_runner, task_id)

    assert response.status_code == 409, response.text
    assert NO_EVIDENCE_WORDS in response.json()["detail"]


async def test_flow_task_unchanged(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    loop_id = await _loop(work_needs_evidence=None, document=True, suffix="flow")
    task_id = await _task("task-f510000000a6", loop_id=loop_id)
    _branch_work(repo, task_id)

    async with async_session_factory() as db:
        assert await task_integration.evidence_governs(db, await db.get(Task, task_id))
    response = await _request_review(app, auth_headers, bind_runner, task_id)

    assert response.status_code == 409, response.text
    assert NO_EVIDENCE_WORDS in response.json()["detail"]
    with pytest.raises(ReviewTurnRefused, match=NO_EVIDENCE_WORDS):
        await _prepare(repo, task_id)


async def test_never_committed(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    loop_id = await _loop(work_needs_evidence=False)
    task_id = await _task("task-f510000000a7", loop_id=loop_id)  # no branch is created

    response = await _request_review(app, auth_headers, bind_runner, task_id)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "no branch" in detail, detail
    assert NO_EVIDENCE_WORDS not in detail
    with pytest.raises(ReviewTurnRefused) as refused:
        await _prepare(repo, task_id)
    assert "no branch" in str(refused.value)
    assert NO_EVIDENCE_WORDS not in str(refused.value)


async def test_flow_staffing_gate_reads_the_branch_tip(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """`decide_firing`'s "is there a commit to review" gate shares the resolver: a task whose merge
    is not governed by evidence is selected for review on its branch tip, not reported unstaffed
    for missing evidence."""
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    loop_id = await _loop(work_needs_evidence=False, document=True, suffix="gate")
    task_id = await _task("task-f510000000a8", loop_id=loop_id, status="pending")
    _branch_work(repo, task_id)
    async with async_session_factory() as db:
        await _completed_by(db, await db.get(Task, task_id), agent=WORKER)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop_id), default_agent=WORKER)

    assert not decision.unstaffed
    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (task_id, REVIEWER, True)
    ]


async def test_queued_review_counts_where_the_branch_tip_resolves(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """`other_input_would_have_run_elsewhere` asks the same resolver whether a queued review could
    have started: an evidence-free task with a branch can, one with no branch cannot."""
    from hub.db.models import Conversation

    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    loop_id = await _loop(work_needs_evidence=False)
    with_branch = await _task("task-f510000000a9", loop_id=loop_id)
    without_branch = await _task("task-f510000000b0", loop_id=loop_id)
    _branch_work(repo, with_branch)

    async def _asks(task_id, conversation_id):
        async with async_session_factory() as db:
            db.add(
                Conversation(
                    id=conversation_id, project_id="proj-test", agent=REVIEWER, lifecycle="open"
                )
            )
            entry = new_entry(
                project_id="proj-test",
                agent=REVIEWER,
                origin_type="operator",
                content="review",
                hop_depth=0,
                conversation_id=conversation_id,
                review_task_id=task_id,
            )
            db.add(entry)
            await db.commit()
            return await other_input_would_have_run_elsewhere(
                db,
                project_id="proj-test",
                agent=REVIEWER,
                entries=[entry],
                selected=[],
                controlling_conversation_id="conv-f510-controlling",
                hop_budget=6,
            )

    assert await _asks(with_branch, "conv-f510-a") is True
    assert await _asks(without_branch, "conv-f510-b") is False
