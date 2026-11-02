"""A flow's task that serves no requirement is reviewed and landed at its branch tip.

Measured on the trial Hub, 2026-11-01 (d1101, build-bbeba7a46fe7): an author submitted a document
with `requirements: []`, the operator approved it anyway, and a builder completed the first task
with no evidence, because there was no requirement to record any against. Every firing then answered
409 "no recorded evidence" and the task depending on it stayed pending: 15 firings in five minutes,
on a build that could never finish.

`review_alone_gates` already answers this for a task with no loop (F622); the flow arm of
`evidence_governs` is what still answered "evidence decides" for a task no evidence could reach.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import task_integration
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    JobRun,
    Loop,
    SpecRequirement,
    Task,
    TaskDependency,
    TaskRequirementLink,
    TaskTransition,
)
from hub.scheduler import JobScheduler, decide_firing

from .test_a_flow_names_what_it_cannot_staff import _roster
from .test_a_loop_does_not_staff_its_own_review import _completed_by
from .test_a_review_turn_reviews_the_branch_tip import (
    NO_EVIDENCE_WORDS,
    REVIEWER,
    WORKER,
    _branch_work,
    _evidence,
    _head_of,
    _loop,
    _prepare,
    _repo,
    _task,
)
from .test_task_integration import approve, commits_on, integrations

pytestmark = pytest.mark.asyncio


@pytest.fixture
def live_scheduler(monkeypatch):
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _completed_flow_task(task_id, *, suffix):
    """A flow on a document with no requirements, and its task walked to `completed`."""
    loop_id = await _loop(work_needs_evidence=None, document=True, suffix=suffix)
    await _task(task_id, loop_id=loop_id, status="pending")
    async with async_session_factory() as db:
        await _completed_by(db, await db.get(Task, task_id), agent=WORKER)
    return loop_id


async def _decide(loop_id):
    async with async_session_factory() as db:
        return await decide_firing(db, await db.get(Loop, loop_id), default_agent=WORKER)


async def test_the_firing_selects_its_review_at_the_branch_tip(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The reproduction: a prerequisite nobody could review held the task behind it forever."""
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    task_id = "task-f1101000000a"
    loop_id = await _completed_flow_task(task_id, suffix="stall")
    tip = _branch_work(repo, task_id)
    await _task("task-f1101000000b", loop_id=loop_id, status="pending")
    async with async_session_factory() as db:
        db.add(
            TaskDependency(
                id="dep-f1101",
                project_id="proj-test",
                task_id="task-f1101000000b",
                depends_on_task_id=task_id,
            )
        )
        await db.commit()

    decision = await _decide(loop_id)

    assert not decision.unstaffed, decision.unstaffed
    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (task_id, REVIEWER, True)
    ]
    context = await _prepare(repo, task_id)
    assert context.commit_sha == tip
    assert _head_of(context.workspace) == tip


