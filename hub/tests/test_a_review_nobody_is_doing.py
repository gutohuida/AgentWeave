"""`a-review-nobody-is-doing-is-named` — F154, and the two ways a task reaches the same wedge.

A task in `under_review` with an agent's name on it and no turn behind it is not being reviewed by
anybody. The firing decided otherwise on the strength of `task.assignee` alone, answered
`DECISION_IN_FLIGHT`, and the operator's Run button said *"Every task on this loop's queue is
already being worked. Nothing was started, and nothing is wrong — the next firing picks up whatever
finishes."* Nothing finishes. `stall_reason` was `None` for a queue that would never move again.

**Two populations, one rule.** A review turn that ended without recording a verdict leaves this row
(the run boundary's own resolution surfaces it and correctly substitutes nobody when nobody is
left); so does an operator walking a task into `under_review` by hand, which is the only route the
lifecycle offers them and which has no run boundary at all to have diagnosed it. The predicate this
change adds asks whether anybody is *on* the task, so it does not care which door the row came
through — and the author-wedged row of F167, which F70's recovery cannot recognise because
`agents_that_worked` reads `TaskTransition.actor_agent` and every edge here was the operator's,
reaches the same sentence for the same reason.

**What must not move, and why each is here.** `_cannot_staff` still holds the row, because
`task_attribution` builds the board's `held` capacity from it (F63) and a repair that emptied the
collection would revert that two modules away, where no scheduler test would see it. A genuinely
busy flow must still answer in flight (F23). A review that is staffed but still *queued* for its
agent is attended, not abandoned — `schedule_agent` leaves one durably queued whenever the agent is
already running — so the predicate counts an undelivered queue entry as somebody being on it.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Conversation,
    EventLog,
    InboundQueueEntry,
    JobRun,
    Loop,
    Run,
    SpecDocument,
    Task,
)
from hub.run_task_binding import (
    tasks_held_by_a_running_turn,
    tasks_with_a_turn_pending_or_running,
)
from hub.scheduler import (
    DECISION_IN_FLIGHT,
    DECISION_PROCEED_EMPTY,
    DECISION_STALLED,
    decide_firing,
)
from hub.task_attribution import (
    CAPACITY_ASSIGNED,
    CAPACITY_HELD,
    CAPACITY_WORKING,
    attribute,
    live_runs,
    staffing_from_decision,
)
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator, run_actor

pytestmark = pytest.mark.asyncio

AUTHOR = "alpha"
REVIEWER = "beta"


@pytest.fixture
def live_scheduler(monkeypatch):
    """A `JobScheduler` the manual-run route can find.

    `run_job` refuses with 503 when `get_scheduler()` is None, so a test of the route that omitted
    this would never reach the firing at all — which is how F48 survived, and would have hidden
    this change's route behaviour just as thoroughly. Copied from `test_board_agent_role.py`, which
    is where that lesson is recorded.
    """
    import hub.scheduler as scheduler_module
    from hub.scheduler import JobScheduler

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _roster(app, auth_headers, bind_runner, *names):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    for name in names:
        await bind_runner(name, cli="claude")


async def _flow(db, *, suffix, agent=AUTHOR):
    """A flow, its job and the document that makes it one.

    The document is not decoration: a documentless `Loop` is a loop, and the review arm this file
    exercises belongs to `agent-flows`, which a loop declaring no document is required to be
    unaffected by.
    """
    job = AIJob(
        id=f"job-f154-{suffix}",
        project_id="proj-test",
        name=f"F154 {suffix}",
        agent=agent,
        message="keep the queue moving",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    db.add(
        SpecDocument(
            id=f"doc-f154-{suffix}",
            project_id="proj-test",
            path=f"spec/f154-{suffix}.html",
            title=f"Doc {suffix}",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()
    loop = Loop(
        id=f"loop-f154-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"f154 {suffix}",
        spec_document_id=f"doc-f154-{suffix}",
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _wedged(db, loop, *, suffix, assignee, by_agent=True):
    """A task at `under_review` with `assignee` on it and no turn anywhere.

    `by_agent` decides whose hand walked the edges, and that is the only variable between this
    file's two populations. With it, the transitions name `AUTHOR` and F70's author recovery can
    see who produced the work; without it every edge is the operator's, `TaskTransition.actor_agent`
    is NULL throughout, and the recovery is blind — F167. Neither is supposed to change the
    outcome this change is about.
    """
    task = Task(
        id=f"task-f154-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status="pending",
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    actor = run_actor(run_id=f"run-f154-{suffix}", agent=AUTHOR) if by_agent else operator()
    for status in ("assigned", "in_progress", "completed"):
        await apply_transition(db, task, status, actor)
    await apply_transition(db, task, "under_review", operator())
    task.assignee = assignee
    await db.commit()
    return task


async def _running_turn(db, task, *, agent):
    """A run genuinely mid-turn on `task` — the case that must still read as in flight."""
    run = Run(
        id=f"run-live-{task.id}",
        project_id="proj-test",
        agent=agent,
        status="running",
        task_id=task.id,
        turn_depth=0,
    )
    db.add(run)
    await db.commit()
    return run


async def _queued_review(db, task, *, agent, state="queued"):
    """A review staffed but not yet started: its input is sitting in the agent's queue.

    `schedule_agent` produces exactly this whenever the chosen agent is already running, and
    `run_divergence` produces it for a substituted reviewer. Undelivered input naming the task is
    somebody being on it.
    """
    conversation = Conversation(
        id=f"conv-{task.id}",
        project_id="proj-test",
        agent=agent,
        lifecycle="open",
    )
    db.add(conversation)
    await db.commit()
    entry = InboundQueueEntry(
        id=f"iq-{task.id}",
        project_id="proj-test",
        agent=agent,
        origin_type="job",
        conversation_id=conversation.id,
        sequence=1,
        content="review this",
        hop_depth=0,
        state=state,
        task_id=task.id,
        review_task_id=task.id,
    )
    db.add(entry)
    await db.commit()
    return entry


# ---------------------------------------------------------------------------
# 1.1 / 1.2 — the reproduction, both populations
# ---------------------------------------------------------------------------


async def test_a_review_with_no_turn_behind_it_is_named_not_called_in_flight(
    app, auth_headers, bind_runner
):
    """1.1 — the reviewer-wedged row. `t_f154_wedged_review.py` LANE 1–3, in one process.

    Before this change every assertion below held the opposite value: the decision was
    `DECISION_IN_FLIGHT` and `stall_reason` was `None`.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="reviewer")
        task = await _wedged(db, loop, suffix="reviewer", assignee=REVIEWER)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)

    assert decision.kind == DECISION_STALLED
    assert decision.selections == ()
    assert [task_id for task_id, _ in decision.unstaffed] == [task.id]

    reason = decision.unstaffed[0][1]
    assert task.id in reason
    assert REVIEWER in reason
    # The two falsehoods F154 is named for. Neither may survive in any wording.
    assert "already being worked" not in reason
    assert "nothing is wrong" not in reason
    assert "next firing" not in reason
    # The attributed sentence replaces the queue histogram rather than sitting beside it (F64).
    assert decision.stall_reason == reason


