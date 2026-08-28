"""A review that gave no verdict — `one-answer-to-what-is-happening`, group 2 (D3–D6).

`test_run_divergence.py` covers a **work** run that dropped its task. These cover the case that
could not exist until this change: a bound *review* reaching the run boundary.

Two régimes now arrive at that boundary and they must not be confused, because the confusion is the
whole defect. A work run answers to its task's `divergence_policy` — surface, retry, escalate. A
review answers to the reviewer resolution instead (D3): re-running the same reviewer on the same
evidence and the same briefing is the least likely intervention to change the outcome, and the
observed causes are deterministic rather than flaky. `escalate` would be a *second* reviewer
resolution, which `agent-flows` forbids in terms — *"by the same resolution the rest of the product
already uses for a declared reviewer, never a second one."*

So a review takes D4's split instead:

```
  reviewer was DECLARED   ──▶ surface. Never substitute.
  reviewer was AVAILABLE  ──▶ resolve again, excluding everyone already silent on this task
```
"""

import pytest
from sqlalchemy import select

from hub.conversations import get_conversation_by_id, new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EventLog,
    InboundQueueEntry,
    Run,
    RunDivergence,
    SpecDocument,
    Task,
)
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT, return_run_entries
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import bind_run_to_task
from hub.spec_payload import SCHEMA_VERSION, embed_payload
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_agent_trigger import _init_repo
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

AUTHOR = "rev-author"


