"""`an-agent-that-recorded-the-evidence-is-the-author` — F306 and F316, at all five call sites.

**F306, measured on a live Hub 2026-09-09.** `proj-f741298c9c6b` on `:8011`, Haiku,
`scripts/drive/t_row12_review_leg.py` with `AW_COMPLETE_BY=untouched`. Agent `r7af142d` was
triggered without a `task_id` (run `run-e8ff74d5c129`, `task_id` NULL — never bound), wrote the
code, and called `record_evidence(task_id='task-930385ddb031')`. The operator walked the task
`pending -> in_progress -> completed` by hand and fired the flow. The flow staffed **`r7af142d`** to
review its own code, and sequence 19 of the task's history is `under_review -> approved`,
`actor_kind='run'`, `actor_agent='r7af142d'`. Nothing refused it and nothing recorded that it
happened. The drive's own assertion passed; only `task_transitions` and `requirement_evidence` told
the two states apart.

Every record the exclusion read was empty, correctly — every transition the operator's, no
assignee, no bound run — and the evidence row naming the commit was the one record that named the
author, and it was not a source.

**F316, reproduced at unit level 2026-09-11.** An operator-completed task, an agent associated with
it by a bound run only, and a staffed reviewer whose turn ended with no verdict.
`_answer_failed_review` built its own exclusion from the completer alone, so the re-resolution
restaffed the review onto the agent that worked the task and queued it the review checkout.

**The fixtures are the tests.** Near enough all of this change's coverage is new, and a new test
that passes against the unfixed tree is worth nothing, so each leg's docstring says which removal
it must fail under (tasks.md §4.7, run in a separate firing). The legs whose fixtures carry the
weight say why in their docstrings: the author sorts **first** by name (D6), the approving
reviewer **is** the assignee when it approves (D3), the operator's evidence carries a name an agent
also has (D2), and the evidence is `awaiting` or `rejected`, never `accepted` (the operator's
verdict).
"""

from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from hub.api.v1 import agent_trigger
from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import (
    EventLog,
    EvidenceFootprint,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    RunDivergence,
    SpecRequirement,
    Task,
    TaskTransition,
)
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import bind_run_to_task
from hub.scheduler import decide_firing, enter_selected_task, task_is_claimable_by
from hub.task_transition_service import (
    ActorNotPermittedError,
    agent_that_completed,
    agents_of_runs_bound_to,
    agents_that_may_have_authored,
    agents_that_recorded_evidence_for,
    agents_that_worked,
    apply_transition,
)
from hub.task_transitions import operator, run_actor

from .test_a_flow_names_what_it_cannot_staff import _flow, _roster, _rows
from .test_agent_trigger import _init_repo

pytestmark = pytest.mark.asyncio

# D6: the resolver walks free agents by name, so the author sorts FIRST. With the author second,
# the ladder picks the other agent whether or not the author is excluded, and the leg passes
# against the unfixed tree. Asserted in the ladder leg, not only stated here.
AUTHOR = "ev-author"
OTHER = "ev-reviewer"
TASKS = "/api/v1/projects/proj-test/tasks"


# ---------------------------------------------------------------------------
# The fixtures
# ---------------------------------------------------------------------------


async def _operator_completed(db, loop, *, suffix, loop_task=True):
    """F306's task: every move the operator's, no assignee, no run bound to it.

    Built through `apply_transition` rather than written at `completed`, because a task with no
    history has no recorded completion at all, which is a different world (`completion_attribution`
    `recorded=False`) that the review arm treats differently.
    """
    task = Task(
        id=f"task-ev-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status="pending",
        loop_id=loop.id if loop_task else None,
    )
    db.add(task)
    await db.commit()
    for status in ("in_progress", "completed"):
        await apply_transition(db, task, status, operator())
    await db.commit()
    return task


