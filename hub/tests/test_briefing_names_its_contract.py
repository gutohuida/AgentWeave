"""`a-flow-briefing-names-its-contract` — F140 and F143.

The briefing is the one text an agent inside a flow reliably reads, and it told the agent to
*"finish the task and stop"* without ever saying what finishing **is**. Measured on 2026-08-30: two
Haiku agents did the work, committed it, recorded evidence and submitted checkpoint notes; neither
task ever left `in_progress`, because the briefing named `submit_checkpoint_notes` (which both
called) and never named `update_task` (which neither called). The next firing re-briefed both for
the same work, and would have done so forever.

The same function computed `is_review` at both call sites and dropped it on the next line, so a
reviewer received the implementation briefing verbatim while the turn context said the opposite.

**Both defects were reproduced against unmodified code before anything was written**, in the
inverted form these tests now hold: `_compose_loop_briefing(db, loop, task, None)` called twice
returned byte-identical strings (F143 — there was no parameter that could have made them differ),
and the composed briefing contained `submit_checkpoint_notes` while containing neither
`update_task`, nor `record_evidence`, nor the word `completed` (F140). Section 1 is that
reproduction with its assertions turned around.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    Loop,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskRequirementLink,
)
from hub.scheduler import _compose_loop_briefing

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"


async def _loop(db, *, suffix, document=None):
    job = AIJob(
        id=f"job-contract-{suffix}",
        project_id=PROJECT,
        name=f"Contract {suffix}",
        agent="contract-owner",
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-contract-{suffix}",
        project_id=PROJECT,
        job_id=job.id,
        purpose=f"contract {suffix}",
        spec_document_id=document,
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _task(db, loop, key, *, status="assigned", title=None):
    task = Task(
        id=f"task-contract-{key}",
        project_id=PROJECT,
        title=title or f"Add power(a, b) to calc_{key}.py",
        description="Create the file with exactly one function. Change nothing else.",
        acceptance_criteria=["the function exists", "nothing else moved"],
        status=status,
        loop_id=loop.id,
        assignee="contract-owner",
    )
    db.add(task)
    await db.commit()
    return task


async def _link_requirement(db, task, *, suffix, identifier="FR-1"):
    """A requirement of record the task serves, so the briefing has an identifier to name."""
    db.add(
        SpecDocument(
            id=f"doc-contract-{suffix}",
            project_id=PROJECT,
            path=f"spec/contract-{suffix}.html",
            title=f"Contract {suffix}",
            phase="approved",
            kind="change-spec",
        )
    )
    db.add(
        SpecRequirement(
            id=f"req-contract-{suffix}",
            project_id=PROJECT,
            document_id=f"doc-contract-{suffix}",
            identifier=identifier,
            key=identifier.lower(),
            digest="d" * 64,
        )
    )
    db.add(
        TaskRequirementLink(
            id=f"trl-contract-{suffix}",
            project_id=PROJECT,
            task_id=task.id,
            requirement_id=f"req-contract-{suffix}",
        )
    )
    await db.commit()


async def _brief(loop, task, *, is_review):
    async with async_session_factory() as db:
        fresh = (await db.execute(select(Loop).where(Loop.id == loop.id))).scalar_one()
        fresh_task = None
        if task is not None:
            fresh_task = (await db.execute(select(Task).where(Task.id == task.id))).scalar_one()
        return await _compose_loop_briefing(db, fresh, fresh_task, None, is_review=is_review)


# ---------------------------------------------------------------------------
# 1. The two reproductions
# ---------------------------------------------------------------------------


async def test_f143_a_review_briefing_differs_from_an_implementation_briefing(app):
    """F143 in one line, and the cheapest deterministic reproduction of it.

    Before the fix these two strings were **identical**, because `_compose_loop_briefing` had no
    `is_review` parameter — there was nothing that could have made them differ. The reviewer was
    handed *"Finish the task below and stop"* followed by the implementation description, while the
    turn context said *"You are reviewing someone else's work, not doing your own."* The agent's own
    transcript recorded the contradiction and resolved it correctly by luck; the other resolution is
    a reviewer that re-implements the work it was meant to check and approves its own edit.
    """
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="f143", document="doc-f143")
        task = await _task(db, loop, "f143")
        task.status = "under_review"
        await db.commit()

    as_work = await _brief(loop, task, is_review=False)
    as_review = await _brief(loop, task, is_review=True)

    assert as_work != as_review, "the reviewer is still handed the implementation briefing"


async def test_f140_the_implementation_briefing_names_the_transition_that_finishes_the_work(app):
    """F140. The briefing named the tool both agents called and never named the one neither did.

    `update_task` was in the turn context's tool inventory the whole time, as a bare signature. An
    inventory says a capability exists; it does not say that using it is how the firing's work is
    concluded. This asserts the briefing itself says so.
    """
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="f140", document="doc-f140")
        task = await _task(db, loop, "f140")

    briefing = await _brief(loop, task, is_review=False)

    assert "update_task" in briefing
    assert "completed" in briefing
    assert task.id in briefing


# ---------------------------------------------------------------------------
# 2. The completion contract
# ---------------------------------------------------------------------------


async def test_the_briefing_states_the_status_the_task_is_in_now(app):
    """A transition needing two steps is visible as two steps rather than implied as one."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="status", document="doc-status")
        task = await _task(db, loop, "status", status="assigned")

    briefing = await _brief(loop, task, is_review=False)

    assert "assigned" in briefing
    assert "in_progress" in briefing, "the hop through in_progress is not optional from `assigned`"


