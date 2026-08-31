"""`a-review-a-flow-cannot-staff-is-named` — F142, and the trap in fixing it.

The defect is one line: `decide_firing`'s review arm dropped a task whose completion named no agent
with a bare `continue` that recorded nothing — not `unstaffed`, not `deferred`, not `in_flight`, not
`gated`, no log, no event. The operator got the queue's status histogram in place of a fact about
the one task, forever, and `completed` has no exit that returns the work to an agent.

**The fixture is the whole test.** Five tasks that differ only in provenance, all sitting at
`completed`, and every assertion below is meaningless if the fixture is not what it claims:

| | how it got to `completed` | what the records say |
|---|---|---|
| (a) | walked through `apply_transition` as an agent | the completion names the agent |
| (b) | the same walk, the last step by the operator | the completion names nobody; transitions name the agent |
| (c) | written straight into the status | nothing at all |
| (d) | operator started it by hand, an agent's run bound to it, operator finished it | transitions name **nobody**; `assignee` names the agent |
| (e) | flow staffed `builder-1`, `builder-2`'s run bound to it later, operator finished it | transitions and `assignee` name `builder-1`; only `runs.task_id` names `builder-2` |

`test_flow_fires_a_review_turn.py:78` and `test_flow_chain_end_to_end.py:64` both record that a
fixture skipping the history produces a queue the flow correctly refuses — which is case (c) and not
case (b), and reading that as "operator-completed work is refused" is how this defect survived being
read. Every fixture here reads its rows back before anything asserts on behaviour.

Cases (d) and (e) are the reason the exclusion is three terms rather than one. They were each found
by a round of the spec discipline re-deriving the previous round's repair against the code, and each
one is a *self-approval route*: an agent offered its own work to review, through the door this
change opens. (d) is round 2's, (e) is round 3's — and (e) is the one that a
`worked | {assignee}` exclusion still walks into, because the assignee column holds one name and
`bind_run_to_task` fills it only when it is empty.
"""

import pytest
from sqlalchemy import select

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
    TaskTransition,
)
from hub.run_task_binding import bind_run_to_task
from hub.scheduler import decide_firing, resolve_reviewer, task_is_claimable_by
from hub.task_transition_service import (
    CompletionAttribution,
    agent_that_completed,
    agents_of_runs_bound_to,
    agents_that_may_have_authored,
    agents_that_worked,
    apply_transition,
    completion_attribution,
)
from hub.task_transitions import Actor, operator, run_actor

pytestmark = pytest.mark.asyncio

WORKER = "builder"
SECOND = "builder-2"
REVIEWER = "critic"


# ---------------------------------------------------------------------------
# The fixtures
# ---------------------------------------------------------------------------