async def _declare_reviewer(repo, db, *, name, document_id="doc-revdiv"):
    """A document on disk declaring *name* as the reviewer of task key `t1`.

    Written with the real `embed_payload`, matching `test_reviewer_ladder.py`: a fixture that fakes
    the envelope stops testing the thing that reads it the moment the envelope changes.
    """
    document = repo / "spec" / "revdiv.html"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        embed_payload(
            {"schema_version": SCHEMA_VERSION, "tasks": [{"key": "t1", "reviewer": name}]}
        ),
        encoding="utf-8",
    )
    db.add(
        SpecDocument(
            id=document_id,
            project_id="proj-test",
            path="spec/revdiv.html",
            title="Review divergence",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()


async def _completed_by_the_author(
    db,
    task_id: str,
    *,
    policy: str = "surface",
    escalation_agent: str | None = None,
    document_id: str | None = None,
    task_key: str | None = None,
) -> Task:
    """A task the author genuinely moved to `completed`, then a reviewer was staffed onto.

    The completion goes through `apply_transition` with a run actor rather than being written
    directly, because `agent_that_completed` reads the transition history — and that history is
    what bars the author from reviewing its own work. A fixture that set `status` by hand would
    leave the author eligible and quietly test a different product.
    """
    task = Task(
        id=task_id,
        project_id="proj-test",
        title="finished work awaiting a verdict",
        status="pending",
        divergence_policy=policy,
        escalation_agent=escalation_agent,
        spec_document_id=document_id,
        spec_task_key=task_key,
    )
    db.add(task)
    authoring_run = Run(
        id=f"run-authored-{task_id}", project_id="proj-test", agent=AUTHOR, status="completed"
    )
    db.add(authoring_run)
    await db.flush()
    await bind_run_to_task(db, authoring_run, task)
    await apply_transition(db, task, "completed", run_actor(authoring_run.id, AUTHOR))
    await db.commit()
    return task


async def _review_run_that_said_nothing(db, run_id: str, task: Task, *, reviewer: str) -> Run:
    """A staffed review turn that ended having recorded no verdict.

    Built the way the product builds one: the task enters `under_review` with the reviewer as its
    assignee (what `enter_selected_task` does for every staged review), and the entry delivered to
    the run carries `review_task_id` and no `task_id` — which is exactly the shape that made every
    review run in this product's history unbound before D1.

    **The assignee is written before the transition, and the order is now load-bearing** (finding
    F70). `_guard_reviewer_is_not_the_author` refuses `-> under_review` while the task still names
    the agent that completed it, which is what `assignee` holds until this line runs. Writing it
    afterwards — as this fixture did, and as `enter_selected_task` itself did — meant the guard saw
    the author and refused a review the product had staffed correctly. Both moved together, so this
    fixture keeps meaning what its first paragraph claims.
    """
    task.assignee = reviewer
    await apply_transition(db, task, "under_review", run_actor(f"run-stage-{task.id}", reviewer))
    run = Run(id=run_id, project_id="proj-test", agent=reviewer, status="completed")
    db.add(run)
    await db.flush()
    db.add(
        InboundQueueEntry(
            id=f"entry-{run_id}",
            project_id="proj-test",
            agent=reviewer,
            origin_type="job",
            content="Review the work",
            hop_depth=0,
            state="delivered",
            delivered_in_run_id=run_id,
            review_task_id=task.id,
        )
    )
    await bind_run_to_task(db, run, task)
    await db.commit()
    return run


async def _divergence(run_id: str) -> RunDivergence | None:
    async with async_session_factory() as db:
        result = await db.execute(select(RunDivergence).where(RunDivergence.run_id == run_id))
        return result.scalars().first()


async def _divergence_responses(agent: str | None = None) -> list[InboundQueueEntry]:
    async with async_session_factory() as db:
        predicates = [InboundQueueEntry.origin_type == "divergence"]
        if agent is not None:
            predicates.append(InboundQueueEntry.agent == agent)
        result = await db.execute(
            select(InboundQueueEntry).where(*predicates).order_by(InboundQueueEntry.sequence)
        )
        return list(result.scalars().all())


async def _diverged_event(run_id: str) -> dict | None:
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged")))
            .scalars()
            .all()
        )
    for row in rows:
        if (row.data or {}).get("run_id") == run_id:
            return row.data
    return None


# ---------------------------------------------------------------------------
# 2.1–2.3 — the task's policy does not govern a review, and still governs work
# ---------------------------------------------------------------------------


async def test_a_failed_review_on_a_retry_task_is_not_retried(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.1. `retry` means *the agent had its full turn and moved nothing*. For a work run that is
    defensible. For a review it is close to indefensible — the same reviewer, the same evidence and
    the same briefing produce the same silence."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-rev-retry", policy="retry")
        await _review_run_that_said_nothing(db, "run-rev-retry", task, reviewer="critic")

    assert await evaluate_run_end("run-rev-retry") is not None

    divergence = await _divergence("run-rev-retry")
    assert divergence is not None
    assert (
        divergence.policy_applied == "review"
    ), "the review régime governed, not the task's policy"
    assert divergence.outcome != "retried"
    assert await _divergence_responses("critic") == [], "the reviewer was not given another turn"


async def test_a_failed_review_on_an_escalate_task_does_not_reassign_to_the_escalation_agent(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.2. `escalate` routes through `task.escalation_agent`, which is a second reviewer
    resolution. It is also D6's trap: nothing stops an operator naming the author there, and an
    agent cannot record a verdict on work it completed, so the review would be a guaranteed 403 on
    arrival.

    `escalation-target` is made **busy**, and that is what gives this test its teeth. Left free it
    would be picked by availability anyway, and the test would pass while proving nothing — the
    first draft did exactly that. Busy, the reviewer resolution will not choose it, so the only way
    it can receive anything is the task's policy reaching a review, which is what D3 forbids."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "escalation-target")

    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-esc-target-busy",
                project_id="proj-test",
                agent="escalation-target",
                status="running",
            )
        )
        task = await _completed_by_the_author(
            db, "task-rev-esc", policy="escalate", escalation_agent="escalation-target"
        )
        await _review_run_that_said_nothing(db, "run-rev-esc", task, reviewer="critic")

    assert await evaluate_run_end("run-rev-esc") is not None

    divergence = await _divergence("run-rev-esc")
    assert divergence.policy_applied == "review"
    assert divergence.outcome == "surfaced", "no rung produced an agent, so nothing was fired"
    assert await _divergence_responses("escalation-target") == []
    assert await _divergence_responses() == []

    async with async_session_factory() as db:
        task = await db.get(Task, "task-rev-esc")
        assert task.assignee == "critic", "the policy did not reassign the task"


async def test_a_work_run_on_the_same_policy_still_retries(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.3. The carve-out is for reviews, not a removal of the policy. A `retry` task whose *work*
    run drops it still gets its one further turn from the same agent."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic")

    async with async_session_factory() as db:
        task = Task(
            id="task-work-retry",
            project_id="proj-test",
            title="ordinary work",
            status="pending",
            divergence_policy="retry",
        )
        db.add(task)
        run = Run(id="run-work-retry", project_id="proj-test", agent="worker", status="completed")
        db.add(run)
        await db.flush()
        await bind_run_to_task(db, run, task)
        await db.commit()

    assert await evaluate_run_end("run-work-retry") is not None

    divergence = await _divergence("run-work-retry")
    assert divergence.policy_applied == "retry", "a work run is still governed by the task's policy"
    assert divergence.outcome == "retried"
    assert [entry.agent for entry in await _divergence_responses("worker")] == ["worker"]


