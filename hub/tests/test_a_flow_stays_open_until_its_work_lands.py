"""F1080 -- a flow stays open until its approved work has landed
(`a-checks-send-back-returns-the-task-s-accepted-evidence`, FR-6 to FR-8, design D2).

A flow with `stop_when_queue_empties` ended on the firing after its last task was approved, while
that task's landing was still queued for its batch's checks. The batch then failed and sent the
task back to `revision_needed`, and nothing resumed it: the flow that would have was already over.

Driven through real firings (`_fire_job_internal`), the real `stalls` recorder and the mender.
Landings are written as rows, in the states `landing_queue` gives them; the send-back writes what
`landing_queue._send_back` writes (the landing `sent_back`, the task `revision_needed`).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub import stalls
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, JobRun, Loop, Stall, Task, TaskLanding
from hub.landing_queue import CHECKING, LANDED, QUEUED, SENT_BACK
from hub.loop_ending import QUEUE_DRAINED_REASON
from hub.scheduler import DECISION_CLAIM, DECISION_IN_FLIGHT, JobScheduler, decide_firing

from .test_a_stalled_project_wakes_the_mender import mender_on
from .test_agent_trigger import _init_repo
from .test_flow_fires_a_review_turn import AUTHOR, REVIEWER, _flow
from .test_review_turn import _roster
from .test_the_mender_wakes_only_for_real_stalls import _fire, _the_mender_was_woken

pytestmark = pytest.mark.asyncio

TASK = "task-a5f1"
LANDING_ID = "landing-1"


async def _approved_flow(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, *, landing_state
):
    """A flow with `stop_when_queue_empties` whose only task is approved, with one landing in
    *landing_state* (or none, for a project whose landing runs inside the approval)."""
    await bind_project_workspace(_init_repo(tmp_path / "repo"))
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await mender_on()
    async with async_session_factory() as db:
        db.add(
            Task(
                id=TASK,
                project_id="proj-test",
                title="the flow's last task",
                status="approved",
                assignee=AUTHOR,
            )
        )
        await db.commit()
        job, loop = await _flow(db, suffix="landing", task_id=TASK)
        loop.stop_when_queue_empties = True
        if landing_state is not None:
            db.add(
                TaskLanding(
                    id=LANDING_ID,
                    project_id="proj-test",
                    task_id=TASK,
                    state=landing_state,
                    order_key=1.0,
                )
            )
        await db.commit()
    return job.id, loop.id


async def _set_landing(state):
    async with async_session_factory() as db:
        landing = await db.get(TaskLanding, LANDING_ID)
        landing.state = state
        landing.ended_at = datetime.now(timezone.utc)
        await db.commit()


async def _ended(job_id, loop_id):
    async with async_session_factory() as db:
        job = await db.get(AIJob, job_id)
        loop = await db.get(Loop, loop_id)
        return loop.stop_reason, loop.ending_state, job.enabled


# ---------------------------------------------------------------------------
# FR-6: flow-open-while-landing
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_ac_flow_stays_open_while_its_last_tasks_landing_is_queued(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    job_id, loop_id = await _approved_flow(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, landing_state=QUEUED
    )

    await _fire(JobScheduler(), job_id)

    stop_reason, ending_state, enabled = await _ended(job_id, loop_id)
    assert stop_reason != QUEUE_DRAINED_REASON
    assert ending_state is None
    assert enabled is True


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_ac_flow_ends_after_landing_has_landed(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    job_id, loop_id = await _approved_flow(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, landing_state=QUEUED
    )
    scheduler = JobScheduler()
    await _fire(scheduler, job_id)
    await _set_landing(LANDED)

    await _fire(scheduler, job_id)

    stop_reason, ending_state, enabled = await _ended(job_id, loop_id)
    assert stop_reason == QUEUE_DRAINED_REASON
    assert ending_state == "completed"
    assert enabled is False


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_ac_no_landing_ends_at_approval(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    job_id, loop_id = await _approved_flow(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, landing_state=None
    )

    await _fire(JobScheduler(), job_id)

    stop_reason, ending_state, enabled = await _ended(job_id, loop_id)
    assert stop_reason == QUEUE_DRAINED_REASON
    assert ending_state == "completed"
    assert enabled is False


# ---------------------------------------------------------------------------
# FR-7: landing-wait-is-not-a-stall
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_ac_landing_wait_quiet_records_in_progress_and_wakes_no_mender(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    job_id, loop_id = await _approved_flow(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, landing_state=CHECKING
    )

    await _fire(JobScheduler(), job_id)

    stalled, briefs, skipped = await _the_mender_was_woken()
    assert stalled == [], [s.reason for s in stalled]
    assert briefs == []
    assert skipped == [], [r.error_summary for r in skipped]
    async with async_session_factory() as db:
        assert (await db.execute(select(Stall))).scalars().all() == []
        loop = await db.get(Loop, loop_id)
        decision = await decide_firing(db, loop, default_agent=AUTHOR)
    assert decision.kind == DECISION_IN_FLIGHT
    assert decision.stall_reason is None


# ---------------------------------------------------------------------------
# FR-8: sent-back-task-resumed -- F1080 end to end
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("no_agent_cli_spawn")
async def test_ac_resumed_after_landing_send_back_starts_the_assignees_turn(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    job_id, loop_id = await _approved_flow(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, landing_state=QUEUED
    )
    scheduler = JobScheduler()
    # The firing right after approval, while the batch is still checking it.
    await _fire(scheduler, job_id)
    # The batch fails and sends the task back, as `landing_queue._send_back` writes it.
    await _set_landing(SENT_BACK)
    async with async_session_factory() as db:
        (await db.get(Task, TASK)).status = "revision_needed"
        await db.commit()
        loop = await db.get(Loop, loop_id)
        decision = await decide_firing(db, loop, default_agent=AUTHOR)
    assert decision.kind == DECISION_CLAIM
    assert [(s.task.id, s.agent) for s in decision.selections] == [(TASK, AUTHOR)]

    await _fire(scheduler, job_id)

    stop_reason, ending_state, enabled = await _ended(job_id, loop_id)
    assert (stop_reason, ending_state, enabled) == (None, None, True)
    async with async_session_factory() as db:
        turns = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == AUTHOR)))
            .scalars()
            .all()
        )
        runs = (await db.execute(select(JobRun).where(JobRun.job_id == job_id))).scalars().all()
    assert turns, "no turn was started for the sent-back task's assignee"
    assert any(TASK in entry.content for entry in turns)
    assert not [r for r in runs if r.error_summary == QUEUE_DRAINED_REASON]
    await stalls.drain()
