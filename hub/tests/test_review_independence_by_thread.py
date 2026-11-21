"""Authority by profile, independence by thread (`a-two-profile-build-cannot-deadlock-and-a-stall-
says-so`, FR-1, FR-2, FR-4; task independence-by-thread).

A thread is its conversation lineage, read from rows that already exist: a completion's
`TaskTransition.run_id` and an evidence row's `RequirementEvidence.run_id`, each to
`Run.conversation_id` to the conversation's lineage (D1). The builder profile never reviews, in any
thread (FR-1). Another thread of the checker profile may review work an earlier thread of it
completed or recorded evidence for (FR-2), so a two-profile build is staffed rather than stalled
(FR-3). A `review_unstaffed` stall is left for causes no new thread removes, naming the cause
(FR-4).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import requirement_evidence, stalls, worktrees
from hub.api.v1.agent_trigger import review_dispatch_refusal
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Build,
    Conversation,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    Stall,
    Task,
    TaskTransition,
)
from hub.review_on_completion import _choose
from hub.scheduler import JobScheduler, decide_firing, resolve_reviewer
from hub.spec_lifecycle import Actor as EvidenceActor
from hub.task_transition_service import (
    NEW_THREAD,
    decide_move,
    lineage_of_conversation,
    review_exclusions,
)
from hub.task_transitions import Actor as TransitionActor

from .test_agent_trigger import _init_repo
from .test_flow_fires_a_review_turn import _flow
from .test_review_turn import _REAL_ENSURE_REVIEW_CHECKOUT, _author_commit, _reviewable_task

pytestmark = pytest.mark.asyncio

P = "proj-test"
TASK = "task-1"
BUILDER = "Developer"
CHECKER = "QA"


async def _add(*rows) -> None:
    async with async_session_factory() as db:
        for row in rows:
            db.add(row)
        await db.commit()


async def _thread(agent: str, conversation: str, *, lineage: str | None = None) -> str:
    """A conversation of *agent* (of *lineage*, or its own) with one run in it; the run's id."""
    run_id = f"run-{conversation}"
    await _add(
        Conversation(
            id=conversation,
            project_id=P,
            agent=agent,
            origin="job",
            lineage_id=lineage or conversation,
        ),
        _run_row(run_id, agent, conversation),
    )
    return run_id


def _run_row(run_id: str, agent: str, conversation: str) -> Run:
    """A run the Hub started (a flow's turn), not the operator: it keeps the map's edges."""
    return Run(
        id=run_id,
        project_id=P,
        agent=agent,
        status="completed",
        conversation_id=conversation,
        initiator="autonomous",
    )


async def _another_run(agent: str, conversation: str, suffix: str) -> str:
    """A later run in an existing conversation: a new turn of the same thread."""
    run_id = f"run-{conversation}-{suffix}"
    await _add(_run_row(run_id, agent, conversation))
    return run_id


async def _task(task_id: str = TASK, *, status: str = "completed", **columns) -> None:
    await _add(
        Task(
            id=task_id,
            project_id=P,
            readable_id=task_id.upper(),
            title=f"Task {task_id}",
            status=status,
            builder=BUILDER,
            **columns,
        )
    )


async def _completed_in(task_id: str, agent: str, run_id: str | None) -> None:
    await _add(
        TaskTransition(
            id=f"tt-{task_id}-{agent}",
            project_id=P,
            task_id=task_id,
            from_status="in_progress",
            to_status="completed",
            actor_kind="run",
            actor_agent=agent,
            run_id=run_id,
        )
    )


async def _evidence_in(task_id: str, agent: str, run_id: str | None, evidence_id: str) -> None:
    await _add(
        RequirementEvidence(
            id=evidence_id,
            project_id=P,
            requirement_id="spreq-x",
            digest="d" * 64,
            kind="test_result",
            actor_kind="agent",
            actor=agent,
            task_id=task_id,
            run_id=run_id,
        )
    )