async def test_a_task_already_in_progress_is_told_only_the_remaining_step(app):
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="inprog", document="doc-inprog")
        task = await _task(db, loop, "inprog", status="in_progress")

    briefing = await _brief(loop, task, is_review=False)

    assert "in_progress" in briefing
    assert "completed" in briefing


async def test_a_task_returned_for_revision_is_told_the_step_that_is_actually_legal(app):
    """Round 2, design D7 — the case round 1 of this change got wrong.

    `CLAIMABLE_STATUSES` is `_statuses_in(BAND_AGENT_ACTIONABLE)`, which includes
    `revision_needed`, and `enter_selected_task` moves only `pending -> assigned`. So a task
    returned for revision is claimed and briefed **at `revision_needed`** — from which `TRANSITIONS`
    offers `in_progress` and nothing else but operator rejection. A briefing naming `completed` as
    the next call would describe a call the machine refuses, which is the defect this change exists
    to remove, reintroduced by the fix.
    """
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="revneed", document="doc-revneed")
        task = await _task(db, loop, "revneed", status="revision_needed")

    briefing = await _brief(loop, task, is_review=False)

    assert "revision_needed" in briefing
    assert "in_progress" in briefing, "the only legal edge out of revision_needed is not named"


async def test_the_cost_of_ending_without_moving_the_task_is_stated(app):
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="cost", document="doc-cost")
        task = await _task(db, loop, "cost")

    briefing = await _brief(loop, task, is_review=False)

    assert "next firing" in briefing


async def test_a_firing_that_claims_no_task_states_no_contract(app):
    """`selection` is None on the never-filled queue: no task, so nothing to finish."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="notask", document="doc-notask")

    briefing = await _brief(loop, None, is_review=False)

    assert "update_task" not in briefing
    assert "record_evidence" not in briefing


# ---------------------------------------------------------------------------
# 3. Requirements and evidence, named only when they exist
# ---------------------------------------------------------------------------


async def test_a_task_that_serves_requirements_has_them_named_by_identifier(app):
    """Design D3. Naming the identifiers the link table actually holds is what keeps the
    instruction from producing the 404 a guessed identifier gets."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="reqs", document="doc-reqs")
        task = await _task(db, loop, "reqs")
        await _link_requirement(db, task, suffix="reqs", identifier="FR-3")

    briefing = await _brief(loop, task, is_review=False)

    assert "record_evidence" in briefing
    assert "FR-3" in briefing


async def test_a_task_that_serves_no_requirement_says_nothing_about_evidence(app):
    """An instruction to record evidence against a requirement that does not exist is refused
    when followed, which is worse than silence."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="noreqs", document="doc-noreqs")
        task = await _task(db, loop, "noreqs")

    briefing = await _brief(loop, task, is_review=False)

    assert "record_evidence" not in briefing
    assert "FR-" not in briefing


async def test_the_evidence_wording_survives_the_approval_refusal_change(app):
    """Round 2, design D12. `record_evidence`'s tool-surface line says *"approving a task
    integrates nothing until evidence has been accepted"* — true today and **false** the moment
    `approval-refuses-unaccepted-evidence` lands, because approval will then be refused outright
    rather than approving and merging nothing. The briefing must be true under both regimes."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="evwording", document="doc-evwording")
        task = await _task(db, loop, "evwording")
        await _link_requirement(db, task, suffix="evwording")

    briefing = await _brief(loop, task, is_review=False)

    assert "integrates nothing" not in briefing
    assert "awaiting" in briefing