async def _evidence(
    db,
    task_id,
    *,
    suffix,
    actor=AUTHOR,
    actor_kind="agent",
    review_state="awaiting",
    document_id=None,
):
    """One evidence row naming a commit, as `requirement_evidence.record` writes one.

    It names a commit so the review arm's `commit_for_task_review` gate is satisfied: that gate is
    checked before a reviewer is resolved, and a fixture without it meets a different refusal and
    never reaches the ladder. `review_state` is written onto the materialised column directly,
    which is the column `agents_that_recorded_evidence_for` would be filtered on if somebody added
    the filter it must not have.
    """
    document_id = document_id or f"doc-{suffix}"
    db.add(
        SpecRequirement(
            id=f"req-ev-{suffix}",
            project_id="proj-test",
            document_id=document_id,
            identifier="FR-1",
            key="fr-1",
            digest="d" * 64,
        )
    )
    db.add(
        RequirementEvidence(
            id=f"ev-ev-{suffix}",
            project_id="proj-test",
            requirement_id=f"req-ev-{suffix}",
            task_id=task_id,
            digest="d" * 64,
            kind="artifact_diff",
            actor_kind=actor_kind,
            actor=actor,
            summary="implemented it",
            review_state=review_state,
        )
    )
    db.add(
        EvidenceFootprint(
            id=f"fp-ev-{suffix}",
            project_id="proj-test",
            evidence_id=f"ev-ev-{suffix}",
            kind="git",
            commit_sha="e" * 40,
            branch=f"agentweave/{actor}",
        )
    )
    await db.commit()


async def _f306(db, *, suffix, **evidence):
    """A flow, and on it F306's task with one evidence row. Returns `(loop, task)`."""
    _job, loop = await _flow(db, suffix=suffix, agent=AUTHOR)
    task = await _operator_completed(db, loop, suffix=suffix)
    await _evidence(db, task.id, suffix=suffix, **evidence)
    return loop, task


async def _transition_count(db, task_id):
    return await db.scalar(
        select(func.count()).select_from(TaskTransition).where(TaskTransition.task_id == task_id)
    )


async def _into_review_unassigned(db, task):
    """The operator sends it to review holding nobody, which the entry guard permits in every
    world: nothing is claimed to hold the task, so nothing is false."""
    await apply_transition(db, task, "under_review", operator())
    await db.commit()


# ---------------------------------------------------------------------------
# 4.1 — the fixture is F306's, read back off the rows
# ---------------------------------------------------------------------------


async def test_the_evidence_is_the_only_record_naming_the_author(app):
    """F306's table, reproduced: three sources empty, the fourth naming the author.

    Every later leg is about which record names the agent, so this reads the rows back before
    anything asserts on behaviour. If a future fixture change made the transitions, the assignee or
    a bound run name the author, the ladder leg would pass on one of the old three terms and prove
    nothing about the fourth.
    """
    async with async_session_factory() as db:
        _loop, task = await _f306(db, suffix="rows")

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        assert fresh.status == "completed"
        assert fresh.assignee is None
        assert [(r.to_status, r.actor_kind, r.actor_agent) for r in await _rows(db, task.id)] == [
            ("in_progress", "operator", None),
            ("completed", "operator", None),
        ]
        assert await agent_that_completed(db, task.id) is None
        assert await agents_that_worked(db, task.id) == set()
        assert await agents_of_runs_bound_to(db, task.id) == set()
        assert await agents_that_recorded_evidence_for(db, task.id) == {AUTHOR}
        assert await agents_that_may_have_authored(db, fresh) == {AUTHOR}


# ---------------------------------------------------------------------------
# 4.2 — the ladder
# ---------------------------------------------------------------------------


async def test_the_flow_staffs_the_agent_that_did_not_record_the_evidence(
    app, auth_headers, bind_runner
):
    """4.2. F306 inverted: the flow staffs `OTHER`, not the author.

    **The name order is the test** (design D6). `_agents_that_are_free` walks by name, so with the
    author sorting first an empty exclusion picks the author — which is what the live drive saw.
    Must fail with the union's evidence term removed.
    """
    assert sorted([OTHER, AUTHOR])[0] == AUTHOR, "the author must sort first or this proves nothing"
    await _roster(app, auth_headers, bind_runner, AUTHOR, OTHER)
    async with async_session_factory() as db:
        loop, task = await _f306(db, suffix="ladder")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)

    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (task.id, OTHER, True)
    ]
    assert decision.unstaffed == ()


