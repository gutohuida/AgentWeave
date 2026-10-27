"""F1049 -- the mender wakes only for real stalls (`the-mender-wakes-only-for-real-stalls`, task 1).

The night of 2026-10-26/27 on the operator's Hub: a flow task reached `completed`, the flow fired
three seconds later (`flow_advance`), the author's turn was still running so the review was
deferred, nothing else was claimable, and the firing recorded `loop_stalled` -- six Opus mender
turns, each finding a review about to start. The seconds between an author's `completed` and the end
of its turn are the flow working, not a stall; the end of that turn requests the firing that offers
the review. The sweep still catches a turn that never ends.

These are the acceptance drive of the slice, through real firings (`_fire_job_internal`), the real
`stalls` recorder and the real flow-advance request.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub import flow_advance, stalls
from hub import scheduler as scheduler_module
from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    InboundQueueEntry,
    JobRun,
    Loop,
    Run,
    Stall,
    Task,
    TaskDependency,
)
from hub.scheduler import DECISION_IN_FLIGHT, JobScheduler, decide_firing

from .test_a_stalled_project_wakes_the_mender import mender_on
from .test_agent_trigger import _init_repo
from .test_flow_fires_a_review_turn import AUTHOR, REVIEWER, _attribute_completion, _flow
from .test_review_turn import _author_commit, _reviewable_task, _roster

pytestmark = pytest.mark.asyncio

AUTHOR_RUN = "run-gap-author"


async def _flow_with_a_gap(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, *, dependent, started_at=None
):
    """T1 completed by the author with evidence naming a commit, the author's turn on it still
    `running`, the mender on, and (when asked) T2 waiting on T1's approval."""
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)
    await mender_on()
    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        job, loop = await _flow(db, suffix="gap", task_id="task-1")
        db.add(
            Run(
                id=AUTHOR_RUN,
                project_id="proj-test",
                agent=AUTHOR,
                status="running",
                turn_depth=0,
                task_id="task-1",
                started_at=started_at or datetime.now(timezone.utc),
            )
        )
        if dependent:
            db.add(
                Task(
                    id="task-2",
                    project_id="proj-test",
                    title="needs T1",
                    status="pending",
                    loop_id=loop.id,
                )
            )
            await db.commit()
            db.add(
                TaskDependency(
                    id="tdep-gap",
                    project_id="proj-test",
                    task_id="task-2",
                    depends_on_task_id="task-1",
                )
            )
        await db.commit()
    return job.id, loop.id


async def _fire(scheduler, job_id):
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            await scheduler._fire_job_internal(
                await db.get(AIJob, job_id), trigger="scheduled", session=db
            )
    await stalls.drain()


async def _the_mender_was_woken():
    async with async_session_factory() as db:
        stalled = (
            (await db.execute(select(Stall).where(Stall.cause == "loop_stalled"))).scalars().all()
        )
        briefs = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(InboundQueueEntry.agent == stalls.MENDER)
                )
            )
            .scalars()
            .all()
        )
        skipped = (
            (await db.execute(select(JobRun).where(JobRun.status == "skipped"))).scalars().all()
        )
    return stalled, briefs, skipped


# ---------------------------------------------------------------------------
# hand-off-gap-is-not-a-stall
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_the_gap_between_completed_and_the_turns_end_fires_no_stall(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    job_id, loop_id = await _flow_with_a_gap(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, dependent=True
    )

    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()) as scheduled:
        await _fire(JobScheduler(), job_id)

    stalled, briefs, skipped = await _the_mender_was_woken()
    assert stalled == [], [s.reason for s in stalled]
    assert briefs == []
    assert skipped == []
    assert scheduled.await_count == 0
    async with async_session_factory() as db:
        loop = (await db.execute(select(Loop).where(Loop.id == loop_id))).scalar_one()
        decision = await decide_firing(db, loop, default_agent=AUTHOR)
    assert decision.kind == DECISION_IN_FLIGHT
    assert decision.stall_reason is None


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_the_gap_fires_no_stall_for_a_flow_with_no_dependents(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    job_id, loop_id = await _flow_with_a_gap(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, dependent=False
    )

    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()):
        await _fire(JobScheduler(), job_id)

    stalled, briefs, skipped = await _the_mender_was_woken()
    assert (stalled, briefs, skipped) == ([], [], [])
    async with async_session_factory() as db:
        loop = (await db.execute(select(Loop).where(Loop.id == loop_id))).scalar_one()
        decision = await decide_firing(db, loop, default_agent=AUTHOR)
    assert decision.stall_reason is None


# ---------------------------------------------------------------------------
# review-follows-the-turns-end: what makes the gap safe
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_the_end_of_the_authors_turn_dispatches_the_review(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    job_id, _loop_id = await _flow_with_a_gap(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, dependent=True
    )
    scheduler = JobScheduler()
    monkeypatch.setattr(scheduler_module, "_scheduler_instance", scheduler)
    monkeypatch.setattr(flow_advance, "DEBOUNCE_SECONDS", 0)

    # No `schedule_accepted` stand-in here: the review turn is dispatched for real (its spawn is
    # refused by `no_agent_cli_spawn`, after the entry is queued), and a stall would wake the mender.
    await _fire(scheduler, job_id)
    async with async_session_factory() as db:
        (await db.get(Run, AUTHOR_RUN)).status = "completed"
        await db.commit()
    with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
        flow_advance.after_run("proj-test", AUTHOR_RUN)
        await flow_advance.settled()
    await stalls.drain()

    stalled, briefs, _skipped = await _the_mender_was_woken()
    assert stalled == [] and briefs == []
    async with async_session_factory() as db:
        review = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == REVIEWER)))
            .scalars()
            .all()
        )
    assert [entry.review_task_id for entry in review] == ["task-1"]


# ---------------------------------------------------------------------------
# real-stalls-still-wake-at-once
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_real_stall_wakes_the_mender_on_its_first_firing(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """Nothing is claimable and no run is on any of the flow's tasks: the first firing says so."""
    job_id, _loop_id = await _flow_with_a_gap(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, dependent=True
    )
    async with async_session_factory() as db:
        (await db.get(Run, AUTHOR_RUN)).status = "completed"
        (await db.get(Task, "task-1")).status = "rejected"
        await db.commit()

    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()) as scheduled:
        await _fire(JobScheduler(), job_id)

    stalled, briefs, _skipped = await _the_mender_was_woken()
    assert len(stalled) == 1
    assert len(briefs) == 1 and scheduled.await_count == 1


# ---------------------------------------------------------------------------
# a-hung-author-turn-is-still-caught
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_a_turn_that_never_ends_is_still_reported_by_the_sweep(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    now = datetime.now(timezone.utc) + timedelta(minutes=35)
    await _flow_with_a_gap(
        app,
        auth_headers,
        bind_runner,
        bind_project_workspace,
        tmp_path,
        dependent=True,
        started_at=now - timedelta(minutes=40),
    )

    with patch("hub.turn_scheduler.schedule_accepted", new=AsyncMock()):
        async with async_session_factory() as db:
            await stalls._sweep(db, now)
        await stalls.drain()

    async with async_session_factory() as db:
        causes = {row.cause for row in (await db.execute(select(Stall))).scalars().all()}
    assert {"dead_run", "no_progress"} <= causes