def _run(agent: str, run_id: str) -> TransitionActor:
    return TransitionActor(kind="run", run_id=run_id, agent=agent)


async def _grant(*names: str) -> None:
    async with async_session_factory() as db:
        for agent in (
            await db.execute(select(Agent).where(Agent.project_id == P, Agent.name.in_(names)))
        ).scalars():
            agent.can_accept_evidence = True
        await db.commit()


# ------------------------------------------------------------- FR-1 builder-profile-never-reviews


async def test_no_developer_thread_is_given_the_review(add_agent, bind_runner):
    """Developer thread A built and completed it; Developer thread B never touched it. Neither is
    given the review, and QA, the checker, is."""
    for name in (BUILDER, CHECKER):
        await add_agent(name)
        await bind_runner(name)
    a = await _thread(BUILDER, "conv-dev-a")
    b = await _thread(BUILDER, "conv-dev-b")
    qa = await _thread(CHECKER, "conv-qa-1")
    await _task(checker=CHECKER)
    await _completed_in(TASK, BUILDER, a)
    await _evidence_in(TASK, BUILDER, a, "ev-dev")

    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        exclude = await review_exclusions(db, task)
        assert BUILDER in exclude and "builder" in exclude[BUILDER]
        agent, declared, reason = await _choose(db, task)
        assert (agent, declared, reason) == (CHECKER, True, None)

        # The guards and the dispatch say the same of thread B, which did nothing.
        refused = await review_dispatch_refusal(db, task, reviewer=BUILDER)
        assert refused is not None and refused[0] == 403
        assert "is this task's builder" in refused[1]
        task.status, task.assignee = "under_review", CHECKER
        verdict = await decide_move(db, task, "approved", _run(BUILDER, b))
        assert verdict.allowed is False
        assert "is this task's builder" in verdict.reason
        assert (await decide_move(db, task, "approved", _run(CHECKER, qa))).allowed is True


# ----------------------------------------------------- FR-1 no-checker-named-picks-another-profile


async def test_with_no_checker_named_availability_picks_qa(add_agent, bind_runner):
    for name in (BUILDER, CHECKER):
        await add_agent(name)
        await bind_runner(name)
    a = await _thread(BUILDER, "conv-dev-a")
    await _task()
    await _completed_in(TASK, BUILDER, a)

    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        # "Developer" sorts before "QA": only the builder rule keeps it off.
        choice = await resolve_reviewer(
            db, task, project_id=P, exclude=await review_exclusions(db, task)
        )
        assert choice.agent == CHECKER, choice
        agent, declared, _ = await _choose(db, task)
        assert (agent, declared) == (CHECKER, False)


# ------------------------------------------------------- FR-2 excluded-thread-not-given-review


def _launchable():
    return (
        patch("hub.api.v1.agent_trigger.PtySession.spawn"),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
        patch("hub.api.v1.agent_trigger._execute_run", new=AsyncMock(return_value=None)),
    )