async def _flow(db, *, suffix, agent=WORKER):
    """A flow and its job. The job's agent is the flow's default, not necessarily the reviewer.

    **It declares a document, and that is load-bearing rather than decorative**
    (`approval-waits-for-the-turn-to-end`, design D5). Every test in this file is about the review
    arm of `decide_firing` — F142's three arms, the `unstaffed` sentences, the exclusion — and that
    arm belongs to `agent-flows`, which a loop declaring no document is required to be unaffected
    by. Until this change the fixture was a documentless `Loop`, so the file was standing in for a
    flow with a row the product does not treat as one. The document is the one `_evidence` hangs
    its requirement on, so the flow declares the specification its own evidence demonstrates.
    """
    job = AIJob(
        id=f"job-f142-{suffix}",
        project_id="proj-test",
        name=f"F142 {suffix}",
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
            id=f"doc-{suffix}",
            project_id="proj-test",
            path=f"spec/{suffix}.html",
            title=f"Doc {suffix}",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()
    loop = Loop(
        id=f"loop-f142-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"f142 {suffix}",
        spec_document_id=f"doc-{suffix}",
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _task(db, loop, *, suffix, status="pending", assignee=None):
    task = Task(
        id=f"task-f142-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status=status,
        assignee=assignee,
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return task


async def _evidence(db, task_id, *, suffix, commit="c" * 40, agent=WORKER):
    """Evidence naming a commit, so the review arm's `commit_for_task_review` gate is satisfied.

    The gate is checked **before** a reviewer is resolved and stays there (design D9), so a fixture
    that omits this reaches a different, more specific refusal and never exercises the ladder at
    all — which would make every exclusion assertion below pass for the wrong reason.

    The document is `_flow`'s, not this function's: the flow declares it, and the requirement this
    evidence demonstrates belongs to it. Callers pass the same `suffix` to both.
    """
    db.add(
        SpecRequirement(
            id=f"req-{suffix}",
            project_id="proj-test",
            document_id=f"doc-{suffix}",
            identifier="FR-1",
            key="fr-1",
            digest="d" * 64,
        )
    )
    db.add(
        RequirementEvidence(
            id=f"ev-{suffix}",
            project_id="proj-test",
            requirement_id=f"req-{suffix}",
            task_id=task_id,
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor=agent,
            summary="all green",
        )
    )
    db.add(
        EvidenceFootprint(
            id=f"fp-{suffix}",
            project_id="proj-test",
            evidence_id=f"ev-{suffix}",
            kind="git",
            commit_sha=commit,
            branch=f"agentweave/{agent}",
        )
    )
    await db.commit()


async def _fixture_a(db, loop, *, suffix="a"):
    """(a) An agent walked it all the way to `completed`."""
    task = await _task(db, loop, suffix=suffix)
    actor = run_actor(run_id=f"run-a-{suffix}", agent=WORKER)
    for status in ("assigned", "in_progress", "completed"):
        await apply_transition(db, task, status, actor)
    task.assignee = WORKER
    await db.commit()
    return task


async def _fixture_b(db, loop, *, suffix="b"):
    """(b) The agent worked it; the **operator** recorded the completion.

    F142's own row, read off `proj-1964cdedffe2` on 2026-08-30: `in_progress -> completed`,
    `actor_kind='operator'`, `actor_agent=NULL`.
    """
    task = await _task(db, loop, suffix=suffix)
    actor = run_actor(run_id=f"run-b-{suffix}", agent=WORKER)
    for status in ("assigned", "in_progress"):
        await apply_transition(db, task, status, actor)
    task.assignee = WORKER
    await apply_transition(db, task, "completed", operator())
    await db.commit()
    return task


async def _fixture_c(db, loop, *, suffix="c"):
    """(c) Written straight into `completed`. No history at all — the legacy and hand-written case."""
    return await _task(db, loop, suffix=suffix, status="completed")


async def _fixture_d(db, loop, *, suffix="d"):
    """(d) Round 2's: the transitions name **nobody** while an agent wrote every line.

    The operator moves the card to `in_progress` by hand, an agent's run binds to it — taking no
    edge, because `TRANSITIONS` has no `in_progress -> in_progress` — and the operator marks it
    done. `assignee` is the only record that names the agent, and it is named only because
    `bind_run_to_task` found the column empty.
    """
    task = await _task(db, loop, suffix=suffix)
    await apply_transition(db, task, "in_progress", operator())
    await db.commit()
    run = Run(id=f"run-d-{suffix}", project_id="proj-test", agent=WORKER, status="running")
    db.add(run)
    moved = await bind_run_to_task(db, run, task)
    await db.commit()
    assert moved is None, "binding to an already-in_progress task must take no edge"
    # The turn ended. Left `running`, the agent would be excluded from the free pool for being
    # busy, and every exclusion assertion below would pass without the exclusion existing.
    run.status = "completed"
    await apply_transition(db, task, "completed", operator())
    await db.commit()
    return task


async def _fixture_e(db, loop, *, suffix="e"):
    """(e) Round 3's: a **second** agent works an already-started task and no ordinary record names it.

    `builder` is staffed the ordinary way, so it holds the transitions and the assignee. `builder-2`
    then binds to the same card while it is `in_progress`: no edge (already `in_progress`), no
    assignee (already set). The one record that names it is `runs.task_id`, written on
    `bind_run_to_task`'s first statement above every guard.
    """
    task = await _task(db, loop, suffix=suffix)
    # 1. The flow staffs `builder`: `enter_selected_task` writes the assignee and takes
    #    `pending -> assigned` as the operator; `builder`'s own run then takes `-> in_progress`.
    await apply_transition(db, task, "assigned", operator())
    task.assignee = WORKER
    first = Run(id=f"run-e1-{suffix}", project_id="proj-test", agent=WORKER, status="running")
    db.add(first)
    moved = await bind_run_to_task(db, first, task)
    await db.commit()
    assert moved is not None, "the first binding travels assigned -> in_progress"
    first.status = "completed"
    await db.commit()
    # 2. `builder` stalls or ends without calling `update_task` (F140). The operator starts
    #    `builder-2` on the same card, which `resolve_bound_task` permits: it never consults
    #    `Task.assignee`, and the only concurrency refusal is against a turn running right now.
    second = Run(id=f"run-e2-{suffix}", project_id="proj-test", agent=SECOND, status="running")
    db.add(second)
    moved = await bind_run_to_task(db, second, task)
    await db.commit()
    assert moved is None, "the second binding takes no edge: the task is already in_progress"
    second.status = "completed"
    # 3. The operator marks the card done.
    await apply_transition(db, task, "completed", operator())
    await db.commit()
    return task


async def _rows(db, task_id):
    return (
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


async def _roster(app, auth_headers, bind_runner, *names):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    for name in names:
        await bind_runner(name, cli="claude")


# ---------------------------------------------------------------------------
# 1.2 — the fixtures are what they claim, read back off the rows
# ---------------------------------------------------------------------------


async def test_the_five_fixtures_differ_only_in_provenance(app):
    """Read the rows back before anything asserts on behaviour.

    Every later assertion is about *which records name an agent*, so a fixture that quietly built
    the wrong history would make the whole file pass while testing nothing.
    """
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="fixtures")
        a = await _fixture_a(db, loop)
        b = await _fixture_b(db, loop)
        c = await _fixture_c(db, loop)
        d = await _fixture_d(db, loop)
        e = await _fixture_e(db, loop)

    async with async_session_factory() as db:
        for task in (a, b, c, d, e):
            assert (await db.get(Task, task.id)).status == "completed"

        # (a) — the completion names the agent.
        finals = [(r.to_status, r.actor_kind, r.actor_agent) for r in await _rows(db, a.id)]
        assert finals[-1] == ("completed", "run", WORKER)

        # (b) — F142's row exactly: the operator's completion over the agent's work.
        rows_b = await _rows(db, b.id)
        assert [(r.to_status, r.actor_kind, r.actor_agent) for r in rows_b] == [
            ("assigned", "run", WORKER),
            ("in_progress", "run", WORKER),
            ("completed", "operator", None),
        ]

        # (c) — nothing at all.
        assert await _rows(db, c.id) == []

        # (d) — the history names nobody, and `assignee` is the only record that does.
        assert {r.actor_agent for r in await _rows(db, d.id)} == {None}
        assert (await db.get(Task, d.id)).assignee == WORKER
        assert await _bound_agents(db, d.id) == {WORKER}

        # (e) — the history and the assignee name the FIRST agent; only the runs name the second.
        assert {r.actor_agent for r in await _rows(db, e.id)} == {None, WORKER}
        assert (await db.get(Task, e.id)).assignee == WORKER
        assert await _bound_agents(db, e.id) == {WORKER, SECOND}


async def _bound_agents(db, task_id):
    return set(
        (await db.execute(select(Run.agent).where(Run.task_id == task_id).distinct()))
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# 2.3 — the invariant D2 rests on, asserted rather than assumed
# ---------------------------------------------------------------------------


async def test_a_null_completing_agent_means_the_operator_and_nothing_else(app):
    """On a `-> completed` row, `actor_agent IS NULL` <=> the operator made the move.

    The whole change rests on this, and it holds because `Actor.__post_init__` makes the two
    counterexamples unconstructible. Asserted here so the day somebody relaxes that constructor,
    this change fails loudly rather than silently mis-attributing every operator completion to an
    absent agent.
    """
    with pytest.raises(ValueError):
        Actor(kind="run", run_id="r", agent=None)
    with pytest.raises(ValueError):
        Actor(kind="operator", agent="x")


# ---------------------------------------------------------------------------
# 1.3 / 2.x — what the records say about each fixture
# ---------------------------------------------------------------------------


async def test_completion_attribution_tells_the_three_worlds_apart(app):
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="attribution")
        a = await _fixture_a(db, loop)
        b = await _fixture_b(db, loop)
        c = await _fixture_c(db, loop)

    async with async_session_factory() as db:
        assert await completion_attribution(db, a.id) == CompletionAttribution(
            recorded=True, actor_kind="run", agent=WORKER
        )
        # F142's own row: a completion that happened, made by a person, naming no agent.
        assert await completion_attribution(db, b.id) == CompletionAttribution(
            recorded=True, actor_kind="operator", agent=None
        )
        assert await completion_attribution(db, c.id) == CompletionAttribution(
            recorded=False, actor_kind=None, agent=None
        )
        # The wrapper's contract is unchanged for all three.
        assert await agent_that_completed(db, a.id) == WORKER
        assert await agent_that_completed(db, b.id) is None
        assert await agent_that_completed(db, c.id) is None


async def test_agents_that_worked_on_all_five_fixtures(app):
    """2.6. The transitions-only set, and the two fixtures where it is empty or short.

    (d) and (e) are the point: the set is honest about what it reads, and what it reads is not
    every agent that worked the task.
    """
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="worked")
        a = await _fixture_a(db, loop)
        b = await _fixture_b(db, loop)
        c = await _fixture_c(db, loop)
        d = await _fixture_d(db, loop)
        e = await _fixture_e(db, loop)

    async with async_session_factory() as db:
        assert await agents_that_worked(db, a.id) == {WORKER}
        assert await agents_that_worked(db, b.id) == {WORKER}
        assert await agents_that_worked(db, c.id) == set()
        # (d) — empty WHILE an agent wrote the work.
        assert await agents_that_worked(db, d.id) == set()
        # (e) — names the first agent WHILE a second one also worked it.
        assert await agents_that_worked(db, e.id) == {WORKER}

        assert await agents_of_runs_bound_to(db, d.id) == {WORKER}
        assert await agents_of_runs_bound_to(db, e.id) == {WORKER, SECOND}


async def test_the_exclusion_contains_every_agent_any_record_associates_with_the_task(app):
    """2.6's second half, and the assertion 1.5a's defect inverts into.

    The union is three terms and none is droppable. (d) fails on transitions alone; (e) fails on
    `transitions | {assignee}`, which is round 2's repair — the line marked below is the one that
    was false before the third term.
    """
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="union")
        a = await _fixture_a(db, loop)
        c = await _fixture_c(db, loop)
        d = await _fixture_d(db, loop)
        e = await _fixture_e(db, loop)

    async with async_session_factory() as db:
        assert await agents_that_may_have_authored(db, await db.get(Task, a.id)) == {WORKER}
        assert await agents_that_may_have_authored(db, await db.get(Task, c.id)) == set()
        # (d) — the worker is in the set although no transition names it.
        assert await agents_that_may_have_authored(db, await db.get(Task, d.id)) == {WORKER}
        # (e) — BOTH agents. Round 2's `worked | {assignee}` is `{builder}` here, and offering
        # `builder-2` its own work to review is the defect this term closes.
        fresh_e = await db.get(Task, e.id)
        assert await agents_that_may_have_authored(db, fresh_e) == {WORKER, SECOND}
        assert SECOND not in (await agents_that_worked(db, e.id)) | {fresh_e.assignee}


# ---------------------------------------------------------------------------
# 1.4 — the trap is real, asserted at the resolver before the arm exists
# ---------------------------------------------------------------------------


async def test_an_empty_exclusion_would_resolve_the_worker_as_its_own_reviewer(
    app, auth_headers, bind_runner
):
    """The naive repair — `author is None` so `exclude=set()` — is a self-approval route.

    Not a defect today: the arm that would walk into it does not exist, and the task is dropped
    before any reviewer is resolved. Asserted directly against `resolve_reviewer` so the trap is on
    the record *before* the arm is built, because the arm is what makes it reachable.
    """
    await _roster(app, auth_headers, bind_runner, WORKER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="trap")
        b = await _fixture_b(db, loop)

    async with async_session_factory() as db:
        naive = await resolve_reviewer(
            db, await db.get(Task, b.id), project_id="proj-test", exclude=set()
        )
        assert (
            naive.agent == WORKER
        ), "an empty exclusion hands the work back to the agent that did it"

        guarded = await resolve_reviewer(
            db,
            await db.get(Task, b.id),
            project_id="proj-test",
            exclude=await agents_that_worked(db, b.id),
        )
        assert guarded.agent is None
        assert guarded.rung == "unstaffed"


# ---------------------------------------------------------------------------
# 3 — the review arm, one test per fixture
# ---------------------------------------------------------------------------


async def test_an_operator_completed_task_staffs_a_review(app, auth_headers, bind_runner):
    """(b) reaches the ladder and a reviewer that did not work it is selected.

    This is F142's inversion: the firing that reported *"no claimable task among 1 open"* now
    staffs the review the operator was waiting for.
    """
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="staffs")
        b = await _fixture_b(db, loop)
        await _evidence(db, b.id, suffix="staffs")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (b.id, REVIEWER, True)
    ]
    assert decision.unstaffed == ()