async def test_the_notes_and_the_transition_are_asked_for_together(app):
    """Round 3, design D14. The flow branch already asks for notes *"somebody else reads it"*, and
    that was **false**: `consider_handover` declines when `_task_this_run_completed` finds no
    `completed` transition for the run, so in F140's drive both agents' notes were never consumed
    and `agent-flows:379` and `:412` were unreachable in a real flow. The briefing must ask for the
    record and for the thing that delivers it in the same breath."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="notes", document="doc-notes")
        task = await _task(db, loop, "notes")

    briefing = await _brief(loop, task, is_review=False)

    notes_at = briefing.index("submit_checkpoint_notes")
    moves_at = briefing.index("update_task")
    assert (
        abs(notes_at - moves_at) < 700
    ), "the two are stated far enough apart to read as unrelated"


# ---------------------------------------------------------------------------
# 4. The review branch
# ---------------------------------------------------------------------------


async def _review_briefing(suffix):
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix=suffix, document=f"doc-{suffix}")
        task = await _task(db, loop, suffix, status="under_review")
    return await _brief(loop, task, is_review=True), task


async def test_a_reviewer_is_not_told_to_build_what_it_is_reviewing(app):
    briefing, _task_row = await _review_briefing("revbuild")

    assert "Finish the task below and stop." not in briefing
    assert "review" in briefing.lower()


async def test_the_review_briefing_names_both_verdicts_and_both_are_legal(app):
    """Design D5. Stated on this channel as well as the turn context, deliberately: F140 measured
    that the briefing is the channel that drives tool calls, and F45 measured the other side — with
    the context channel already saying how, no flow-dispatched reviewer had ever recorded a verdict.

    Both are legal from `under_review`, which is where `enter_selected_task` puts a review's task
    before the turn begins.
    """
    briefing, _task_row = await _review_briefing("verdicts")

    assert "approved" in briefing
    assert "revision_needed" in briefing
    assert "update_task" in briefing


async def test_the_review_briefing_does_not_name_the_commit(app):
    """Round 2, design D9. The briefing is composed at firing time; the commit is resolved one step
    later at spawn, by `commit_for_task_review`. Naming it here is a second copy of a fact that can
    disagree with the checkout the reviewer is standing in — the case `ReviewContext.work_moved`
    already exists to handle, on the channel that resolved it."""
    briefing, _task_row = await _review_briefing("shaless")

    assert "commit" not in briefing.lower()


async def test_the_review_briefing_identifies_the_loops_standing_message(app):
    """Round 2 D8 as narrowed by round 3 D16. The delivered text is the briefing followed by
    `job.message`, which is authored once and delivered on every firing — in F143's own transcript
    it read *"Work the task you have been given"*, to a reviewer. The briefing says what that text
    **is**; it must not tell the agent to disregard it, because a loop's message may itself be
    written to address a review."""
    briefing, _task_row = await _review_briefing("standing")

    assert "standing message" in briefing.lower()
    assert "ignore" not in briefing.lower()
    assert "disregard" not in briefing.lower()


async def test_the_review_branch_still_states_the_tier(app):
    """`agent-flows:314` is not suspended by a review turn."""
    briefing, _task_row = await _review_briefing("tier")

    assert "flow" in briefing.lower()


# ---------------------------------------------------------------------------
# 5. What must not regress
# ---------------------------------------------------------------------------


async def test_a_document_less_loop_still_claims_nothing_about_routing(app):
    """`agent-flows:314`'s second scenario, and round 2's D11: `test_flow_width.py` asserts the
    words "review" and "flow" are absent from a document-less loop's *entire* briefing. Every word
    the completion contract adds to that branch has to clear both."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="plainloop")
        assert loop.spec_document_id is None
        task = await _task(db, loop, "plainloop")

    briefing = await _brief(loop, task, is_review=False)

    assert "review" not in briefing.lower()
    assert "flow" not in briefing.lower()
    assert "update_task" in briefing, "the lifecycle is the same in a loop; the contract is too"
    assert "completed" in briefing


async def test_a_flow_still_names_submit_checkpoint_notes(app):
    """It is excluded from the turn context's tool inventory on purpose, so the briefing is the
    only place it is named. Adding the completion contract must not displace it."""
    async with async_session_factory() as db:
        _job, loop = await _loop(db, suffix="notesstay", document="doc-notesstay")
        task = await _task(db, loop, "notesstay")

    briefing = await _brief(loop, task, is_review=False)

    assert "submit_checkpoint_notes" in briefing
    assert "routing is the flow's job" in briefing