async def _two_profile_flow(app, auth_headers, bind_runner, bind_project_workspace, tmp_path):
    """The 11-21 shape: Developer builds, and QA thread X completed the task and recorded its
    evidence (`stall-442d07c7b549`). The task is in a flow naming no checker."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await app.post(
        f"/api/v1/projects/{P}/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in (BUILDER, CHECKER)}}},
        headers=auth_headers,
    )
    for name in (BUILDER, CHECKER):
        await bind_runner(name, cli="claude")
    await _reviewable_task(commit=sha)
    x = await _thread(CHECKER, "conv-qa-x")
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        task.builder, task.assignee = BUILDER, BUILDER
        evidence = await db.get(RequirementEvidence, "ev-1")
        evidence.actor, evidence.run_id = CHECKER, x
        await db.commit()
    await _completed_in(TASK, CHECKER, x)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="two", agent=BUILDER, task_id=TASK)
    return job, loop


async def test_the_review_goes_to_a_new_qa_thread_not_to_x(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    job, loop = await _two_profile_flow(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path
    )

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=BUILDER)
    assert decision.unstaffed == (), decision.unstaffed
    assert [(s.task.id, s.agent, s.is_review) for s in decision.selections] == [
        (TASK, CHECKER, True)
    ]

    a, b, c = _launchable()
    with a, b, c:
        async with async_session_factory() as db:
            await JobScheduler()._fire_job_internal(
                await db.get(AIJob, job.id), trigger="scheduled", session=db
            )
    await stalls.drain()

    async with async_session_factory() as db:
        entries = list(
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.review_task_id == TASK)
                )
            )
            .scalars()
            .all()
        )
        assert [entry.agent for entry in entries] == [CHECKER]
        [entry] = entries
        assert entry.conversation_id and entry.conversation_id != "conv-qa-x"
        assert await lineage_of_conversation(db, entry.conversation_id) != "conv-qa-x"
        assert (await db.get(Task, TASK)).status == "under_review"
        open_stalls = (await db.execute(select(Stall).where(Stall.task_id == TASK))).scalars().all()
        assert [s.cause for s in open_stalls if s.cause == "review_unstaffed"] == []


async def test_x_itself_may_not_review_or_give_the_verdict(add_agent):
    for name in (BUILDER, CHECKER):
        await add_agent(name)
    x = await _thread(CHECKER, "conv-qa-x")
    y = await _thread(CHECKER, "conv-qa-y")
    await _task(checker=CHECKER, status="completed")
    await _completed_in(TASK, CHECKER, x)

    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        # Into X: refused, naming the thread. Into a new thread, or Y: allowed.
        refused = await review_dispatch_refusal(db, task, reviewer=CHECKER, thread="conv-qa-x")
        assert refused is not None and "this thread of 'QA'" in refused[1]
        assert await review_dispatch_refusal(db, task, reviewer=CHECKER) is None
        assert await review_dispatch_refusal(db, task, reviewer=CHECKER, thread=NEW_THREAD) is None
        assert await review_dispatch_refusal(db, task, reviewer=CHECKER, thread="conv-qa-y") is None

        task.status, task.assignee = "under_review", CHECKER
        later_x = await _another_run(CHECKER, "conv-qa-x", "later")
        refused_x = await decide_move(db, task, "approved", _run(CHECKER, later_x))
        assert refused_x.allowed is False
        assert "this thread of 'QA'" in refused_x.reason
        assert (await decide_move(db, task, "approved", _run(CHECKER, y))).allowed is True


async def test_a_message_turn_in_the_task_does_not_exclude_a_thread(add_agent):
    """Receiving messages, or running in the task's checkout, records no completion or evidence:
    the thread that did only that stays eligible."""
    for name in (BUILDER, CHECKER):
        await add_agent(name)
    a = await _thread(BUILDER, "conv-dev-a")
    m = await _thread(CHECKER, "conv-qa-m")
    await _task(status="completed")
    await _completed_in(TASK, BUILDER, a)
    async with async_session_factory() as db:
        (await db.get(Run, m)).task_id = TASK
        await db.commit()
        task = await db.get(Task, TASK)
        assert CHECKER not in await review_exclusions(db, task)
        task.status, task.assignee = "under_review", CHECKER
        assert (await decide_move(db, task, "approved", _run(CHECKER, m))).allowed is True


async def test_a_fact_with_no_lineage_still_excludes_the_whole_agent(add_agent):
    """D1's fallback: a completion recorded outside a run names the agent, never a thread."""
    for name in (BUILDER, CHECKER):
        await add_agent(name)
    await _task(status="completed")
    await _completed_in(TASK, CHECKER, None)
    y = await _thread(CHECKER, "conv-qa-y")
    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        assert "completed" in (await review_exclusions(db, task))[CHECKER]
        refused = await review_dispatch_refusal(db, task, reviewer=CHECKER)
        assert refused is not None and "'QA' is the agent recorded" in refused[1]
        task.status, task.assignee = "under_review", BUILDER
        assert (await decide_move(db, task, "approved", _run(CHECKER, y))).allowed is False