async def test_the_author_wedged_row_reaches_the_same_sentence(app, auth_headers, bind_runner):
    """1.2 — F167's row: every edge walked by the operator, so no transition names an agent.

    F70's recovery cannot see the author here, and that is not repaired by this change. What is
    repaired is that the row stops claiming somebody is working it — by a predicate that never asks
    who the assignee is, which is why one rule covers a population the recovery cannot reach.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="author")
        task = await _wedged(db, loop, suffix="author", assignee=AUTHOR, by_agent=False)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)

    assert decision.kind == DECISION_STALLED
    assert [task_id for task_id, _ in decision.unstaffed] == [task.id]
    assert AUTHOR in decision.unstaffed[0][1]
    assert decision.stall_reason == decision.unstaffed[0][1]


async def test_the_fixture_names_nobody_when_the_operator_walked_it(app):
    """The 1.2 fixture is what it claims, read off the rows rather than assumed.

    If any edge named an agent, F70's recovery would fire and 1.2 would be passing for a different
    reason than the one it is written for.
    """
    from hub.db.models import TaskTransition

    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="fixture")
        task = await _wedged(db, loop, suffix="fixture", assignee=AUTHOR, by_agent=False)
        actors = (
            (
                await db.execute(
                    select(TaskTransition.actor_agent).where(TaskTransition.task_id == task.id)
                )
            )
            .scalars()
            .all()
        )

    assert actors, "the fixture recorded no transitions at all"
    assert set(actors) == {None}


# ---------------------------------------------------------------------------
# 4.1 / 4.2 — what must not move
# ---------------------------------------------------------------------------


async def test_a_review_with_a_running_turn_is_still_in_flight(app, auth_headers, bind_runner):
    """4.1 — F23. A busy flow must not call itself stalled, and this is the case that proves the
    predicate discriminates rather than simply always answering "nobody"."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="running")
        task = await _wedged(db, loop, suffix="running", assignee=REVIEWER)
        await _running_turn(db, task, agent=REVIEWER)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)

    assert decision.kind == DECISION_IN_FLIGHT
    assert decision.unstaffed == ()
    assert decision.stall_reason is None
    assert [t for t, _ in decision._cannot_staff] == [task.id]