# ---------------------------------------------------------------------------
# 4.3 / 4.4 — the guard: the author is refused, the flow's reviewer is not
# ---------------------------------------------------------------------------


async def test_the_author_s_approval_is_refused_and_records_nothing(app):
    """4.3. The author asking for `approved` on the task its evidence claims.

    Refused as an author, with a sentence naming the evidence and not claiming any agent completed
    the task — because none did. Status unchanged and no row written, read back through a fresh
    session so a refusal that staged a row it then lost to the rollback is not mistaken for one that
    never wrote it. Must fail with `_guard_author_is_not_reviewer`'s fallback removed.
    """
    async with async_session_factory() as db:
        _loop, task = await _f306(db, suffix="guard")
        await _into_review_unassigned(db, task)
        before = await _transition_count(db, task.id)

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        with pytest.raises(ActorNotPermittedError) as refused:
            await apply_transition(db, fresh, "approved", run_actor("run-ev-guard", AUTHOR))
        await db.rollback()

    message = str(refused.value)
    assert "recorded evidence for this task" in message, message
    assert "No agent is recorded as completing it" in message, message
    assert "the agent recorded as completing it" not in message, message

    async with async_session_factory() as db:
        assert (await db.get(Task, task.id)).status == "under_review"
        assert await _transition_count(db, task.id) == before


