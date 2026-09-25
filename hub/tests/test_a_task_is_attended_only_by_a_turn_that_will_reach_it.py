"""`a-task-is-attended-only-by-a-turn-that-will-reach-it` — F370, F371, F368.

A task is attended by the agent whose turn will reach it, read by `(task, agent)` pair
(`run_task_binding.task_attendance`), not by whichever agent a `task -> agent` map kept.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import JOB_RUN_ERROR_SUMMARY_CHARS, Conversation, InboundQueueEntry, Loop, Run
from hub.run_task_binding import task_attendance
from hub.scheduler import (
    DECISION_IN_FLIGHT,
    DECISION_STALLED,
    _refused_review_reason,
    _refused_work_reason,
    decide_firing,
)

from .test_a_held_agent_is_busy import _entries_for, _fire, _hold
from .test_a_review_nobody_is_doing import (
    AUTHOR,
    REVIEWER,
    _queued_review,
    _roster,
    _running_turn,
    _wedged,
)
from .test_a_review_nobody_is_doing import _flow as _review_flow
from .test_flow_width import _decide, _flow, _task

pytestmark = pytest.mark.asyncio

DEV = "held-dev"
_SEQ = 10_000
REFUSAL = "Could not prepare the checkout for task X: merge conflict in a.py"


async def _entry(
    agent,
    task_id,
    *,
    seq,
    conversation="conv-a",
    origin_type="job",
    hop=0,
    attempts=0,
    reason=None,
    review=False,
    state="queued",
):
    global _SEQ
    _SEQ += 1
    async with async_session_factory() as db:
        if (
            await db.execute(
                select(Conversation).where(Conversation.id == f"{conversation}-{agent}")
            )
        ).scalar_one_or_none() is None:
            db.add(
                Conversation(
                    id=f"{conversation}-{agent}",
                    project_id="proj-test",
                    agent=agent,
                    lifecycle="open",
                )
            )
            await db.flush()
        db.add(
            InboundQueueEntry(
                id=f"iq-att-{agent}-{seq}",
                project_id="proj-test",
                agent=agent,
                origin_type=origin_type,
                origin_agent="peer" if origin_type == "agent" else None,
                conversation_id=f"{conversation}-{agent}",
                sequence=_SEQ,
                content="work",
                hop_depth=hop,
                state=state,
                task_id=task_id,
                review_task_id=task_id if review else None,
                delivery_attempts=attempts,
                waiting_reason=reason,
            )
        )
        await db.commit()


async def _attendance():
    async with async_session_factory() as db:
        return await task_attendance(db, "proj-test")


async def _job_entries(agent):
    return [e for e in await _entries_for(agent) if e.origin_type == "job"]


# ---------------------------------------------------------------------------
# F370 — a held assignee is not re-briefed because a peer's entry sorts first
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "peer,first", [("aaa-peer", True), ("aaa-peer", False), ("zzz-peer", True)]
)
async def test_a_peers_entry_does_not_hide_the_held_assignees_own(
    app, auth_headers, bind_runner, peer, first
):
    await _roster(app, auth_headers, bind_runner, DEV, peer)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix=f"f370-{peer}-{first}", agent=DEV)
        task = await _task(db, loop, f"f370-{peer}-{first}", status="assigned", assignee=DEV)
    await _hold(DEV)
    if first:
        await _entry(peer, task.id, seq=1, origin_type="agent")
    await _entry(DEV, task.id, seq=1)
    if not first:
        await _entry(peer, task.id, seq=2, origin_type="agent")

    await _fire(job.id, times=3)

    assert len(await _job_entries(DEV)) == 1


# ---------------------------------------------------------------------------
# F368 — an idle assignee whose queued turn cannot start is not re-briefed
# ---------------------------------------------------------------------------


async def test_an_idle_assignee_whose_turn_waits_on_the_token_budget_is_not_rebriefed(
    app, auth_headers, bind_runner, monkeypatch
):
    from hub.turn_scheduler import ScheduleResult

    monkeypatch.setattr(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=ScheduleResult(waiting_reason="token budget exhausted")),
    )
    await _roster(app, auth_headers, bind_runner, "dev")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="f368", agent="dev")
        task = await _task(db, loop, "f368", status="assigned", assignee="dev")
    await _entry("dev", task.id, seq=1)

    await _fire(job.id, times=3)

    assert len(await _job_entries("dev")) == 1
    assert (await _decide(job.id, loop.id, agent="dev")).kind == DECISION_IN_FLIGHT


# ---------------------------------------------------------------------------
# D3 — a refused work head is surfaced, not re-briefed
# ---------------------------------------------------------------------------


async def test_a_refused_work_head_is_surfaced_with_its_words_and_not_rebriefed(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="refused", agent="dev")
        task = await _task(db, loop, "refused", status="assigned", assignee="dev")
    await _entry("dev", task.id, seq=1, attempts=1, reason=REFUSAL)

    await _fire(job.id, times=3)
    decision = await _decide(job.id, loop.id, agent="dev")

    assert len(await _job_entries("dev")) == 1
    assert decision.kind == DECISION_STALLED
    [(task_id, sentence)] = decision.unstaffed
    assert task_id == task.id
    assert "merge conflict in a.py" in sentence and "dev" in sentence and "withdraw" in sentence
    assert decision.stall_reason == sentence


async def test_a_refused_head_naming_another_task_surfaces_the_briefing_behind_it(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="behind", agent="dev")
        task = await _task(db, loop, "behind", status="assigned", assignee="dev")
    await _entry("dev", "task-elsewhere", seq=1, attempts=1, reason=REFUSAL, conversation="conv-x")
    await _entry("dev", task.id, seq=2, conversation="conv-y")

    await _fire(job.id, times=3)
    decision = await _decide(job.id, loop.id, agent="dev")

    assert len(await _job_entries("dev")) == 2
    assert decision.kind == DECISION_STALLED
    assert "behind refused input" in decision.unstaffed[0][1]
    assert "merge conflict in a.py" in decision.unstaffed[0][1]


async def test_a_refused_head_of_a_held_assignee_is_not_rebriefed(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="refheld", agent="dev")
        task = await _task(db, loop, "refheld", status="assigned", assignee="dev")
    await _hold("dev")
    await _entry("dev", task.id, seq=1, attempts=1, reason=REFUSAL)

    await _fire(job.id, times=3)

    assert len(await _job_entries("dev")) == 1


async def test_withdrawing_the_refused_entry_lets_the_next_firing_brief_once(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="exit", agent="dev")
        task = await _task(db, loop, "exit", status="assigned", assignee="dev")
    await _entry("dev", task.id, seq=1, attempts=1, reason=REFUSAL)
    await _fire(job.id, times=2)
    assert len(await _job_entries("dev")) == 1

    async with async_session_factory() as db:
        entry = (
            await db.execute(
                select(InboundQueueEntry).where(InboundQueueEntry.id == "iq-att-dev-1")
            )
        ).scalar_one()
        entry.state = "withdrawn"
        await db.commit()
    await _fire(job.id)

    assert len(await _job_entries("dev")) == 2


async def test_an_agent_running_a_turn_bound_to_no_task_is_in_flight(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "dev")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="runany", agent="dev")
        await _task(db, loop, "runany", status="assigned", assignee="dev")
        db.add(Run(id="run-any", project_id="proj-test", agent="dev", status="running"))
        await db.commit()

    await _fire(job.id)

    assert await _job_entries("dev") == []
    assert (await _decide(job.id, loop.id, agent="dev")).kind == DECISION_IN_FLIGHT


# ---------------------------------------------------------------------------
# F371 — a review nobody is doing reads as unattended
# ---------------------------------------------------------------------------


async def _decided(loop_id):
    async with async_session_factory() as db:
        return await decide_firing(db, await db.get(Loop, loop_id), default_agent=AUTHOR)


async def _wedge(app, auth_headers, bind_runner, suffix):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, "gamma")
    async with async_session_factory() as db:
        _job, loop = await _review_flow(db, suffix=suffix)
        task = await _wedged(db, loop, suffix=suffix, assignee=REVIEWER)
    return loop, task


async def test_a_third_agents_input_does_not_make_the_review_attended(
    app, auth_headers, bind_runner
):
    loop, task = await _wedge(app, auth_headers, bind_runner, "f371a")
    await _entry("gamma", task.id, seq=1, origin_type="agent")

    decision = await _decided(loop.id)

    assert decision.kind == DECISION_STALLED
    assert REVIEWER in decision.unstaffed[0][1]


async def test_input_past_the_hop_budget_does_not_make_the_review_attended(
    app, auth_headers, bind_runner
):
    loop, task = await _wedge(app, auth_headers, bind_runner, "f371b")
    await _entry(REVIEWER, task.id, seq=1, hop=99, origin_type="agent")

    decision = await _decided(loop.id)

    assert decision.kind == DECISION_STALLED
    sentence = decision.unstaffed[0][1]
    assert "none is queued" not in sentence
    assert len(sentence) <= JOB_RUN_ERROR_SUMMARY_CHARS


async def test_a_refused_review_delivery_is_named_with_the_refusal(app, auth_headers, bind_runner):
    loop, task = await _wedge(app, auth_headers, bind_runner, "f371c")
    await _entry(
        REVIEWER,
        task.id,
        seq=1,
        review=True,
        attempts=1,
        reason="commit abc is not present in this repository",
    )

    decision = await _decided(loop.id)

    assert decision.kind == DECISION_STALLED
    sentence = decision.unstaffed[0][1]
    assert "commit abc is not present" in sentence and REVIEWER in sentence
    assert "Ask beta again" not in sentence
    assert len(sentence) <= JOB_RUN_ERROR_SUMMARY_CHARS


async def test_the_reviewers_own_unrefused_entry_is_still_attended(app, auth_headers, bind_runner):
    loop, task = await _wedge(app, auth_headers, bind_runner, "f371d")
    async with async_session_factory() as db:
        await _queued_review(db, task, agent=REVIEWER)

    decision = await _decided(loop.id)

    assert decision.kind == DECISION_IN_FLIGHT
    assert decision.unstaffed == ()


async def test_a_running_turn_of_the_reviewer_is_still_attended(app, auth_headers, bind_runner):
    loop, task = await _wedge(app, auth_headers, bind_runner, "f371e")
    async with async_session_factory() as db:
        await _running_turn(db, task, agent=REVIEWER)

    assert (await _decided(loop.id)).kind == DECISION_IN_FLIGHT


# ---------------------------------------------------------------------------
# D1 — `task_attendance` on its own; D4 — the sentences' fit
# ---------------------------------------------------------------------------


async def test_a_crashed_runs_returned_entry_is_queued_not_refused(app):
    await _entry("dev", "t-crash", seq=1, attempts=1, reason=None)
    found = (await _attendance()).pairs[("t-crash", "dev")]
    assert found.how == "queued"


async def test_a_refused_head_refuses_every_pair_of_the_agent_but_owns_only_its_own(app):
    await _entry("dev", "t-head", seq=1, attempts=1, reason="refused", conversation="c1")
    await _entry("dev", "t-behind", seq=2, conversation="c2")
    attendance = await _attendance()

    assert attendance.refusal("t-head", "dev") == "refused"
    assert attendance.refusal("t-behind", "dev") == "refused"
    assert attendance.refused_here("t-head", "dev")
    assert not attendance.refused_here("t-behind", "dev")
    assert not attendance.attends("t-head", "dev")
    assert attendance.has_turn("t-behind", "dev")


async def test_a_fresh_head_with_an_older_refused_rider_is_queued(app):
    await _entry("dev", "t-fresh", seq=1, conversation="c1")
    await _entry("dev", "t-rider", seq=2, attempts=1, reason="refused", conversation="c2")
    attendance = await _attendance()

    assert attendance.attends("t-fresh", "dev")
    assert attendance.attends("t-rider", "dev")


async def test_a_head_past_the_hop_budget_is_skipped_and_suspended_input_is_no_pair(app):
    await _entry("dev", "t-far", seq=1, hop=99, attempts=1, reason="refused", conversation="c1")
    await _entry("dev", "t-near", seq=2, conversation="c2")
    attendance = await _attendance()

    assert ("t-far", "dev") not in attendance.pairs
    assert attendance.attends("t-near", "dev")


async def test_review_is_an_or_over_the_pairs_entries(app):
    await _entry("dev", "t-both", seq=1, review=False, conversation="c1")
    await _entry("dev", "t-both", seq=2, review=True, conversation="c1")
    assert (await _attendance()).pairs[("t-both", "dev")].review


async def test_a_running_pair_beats_a_queued_one_but_is_not_a_has_turn(app):
    async with async_session_factory() as db:
        db.add(
            Run(id="run-att", project_id="proj-test", agent="dev", status="running", task_id="t-r")
        )
        await db.commit()
    attendance = await _attendance()

    assert attendance.pairs[("t-r", "dev")].how == "running"
    assert attendance.attends("t-r", "dev")
    assert not attendance.has_turn("t-r", "dev")


class _T:
    id = "task-1"
    title = "x" * 200


@pytest.mark.parametrize("fn", [_refused_work_reason, _refused_review_reason])
@pytest.mark.parametrize("here", [True, False])
def test_the_refused_sentences_fit_and_keep_the_refusal_and_the_remedy(fn, here):
    refusal = "R" * 300
    sentence = fn(_T, "dev", refusal, here)

    assert len(sentence) <= JOB_RUN_ERROR_SUMMARY_CHARS
    assert refusal in sentence
    assert sentence.endswith(("reject the task.", "revision_needed."))


async def test_a_deferred_author_wedge_is_not_surfaced_as_a_review_the_author_is_not_doing(
    app, auth_headers, bind_runner
):
    """1.11b (R3, `wedge_deferred`). The F70 guard waits on a third agent's turn; the surfacing,
    now a pair question, must not then name the author as the reviewer."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, "gamma")
    async with async_session_factory() as db:
        _job, loop = await _review_flow(db, suffix="deferred")
        task = await _wedged(db, loop, suffix="deferred", assignee=AUTHOR)
    await _entry("gamma", task.id, seq=1, origin_type="agent")

    decision = await _decided(loop.id)

    assert decision.kind == DECISION_IN_FLIGHT
    assert decision.unstaffed == ()