async def test_a_task_with_no_recorded_completion_is_named_not_dropped(
    app, auth_headers, bind_runner
):
    """(c) — 1.3's reproduction, inverted.

    Before this change the assertion here was `decision.unstaffed == ()` and
    `"no claimable task among"` in the stall reason: the task was dropped in silence and the
    operator was handed the queue's status histogram. Now it is named, with the remedy, and the
    stall reason *is* that sentence.
    """
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="nameless")
        c = await _fixture_c(db, loop)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)

    assert decision.selections == ()
    assert decision.deferred == ()
    assert decision._cannot_staff == ()
    assert [task_id for task_id, _ in decision.unstaffed] == [c.id]
    reason = decision.unstaffed[0][1]
    assert "no recorded completion" in reason
    assert "Reviewing it directly" in reason
    # The remedy is the operator's own, and saying a later firing will pick it up would be false.
    assert "next firing" not in reason
    # 6.1 — the attributed sentence replaces the histogram rather than sitting beside it.
    assert decision.stall_reason == reason
    assert "no claimable task among" not in (decision.stall_reason or "")


async def test_an_agent_completed_task_is_unchanged(app, auth_headers, bind_runner):
    """(a) — the attributed arm is byte-identical to today: `exclude={author}`, nothing widened."""
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="attributed")
        a = await _fixture_a(db, loop)
        await _evidence(db, a.id, suffix="attributed")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (a.id, REVIEWER, True)
    ]