# ------------------------------------------------- FR-2 other-checker-thread-decides-evidence


async def test_another_qa_thread_decides_xs_evidence_and_x_may_not(add_agent):
    for name in (BUILDER, CHECKER):
        await add_agent(name)
    await _grant(CHECKER)
    x = await _thread(CHECKER, "conv-qa-x")
    y = await _thread(CHECKER, "conv-qa-y")
    await _task(status="under_review", assignee=CHECKER)
    await _evidence_in(TASK, CHECKER, x, "ev-x")
    await _evidence_in(TASK, CHECKER, x, "ev-x2")

    async with async_session_factory() as db:
        evidence = await db.get(RequirementEvidence, "ev-x")
        review = await requirement_evidence.decide(
            db,
            evidence,
            decision="accepted",
            actor=EvidenceActor(kind="agent", name=CHECKER, run_id=y),
        )
        assert review.decision == "accepted"

        later_x = await _another_run(CHECKER, "conv-qa-x", "later")
        other = await db.get(RequirementEvidence, "ev-x2")
        with pytest.raises(requirement_evidence.EvidenceRefusedError) as refused:
            await requirement_evidence.decide(
                db,
                other,
                decision="accepted",
                actor=EvidenceActor(kind="agent", name=CHECKER, run_id=later_x),
            )
        assert refused.value.code == "self_acceptance"
        assert "this thread of 'QA' recorded ev-x2" in str(refused.value)


async def test_a_builder_thread_decides_none_of_its_profiles_evidence(add_agent):
    for name in (BUILDER, CHECKER):
        await add_agent(name)
    await _grant(BUILDER)
    a = await _thread(BUILDER, "conv-dev-a")
    b = await _thread(BUILDER, "conv-dev-b")
    await _task(status="under_review", assignee=CHECKER)
    await _evidence_in(TASK, BUILDER, a, "ev-a")
    async with async_session_factory() as db:
        with pytest.raises(requirement_evidence.EvidenceRefusedError) as refused:
            await requirement_evidence.decide(
                db,
                await db.get(RequirementEvidence, "ev-a"),
                decision="accepted",
                actor=EvidenceActor(kind="agent", name=BUILDER, run_id=b),
            )
        assert refused.value.code == "self_acceptance"


# --------------------------------------------------- FR-2 continued-thread-is-the-same-agent


async def test_a_thread_continued_past_a_checkpoint_is_still_x(add_agent):
    for name in (BUILDER, CHECKER):
        await add_agent(name)
    x = await _thread(CHECKER, "conv-qa-x")
    x2 = await _thread(CHECKER, "conv-qa-x2", lineage="conv-qa-x")
    await _task(status="completed")
    await _completed_in(TASK, CHECKER, x)

    async with async_session_factory() as db:
        task = await db.get(Task, TASK)
        thread = await lineage_of_conversation(db, "conv-qa-x2")
        assert thread == "conv-qa-x"
        refused = await review_dispatch_refusal(db, task, reviewer=CHECKER, thread=thread)
        assert refused is not None and refused[0] == 403
        task.status, task.assignee = "under_review", CHECKER
        assert (await decide_move(db, task, "approved", _run(CHECKER, x2))).allowed is False