async def test_a_staffed_review_still_waiting_in_the_queue_is_attended(
    app, auth_headers, bind_runner
):
    """4.2 — the staffing window. Between the assignee write and the run reaching `running`, the
    review's input is already queued; calling that abandoned would report a stall on the tick
    immediately after a correct staffing."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="queued")
        task = await _wedged(db, loop, suffix="queued", assignee=REVIEWER)
        await _queued_review(db, task, agent=REVIEWER)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)

    assert decision.kind == DECISION_IN_FLIGHT
    assert decision.unstaffed == ()


async def test_a_withdrawn_entry_is_not_attendance(app, auth_headers, bind_runner):
    """`withdrawn` already means "this will never be delivered", so it must not count as somebody
    being on the task — otherwise an abandoned review reads as attended forever."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="withdrawn")
        task = await _wedged(db, loop, suffix="withdrawn", assignee=REVIEWER)
        await _queued_review(db, task, agent=REVIEWER, state="withdrawn")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)

    assert decision.kind == DECISION_STALLED
    assert [task_id for task_id, _ in decision.unstaffed] == [task.id]


async def test_the_board_still_says_held_not_assigned(app, auth_headers, bind_runner):
    """4.3 — D1's tripwire, and the reason the row stays in `_cannot_staff`.

    `held` was split out of `working` for F63 to mean exactly this row. The tidier-looking repair —
    moving the task from `_cannot_staff` to `unstaffed` — would send `attribute` down its
    fall-through to `assigned`, changing the board two modules from anything this change touches.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="board")
        task = await _wedged(db, loop, suffix="board", assignee=REVIEWER)

    async with async_session_factory() as db:
        loop_row = await db.get(Loop, loop.id)
        decision = await decide_firing(db, loop_row, default_agent=AUTHOR)
        live = await live_runs(db, {"proj-test"})
        attribution = attribute(
            await db.get(Task, task.id), staffing=staffing_from_decision(decision), live=live
        )

    assert attribution.agent == REVIEWER
    assert attribution.capacity == CAPACITY_HELD
    assert attribution.capacity != CAPACITY_ASSIGNED


async def test_the_board_says_working_while_a_turn_runs(app, auth_headers, bind_runner):
    """The other side of the same fall-through: `held` only means something because `working` is a
    different word for a different row."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="boardrun")
        task = await _wedged(db, loop, suffix="boardrun", assignee=REVIEWER)
        await _running_turn(db, task, agent=REVIEWER)

    async with async_session_factory() as db:
        loop_row = await db.get(Loop, loop.id)
        decision = await decide_firing(db, loop_row, default_agent=AUTHOR)
        live = await live_runs(db, {"proj-test"})
        attribution = attribute(
            await db.get(Task, task.id), staffing=staffing_from_decision(decision), live=live
        )

    assert attribution.capacity == CAPACITY_WORKING