async def test_the_agent_that_worked_it_is_not_offered_operator_completed_work(
    app, auth_headers, bind_runner
):
    """3.3a — round 2's self-approval reproduction, inverted, against the arm.

    Fixture (d): the transitions name nobody, so an exclusion built from them alone is empty and
    the ladder hands the work straight back to the agent that wrote it. `assignee` is the term that
    catches this one.
    """
    await _roster(app, auth_headers, bind_runner, WORKER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="selfd")
        d = await _fixture_d(db, loop)
        await _evidence(db, d.id, suffix="selfd")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)

    assert decision.selections == ()
    assert [task_id for task_id, _ in decision.unstaffed] == [d.id]


async def test_the_second_agent_that_worked_it_is_not_offered_it_either(
    app, auth_headers, bind_runner
):
    """3.3b — round 3's, and the one a two-term exclusion passes.

    Fixture (e): `builder-2` is named by neither the transitions nor the assignee. Run this against
    an exclusion of `worked | {assignee}` and it selects `builder-2` for its own work; that is the
    defect, and it is why the third term exists.
    """
    await _roster(app, auth_headers, bind_runner, SECOND)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="selfe", agent=SECOND)
        e = await _fixture_e(db, loop)
        await _evidence(db, e.id, suffix="selfe", agent=SECOND)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=SECOND)

    assert decision.selections == (), "builder-2 wrote this work and may not review it"
    assert [task_id for task_id, _ in decision.unstaffed] == [e.id]


