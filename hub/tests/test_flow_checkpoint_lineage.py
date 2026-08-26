"""`loop-becomes-a-flow` group 6 — the checkpoint lineage belongs to the flow, not to one agent.

Design D7. `agent-loops` §231 already says a firing is briefed with the checkpoint of *"any prior
firing of that same loop, regardless of which conversation produced it"*, and
`latest_checkpoint_for_loop` already retrieves that way — so this group resolves a **latent
disagreement between a requirement that already said "the loop's" and a comment that said "one
agent's"**, which nothing had to settle while every loop had one agent.

That makes most of what is asserted here shipped behaviour rather than new behaviour, and the tests
are written to say so: they are the regression guard that a flow's second agent inherits the first
one's handover, which is the property D7 rejected per-agent chains in order to keep.

**The one thing the review found that D7 does not say** is recorded on the `Checkpoint` model and in
`tasks.md`: for a loop these lineage columns are not merely single-agent, they are *empty*.
`generate_checkpoint` anchors on `latest_checkpoint(conversation.id)`, a loop may not be resume-mode
at all, so every firing is a fresh conversation and every loop checkpoint founds its own lineage.
`test_a_loops_checkpoints_do_not_chain_and_that_is_the_point` pins that down, because a future
reader correcting the comment "back" is the failure this group exists to prevent.
"""

import pytest
from sqlalchemy import select

from hub.checkpoint_generation import render_checkpoint
from hub.checkpoints import (
    compute_envelope,
    create_checkpoint,
    latest_checkpoint_for_loop,
)
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Checkpoint, InboundQueueEntry, Loop, Task
from hub.scheduler import JobScheduler, _compose_loop_briefing

from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

FIRST = "lineage-first"
SECOND = "lineage-second"