async def test_the_operator_cannot_send_the_review_into_x2(
    app, auth_headers, add_agent, bind_runner
):
    """The trigger route with `review_task_id` and a named conversation reads that
    conversation's lineage."""
    for name in (BUILDER, CHECKER):
        await add_agent(name)
        await bind_runner(name)
    x = await _thread(CHECKER, "conv-qa-x")
    await _thread(CHECKER, "conv-qa-x2", lineage="conv-qa-x")
    await _task(status="completed")
    await _completed_in(TASK, CHECKER, x)
    async with async_session_factory() as db:
        conversation = await db.scalar(select(Conversation).where(Conversation.id == "conv-qa-x2"))
        conversation.origin = "operator"
        await db.commit()

    response = await app.post(
        f"/api/v1/projects/{P}/agent/trigger",
        json={
            "agent": CHECKER,
            "message": "review",
            "review_task_id": TASK,
            "conversation_id": "conv-qa-x2",
        },
        headers=auth_headers,
    )
    assert response.status_code == 403, response.text
    assert "this thread of 'QA'" in response.json()["detail"]


# ------------------------------------------------------- FR-4 unstaffed-names-missing-runner


async def test_a_checker_with_no_runner_opens_a_stall_naming_it(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await app.post(
        f"/api/v1/projects/{P}/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in (BUILDER, CHECKER)}}},
        headers=auth_headers,
    )
    await bind_runner(BUILDER, cli="claude")  # QA has no runner bound
    await _reviewable_task(commit=sha)
    x = await _thread(CHECKER, "conv-qa-x")
    # QA's thread completed it, as on 11-21: the reason must not be about that.
    await _completed_in(TASK, CHECKER, x)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="norunner", agent=BUILDER, task_id=TASK)
        db.add(
            Build(
                id="build-1",
                project_id=P,
                document_id=loop.spec_document_id,
                driver="flow",
                level="reviewed",
                loop_id=loop.id,
                people={
                    "builder": BUILDER,
                    "checker": CHECKER,
                    "tasks": {TASK: {"builder": BUILDER, "checker": CHECKER}},
                },
            )
        )
        task = await db.get(Task, TASK)
        task.build_id, task.level, task.builder = "build-1", "reviewed", BUILDER
        task.readable_id = "TPB-1"
        await db.commit()

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=BUILDER)
    [(task_id, reason)] = decision.unstaffed or [(None, repr(decision))]
    assert task_id == TASK
    assert CHECKER in reason and "has no runner" in reason, reason
    assert reason[0].isupper()
    assert "completed" not in reason

    async with async_session_factory() as db:
        await JobScheduler()._fire_job_internal(
            await db.get(AIJob, job.id), trigger="scheduled", session=db
        )
    await stalls.drain()
    async with async_session_factory() as db:
        [stall] = (await db.execute(select(Stall).where(Stall.task_id == TASK))).scalars().all()
    assert stall.cause == "review_unstaffed"
    assert "QA" in stall.reason and "has no runner" in stall.reason
    assert "completed" not in stall.reason


async def test_review_on_completion_names_the_missing_runner_too(add_agent, bind_runner):
    await add_agent(BUILDER)
    await bind_runner(BUILDER)
    await add_agent(CHECKER)
    x = await _thread(CHECKER, "conv-qa-x")
    await _task(checker=CHECKER)
    await _completed_in(TASK, CHECKER, x)
    async with async_session_factory() as db:
        agent, declared, reason = await _choose(db, await db.get(Task, TASK))
    assert (agent, declared) == (None, True)
    assert reason.startswith("TASK-1's checker QA has no runner bound")
    assert "completed" not in reason


async def test_a_named_checker_that_is_the_builder_reads_in_sentence_case(add_agent, bind_runner):
    for name in (BUILDER, CHECKER):
        await add_agent(name)
        await bind_runner(name)
    a = await _thread(BUILDER, "conv-dev-a")
    await _task(checker=BUILDER)
    await _completed_in(TASK, BUILDER, a)
    async with async_session_factory() as db:
        agent, _, reason = await _choose(db, await db.get(Task, TASK))
    assert agent is None
    assert reason.startswith("This task names 'Developer' as its checker")
    assert "builder" in reason