async def test_the_exclusion_excludes_only_the_agents_that_worked_it(
    app, auth_headers, bind_runner
):
    """3.6. Two agents, one of which worked the task: the other is selected, not neither."""
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="excl")
        b = await _fixture_b(db, loop)
        await _evidence(db, b.id, suffix="excl")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
    assert [s.agent for s in decision.selections] == [REVIEWER]


async def test_the_missing_commit_reason_still_wins(app, auth_headers, bind_runner):
    """3.1 / D9 — the gate order is unchanged, so the better sentence still reaches the operator.

    An operator-completed task with no evidence meets `commit_for_task_review`'s existing, more
    specific refusal rather than a new one about staffing.
    """
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="nocommit")
        b = await _fixture_b(db, loop)

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
    assert [task_id for task_id, _ in decision.unstaffed] == [b.id]
    assert "no commit" in decision.unstaffed[0][1] or "evidence" in decision.unstaffed[0][1]


async def test_the_operator_arm_reaches_an_approved_verdict_end_to_end(
    app, auth_headers, bind_runner
):
    """3.5. A resolution that a transition guard then refuses is the failure `agent-flows`' third
    scenario forbids — the flow would fire an agent at work it is structurally unable to sign off,
    forever, since the refusal changes nothing about the queue.

    Driven rather than inferred: the offer comes from the firing, and the permission from
    `apply_transition` itself raising or not.
    """
    from hub.scheduler import enter_selected_task

    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="verdict")
        b = await _fixture_b(db, loop)
        await _evidence(db, b.id, suffix="verdict")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
        selection = decision.selections[0]
        assert selection.agent == REVIEWER
        await enter_selected_task(
            db, selection.task, agent=selection.agent, is_review=selection.is_review
        )
        await db.commit()

    async with async_session_factory() as db:
        under_review = await db.get(Task, b.id)
        assert under_review.status == "under_review"
        await apply_transition(
            db, under_review, "approved", run_actor(run_id="run-verdict", agent=REVIEWER)
        )
        await db.commit()
        assert (await db.get(Task, b.id)).status == "approved"