# ---------------------------------------------------------------------------
# 2.4–2.7 — D4's split, and who may be resolved
# ---------------------------------------------------------------------------


async def test_a_declared_reviewer_that_gave_no_verdict_is_surfaced_never_replaced(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.4. The reasoning of rung 1b does not weaken because the named agent ran and then said
    nothing. `auditor` is free and must not be fired: telling the operator that `critic` checked
    the work when `auditor` did is the false statement 1b exists to refuse."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "auditor")

    async with async_session_factory() as db:
        await _declare_reviewer(repo, db, name="critic")
        task = await _completed_by_the_author(
            db, "task-rev-declared", document_id="doc-revdiv", task_key="t1"
        )
        await _review_run_that_said_nothing(db, "run-rev-declared", task, reviewer="critic")

    assert await evaluate_run_end("run-rev-declared") is not None

    divergence = await _divergence("run-rev-declared")
    assert divergence.policy_applied == "review"
    assert divergence.outcome == "surfaced"
    assert await _divergence_responses() == [], "no agent was fired for the review"

    payload = await _diverged_event("run-rev-declared")
    assert payload["was_review"] is True
    assert payload["agent"] == "critic", "the operator is told which declared reviewer was silent"
    assert payload["task_id"] == "task-rev-declared"
    assert "critic" in payload["reason"] and "task-rev-declared" in payload["reason"]


async def test_an_availability_picked_reviewer_that_gave_no_verdict_is_replaced(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.5. No declaration, so nothing is being misreported by choosing again — and the agent that
    said nothing is not asked twice."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "auditor")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-rev-avail")
        await _review_run_that_said_nothing(db, "run-rev-avail", task, reviewer="critic")

    assert await evaluate_run_end("run-rev-avail") is not None

    divergence = await _divergence("run-rev-avail")
    assert divergence.policy_applied == "review"
    assert divergence.outcome == "restaffed"
    assert divergence.previous_assignee == "critic"

    responses = await _divergence_responses()
    assert [entry.agent for entry in responses] == ["auditor"]
    assert await _divergence_responses("critic") == [], "the silent reviewer was excluded"

    async with async_session_factory() as db:
        task = await db.get(Task, "task-rev-avail")
        assert task.assignee == "auditor"
        assert task.status == "under_review", "restaffing is not a verdict"


async def test_a_second_failure_with_nobody_left_surfaces(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.6. The roster runs out and the flow says so rather than stalling silently. The exclusion
    that makes this terminate is derived from the divergence rows themselves — excluding only the
    agent that just failed would let `critic → auditor → critic` run forever."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "auditor")

    async with async_session_factory() as db:
        db.add(
            AIJob(
                id="job-rev-flow",
                project_id="proj-test",
                name="review flow",
                agent=AUTHOR,
                message="work the queue",
                cron="*/5 * * * *",
                enabled=True,
            )
        )
        task = await _completed_by_the_author(db, "task-rev-exhaust")
        await _review_run_that_said_nothing(db, "run-rev-exhaust-1", task, reviewer="critic")

    assert await evaluate_run_end("run-rev-exhaust-1") is not None
    assert [e.agent for e in await _divergence_responses()] == ["auditor"]

    async with async_session_factory() as db:
        task = await db.get(Task, "task-rev-exhaust")
        await _review_run_that_said_nothing(db, "run-rev-exhaust-2", task, reviewer="auditor")

    assert await evaluate_run_end("run-rev-exhaust-2") is not None

    divergence = await _divergence("run-rev-exhaust-2")
    assert divergence.outcome == "surfaced"
    assert [e.agent for e in await _divergence_responses()] == ["auditor"], "nothing new was queued"

    payload = await _diverged_event("run-rev-exhaust-2")
    assert payload["was_review"] is True
    assert payload["task_id"] == "task-rev-exhaust"
    assert payload["reason"], "the operator is told why, not merely that"

    async with async_session_factory() as db:
        job = await db.get(AIJob, "job-rev-flow")
        assert job.enabled is True, "surfacing does not stop the flow"


async def test_theagent_that_completed_the_work_is_never_restaffed_as_its_reviewer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.7, the half that is new. The first-resolution half is `test_reviewer_ladder.py`'s.

    `AUTHOR` is on the roster, free, and alphabetically ahead of nobody that matters — and is still
    not chosen, because `agent_that_completed` bars it from recording a verdict and a review it
    could not deliver is a 403 discovered one step later."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-rev-author")
        await _review_run_that_said_nothing(db, "run-rev-author", task, reviewer="critic")

    assert await evaluate_run_end("run-rev-author") is not None

    divergence = await _divergence("run-rev-author")
    assert divergence.outcome == "surfaced"
    assert await _divergence_responses(AUTHOR) == []


# ---------------------------------------------------------------------------
# 2.8–2.9 — the responding reviewer can see the work (D5, finding F10)
# ---------------------------------------------------------------------------


async def test_a_response_to_a_failed_review_carries_the_review_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.8. Without `review_task_id` the responding reviewer is fired into its own worktree, where
    the author's unmerged work does not exist — F10 reproduced by the mechanism meant to rescue a
    failed review."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "auditor")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-rev-checkout")
        await _review_run_that_said_nothing(db, "run-rev-checkout", task, reviewer="critic")

    assert await evaluate_run_end("run-rev-checkout") is not None

    responses = await _divergence_responses("auditor")
    assert len(responses) == 1
    assert responses[0].review_task_id == "task-rev-checkout"
    assert responses[0].divergence_source_run_id == "run-rev-checkout"


