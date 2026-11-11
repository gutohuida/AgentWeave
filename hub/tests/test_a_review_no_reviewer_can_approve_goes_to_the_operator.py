"""`a-review-no-reviewer-can-approve-goes-to-the-operator` — F374.

A review that ends without a verdict where the gate refuses approval for a reason only the operator
can lift (evidence nobody has judged) must not be restaffed: a second reviewer meets the same
refusal. The gate is staged the way `test_approval_refuses_unaccepted_evidence.py` stages it (a real
commit, evidence naming it, left `awaiting`), and the review run as `test_the_evidence_names_the_author`
stages a silent one. `evaluate_run_end` is called directly.

Not written: the `unmergeable` control (1.4), the mixed case (1.5) and the drifting leg (1.7b) — see
tasks.md.
"""

import subprocess
import threading
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from hub import requirement_gate, task_integration
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    EventLog,
    InboundQueueEntry,
    Loop,
    RequirementEvidence,
    Run,
    Task,
)
from hub.run_divergence import evaluate_run_end
from hub.run_task_binding import bind_run_to_task
from hub.scheduler import DECISION_IN_FLIGHT, decide_firing

from . import test_approval_refuses_unaccepted_evidence as _unaccepted
from .test_a_flow_names_what_it_cannot_staff import _flow, _roster
from .test_task_integration import make_document, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio

# Re-exported by assignment: importing the fixture by name would trip F811 in every signature.
builder = _unaccepted.builder
# The diagnostic evaluates the gate before a verdict. Only the task's own evidence can
# supply the awaiting commit; taskless evidence cannot hold its review (F1168).
a_task_with_awaiting_evidence = _unaccepted.a_task_with_awaiting_evidence

BETA = "beta"
GAMMA = "gamma"
GATE_SENTENCE = "has been recorded and nobody has judged it"


async def _held_review(
    app, auth_headers, builder, bind_runner, tmp_path, *, grant_gamma=False, taskless=False
):
    """A task under review by `beta`, with evidence awaiting, and `beta`'s silent review run."""
    make_repo(tmp_path)
    await make_document(app, auth_headers, builder)
    await set_main_branch("main")
    await _roster(app, auth_headers, bind_runner, BETA, GAMMA)
    make_work = (
        _unaccepted.a_task_with_unbound_awaiting_evidence
        if taskless
        else a_task_with_awaiting_evidence
    )
    task_id, _evidence, _work = await make_work(app, auth_headers, builder, tmp_path)
    async with async_session_factory() as db:
        if grant_gamma:
            gamma = (await db.execute(select(Agent).where(Agent.name == GAMMA))).scalars().one()
            gamma.can_accept_evidence = True
        task = await db.get(Task, task_id)
        task.status = "under_review"
        task.assignee = BETA
        run = Run(id=f"run-hold-{task_id}", project_id="proj-test", agent=BETA, status="completed")
        db.add(run)
        await db.flush()
        db.add(
            InboundQueueEntry(
                id=f"entry-hold-{task_id}",
                project_id="proj-test",
                agent=BETA,
                origin_type="job",
                content="Review the work",
                hop_depth=0,
                state="delivered",
                delivered_in_run_id=run.id,
                review_task_id=task_id,
            )
        )
        await bind_run_to_task(db, run, task)
        await db.commit()
    return task_id, run.id


async def _diverged_payload(run_id):
    async with async_session_factory() as db:
        events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "run_diverged")))
            .scalars()
            .all()
        )
    [payload] = [e.data for e in events if (e.data or {}).get("run_id") == run_id]
    return payload


async def _queued_for(agent):
    async with async_session_factory() as db:
        return (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == agent)
                    .where(InboundQueueEntry.origin_type == "divergence")
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.parametrize("taskless", [False, True], ids=["own", "taskless"])
async def test_awaiting_evidence_does_not_hold_an_availability_picked_reviewer(
    app, auth_headers, builder, bind_runner, tmp_path, taskless
):
    """Own evidence is decided by the verdict; taskless evidence cannot supply a merge target."""
    _task_id, run_id = await _held_review(
        app, auth_headers, builder, bind_runner, tmp_path, taskless=taskless
    )
    assert await evaluate_run_end(run_id) is not None
    assert len(await _queued_for(GAMMA)) == 1
    payload = await _diverged_payload(run_id)
    assert payload["outcome"] == "restaffed"
    assert "reason" not in payload  # A successful restaff has no hold diagnostic.


