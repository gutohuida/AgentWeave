"""`a-flow-stages-its-review-in-the-dispatch` (F327, F437) -- group 1.

A flow used to stage a review (`completed -> under_review`, the reviewer written into `assignee`)
and commit it **before** the dispatch, so a dispatch refused afterwards (a pruned commit, an
obstructed checkout) left the task held by a reviewer that never ran: F327's measured row. The
dispatch already stages every review entry under its own rollback; the flow now leaves it to it.

The success-path tests replace `_execute_run` with a no-op, so the run a dispatch creates stays
`running` and the state each test reads is the one the dispatch committed -- not whatever the
run-end evaluation of a fake run that recorded no verdict would make of it.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    InboundQueueEntry,
    JobRun,
    Loop,
    RequirementEvidence,
    Run,
    Task,
    TaskTransition,
)
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import bind_run_to_task
from hub.scheduler import (
    DECISION_CLAIM,
    DECISION_IN_FLIGHT,
    DECISION_STALLED,
    JobScheduler,
    _agents_that_are_free,
    decide_firing,
)
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator, run_actor
from hub.turn_scheduler import schedule_agent

from .test_agent_trigger import _init_repo
from .test_flow_fires_a_review_turn import _attribute_completion, _flow
from .test_review_divergence import _review_run_that_said_nothing
from .test_review_turn import (
    _REAL_ENSURE_REVIEW_CHECKOUT,
    _author_commit,
    _reviewable_task,
    _roster,
)

pytestmark = pytest.mark.asyncio

AUTHOR = "builder"
REVIEWER = "critic"
MISSING = "e" * 40
TASK = "task-1"


async def _setup(
    app,
    auth_headers,
    bind_runner,
    bind_project_workspace,
    tmp_path,
    monkeypatch,
    *,
    leg="B1",
    names=(AUTHOR, REVIEWER),
    suffix="x",
    flow=True,
):
    """A completed task by `builder` with evidence, adopted into a flow (or a documentless loop).

    B1: the evidence names a commit the repository lacks. B2: the commit exists but `critic`'s
    review checkout path is a plain directory. `None`: a reviewable commit, nothing obstructed.
    """
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, *names)
    await _reviewable_task(commit=MISSING if leg == "B1" else sha)
    if leg == "B2":
        obstruction = repo / ".agentweave" / "reviews" / REVIEWER
        obstruction.mkdir(parents=True)
        (obstruction / "x.txt").write_text("x")
    async with async_session_factory() as db:
        await _attribute_completion(db, TASK, AUTHOR)
        (await db.get(Task, TASK)).assignee = AUTHOR
        await db.commit()
        if flow:
            job, loop = await _flow(db, suffix=suffix, task_id=TASK)
        else:
            job, loop = await _documentless_loop(db, suffix=suffix)
    return job, loop


async def _documentless_loop(db, *, suffix):
    job = AIJob(
        id=f"job-loop-{suffix}",
        project_id="proj-test",
        name=f"Loop {suffix}",
        agent=AUTHOR,
        message="keep going",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(id=f"loop-{suffix}", project_id="proj-test", job_id=job.id, purpose="loop")
    db.add(loop)
    await db.commit()
    task = await db.get(Task, TASK)
    task.loop_id = loop.id
    await db.commit()
    return job, loop


def _launchable():
    """Every spawn-side seam a real dispatch reaches, with the run itself a no-op."""
    return (
        patch("hub.api.v1.agent_trigger.PtySession.spawn"),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.api.v1.agent_trigger._execute_run", new=AsyncMock(return_value=None)),
    )


async def _fire(job_id, *, busy=None):
    """Fire the job once. *busy*: that agent starts a turn between the firing's decision and its
    dispatch, so the dispatch is deferred (the reviewer is mid-turn) rather than refused."""
    import hub.turn_scheduler as turn_scheduler

    real = turn_scheduler.schedule_agent

    async def _starting_first(project_id, agent, *args, **kwargs):
        if agent == busy:
            await _running_run(busy)
        return await real(project_id, agent, *args, **kwargs)

    a, b, c = _launchable()
    with a, b, c, patch.object(turn_scheduler, "schedule_agent", _starting_first):
        async with async_session_factory() as db:
            await JobScheduler()._fire_job_internal(
                await db.get(AIJob, job_id), trigger="scheduled", session=db
            )


async def _dispatch(agent):
    a, b, c = _launchable()
    with a, b, c:
        return await schedule_agent("proj-test", agent)


async def _task_state(task_id=TASK):
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        count = await db.scalar(
            select(func.count())
            .select_from(TaskTransition)
            .where(TaskTransition.task_id == task_id)
        )
        return task.status, task.assignee, count


async def _entries(agent=None):
    async with async_session_factory() as db:
        query = select(InboundQueueEntry).order_by(InboundQueueEntry.sequence)
        if agent is not None:
            query = query.where(InboundQueueEntry.agent == agent)
        return list((await db.execute(query)).scalars().all())


async def _decide(loop_id):
    async with async_session_factory() as db:
        return await decide_firing(db, await db.get(Loop, loop_id), default_agent=AUTHOR)


async def _job_runs(job_id):
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
        )


async def _running_run(agent, run_id=None, task_id=None):
    async with async_session_factory() as db:
        run = Run(
            id=run_id or f"run-busy-{agent}", project_id="proj-test", agent=agent, status="running"
        )
        db.add(run)
        await db.flush()
        if task_id is not None:
            await bind_run_to_task(db, run, await db.get(Task, task_id))
        await db.commit()
        return run.id


async def _end_run(run_id):
    async with async_session_factory() as db:
        (await db.get(Run, run_id)).status = "completed"
        await db.commit()


# ---------------------------------------------------------------------------
# 1.1 / 1.2 -- D1: a refused dispatch leaves the task as the author left it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("leg", ["B1", "B2"])
async def test_a_refused_flow_review_leaves_the_task_with_its_author(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg
):
    job, _loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=leg
    )
    before = await _task_state()

    await _fire(job.id)

    status, assignee, count = await _task_state()
    assert (status, assignee) == ("completed", before[1]), (
        "F327: the flow staged the review before the dispatch and the refusal left the reviewer "
        "named on a review that never ran"
    )
    assert count == before[2], "no transition for a review that did not start"
    [entry] = await _entries(REVIEWER)
    assert entry.review_task_id == TASK
    assert entry.state == "queued"
    assert entry.delivery_attempts == 1
    assert entry.waiting_reason
    [job_run] = await _job_runs(job.id)
    assert job_run.status == "failed"
    assert job_run.error_summary


# ---------------------------------------------------------------------------
# 1.3 -- D2: the next firing names the refusal instead of re-staffing or calling it in flight
# ---------------------------------------------------------------------------


async def test_a_refused_flow_review_stalls_the_next_firing_with_its_refusal(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _fire(job.id)
    [entry] = await _entries(REVIEWER)

    decision = await _decide(loop.id)

    assert decision.kind == DECISION_STALLED
    assert not decision.selections
    task_id, sentence = decision.unstaffed[0]
    assert task_id == TASK
    assert REVIEWER in sentence
    assert entry.waiting_reason[:40] in sentence
    assert "withdraw that input" in sentence


# ---------------------------------------------------------------------------
# 1.4 -- F327's 409 row: the operator's other reviewer is not refused
# ---------------------------------------------------------------------------


async def test_the_operators_other_reviewer_is_not_refused_after_a_refused_flow_review(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, _loop = await _setup(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        leg="B2",
        names=(AUTHOR, REVIEWER, "other"),
    )
    await _fire(job.id)
    before = await _task_state()

    a, b, c = _launchable()
    with a, b, c:
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "other", "message": "review it", "review_task_id": TASK},
            headers=auth_headers,
        )

    assert response.status_code != 409, response.text
    assert "already under review" not in response.text
    status, assignee, count = await _task_state()
    assert (status, assignee) == ("under_review", "other")
    assert count == before[2] + 1


# ---------------------------------------------------------------------------
# 1.5 / 1.5b / 1.7 / 1.12 -- a review dispatch deferred because the reviewer is mid-turn
# ---------------------------------------------------------------------------


async def test_a_deferred_flow_review_is_in_flight_and_not_staged(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=None
    )
    await _fire(job.id, busy=REVIEWER)

    assert (await _task_state())[:2] == ("completed", AUTHOR)
    [entry] = await _entries(REVIEWER)
    assert entry.state == "queued"
    assert not entry.delivery_attempts
    decision = await _decide(loop.id)
    assert decision.kind == DECISION_IN_FLIGHT
    assert (TASK, REVIEWER) in decision._cannot_staff

    await _fire(job.id)
    assert len(await _entries(REVIEWER)) == 1, "a second firing queued a second review"


async def test_a_deferred_flow_review_refused_at_the_re_drain_stalls_with_its_refusal(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _fire(job.id, busy=REVIEWER)
    await _end_run(f"run-busy-{REVIEWER}")

    await _dispatch(REVIEWER)

    assert (await _task_state())[:2] == ("completed", AUTHOR)
    [entry] = await _entries(REVIEWER)
    assert entry.state == "queued"
    assert entry.delivery_attempts == 1
    assert entry.waiting_reason
    decision = await _decide(loop.id)
    assert decision.kind == DECISION_STALLED
    assert REVIEWER in decision.stall_reason
    assert "withdraw that input" in decision.stall_reason
    # Pre-existing, recorded rather than changed (design: what the operator sees): no run path
    # finalizes a firing's JobRun for a refusal at the re-drain.
    [job_run] = await _job_runs(job.id)
    assert job_run.status == "in_progress"


async def test_a_reviewer_with_a_waiting_review_turn_is_not_free(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, _loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=None
    )
    await _fire(job.id, busy=REVIEWER)
    await _end_run(f"run-busy-{REVIEWER}")
    assert (await _task_state())[:2] == ("completed", AUTHOR)

    async with async_session_factory() as db:
        free = await _agents_that_are_free(db, "proj-test")

    assert (
        REVIEWER not in free
    ), "critic holds no under_review task and is not running, but its review turn is waiting"


async def test_the_review_briefing_names_the_status_the_reviewer_will_find(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, _loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=None
    )
    await _fire(job.id, busy=REVIEWER)

    [entry] = await _entries(REVIEWER)
    assert "The task is `under_review`" in entry.content


# ---------------------------------------------------------------------------
# 1.6 -- withdrawing the refused entry lets the flow staff the review again
# ---------------------------------------------------------------------------


async def test_withdrawing_the_refused_review_lets_the_ladder_run_again(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _fire(job.id)
    [entry] = await _entries(REVIEWER)

    response = await app.delete(
        f"/api/v1/projects/proj-test/queue/entries/{entry.id}", headers=auth_headers
    )
    assert response.status_code == 200, response.text

    decision = await _decide(loop.id)
    assert decision.kind == DECISION_CLAIM
    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (TASK, REVIEWER, True)
    ]


# ---------------------------------------------------------------------------
# 1.8 / 1.9 / 1.10 -- D5: the restaff, and the holder check it must pass
# ---------------------------------------------------------------------------


async def _silent_review_by_beta():
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        await _review_run_that_said_nothing(db, "run-beta-silent", task, reviewer="beta")


async def _restaff_without_dispatching(run_id):
    """`evaluate_run_end`, with the response's own immediate dispatch held back, so the state
    between the restaff and its dispatch can be read; the test then dispatches it itself."""
    with patch("hub.turn_scheduler.schedule_agent", new=AsyncMock(return_value=None)):
        return await evaluate_run_end(run_id)


async def test_a_restaff_leaves_the_silent_reviewer_named_until_its_replacement_is_dispatched(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _setup(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        leg=None,
        names=(AUTHOR, "beta", "gamma"),
    )
    await _silent_review_by_beta()
    assert await _restaff_without_dispatching("run-beta-silent") is not None
    before = await _task_state()

    assert before[:2] == ("under_review", "beta"), "the restaff does not reassign before dispatch"
    [response_entry] = await _entries("gamma")
    assert response_entry.origin_type == "divergence"
    assert response_entry.state == "queued"

    await _dispatch("gamma")

    status, assignee, count = await _task_state()
    assert (status, assignee) == ("under_review", "gamma")
    assert count == before[2], "a handover inside under_review travels no transition"


async def test_a_refused_restaff_leaves_the_silent_reviewer_and_surfaces_the_refusal(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    _job, loop = await _setup(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        names=(AUTHOR, "beta", "gamma"),
    )
    await _silent_review_by_beta()
    assert await _restaff_without_dispatching("run-beta-silent") is not None

    await _dispatch("gamma")

    assert (await _task_state())[:2] == ("under_review", "beta")
    [entry] = await _entries("gamma")
    assert entry.delivery_attempts == 1 and entry.waiting_reason
    decision = await _decide(loop.id)
    sentences = " ".join(sentence for _, sentence in decision.unstaffed)
    assert "gamma" in sentences
    assert entry.waiting_reason[:40] in sentences


async def test_a_plain_request_for_a_task_a_silent_reviewer_holds_is_still_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Control: option (ii), not (iii). Only a recorded restaff replaces a reviewer holder."""
    await _setup(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        leg=None,
        names=(AUTHOR, "beta", "delta"),
    )
    await _silent_review_by_beta()

    a, b, c = _launchable()
    with a, b, c:
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "delta", "message": "review it", "review_task_id": TASK},
            headers=auth_headers,
        )

    assert response.status_code == 409
    assert "already under review by 'beta'" in response.text
    assert (await _task_state())[:2] == ("under_review", "beta")