async def test_a_response_to_a_work_run_prepares_no_review_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """2.9. The other half of the same statement. A retry of ordinary work is not a review, and
    handing it the author's checkout would put an agent on a detached HEAD for no reason."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, "worker")

    async with async_session_factory() as db:
        task = Task(
            id="task-work-checkout",
            project_id="proj-test",
            title="ordinary work",
            status="pending",
            divergence_policy="retry",
        )
        db.add(task)
        run = Run(
            id="run-work-checkout", project_id="proj-test", agent="worker", status="completed"
        )
        db.add(run)
        await db.flush()
        await bind_run_to_task(db, run, task)
        await db.commit()

    assert await evaluate_run_end("run-work-checkout") is not None

    responses = await _divergence_responses("worker")
    assert len(responses) == 1
    assert responses[0].review_task_id is None
    assert responses[0].task_id == "task-work-checkout"


# ---------------------------------------------------------------------------
# 5.1–5.3 — pin what already holds (D7)
#
# Flagged during exploration as needing reconciliation between the crash path and F45's withdrawal.
# Reading both showed they cannot collide: they are separated by the run's exit status. Nothing
# states that today, and a future edit could merge them — which is how F45 would return.
# ---------------------------------------------------------------------------


async def test_the_crash_path_and_the_silence_path_stay_disjoint(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """5.1. A **failed** run's delivered input goes back to the queue and the boundary check is
    skipped for it — nothing was dropped, the work is about to be handed to a new run that binds to
    the same task, and under `retry` checking it anyway would spawn a second run racing the
    redelivery. A **completed** run that moved nothing reaches the boundary and is recorded.

    All 23 divergence rows on the trial database carry `run_exit_status = 'completed'`; none of the
    16 failed runs produced one. That is this separation already holding in production."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "auditor")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-disjoint")
        run = await _review_run_that_said_nothing(db, "run-disjoint", task, reviewer="critic")
        run.status = "failed"
        await db.commit()

        requeued = await return_run_entries(db, "run-disjoint")
        await db.commit()

    assert requeued == ["entry-run-disjoint"], "a failed run's input goes back to the queue"

    # The crash path's own caller passes `input_returned=True`. The boundary is skipped, so the
    # same run produces no divergence — a re-delivery is not a silence.
    assert await evaluate_run_end("run-disjoint", input_returned=True) is None
    assert await _divergence("run-disjoint") is None
    assert await _divergence_responses() == []