async def _flow(db, *, suffix, agent=FIRST, purpose="keep the ledger balanced"):
    job = AIJob(
        id=f"job-lineage-{suffix}",
        project_id="proj-test",
        name=f"Lineage {suffix}",
        agent=agent,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-lineage-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=purpose,
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _task(db, loop, key, *, status="pending", assignee=None):
    task = Task(
        id=f"task-lineage-{key}",
        project_id="proj-test",
        title=f"work {key}",
        status=status,
        loop_id=loop.id,
        assignee=assignee,
    )
    db.add(task)
    await db.commit()
    return task


async def _checkpoint_by(db, loop, agent, body):
    """A checkpoint written by *agent* into its own fresh conversation, as a firing produces one.

    The fresh conversation is the load-bearing part and not incidental: a loop may not be
    resume-mode, so this is the only shape a loop's checkpoint ever has, and reusing one
    conversation across both agents would test a lineage the product cannot produce.
    """
    conversation = new_conversation(project_id="proj-test", agent=agent, origin="job")
    db.add(conversation)
    await db.commit()
    return await create_checkpoint(
        db,
        conversation,
        trigger="task_completion",
        envelope=await compute_envelope(db, conversation),
        body=body,
        loop=loop,
    )


# ---------------------------------------------------------------------------
# 6.1 — the flow fires A, A checkpoints, the flow fires B, B is briefed with A's
# ---------------------------------------------------------------------------


async def test_a_second_agents_briefing_carries_the_first_agents_checkpoint(app):
    """D7's whole position in one assertion. Per-agent chains were rejected because a reviewer
    would start blind to what the implementer was thinking, "which is most of what a handover
    carries" — so the second agent's briefing has to contain the first one's words."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="carry")
        task = await _task(db, loop, "carry")
        await _checkpoint_by(db, loop, FIRST, "The ledger reconciles except for row 42.")

        prior = await latest_checkpoint_for_loop(db, loop.id)
        briefing = await _compose_loop_briefing(db, loop, task, prior)

    assert "row 42" in briefing
    assert f"Agent: {FIRST}" in briefing


async def test_the_briefing_carries_the_newest_checkpoint_whoever_wrote_it(app):
    """Two agents, two checkpoints, and the loop's continuity is the *loop's* — the third firing
    briefs from whichever came last, not from the one belonging to the agent about to run."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="newest")
        task = await _task(db, loop, "newest")
        await _checkpoint_by(db, loop, FIRST, "First pass done; row 42 still off.")
        await _checkpoint_by(db, loop, SECOND, "Row 42 was a rounding error in the importer.")

        prior = await latest_checkpoint_for_loop(db, loop.id)
        briefing = await _compose_loop_briefing(db, loop, task, prior)

    assert "rounding error" in briefing
    assert "First pass done" not in briefing
    assert f"Agent: {SECOND}" in briefing


async def test_a_checkpoint_from_a_different_loop_is_not_carried(app):
    """The other side of `loop_id`. Two loops in one project must not read each other's handover —
    `latest_checkpoint_for_loop` is scoped by the column precisely so that "the newest checkpoint"
    never means "the newest in the project"."""
    async with async_session_factory() as db:
        _job_a, loop_a = await _flow(db, suffix="mine")
        _job_b, loop_b = await _flow(db, suffix="theirs")
        task = await _task(db, loop_a, "mine")
        await _checkpoint_by(db, loop_b, SECOND, "Belongs to the other loop entirely.")

        prior = await latest_checkpoint_for_loop(db, loop_a.id)
        briefing = await _compose_loop_briefing(db, loop_a, task, prior)

    assert prior is None
    assert "other loop entirely" not in briefing


# ---------------------------------------------------------------------------
# 6.2 — each checkpoint in a multi-agent lineage identifies its author
# ---------------------------------------------------------------------------


async def test_every_checkpoint_in_a_multi_agent_lineage_names_its_author(app):
    """Shipped behaviour, asserted because group 6 makes it load-bearing. Once a lineage holds more
    than one agent's work, an unattributed checkpoint is a handover whose reader cannot tell whether
    they are resuming their own reasoning or inheriting somebody else's."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="authors")
        await _checkpoint_by(db, loop, FIRST, "Implemented the importer fix.")
        await _checkpoint_by(db, loop, SECOND, "Reviewed the importer fix; one concern.")

        rows = (
            (
                await db.execute(
                    select(Checkpoint)
                    .where(Checkpoint.loop_id == loop.id)
                    .order_by(Checkpoint.created_at, Checkpoint.id)
                )
            )
            .scalars()
            .all()
        )
        rendered = [render_checkpoint(row) for row in rows]

    assert {row.agent for row in rows} == {FIRST, SECOND}
    for row, text in zip(rows, rendered, strict=True):
        assert f"Agent: {row.agent}" in text


async def test_a_loops_checkpoints_do_not_chain_and_that_is_the_point(app):
    """The finding the group 6 spec review turned up, pinned so a later reader cannot "correct" the
    model comment back.

    `generate_checkpoint` anchors on `latest_checkpoint(conversation.id)`, and a loop may not be
    resume-mode — `api/v1/jobs.py` refuses it outright — so every firing is a fresh conversation and
    every loop checkpoint founds its own lineage. These columns have never linked a loop's
    checkpoints and do not now; `loop_id` plus `created_at` is what carries a loop forward."""
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="nochain")
        first = await _checkpoint_by(db, loop, FIRST, "One.")
        second = await _checkpoint_by(db, loop, SECOND, "Two.")

    assert first.previous_checkpoint_id is None
    assert second.previous_checkpoint_id is None
    assert first.lineage_id == first.id
    assert second.lineage_id == second.id
    # And the loop still reads them as one continuity, which is the whole distinction.
    async with async_session_factory() as db:
        assert (await latest_checkpoint_for_loop(db, loop.id)).id == second.id


# ---------------------------------------------------------------------------
# 6.3 — a document-less loop's lineage behaves exactly as before
# ---------------------------------------------------------------------------


async def test_latest_checkpoint_for_loop_breaks_a_tie_by_insertion_order_not_id(app):
    """F55. `datetime.now()` on this machine can return an identical value across consecutive
    calls (measured: five back-to-back calls, same microsecond), so two checkpoints from the same
    clock tick are a real occurrence, not a theoretical one. `latest_checkpoint_for_loop` used to
    tie-break on `Checkpoint.id.desc()` — a random `ckpt-…` id with no relationship to insertion
    order — so ids are chosen here so the *older* checkpoint's id sorts alphabetically AFTER the
    *newer* one's: the exact shape that picked the wrong row under the old ordering.
    """
    async with async_session_factory() as db:
        _job, loop = await _flow(db, suffix="tie")
        conversation = new_conversation(project_id="proj-test", agent=FIRST, origin="job")
        db.add(conversation)
        await db.commit()
        tied_at = conversation.created_at

        older = Checkpoint(
            id="ckpt-zzz-older",
            project_id="proj-test",
            conversation_id=conversation.id,
            agent=FIRST,
            trigger="task_completion",
            status="ready",
            loop_id=loop.id,
            lineage_id="ckpt-zzz-older",
            body="Older, but its id sorts after the newer one's.",
            created_at=tied_at,
        )
        db.add(older)
        await db.commit()

        newer = Checkpoint(
            id="ckpt-aaa-newer",
            project_id="proj-test",
            conversation_id=conversation.id,
            agent=FIRST,
            trigger="task_completion",
            status="ready",
            loop_id=loop.id,
            lineage_id="ckpt-aaa-newer",
            body="Newer, and must win the tie regardless of its id.",
            created_at=tied_at,
        )
        db.add(newer)
        await db.commit()

    async with async_session_factory() as db:
        latest = await latest_checkpoint_for_loop(db, loop.id)

    assert latest.id == "ckpt-aaa-newer", "insertion order, not a random id, must decide the tie"


async def test_a_document_less_single_agent_loop_is_unchanged(app, auth_headers, bind_runner):
    """The regression bar D7's migration plan sets: *"The behaviour of a flow with one agent is
    today's behaviour, so the regression suite is the existing loop suite, unmodified."* Driven
    through a real firing rather than through the composer, so the assertion covers the path a loop
    actually takes — including that `_fire_additional_selection` never runs for it."""
    await _roster(app, auth_headers, bind_runner, FIRST)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="plain")
        assert loop.spec_document_id is None
        await _task(db, loop, "plain")
        await _checkpoint_by(db, loop, FIRST, "Carried from the previous firing.")

    scheduler = JobScheduler()
    async with async_session_factory() as db:
        fresh_job = await db.get(AIJob, job.id)
        await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    async with async_session_factory() as db:
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.origin_type == "job")
                )
            )
            .scalars()
            .all()
        )

    assert len(entries) == 1
    assert entries[0].agent == FIRST
    assert "Carried from the previous firing." in entries[0].content
    assert entries[0].review_task_id is None