async def test_the_per_agent_walk_agrees_with_the_flow_walk(app, auth_headers, bind_runner):
    """4.4. The board derives its current item from `_first_startable_candidate`, which reads
    `task_is_claimable_by` — so the two must answer the same thing about one operator-completed
    task, or the card and the firing tell the operator different stories.
    """
    from hub.scheduler import _first_startable_candidate

    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="board")
        b = await _fixture_b(db, loop)
        await _evidence(db, b.id, suffix="board")

    async with async_session_factory() as db:
        fresh_loop = await db.get(Loop, loop.id)
        candidate, _gated = await _first_startable_candidate(db, fresh_loop, agent=REVIEWER)
        assert candidate is not None and candidate.id == b.id
        mine, _gated = await _first_startable_candidate(db, fresh_loop, agent=WORKER)
        assert mine is None, "the agent that worked it sees nothing to do, as the firing does"


# ---------------------------------------------------------------------------
# 3a — the ladder's refusal sentence stops asserting a completion that did not happen
# ---------------------------------------------------------------------------


async def test_the_surfaced_reason_does_not_claim_an_agent_completed_the_work(
    app, auth_headers, bind_runner
):
    """3a.3. Presence *and* absence, because this sentence is the whole of what the operator sees.

    `decide_firing` promotes it to `stall_reason` and `_emit_review_unstaffed` broadcasts it. A
    change whose entire subject is that the operator gets a fact about the task instead of a fact
    about the queue cannot ship that fact in a sentence saying an agent completed work the operator
    completed.
    """
    await _roster(app, auth_headers, bind_runner, WORKER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="sentence")
        b = await _fixture_b(db, loop)
        await _evidence(db, b.id, suffix="sentence")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)

    reason = decision.unstaffed[0][1]
    assert "has worked on this task" in reason
    assert "completed" not in reason, reason


async def test_the_attributed_arm_keeps_the_completion_wording(app, auth_headers, bind_runner):
    """3a.3's other half: where an agent *did* complete it, the sentence still says so."""
    await _roster(app, auth_headers, bind_runner, WORKER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="sentencea")
        a = await _fixture_a(db, loop)
        await _evidence(db, a.id, suffix="sentencea")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
    assert "is the one that completed this task" in decision.unstaffed[0][1]


# ---------------------------------------------------------------------------
# 4 — claimability, so the two walks agree
# ---------------------------------------------------------------------------