async def test_a_re_delivered_review_entry_keeps_its_checkout(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """5.2. `review_task_id` survives requeue, so the reviewer that eventually receives this entry
    still gets the checkout of the work under review. An entry that lost it on the way back would
    reproduce F10 through the crash path instead of the divergence path."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-requeue")
        run = await _review_run_that_said_nothing(db, "run-requeue", task, reviewer="critic")
        run.status = "failed"
        await db.commit()
        await return_run_entries(db, "run-requeue")
        await db.commit()

        entry = await db.scalar(
            select(InboundQueueEntry).where(InboundQueueEntry.id == "entry-run-requeue")
        )
        assert entry.state == "queued"
        assert entry.review_task_id == "task-requeue"
        assert entry.delivered_in_run_id is None
        assert entry.delivery_attempts == 1


async def test_re_delivery_is_bounded_and_says_why_it_stopped(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """5.3. The bound already exists — this states it, so the disjointness above cannot be defended
    by "but re-delivery loops anyway". At `DELIVERY_ATTEMPT_LIMIT` the entry is withdrawn carrying
    the reason, and `delivered_in_run_id` is kept as the operator's breadcrumb from a dropped input
    to the run that ate it."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-bounded")
        run = await _review_run_that_said_nothing(db, "run-bounded", task, reviewer="critic")
        run.status = "failed"
        await db.commit()

        for _attempt in range(DELIVERY_ATTEMPT_LIMIT):
            entry = await db.scalar(
                select(InboundQueueEntry).where(InboundQueueEntry.id == "entry-run-bounded")
            )
            entry.state = "delivered"
            entry.delivered_in_run_id = "run-bounded"
            await db.commit()
            await return_run_entries(db, "run-bounded")
            await db.commit()

        entry = await db.scalar(
            select(InboundQueueEntry).where(InboundQueueEntry.id == "entry-run-bounded")
        )
        assert entry.state == "withdrawn"
        assert entry.delivery_attempts >= DELIVERY_ATTEMPT_LIMIT
        assert "stopped retrying" in entry.abandoned_reason
        assert entry.delivered_in_run_id == "run-bounded", "the breadcrumb is kept"


# ---------------------------------------------------------------------------
# F67 — a queued response must be one the scheduler will actually deliver
#
# Found by driving, not by reading, and it is this repository's dominant failure mode appearing in
# this change's own work. Group 2's tests asserted the response entry was queued with the right
# agent and the right columns; none asserted it could ever be *delivered*. It could not:
# `_queue_response` wrote no `conversation_id`, and `turn_scheduler.schedule_agent` refuses exactly
# that shape with "queued entry has no conversation".
#
# Measured on the trial database before the fix: 25 divergence rows, ZERO carrying a
# `response_run_id`. The path had never been walked, because `retry` needs a policy nobody set and
# `escalate` needs `task.escalation_agent`, NULL on every task ever recorded. `restaffed` is the
# first outcome that reaches it with nothing configured.
# ---------------------------------------------------------------------------


async def test_a_restaffed_response_is_deliverable_not_merely_queued(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The assertion whose absence let F67 ship. An entry the scheduler will not pick up is work
    that was recorded and then silently dropped."""
    from hub.turn_scheduler import schedule_agent

    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, "critic", "auditor")

    async with async_session_factory() as db:
        task = await _completed_by_the_author(db, "task-deliverable")
        await _review_run_that_said_nothing(db, "run-deliverable", task, reviewer="critic")

    assert await evaluate_run_end("run-deliverable") is not None

    responses = await _divergence_responses("auditor")
    assert len(responses) == 1
    assert responses[0].conversation_id is not None, (
        "a response with no conversation is refused by schedule_agent and sits queued forever — "
        "which is what 25 divergences with zero response runs looked like"
    )

    async with async_session_factory() as db:
        conversation = await get_conversation_by_id(db, responses[0].conversation_id)
        assert conversation is not None
        assert conversation.agent == "auditor", "a conversation belongs to one agent"
        assert conversation.lifecycle == "open"
        assert (
            conversation.origin == "divergence"
        ), "its own origin, not a borrowed one: nobody asked for this thread"

    # The scheduler's own verdict, rather than our reading of it. Any reason but the one F67 was.
    result = await schedule_agent("proj-test", "auditor")
    assert result.waiting_reason != "queued entry has no conversation"


async def test_a_retry_continues_in_the_thread_the_run_diverged_in(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """Same agent, same work: a fresh conversation would hide the retry from the history that
    explains it, and throw away a resumable provider session. Only a response to a *different*
    agent needs a thread of its own."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, "worker")

    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent="worker", origin="operator")
        db.add(conversation)
        task = Task(
            id="task-retry-thread",
            project_id="proj-test",
            title="ordinary work",
            status="pending",
            divergence_policy="retry",
        )
        db.add(task)
        run = Run(
            id="run-retry-thread",
            project_id="proj-test",
            agent="worker",
            status="completed",
            conversation_id=conversation.id,
        )
        db.add(run)
        await db.flush()
        await bind_run_to_task(db, run, task)
        await db.commit()
        original_conversation = conversation.id

    assert await evaluate_run_end("run-retry-thread") is not None

    responses = await _divergence_responses("worker")
    assert len(responses) == 1
    assert responses[0].conversation_id == original_conversation