async def test_nothing_on_this_path_reassigns_or_fires_anybody(app, auth_headers, bind_runner):
    """4.4 — `agent-flows`' "no substitution". Replacing a reviewer belongs to the run boundary's
    resolution; a second path that also replaced one could reach a different answer."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="nosub")
        task = await _wedged(db, loop, suffix="nosub", assignee=REVIEWER)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)
        after = await db.get(Task, task.id)

    assert decision.selections == ()
    assert after.assignee == REVIEWER
    assert after.status == "under_review"


async def test_proceed_empty_is_not_reachable_for_this_population(app, auth_headers, bind_runner):
    """4.7 — round 2's check, kept as a test rather than as a paragraph.

    `PROCEED_EMPTY` fires an agent to fill the queue. It is chosen when `_stall_reason_from_walk`
    answers `None`, which happens only when the loop holds nothing outside `{approved, rejected}`.
    `under_review` is not one of those — but that is a fact about a tuple two modules away, and a
    change to it would turn this repair into a firing every tick on the queue it was fixing.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="notempty")
        await _wedged(db, loop, suffix="notempty", assignee=REVIEWER)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)

    assert decision.kind != DECISION_PROCEED_EMPTY
    assert decision.kind == DECISION_STALLED


# ---------------------------------------------------------------------------
# 2.3 — the predicate on its own
# ---------------------------------------------------------------------------


async def test_the_predicate_counts_a_running_turn(app):
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="predrun")
        task = await _wedged(db, loop, suffix="predrun", assignee=REVIEWER)
        await _running_turn(db, task, agent=REVIEWER)
        answer = await tasks_with_a_turn_pending_or_running(db, "proj-test")

    assert answer.get(task.id) == REVIEWER


async def test_the_predicate_counts_a_queued_entry_by_either_column(app):
    """`task_id` and `review_task_id` both name what a turn is about, and a review entry carries
    both — but a work entry carries only the first, so neither column alone is enough."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="predq")
        task = await _wedged(db, loop, suffix="predq", assignee=REVIEWER)
        entry = await _queued_review(db, task, agent=REVIEWER)
        entry.review_task_id = None
        await db.commit()
        by_task = await tasks_with_a_turn_pending_or_running(db, "proj-test")

        entry.task_id = None
        entry.review_task_id = task.id
        await db.commit()
        by_review = await tasks_with_a_turn_pending_or_running(db, "proj-test")

    assert by_task.get(task.id) == REVIEWER
    assert by_review.get(task.id) == REVIEWER


async def test_the_predicate_ignores_a_withdrawn_or_delivered_entry(app):
    """`withdrawn` means it will never be delivered. A delivered entry is not attendance either —
    the run it was delivered into answers that, and it has ended."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="predw")
        task = await _wedged(db, loop, suffix="predw", assignee=REVIEWER)
        entry = await _queued_review(db, task, agent=REVIEWER, state="withdrawn")
        withdrawn = await tasks_with_a_turn_pending_or_running(db, "proj-test")

        entry.state = "delivered"
        entry.delivered_in_run_id = "run-gone"
        await db.commit()
        delivered = await tasks_with_a_turn_pending_or_running(db, "proj-test")

    assert task.id not in withdrawn
    assert task.id not in delivered