async def test_own_evidence_does_not_hold_the_ending_review_as_a_live_turn(
    app, auth_headers, builder, bind_runner, tmp_path
):
    """F458. `evaluate_run_end` runs while the ending run is still in the live set, and the hold
    asked the gate with no acting run -- so the reason said "beta is still running the turn ...
    this clears itself" about the very turn that had just ended without a verdict."""
    _task_id, run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)

    with patch("hub.run_liveness.live_run_ids", return_value={run_id}):
        assert await evaluate_run_end(run_id) is not None

    payload = await _diverged_payload(run_id)
    assert payload["outcome"] == "restaffed"
    assert "reason" not in payload  # No stale live-turn or evidence-hold diagnostic.


async def test_a_reviewer_granted_the_decision_is_still_restaffed(
    app, auth_headers, builder, bind_runner, tmp_path
):
    """1.2, control: `gamma` can accept the evidence itself, so the restaff stands."""
    task_id, run_id = await _held_review(
        app, auth_headers, builder, bind_runner, tmp_path, grant_gamma=True
    )

    assert await evaluate_run_end(run_id) is not None

    # The response is queued and the divergence restaffed; gamma becomes the holder when that
    # response's turn is dispatched, not before (`a-flow-stages-its-review-in-the-dispatch`, D5),
    # so the holder here depends on whether this machine can launch a turn and is not asserted.
    assert len(await _queued_for(GAMMA)) == 1
    assert (await _diverged_payload(run_id))["outcome"] == "restaffed"


async def test_a_declared_reviewer_with_own_evidence_is_surfaced_without_an_operator_hold(
    app, auth_headers, builder, bind_runner, tmp_path
):
    """1.3. The declaration is stubbed (`_review_was_declared`): what is under test is the branch."""
    _task_id, run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)

    async def declared(*_args, **_kwargs):
        return True

    with patch("hub.run_divergence._review_was_declared", declared):
        assert await evaluate_run_end(run_id) is not None

    payload = await _diverged_payload(run_id)
    assert payload["outcome"] == "surfaced"
    assert GATE_SENTENCE not in payload["reason"]
    assert "asking this one again" in payload["reason"]
    assert await _queued_for(GAMMA) == []


async def test_a_raise_out_of_the_gate_restaffs_as_before(
    app, auth_headers, builder, bind_runner, tmp_path, caplog
):
    """1.6. Any exception but git's is "not held": warning logged, today's behaviour."""
    task_id, run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)

    async def boom(*_args, **_kwargs):
        raise RuntimeError("gate exploded")

    with patch.object(requirement_gate, "evaluate", boom), caplog.at_level("WARNING"):
        assert await evaluate_run_end(run_id) is not None

    assert task_id in caplog.text
    assert len(await _queued_for(GAMMA)) == 1


async def test_a_database_error_in_the_gate_leaves_the_session_usable(
    app, auth_headers, builder, bind_runner, tmp_path
):
    """1.6b. The divergence row is still written after an `OperationalError` mid-evaluation."""
    _task_id, run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)
    real = requirement_gate.evaluate

    async def broken(session, task, **kwargs):
        await real(session, task, **kwargs)
        raise OperationalError("select 1", {}, Exception("locked"))

    with patch.object(requirement_gate, "evaluate", broken):
        assert await evaluate_run_end(run_id) is not None

    assert (await _diverged_payload(run_id))["run_id"] == run_id


@pytest.mark.parametrize(
    "error", [subprocess.TimeoutExpired("git", 5), OSError("no git")], ids=["timeout", "oserror"]
)
@pytest.mark.parametrize("grant", [False, True], ids=["ungranted", "granted"])
async def test_a_git_that_cannot_be_asked_holds_for_the_operator(
    app, auth_headers, builder, bind_runner, tmp_path, error, grant
):
    """1.6c. Held whatever `gamma` is granted."""
    task_id, run_id = await _held_review(
        app, auth_headers, builder, bind_runner, tmp_path, grant_gamma=grant
    )

    def failing(*_args, **_kwargs):
        raise error

    with patch.object(task_integration, "_git", failing):
        assert await evaluate_run_end(run_id) is not None

    assert await _queued_for(GAMMA) == []
    async with async_session_factory() as db:
        assert (await db.get(Task, task_id)).assignee == BETA
    assert "could not ask git" in (await _diverged_payload(run_id))["reason"]


