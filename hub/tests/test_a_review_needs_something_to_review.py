"""A firing must not stage a review it cannot start.

Measured live on the trial Hub, 2026-08-28. A loop claimed a task, the agent worked it and moved it
to `completed` **without recording evidence**, and the next firing selected it for review. The
selection is staged before the turn is dispatched, so `enter_selected_task` moved the task
`completed -> under_review` and wrote a reviewer into `assignee`, and *then* the trigger refused:

    task task-1b7af6b595e6 has no recorded evidence, so there is no commit to review.
    Evidence naming a commit is what a review turn is given.

The firing was recorded `failed`. The task was left in `under_review` held by a reviewer who never
ran — which is the F70 wedge, reached by a new route — and every firing after it repeated the same
sequence, because `under_review` with a stale assignee is exactly what the walk recovers and
re-staffs.

Nothing in `decide_firing` had ever asked whether a review turn could be provisioned. The word
"evidence" did not appear in `scheduler.py` at all: the reviewer ladder answered *who*, and nothing
answered *whether*.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EvidenceFootprint,
    Loop,
    RequirementEvidence,
    SpecDocument,
    SpecRequirement,
    Task,
)
from hub.scheduler import DECISION_CLAIM, decide_firing
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

pytestmark = pytest.mark.asyncio

AUTHOR = "ev-author"
REVIEWER = "ev-reviewer"
NOW = datetime.now(timezone.utc)


async def _loop_with_completed_task(db, *, suffix):
    job = AIJob(
        id=f"job-ev-{suffix}",
        project_id="proj-test",
        name=f"EV {suffix}",
        agent=AUTHOR,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-ev-{suffix}", project_id="proj-test", job_id=job.id, purpose=f"ev {suffix}"
    )
    db.add(loop)
    await db.commit()
    task = Task(
        id=f"task-ev-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status="pending",
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()

    # Walked, never constructed at `completed`: `_agent_that_completed` reads the history, and a
    # task with no author is declined by the ladder for a different reason entirely — the test
    # would pass while proving nothing.
    actor = run_actor(run_id=f"run-{AUTHOR}-{task.id}", agent=AUTHOR)
    for status in ("assigned", "in_progress", "completed"):
        await apply_transition(db, task, status, actor)
    await db.commit()
    return job, loop, task


async def _evidence_for(db, task_id, *, suffix, commit_sha):
    db.add(
        SpecDocument(
            id=f"doc-ev-{suffix}",
            project_id="proj-test",
            path=f"spec/ev-{suffix}.html",
            title="Ledger",
            phase="current",
            kind="capability",
        )
    )
    db.add(
        SpecRequirement(
            id=f"req-ev-{suffix}",
            project_id="proj-test",
            document_id=f"doc-ev-{suffix}",
            identifier="FR-1",
            key="fr-1",
            digest="d" * 64,
        )
    )
    db.add(
        RequirementEvidence(
            id=f"ev-{suffix}",
            project_id="proj-test",
            requirement_id=f"req-ev-{suffix}",
            task_id=task_id,
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor=AUTHOR,
            summary="all green",
            produced_at=NOW - timedelta(minutes=5),
        )
    )
    db.add(
        EvidenceFootprint(
            id=f"fp-{suffix}",
            project_id="proj-test",
            evidence_id=f"ev-{suffix}",
            kind="git",
            commit_sha=commit_sha,
            branch="agentweave/author",
            observed_at=NOW - timedelta(minutes=5),
        )
    )
    await db.commit()


async def _roster(app, auth_headers, bind_runner, *names):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    for name in names:
        await bind_runner(name, cli="claude")


async def test_a_completed_task_with_no_evidence_is_not_selected_for_review(
    app, auth_headers, bind_runner
):
    """The reproduction, and the assertion that separates the fix from doing nothing."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_completed_task(db, suffix="none")
        decision = await decide_firing(db, loop, default_agent=AUTHOR)

    assert decision.kind != DECISION_CLAIM
    assert [entry[0] for entry in decision.unstaffed] == [task.id]
    reason = decision.unstaffed[0][1]
    assert "no recorded evidence" in reason
    assert "naming a commit" in reason


async def test_the_task_is_left_in_completed_rather_than_wedged_in_under_review(
    app, auth_headers, bind_runner
):
    """The damage the old order did. Selecting it is what moved it, and moving it is what stuck."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_completed_task(db, suffix="wedge")
        await decide_firing(db, loop, default_agent=AUTHOR)

    async with async_session_factory() as db:
        after = (await db.execute(select(Task).where(Task.id == task.id))).scalar_one()
        assert after.status == "completed"
        assert after.assignee != REVIEWER


async def test_a_completed_task_whose_evidence_names_a_commit_is_still_selected(
    app, auth_headers, bind_runner
):
    """The other direction. The gate must refuse only what genuinely cannot be reviewed."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_completed_task(db, suffix="good")
        await _evidence_for(db, task.id, suffix="good", commit_sha="a" * 40)
        decision = await decide_firing(db, loop, default_agent=AUTHOR)

    assert decision.kind == DECISION_CLAIM
    assert [selection.task.id for selection in decision.selections] == [task.id]
    assert decision.selections[0].is_review is True
    assert decision.unstaffed == ()


async def test_evidence_that_names_no_commit_is_refused_with_its_own_reason(
    app, auth_headers, bind_runner
):
    """`commit_for_task_review` distinguishes these two states; the gate must carry both through.

    "No evidence at all" and "evidence that names no commit" have different remedies — record some,
    versus this project is not a git repository — which is why that function keeps them apart. A
    gate that flattened them would undo the distinction at the surface an operator reads.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop, task = await _loop_with_completed_task(db, suffix="nocommit")
        await _evidence_for(db, task.id, suffix="nocommit", commit_sha="")
        decision = await decide_firing(db, loop, default_agent=AUTHOR)

    assert decision.kind != DECISION_CLAIM
    reason = decision.unstaffed[0][1]
    assert "none of it names a commit" in reason


async def test_ordinary_work_behind_an_unreviewable_task_is_still_started(
    app, auth_headers, bind_runner
):
    """D4: surface the step, do not stop the flow. `continue`, not `return`."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, loop, stuck = await _loop_with_completed_task(db, suffix="behind")
        db.add(
            Task(
                id="task-ev-behind-next",
                project_id="proj-test",
                title="the next thing",
                status="pending",
                loop_id=loop.id,
            )
        )
        await db.commit()
        decision = await decide_firing(db, loop, default_agent=AUTHOR)

    assert decision.kind == DECISION_CLAIM
    assert [selection.task.id for selection in decision.selections] == ["task-ev-behind-next"]
    assert [entry[0] for entry in decision.unstaffed] == [stuck.id]