# ---------------------------------------------------------------------------
# 1.11 / 1.11b / 1.11c -- D5: an author holder is replaced, and only where it is not attending
# ---------------------------------------------------------------------------


async def _wedge_with_the_author():
    """F70's row: `under_review`, held by the agent recorded as completing it."""
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        task.status = "under_review"
        task.assignee = AUTHOR
        await db.commit()


async def test_the_flows_recovery_replaces_a_wedged_author_at_the_dispatch(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=None
    )
    await _wedge_with_the_author()
    before = await _task_state()
    decision = await _decide(loop.id)
    assert [(s.agent, s.is_review) for s in decision.selections] == [(REVIEWER, True)]

    await _fire(job.id)

    status, assignee, count = await _task_state()
    assert (status, assignee) == ("under_review", REVIEWER)
    assert count == before[2]


async def test_the_operator_may_send_a_reviewer_to_a_task_its_author_holds_in_review(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=None
    )
    await _wedge_with_the_author()

    a, b, c = _launchable()
    with a, b, c:
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": REVIEWER, "message": "review it", "review_task_id": TASK},
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    assert (await _task_state())[:2] == ("under_review", REVIEWER)


async def test_f142s_row_is_recovered_by_the_wedge_rule_at_the_dispatch(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """The agent moved the task through `in_progress`; the operator recorded `completed` and then
    `under_review` with it still assignee; it recorded no evidence. The entry guard's rule calls
    that holder "not the author" and would refuse every dispatch."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)
    async with async_session_factory() as db:
        evidence = await db.get(RequirementEvidence, "ev-1")
        evidence.actor_kind = "operator"
        evidence.actor = "operator"
        task = await db.get(Task, TASK)
        task.status = "pending"
        task.assignee = AUTHOR
        await db.commit()
        await apply_transition(db, task, "in_progress", run_actor("run-f142", AUTHOR))
        await apply_transition(db, task, "completed", operator())
        await apply_transition(db, task, "under_review", operator())
        await db.commit()
        job, loop = await _flow(db, suffix="f142", task_id=TASK)
    before = await _task_state()
    assert before[:2] == ("under_review", AUTHOR)

    import hub.task_transition_service as service

    real = service.assignee_produced_the_work
    calls = []

    async def _spy(session, task):
        calls.append(task.id)
        return await real(session, task)

    monkeypatch.setattr(service, "assignee_produced_the_work", _spy)

    await _fire(job.id)

    status, assignee, count = await _task_state()
    assert (status, assignee) == ("under_review", REVIEWER)
    assert count == before[2]
    assert len(calls) >= 2, "decide_firing and the holder check ask the one shared predicate"


async def test_an_attending_evidence_author_holding_a_review_is_not_replaced(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Fold-in (operator 2026-09-24): an author holder is replaceable only where not attending."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "alpha", "beta")
    await _reviewable_task(commit=sha)
    async with async_session_factory() as db:
        evidence = await db.get(RequirementEvidence, "ev-1")
        evidence.actor = "alpha"
        task = await db.get(Task, TASK)
        task.status = "in_progress"
        await db.commit()
        await apply_transition(db, task, "completed", operator())
        task.assignee = "alpha"
        task.status = "under_review"
        await db.commit()
        job, loop = await _flow(db, suffix="attending", task_id=TASK)
    await _running_run("alpha", run_id="run-alpha-reviewing", task_id=TASK)
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        task.status = "under_review"
        task.assignee = "alpha"
        await db.commit()

    a, b, c = _launchable()
    with a, b, c:
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": "beta", "message": "review it", "review_task_id": TASK},
            headers=auth_headers,
        )
    assert response.status_code == 409
    assert "already under review by 'alpha'" in response.text
    assert (await _task_state())[:2] == ("under_review", "alpha")

    decision = await _decide(loop.id)
    assert not decision.selections, "the recovery waits for alpha's turn to end"
    assert (TASK, "alpha") in decision._cannot_staff


# ---------------------------------------------------------------------------
# 1.13 / 1.14 -- D2: an operator's waiting review turn keeps the task out of the pool
# ---------------------------------------------------------------------------


async def _operator_requests_review_while_reviewer_busy(app, auth_headers):
    """The row `POST /agent/trigger` leaves when the reviewer is mid-turn: an operator entry,
    queued, naming the task under review. Written directly because whether the route accepts the
    request depends on the review target, which is not what these tests are about."""
    await _running_run(REVIEWER)
    async with async_session_factory() as db:
        db.add(
            InboundQueueEntry(
                id="entry-operator-review",
                project_id="proj-test",
                agent=REVIEWER,
                origin_type="operator",
                content="review it",
                hop_depth=0,
                state="queued",
                review_task_id=TASK,
            )
        )
        await db.commit()


async def test_a_documentless_loops_task_with_a_waiting_review_is_in_flight(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    _job, loop = await _setup(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        leg=None,
        flow=False,
    )
    await _operator_requests_review_while_reviewer_busy(app, auth_headers)

    decision = await _decide(loop.id)

    assert decision.kind == DECISION_IN_FLIGHT
    assert (TASK, REVIEWER) in decision._cannot_staff


async def test_a_flows_task_with_a_waiting_operator_review_gets_no_second_reviewer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    _job, loop = await _setup(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        monkeypatch,
        leg=None,
        names=(AUTHOR, REVIEWER, "other"),
    )
    await _operator_requests_review_while_reviewer_busy(app, auth_headers)

    decision = await _decide(loop.id)

    assert not [s for s in decision.selections if s.task.id == TASK]
    assert (TASK, REVIEWER) in decision._cannot_staff


# ---------------------------------------------------------------------------
# 1.14b -- D4's status filter: a decided task's waiting entry books nobody
# ---------------------------------------------------------------------------


async def test_a_review_entry_left_on_a_decided_task_does_not_book_its_reviewer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, _loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=None
    )
    await _fire(job.id, busy=REVIEWER)
    await _end_run(f"run-busy-{REVIEWER}")
    async with async_session_factory() as db:
        (await db.get(Task, TASK)).status = "approved"
        await db.commit()

    async with async_session_factory() as db:
        free = await _agents_that_are_free(db, "proj-test")

    assert REVIEWER in free


# ---------------------------------------------------------------------------
# 1.14c -- the review staged at the dispatch is still recorded as the flow's move
# ---------------------------------------------------------------------------


async def test_a_flow_review_staged_at_the_dispatch_is_recorded_as_the_flows(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job, _loop = await _setup(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch, leg=None
    )

    await _fire(job.id)

    async with async_session_factory() as db:
        row = (
            (
                await db.execute(
                    select(TaskTransition)
                    .where(
                        TaskTransition.task_id == TASK, TaskTransition.to_status == "under_review"
                    )
                    .order_by(TaskTransition.sequence)
                )
            )
            .scalars()
            .one()
        )
    assert (row.origin, row.job_id) == ("job", job.id)
    assert (await _task_state())[:2] == ("under_review", REVIEWER)