async def test_the_reviewer_the_flow_staffed_is_accepted(app, auth_headers, bind_runner):
    """4.4. The regression test for design D3, and the one a "simplification" breaks.

    The reviewer records its verdict **while it is the task's assignee** — the flow wrote it there
    before transitioning, which it must. So `agents_that_may_have_authored` names the reviewer
    itself at that moment, and a guard falling back to the union instead of the evidence term alone
    refuses every review the flow staffs on operator-completed work. Must fail with the fallback
    changed to the union.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, OTHER)
    async with async_session_factory() as db:
        loop, task = await _f306(db, suffix="accepted")

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=AUTHOR)
        [selection] = decision.selections
        assert selection.agent == OTHER
        await enter_selected_task(
            db, selection.task, agent=selection.agent, is_review=selection.is_review
        )
        await db.commit()

    async with async_session_factory() as db:
        under_review = await db.get(Task, task.id)
        assert under_review.status == "under_review"
        assert under_review.assignee == OTHER, "the reviewer holds the task when it approves"
        assert OTHER in await agents_that_may_have_authored(
            db, under_review
        ), "the union names the reviewer here; that is why the guard must not read it"
        await apply_transition(
            db, under_review, "approved", run_actor(run_id="run-ev-accepted", agent=OTHER)
        )
        await db.commit()

    async with async_session_factory() as db:
        assert (await db.get(Task, task.id)).status == "approved"
        last = (await _rows(db, task.id))[-1]
        assert (last.to_status, last.actor_kind, last.actor_agent) == ("approved", "run", OTHER)


# ---------------------------------------------------------------------------
# 4.5 — the operator's evidence names no agent
# ---------------------------------------------------------------------------


async def test_the_operator_s_evidence_leaves_every_agent_eligible(app, auth_headers, bind_runner):
    """4.5. F306's untouched-task carve-out, and the only test of the `actor_kind` filter.

    `POST /spec/evidence` records the operator's evidence with `actor='operator'`
    (`api/v1/spec.py`, `Actor(kind="operator", name="operator")`), and `operator` is a valid agent
    name — `AGENT_NAME_RE` accepts it and `worktrees.validate_agent_name` reserves only `user`. So
    the fixture's roster has an agent called `operator`, sorting first. That collision is what makes
    the filter observable: with the operator's row carrying any name no agent has, dropping the
    filter excludes nobody and the leg would pass against the mutated tree. Must fail with the
    `actor_kind` filter dropped.
    """
    named_like_the_operator, second = "operator", "reviewer"
    assert sorted([second, named_like_the_operator])[0] == named_like_the_operator
    await _roster(app, auth_headers, bind_runner, named_like_the_operator, second)
    async with async_session_factory() as db:
        loop, task = await _f306(
            db,
            suffix="operator",
            actor="operator",
            actor_kind="operator",
            review_state="accepted",
        )

    async with async_session_factory() as db:
        assert await agents_that_recorded_evidence_for(db, task.id) == set()
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=second)
        [selection] = decision.selections
        assert (selection.task.id, selection.agent) == (task.id, named_like_the_operator)
        await enter_selected_task(db, selection.task, agent=selection.agent, is_review=True)
        await db.commit()

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        await apply_transition(
            db, fresh, "approved", run_actor("run-ev-operator", named_like_the_operator)
        )
        await db.commit()
        assert (await db.get(Task, task.id)).status == "approved"


# ---------------------------------------------------------------------------
# 4.6 — the claim, not the decision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("review_state", ["awaiting", "rejected"])
async def test_unaccepted_evidence_still_names_its_author(app, review_state):
    """4.6. The operator's verdict in executable form: producing evidence is the agent's claim, and
    accepting it is somebody else's decision.

    Keyed on acceptance, evidence still `awaiting` — exactly the evidence a reviewer is staffed to
    judge — would exclude nobody, and the exclusion would depend on the outcome of the review it is
    staffing. `rejected` is the same claim, judged the other way; the author wrote it either way.
    Both the offer and the refusal are asserted. Must fail with `review_state == 'accepted'` added.
    """
    async with async_session_factory() as db:
        _loop, task = await _f306(db, suffix=f"state-{review_state}", review_state=review_state)
        await _into_review_unassigned(db, task)

    async with async_session_factory() as db:
        assert (await db.get(RequirementEvidence, f"ev-ev-state-{review_state}")).review_state == (
            review_state
        )
        fresh = await db.get(Task, task.id)
        assert await agents_that_recorded_evidence_for(db, task.id) == {AUTHOR}
        assert AUTHOR in await agents_that_may_have_authored(db, fresh)
        assert await task_is_claimable_by(db, fresh, AUTHOR) is False
        with pytest.raises(ActorNotPermittedError):
            await apply_transition(db, fresh, "approved", run_actor("run-ev-state", AUTHOR))
        await db.rollback()

    async with async_session_factory() as db:
        assert (await db.get(Task, task.id)).status == "under_review"


# ---------------------------------------------------------------------------
# 4.6a — the entry: no wedge
# ---------------------------------------------------------------------------


async def test_the_evidence_author_cannot_be_entered_as_the_reviewer(app, auth_headers):
    """4.6a, design D14. One `PATCH` making the evidence author the assignee and sending the task
    to review — what an operator does to "have it review this".

    Permitted, it would strand the task: `under_review`, held by an agent whose every verdict §3.1
    refuses, named on no transition, which the flow reports as a review in progress and never
    restaffs. So it is refused at the entry, before a turn is spent, and the sentence does not say
    an agent completed the task. The refusal is the service's `ActorNotPermittedError`, which the
    app's handler sends as `403`; asserted here at both layers. Must fail with the §3.4 fallback
    removed — which is also the §1–§3.3 tree D14 exists for.

    The permissive half is the flow's own path and must not be refused: the same move with a
    different agent as the assignee. Must fail with the §3.4 fallback changed to the union.
    """
    async with async_session_factory() as db:
        _loop, task = await _f306(db, suffix="entry")
        before = await _transition_count(db, task.id)

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        fresh.assignee = AUTHOR
        with pytest.raises(ActorNotPermittedError):
            await apply_transition(db, fresh, "under_review", operator())
        await db.rollback()

    refused = await app.patch(
        f"{TASKS}/{task.id}",
        json={"assignee": AUTHOR, "status": "under_review"},
        headers=auth_headers,
    )
    assert refused.status_code == 403, refused.text
    detail = refused.json()["detail"]
    assert "recorded evidence for this task" in detail, detail
    assert "No agent is recorded as completing it" in detail, detail
    assert "completed" not in detail, detail

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        assert (fresh.status, fresh.assignee) == ("completed", None)
        assert await _transition_count(db, task.id) == before

    permitted = await app.patch(
        f"{TASKS}/{task.id}",
        json={"assignee": OTHER, "status": "under_review"},
        headers=auth_headers,
    )
    assert permitted.status_code == 200, permitted.text

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        assert (fresh.status, fresh.assignee) == ("under_review", OTHER)


# ---------------------------------------------------------------------------
# 4.9 — the dispatch refuses before a turn, and provisions nothing
# ---------------------------------------------------------------------------


async def _queue_entries(db):
    return (await db.execute(select(InboundQueueEntry.id))).scalars().all()


async def test_dispatching_the_evidence_author_as_reviewer_is_refused_before_the_turn(
    app, auth_headers, bind_runner
):
    """4.9, §3.5. `POST /agent/trigger` naming the evidence author as the reviewer.

    `task-lifecycle-governance`: a review that cannot be staffed is refused before a turn is
    started, and a refused review leaves nothing provisioned. Without the route's refusal the
    request is *queued* and answered `200` — the turn is then refused by the entry guard inside
    `trigger_agent_directly` and the refusal is buried in the entry's `waiting_reason` (design D11 of
    the change that added the route check). So the status code is asserted, and so are the three
    things a refusal must leave alone: the task, the queue, and the checkout — the provisioning is
    patched and must never have been called. Must fail with the §3.5 fallback removed.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, OTHER)
    async with async_session_factory() as db:
        _loop, task = await _f306(db, suffix="dispatch")

    with patch.object(
        agent_trigger.review_turn, "prepare_review_turn", autospec=True
    ) as provisioning:
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": AUTHOR, "message": f"review {task.id}", "review_task_id": task.id},
                headers=auth_headers,
            )

    assert response.status_code == 403, response.text
    detail = response.json()["detail"]
    assert "recorded evidence for this task" in detail, detail
    assert "completed" not in detail, detail
    provisioning.assert_not_called()

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        assert (fresh.status, fresh.assignee) == ("completed", None)
        assert await _queue_entries(db) == []
        assert (await db.execute(select(Run.id))).first() is None