async def test_the_predicate_is_empty_for_a_task_with_neither(app):
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="predn")
        task = await _wedged(db, loop, suffix="predn", assignee=REVIEWER)
        answer = await tasks_with_a_turn_pending_or_running(db, "proj-test")

    assert task.id not in answer


async def test_held_is_unchanged_by_this_change(app):
    """The predicate is a second function precisely so this one keeps answering its own question —
    *may a turn start on this checkout* — which a queued entry must not veto."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="predheld")
        task = await _wedged(db, loop, suffix="predheld", assignee=REVIEWER)
        await _queued_review(db, task, agent=REVIEWER)
        held = await tasks_held_by_a_running_turn(db, "proj-test")

    assert task.id not in held


# ---------------------------------------------------------------------------
# 3b — the event says it once
# ---------------------------------------------------------------------------


async def _review_unstaffed_events(db, task_id):
    rows = (
        (await db.execute(select(EventLog).where(EventLog.event_type == "review_unstaffed")))
        .scalars()
        .all()
    )
    return [row for row in rows if (row.data or {}).get("task_id") == task_id]


async def test_an_unchanged_wedge_is_recorded_once_not_once_per_tick(
    app, auth_headers, bind_runner, live_scheduler
):
    """3b.2 — the same fact, five firings, one record.

    This population cannot clear without the operator, so a per-tick event is the same sentence
    twelve times an hour forever, burying the events that carry news.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="onceonly")
        task = await _wedged(db, loop, suffix="onceonly", assignee=REVIEWER)

    for _ in range(5):
        await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)

    async with async_session_factory() as db:
        events = await _review_unstaffed_events(db, task.id)

    assert len(events) == 1
    assert REVIEWER in events[0].data["reason"]


async def test_a_changed_reason_is_recorded_again(app, auth_headers, bind_runner, live_scheduler):
    """3b.2's other half. A condition that changed shape is news; silence there would hide it."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="changed")
        task = await _wedged(db, loop, suffix="changed", assignee=REVIEWER)

    await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        fresh.assignee = AUTHOR
        await db.commit()

    await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)

    async with async_session_factory() as db:
        events = await _review_unstaffed_events(db, task.id)

    assert len(events) == 2
    assert {REVIEWER in event.data["reason"] for event in events} == {True, False}


# ---------------------------------------------------------------------------
# 4.5 / 4.6 — what the operator's Run button actually returns
# ---------------------------------------------------------------------------


async def test_the_route_answers_409_with_the_sentence_not_500(
    app, auth_headers, bind_runner, live_scheduler
):
    """4.5 — no scheduler-level test can see this.

    The 409 is not rendered from `FiringDecision`: the route reads the latest `JobRun`, and only
    failing that asks `_loop_work_is_all_in_flight`, which now answers `False` here — falling to
    `500 "Failed to fire job"` if the stalled path had not written a skipped row first. That is
    the difference between a calm wrong answer and an alarming one.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="route")
        task = await _wedged(db, loop, suffix="route", assignee=REVIEWER)

    res = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)

    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert task.id in detail
    assert REVIEWER in detail
    assert "already being worked" not in detail
    assert "nothing is wrong" not in detail
    assert "Failed to fire job" not in detail


async def test_a_second_press_says_the_same_thing_and_writes_one_row(
    app, auth_headers, bind_runner, live_scheduler
):
    """4.6 — `agent-loops`' "records only what is new", which this wedge is now a permanent client
    of: one row counting up, not one row per press."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="twice")
        await _wedged(db, loop, suffix="twice", assignee=REVIEWER)

    first = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)
    second = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)

    assert first.status_code == 409
    assert second.status_code == 409
    assert first.json()["detail"] == second.json()["detail"]

    async with async_session_factory() as db:
        rows = (await db.execute(select(JobRun).where(JobRun.job_id == job.id))).scalars().all()

    assert len(rows) == 1
    assert rows[0].status == "skipped"
    assert rows[0].tick_count == 2