async def test_claimability_agrees_with_the_review_arm_on_every_fixture(app):
    """4.1. The same set, called — not a second composition of the same three terms.

    The flow walk and the per-agent walk (`_first_startable_candidate`, which the board also reads)
    answering opposite things about one task is the drift this file's own subject is a case of.
    """
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="claim")
        a = await _fixture_a(db, loop)
        b = await _fixture_b(db, loop)
        c = await _fixture_c(db, loop)
        d = await _fixture_d(db, loop)
        e = await _fixture_e(db, loop)

    async with async_session_factory() as db:
        assert await task_is_claimable_by(db, await db.get(Task, a.id), REVIEWER) is True
        assert await task_is_claimable_by(db, await db.get(Task, a.id), WORKER) is False

        assert await task_is_claimable_by(db, await db.get(Task, b.id), REVIEWER) is True
        assert await task_is_claimable_by(db, await db.get(Task, b.id), WORKER) is False

        # (c) stays claimable by nobody: nothing rules any agent out, so nothing rules out the
        # author either.
        assert await task_is_claimable_by(db, await db.get(Task, c.id), REVIEWER) is False
        assert await task_is_claimable_by(db, await db.get(Task, c.id), WORKER) is False

        assert await task_is_claimable_by(db, await db.get(Task, d.id), WORKER) is False
        assert await task_is_claimable_by(db, await db.get(Task, d.id), REVIEWER) is True

        assert await task_is_claimable_by(db, await db.get(Task, e.id), SECOND) is False
        assert await task_is_claimable_by(db, await db.get(Task, e.id), WORKER) is False
        assert await task_is_claimable_by(db, await db.get(Task, e.id), REVIEWER) is True


# ---------------------------------------------------------------------------
# 5 — the wedged-review branch
# ---------------------------------------------------------------------------


async def test_an_operator_completed_task_wedged_in_review_is_restaffed(
    app, auth_headers, bind_runner
):
    """5.3 / 1.6 inverted. Before this change it landed in `_cannot_staff` — *"a reviewer holds
    this"* — which was false: nobody was reviewing it and its assignee was counted busy forever.
    """
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="wedge")
        b = await _fixture_b(db, loop)
        await _evidence(db, b.id, suffix="wedge")
        fresh = await db.get(Task, b.id)
        await apply_transition(db, fresh, "under_review", operator())
        await db.commit()
        assert fresh.assignee == WORKER

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)

    assert decision._cannot_staff == (), "nobody is reviewing this; reporting it held is the bug"
    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (b.id, REVIEWER, True)
    ]


async def test_a_review_genuinely_in_progress_is_still_reported_as_held(
    app, auth_headers, bind_runner
):
    """5.4 — the case that must NOT change, and the risk in widening the wedge predicate.

    A flow that reports every review in progress as unstaffable is worse than the bug. Built
    through the flow's own staffing rather than by writing `assignee`, because the argument that a
    legitimate reviewer is absent from the transition set rests on `completed -> under_review`
    being operator-attributed and the reviewer's binding recording nothing — and a hand-written
    fixture exercises neither.
    """
    from hub.scheduler import enter_selected_task

    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="held")
        b = await _fixture_b(db, loop)
        await _evidence(db, b.id, suffix="held")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
        selection = decision.selections[0]
        assert selection.agent == REVIEWER
        await enter_selected_task(
            db, selection.task, agent=selection.agent, is_review=selection.is_review
        )
        await db.commit()

    async with async_session_factory() as db:
        held = await db.get(Task, b.id)
        assert held.status == "under_review"
        assert held.assignee == REVIEWER
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)

    assert decision._cannot_staff == ((b.id, REVIEWER),)
    assert decision.selections == ()


async def test_a_task_with_no_completion_wedged_in_review_is_surfaced(
    app, auth_headers, bind_runner
):
    """5.2's carry-through. A task whose `-> completed` row is missing but whose later transitions
    name its assignee reaches the ladder and comes back `unstaffed`, with 3.2's sentence.

    Recovery is impossible for it — no agent can be ruled out as its author — and saying so beats
    reporting a reviewer that is not there.
    """
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="wedgec")
        c = await _fixture_c(db, loop)
        fresh = await db.get(Task, c.id)
        fresh.assignee = WORKER
        # The completion predates the table; the move into review does not, and it names the agent
        # that is now sitting on the task as its own reviewer.
        await apply_transition(
            db, fresh, "under_review", run_actor(run_id="run-wedgec", agent=WORKER)
        )
        await db.commit()

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)

    assert decision._cannot_staff == ()
    assert [task_id for task_id, _ in decision.unstaffed] == [c.id]
    assert "no recorded completion" in decision.unstaffed[0][1]