async def test_the_direct_dispatch_refuses_the_evidence_author_before_the_checkout(
    app, auth_headers, bind_runner
):
    """The route's check is the operator's answer; `trigger_agent_directly` is the authority, and
    the flow reaches it without passing through the route. There the refusal is the entry guard's
    (§3.4) — `enter_selected_task` writes the reviewer into `assignee` before it transitions — and
    it must land before `prepare_review_turn`, leaving the staged staffing abandoned."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, OTHER)
    async with async_session_factory() as db:
        _loop, task = await _f306(db, suffix="direct")

    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent=AUTHOR, origin="operator")
        db.add(conversation)
        await db.commit()
        with patch.object(
            agent_trigger.review_turn, "prepare_review_turn", autospec=True
        ) as provisioning:
            with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
                with pytest.raises(TriggerAgentError) as refused:
                    await trigger_agent_directly(
                        project_id="proj-test",
                        agent=AUTHOR,
                        message=f"review {task.id}",
                        conversation_id=conversation.id,
                        session=db,
                        review_task_id=task.id,
                    )

    assert refused.value.status_code == 403
    assert "recorded evidence for this task" in refused.value.detail
    provisioning.assert_not_called()

    async with async_session_factory() as db:
        fresh = await db.get(Task, task.id)
        assert (fresh.status, fresh.assignee) == ("completed", None)
        assert (await db.execute(select(Run.id))).first() is None


# ---------------------------------------------------------------------------
# 4.10 / 4.10a — the silent review (F316)
# ---------------------------------------------------------------------------

WORKER = "aa-author"  # sorts ahead of the reviewer, as F316's reproduction did
SILENT = "critic"


async def _silent_review_of_operator_completed_work(db, *, suffix):
    """F316's fixture, exactly: the worker is associated with the task by a **bound run only**.

    The operator takes `in_progress` and `completed`; the worker's run binds to the task while it is
    already `in_progress`, which takes no edge, so no transition names it. Then the flow's own
    staffing of `critic` — assignee written first, then `-> under_review` — and `critic`'s turn ends
    with no verdict, delivered the review entry the product delivers.
    """
    task = Task(id=f"task-ev-{suffix}", project_id="proj-test", title="work", status="pending")
    db.add(task)
    await db.commit()
    await apply_transition(db, task, "in_progress", operator())
    worker_run = Run(
        id=f"run-ev-worker-{suffix}", project_id="proj-test", agent=WORKER, status="running"
    )
    db.add(worker_run)
    await db.flush()
    assert await bind_run_to_task(db, worker_run, task) is None, "binding takes no edge"
    worker_run.status = "completed"
    task.assignee = None
    await apply_transition(db, task, "completed", operator())
    await db.commit()

    task.assignee = SILENT
    await apply_transition(db, task, "under_review", run_actor(f"run-stage-{suffix}", SILENT))
    review_run = Run(
        id=f"run-ev-silent-{suffix}", project_id="proj-test", agent=SILENT, status="completed"
    )
    db.add(review_run)
    await db.flush()
    db.add(
        InboundQueueEntry(
            id=f"entry-ev-{suffix}",
            project_id="proj-test",
            agent=SILENT,
            origin_type="job",
            content="Review the work",
            hop_depth=0,
            state="delivered",
            delivered_in_run_id=review_run.id,
            review_task_id=task.id,
        )
    )
    await bind_run_to_task(db, review_run, task)
    await db.commit()

    assert await agent_that_completed(db, task.id) is None
    assert WORKER not in await agents_that_worked(db, task.id)
    assert WORKER in await agents_of_runs_bound_to(db, task.id)
    return task, review_run


async def _divergence_responses(db):
    return (
        (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "divergence")
            )
        )
        .scalars()
        .all()
    )


async def test_a_silent_review_is_not_restaffed_onto_the_agent_that_worked_it(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.10, F316 in executable form, asserting R3's measured numbers rather than an absence.

    Against the unfixed tree R3 measured `restaffed`, `task.assignee` moved to the worker, and a
    `divergence` entry queued to it carrying the review checkout — the worker made the reviewer of
    its own work. With §2.4 the re-resolution excludes every agent any record associates with the
    task, so with nobody else on the roster it is `surfaced`, the assignee stays the silent
    reviewer, and nothing is queued. Must fail with §2.4 removed, and against the §1–§3-only tree.
    """
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, WORKER, SILENT)
    async with async_session_factory() as db:
        task, review_run = await _silent_review_of_operator_completed_work(db, suffix="silent")

    assert await evaluate_run_end(review_run.id) is not None

    async with async_session_factory() as db:
        divergence = (
            (await db.execute(select(RunDivergence).where(RunDivergence.run_id == review_run.id)))
            .scalars()
            .one()
        )
        assert divergence.policy_applied == "review"
        assert divergence.outcome == "surfaced", divergence.outcome
        fresh = await db.get(Task, task.id)
        assert (fresh.status, fresh.assignee) == ("under_review", SILENT)
        assert await _divergence_responses(db) == []


async def test_the_surfaced_reason_says_worked_on_not_completed(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """4.10a, §2.4a. The `run_diverged` event's `reason` is the whole of what the operator is shown
    for a surfaced review, at `severity="warn"`.

    On this task no agent completed anything — the operator did — so the resolver's default clause,
    *"is the one that completed this task"*, would state an untruth `agent-flows` forbids in terms.
    R3 ran the five obvious suites against a prototype without the argument and got 88 passed: no
    other test defends this sentence. Must fail with `excluded_because` dropped.
    """
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, WORKER, SILENT)
    async with async_session_factory() as db:
        task, review_run = await _silent_review_of_operator_completed_work(db, suffix="reason")

    assert await evaluate_run_end(review_run.id) is not None

    async with async_session_factory() as db:
        events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged")))
            .scalars()
            .all()
        )
    [payload] = [e.data for e in events if (e.data or {}).get("run_id") == review_run.id]
    assert payload["task_id"] == task.id
    assert payload["was_review"] is True
    assert payload["outcome"] == "surfaced"
    reason = payload["reason"]
    assert "could not staff this step" in reason, reason
    assert "has worked on this task" in reason, reason
    assert "completed" not in reason, reason