async def test_the_predicates_git_is_bounded_and_off_the_loop(
    app, auth_headers, builder, bind_runner, tmp_path
):
    """1.6d. The predicate's spawns see the diagnostic timeout and run on another thread; a
    transition's own evaluation still sees 60."""
    task_id, _run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)
    seen = []
    real = task_integration._git

    def recording(root, *args):
        seen.append((task_integration.GIT_TIMEOUT_SECONDS.get(), threading.current_thread()))
        return real(root, *args)

    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        with patch.object(task_integration, "_git", recording):
            hold = await requirement_gate.approval_held_for_operator(db, task, candidate=BETA)
            held = list(seen)
            seen.clear()
            await requirement_gate.evaluate(db, task)
            plain = list(seen)

    assert hold is None  # The verdict can decide this task's own evidence.
    main = threading.main_thread()
    assert held and all(
        t == task_integration.DIAGNOSTIC_GIT_TIMEOUT_SECONDS and th is not main for t, th in held
    )
    assert plain and all(t == 60 for t, _ in plain)


async def test_the_flow_waits_for_the_restaffed_review_without_an_evidence_hold(
    app, auth_headers, builder, bind_runner, tmp_path
):
    """Own awaiting evidence does not turn an active review into an operator approval wedge."""
    task_id, run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)
    assert await evaluate_run_end(run_id) is not None
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="hold")
        task = await db.get(Task, task_id)
        task.title = "T" * 300
        task.loop_id = loop.id
        await db.commit()
        decision = await decide_firing(db, await db.get(Loop, loop.id), default_agent=GAMMA)

    assert decision.kind == DECISION_IN_FLIGHT, decision
    assert decision.stall_reason is None
    assert decision.approvals == ()


async def test_a_wedged_review_with_nothing_to_hold_never_reaches_the_gate(
    app, auth_headers, bind_runner
):
    """1.7c. No awaiting evidence and no `gate` document: `None`, and `evaluate` is not called."""
    await _roster(app, auth_headers, bind_runner, BETA)
    async with async_session_factory() as db:
        task = Task(id="task-nohold", project_id="proj-test", title="x", status="under_review")
        db.add(task)
        await db.commit()

        async def must_not_run(*_a, **_k):
            raise AssertionError("evaluate was reached")

        with patch.object(requirement_gate, "evaluate", must_not_run):
            hold = await requirement_gate.approval_held_for_operator(db, task, candidate=BETA)
    assert hold is None


# --- F621: the operator lifting the hold asks the held reviewer again ------------------------------


async def _decide_the_awaiting_evidence(app, auth_headers, task_id, decision, reason=""):
    # Decide the held task's own awaiting evidence.
    async with async_session_factory() as db:
        [evidence] = (
            (
                await db.execute(
                    select(RequirementEvidence).where(
                        RequirementEvidence.project_id == "proj-test",
                        RequirementEvidence.task_id == task_id,
                        RequirementEvidence.review_state == "awaiting",
                    )
                )
            )
            .scalars()
            .all()
        )
    answer = await app.post(
        f"/api/v1/projects/proj-test/project/spec/evidence/{evidence.id}/decision",
        json={"decision": decision, "reason": reason},
        headers=auth_headers,
    )
    assert answer.status_code == 200, answer.text


async def _review_entries_for(agent, task_id):
    async with async_session_factory() as db:
        return (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == agent)
                    .where(InboundQueueEntry.origin_type == "divergence")
                    .where(InboundQueueEntry.review_task_id == task_id)
                )
            )
            .scalars()
            .all()
        )


@pytest.mark.parametrize("decision", ["accepted", "rejected"])
async def test_deciding_own_evidence_does_not_duplicate_a_restaffed_review(
    app, auth_headers, builder, bind_runner, tmp_path, decision
):
    """F1168: no operator hold exists here, so deciding evidence asks no previous reviewer again."""
    task_id, run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)
    assert await evaluate_run_end(run_id) is not None
    assert (await _diverged_payload(run_id))["outcome"] == "restaffed"
    before = await _review_entries_for(GAMMA, task_id)
    assert len(before) == 1
    with patch("hub.turn_scheduler.schedule_agent", _no_schedule):
        await _decide_the_awaiting_evidence(app, auth_headers, task_id, decision, "wrong commit")
    assert await _review_entries_for(BETA, task_id) == []
    assert [e.id for e in await _review_entries_for(GAMMA, task_id)] == [e.id for e in before]
    assert (await _diverged_payload(run_id))["outcome"] == "restaffed"


async def test_a_decision_with_no_held_review_on_record_asks_nobody(
    app, auth_headers, builder, bind_runner, tmp_path
):
    """Control: the review never ended on the hold (no divergence recorded), so nothing is asked."""
    task_id, _run_id = await _held_review(app, auth_headers, builder, bind_runner, tmp_path)

    with patch("hub.turn_scheduler.schedule_agent", _no_schedule):
        await _decide_the_awaiting_evidence(app, auth_headers, task_id, "accepted")

    assert await _review_entries_for(BETA, task_id) == []


async def _no_schedule(*_args, **_kwargs):
    return None