async def test_the_operator_is_told_through_the_event_and_the_stream_not_only_the_stall_string(
    app, auth_headers, bind_runner
):
    """6.1 and 6.2 — verified by firing, not by reading the code.

    F64's own history is that the sentence *"was already being computed on this very walk and
    emitted as a `review_unstaffed` event; it simply never reached the surface an operator looks
    at."* A fix that never reaches the operator is not a fix, so this asserts the persisted row and
    the broadcast payload as well as the refusal's reason — and that the job stays enabled, since
    the remedy is the operator's and the next firing should pick it up by itself.
    """
    from unittest.mock import patch

    from hub.db.models import EventLog
    from hub.scheduler import JobScheduler

    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="event")
        c = await _fixture_c(db, loop)

    broadcasts: list = []

    async def _capture(project_id, event_type, payload):
        broadcasts.append((event_type, payload))

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        with patch("hub.scheduler.sse_manager.broadcast", _capture):
            async with async_session_factory() as db:
                fired = await scheduler._fire_job_internal(
                    await db.get(AIJob, job.id), trigger="scheduled", session=db
                )
    assert fired is False

    async with async_session_factory() as db:
        events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "review_unstaffed")))
            .scalars()
            .all()
        )
        assert len(events) == 1
        assert events[0].data["task_id"] == c.id
        assert "no recorded completion" in events[0].data["reason"]
        assert (await db.get(AIJob, job.id)).enabled is True

    unstaffed = [payload for kind, payload in broadcasts if kind == "review_unstaffed"]
    assert len(unstaffed) == 1
    assert unstaffed[0]["task_id"] == c.id
    assert "no recorded completion" in unstaffed[0]["reason"]


async def test_the_event_fires_before_the_refusal_decides_anything(app, auth_headers, bind_runner):
    """6.3. The emit loop runs over `decision.unstaffed` **whatever the decision kind is** — above
    the branch that returns a refusal and above the one that proceeds on an empty queue.

    Asserted on a queue that also holds claimable work, which is the case where the firing goes on
    to do something else entirely: a flow that quietly claimed other work and never mentioned the
    review nobody can take would leave the operator with a queue that never finishes and no
    indication why.
    """
    from unittest.mock import patch

    from hub.db.models import EventLog
    from hub.scheduler import JobScheduler

    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="alongside")
        c = await _fixture_c(db, loop)
        await _task(db, loop, suffix="alongside-open")

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)
            assert decision.kind == "claim", "there is ordinary work to do alongside"
            assert [task_id for task_id, _ in decision.unstaffed] == [c.id]
            await scheduler._fire_job_internal(
                await db.get(AIJob, job.id), trigger="scheduled", session=db
            )

    async with async_session_factory() as db:
        events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "review_unstaffed")))
            .scalars()
            .all()
        )
        assert [e.data["task_id"] for e in events] == [c.id]


async def test_a_hand_dispatched_review_on_an_unattributed_task_is_still_held(
    app, auth_headers, bind_runner
):
    """The counterpart, and the reason the wedge predicate is not simply *"no completion recorded"*.

    Dispatching a review by hand refuses only an agent *recorded* as completing the task, so on a
    task with no recorded completion any agent may be dispatched — and dispatching staffs the task.
    Reporting that review as unstaffable would tell the operator a real reviewer's work is nobody's,
    which is this requirement's own false statement made in the opposite direction. The delta's
    scenario as written through round 3 required exactly that; it was corrected during
    implementation.
    """
    await _roster(app, auth_headers, bind_runner, WORKER, REVIEWER)
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="handdisp")
        c = await _fixture_c(db, loop)
        fresh = await db.get(Task, c.id)
        await apply_transition(db, fresh, "under_review", operator())
        fresh.assignee = REVIEWER
        await db.commit()

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=WORKER)

    assert decision._cannot_staff == ((c.id, REVIEWER),)
    assert decision.unstaffed == ()