async def test_approving_it_lands_the_work(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Reaching review is not enough: an approval that merged nothing would strand the work."""
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    task_id = "task-f1101000000c"
    # Left pending: `approve` walks the task through the transitions itself.
    loop_id = await _loop(work_needs_evidence=None, document=True, suffix="land")
    await _task(task_id, loop_id=loop_id, status="pending")
    tip = _branch_work(repo, task_id)

    approved = await approve(app, auth_headers, task_id)

    assert approved.status_code == 200, approved.text
    recorded = await integrations(app, auth_headers, task_id)
    assert [row["outcome"] for row in recorded] == [task_integration.MERGED], recorded
    assert tip in commits_on(repo, "main")


async def test_with_no_commit_the_operator_is_told_that_and_not_to_record_evidence(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The other half of the criterion: what cannot reach review says what is actually stuck."""
    await _repo(tmp_path, bind_project_workspace, monkeypatch)
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    task_id = "task-f1101000000d"
    loop_id = await _completed_flow_task(task_id, suffix="nobranch")

    decision = await _decide(loop_id)

    assert not decision.selections
    assert [entry[0] for entry in decision.unstaffed] == [task_id]
    reason = decision.unstaffed[0][1]
    assert "no branch to review" in reason
    assert NO_EVIDENCE_WORDS not in reason
    assert "recorded as evidence" not in reason
    assert decision.stall_reason == reason


async def test_a_task_that_serves_a_requirement_still_needs_its_evidence(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The boundary: a link means evidence can be recorded, so the refusal still stands."""
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    task_id = "task-f1101000000e"
    loop_id = await _completed_flow_task(task_id, suffix="linked")
    _branch_work(repo, task_id)
    async with async_session_factory() as db:
        db.add(
            SpecRequirement(
                id="req-f1101-linked",
                project_id="proj-test",
                document_id="doc-f510-linked",
                identifier="FR-1",
                key="fr-1",
                digest="d" * 64,
            )
        )
        db.add(
            TaskRequirementLink(
                id="link-f1101",
                project_id="proj-test",
                task_id=task_id,
                requirement_id="req-f1101-linked",
            )
        )
        await db.commit()

    decision = await _decide(loop_id)

    assert not decision.selections
    assert NO_EVIDENCE_WORDS in decision.unstaffed[0][1]


async def test_evidence_already_recorded_keeps_deciding(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """D10: the merge source is not switched once evidence exists, link or no link."""
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    task_id = "task-f1101000000f"
    await _completed_flow_task(task_id, suffix="evidence")
    named = _head_of(repo)
    await _evidence(task_id, named)
    _branch_work(repo, task_id)

    context = await _prepare(repo, task_id)

    assert context.commit_sha == named


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_the_job_route_no_longer_answers_409(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, live_scheduler
):
    """The seam the finding names: `POST /jobs/{id}/run` answered 409 on every firing.

    `which` is faked so the reviewer's runner resolves: without it the review turn waits for a
    `claude` on PATH and the task stays `completed`, which passed only on machines that have one
    (CI run 41463365902: "Runner CLI 'claude' was not found in PATH."). No CLI is spawned."""
    repo = await _repo(tmp_path, bind_project_workspace, monkeypatch)
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    task_id = "task-f11010000010"
    loop_id = await _completed_flow_task(task_id, suffix="route")
    _branch_work(repo, task_id)
    async with async_session_factory() as db:
        job_id = (await db.get(Loop, loop_id)).job_id
        (await db.get(AIJob, job_id)).enabled = True
        await db.commit()

    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        fired = await app.post(
            f"/api/v1/projects/proj-test/jobs/{job_id}/run", headers=auth_headers
        )

    assert fired.status_code < 300, fired.text
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
    if (task.status, task.assignee) != ("under_review", REVIEWER):
        pytest.fail(await _why_no_review(loop_id, job_id, task_id, fired))


async def _why_no_review(loop_id, job_id, task_id, fired):
    """Everything that says why a firing staged no review: fails only on CI's runner, where the
    route answers 2xx and the task stays `completed` (2026-11-02, CI run 41421652793)."""
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        transitions = (
            (
                await db.execute(
                    select(TaskTransition)
                    .where(TaskTransition.task_id == task_id)
                    .order_by(TaskTransition.sequence)
                )
            )
            .scalars()
            .all()
        )
        job_runs = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
    decision = await _decide(loop_id)
    return "\n".join(
        [
            f"task: status={task.status!r} assignee={task.assignee!r}",
            f"route: {fired.status_code} {fired.text}",
            "transitions: "
            + repr(
                [
                    (t.from_status, t.to_status, t.actor_kind, t.actor_agent, t.origin, t.reason)
                    for t in transitions
                ]
            ),
            "job runs: " + repr([(r.status, r.trigger, r.error_summary) for r in job_runs]),
            f"decision now: kind={decision.kind!r} stall={decision.stall_reason!r}",
            "  selections: "
            + repr([(s.task.id, s.agent, s.is_review) for s in decision.selections]),
            f"  unstaffed: {decision.unstaffed!r}",
            f"  deferred: {decision.deferred!r}",
            f"  cannot staff: {decision._cannot_staff!r}",
            f"  checks waits: {decision.checks_waits!r}",
            f"  approvals: {decision.approvals!r}",
        ]
    )
