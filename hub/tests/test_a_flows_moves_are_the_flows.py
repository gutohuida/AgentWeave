"""`a-flows-own-moves-are-recorded-as-the-flows` (F47, F120) — a scheduled job's staging move is
recorded as the job's (`origin="job"`, with `job_id`), the operator's authority unchanged.

Tasks 1.2-1.4 and 1.6. Each of the job assertions fails on the code before the change (the rows
were `origin="actor"` and carried no job).
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.api.v1.agent_trigger import trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Task, TaskTransition
from hub.inbound_queue import new_entry
from hub.scheduler import JobScheduler
from hub.task_transition_service import ORIGIN_ACTOR, ORIGIN_JOB, apply_transition
from hub.task_transitions import operator, run_actor

from .review_evidence import record_review_evidence
from .test_a_loop_does_not_staff_its_own_review import (
    AUTHOR,
    REVIEWER,
    _completed_by,
    _queue,
    _task,
)
from .test_a_task_nothing_will_move_holds_nobody import _no_spawn
from .test_review_dispatch_staffs_the_task import _init_repo
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"


@pytest.fixture
def live_scheduler(monkeypatch):
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _transitions(task_id):
    async with async_session_factory() as db:
        rows = await db.execute(
            select(TaskTransition)
            .where(TaskTransition.task_id == task_id)
            .order_by(TaskTransition.sequence)
        )
        return list(rows.scalars().all())


async def _fire(job_id):
    async with async_session_factory() as db:
        await JobScheduler()._fire_job_internal(
            await db.get(AIJob, job_id), trigger="scheduled", session=db
        )


async def test_a_loop_firing_records_its_staging_move_as_the_jobs(app, auth_headers, bind_runner):
    """1.2 — `pending -> assigned` at a firing: the operator's authority, the job's cause."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="fires")
        task = await _task(db, loop, suffix="fires")
    with _no_spawn():
        await _fire(job.id)
    (row,) = [t for t in await _transitions(task.id) if t.to_status == "assigned"]
    assert row.actor_kind == "operator"
    assert row.origin == ORIGIN_JOB
    assert row.job_id == job.id


async def test_pressing_run_stages_the_move_as_the_loops(
    app, auth_headers, bind_runner, live_scheduler
):
    """1.3c — the loop chose the task; the operator chose only when."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        job, loop = await _queue(db, suffix="press")
        task = await _task(db, loop, suffix="press")
    with _no_spawn():
        res = await app.post(f"/api/v1/projects/{PROJECT}/jobs/{job.id}/run", headers=auth_headers)
    assert res.status_code == 200, res.text
    (row,) = [t for t in await _transitions(task.id) if t.to_status == "assigned"]
    assert (row.origin, row.job_id) == (ORIGIN_JOB, job.id)


async def _completed_review_task(db, suffix):
    job, loop = await _queue(db, suffix=suffix)
    task = await _task(db, loop, suffix=suffix)
    await _completed_by(db, task)
    await record_review_evidence(db, task.id, suffix=f"flows-{suffix}", actor=AUTHOR)
    return job, task


async def _deliver_review(db, task_id, *, entries):
    """`trigger_agent_directly` for REVIEWER with `entries` as the delivered queue entries."""
    conversation = new_conversation(project_id=PROJECT, agent=REVIEWER, origin="operator")
    db.add(conversation)
    for entry in entries:
        entry.conversation_id = conversation.id
        db.add(entry)
    await db.commit()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        await trigger_agent_directly(
            project_id=PROJECT,
            agent=REVIEWER,
            message=f"review {task_id}",
            conversation_id=conversation.id,
            session=db,
            queue_entry_ids=[e.id for e in entries],
        )


def _review_entry(task_id, *, origin_type, job_id=None):
    return new_entry(
        project_id=PROJECT,
        agent=REVIEWER,
        origin_type=origin_type,
        content="review",
        hop_depth=0,
        review_task_id=task_id,
        job_id=job_id,
    )


async def _review_row(task_id):
    return [t for t in await _transitions(task_id) if t.to_status == "under_review"][-1]


async def test_an_operators_by_hand_review_is_the_operators(
    app, auth_headers, bind_runner, tmp_path
):
    """1.3 — control: the operator's own dispatch records `actor`, no job."""
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, task = await _completed_review_task(db, "byhand")
        conversation = new_conversation(project_id=PROJECT, agent=REVIEWER, origin="operator")
        db.add(conversation)
        await db.commit()
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await trigger_agent_directly(
                project_id=PROJECT,
                agent=REVIEWER,
                message="review",
                conversation_id=conversation.id,
                session=db,
                review_task_id=task.id,
            )
    row = await _review_row(task.id)
    assert (row.origin, row.job_id) == (ORIGIN_ACTOR, None)


async def test_a_loop_queued_review_delivered_late_is_recorded_as_the_loops(
    app, auth_headers, bind_runner, tmp_path
):
    """1.3a — the delivery path: the entry carries the job, so a review the operator's own moves
    left `completed` again is still staged as the loop's when its entry is finally delivered."""
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, task = await _completed_review_task(db, "late")
        entry = _review_entry(task.id, origin_type="job", job_id=job.id)
        await _deliver_review(db, task.id, entries=[entry])
    row = await _review_row(task.id)
    assert (row.actor_kind, row.origin, row.job_id) == ("operator", ORIGIN_JOB, job.id)


async def test_a_delivery_with_the_operators_own_entry_is_the_operators(
    app, auth_headers, bind_runner, tmp_path
):
    """1.3b — control: an operator entry among the delivered ones means the operator asked."""
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, task = await _completed_review_task(db, "both")
        entries = [
            _review_entry(task.id, origin_type="job", job_id=job.id),
            _review_entry(task.id, origin_type="operator"),
        ]
        await _deliver_review(db, task.id, entries=entries)
    row = await _review_row(task.id)
    assert (row.origin, row.job_id) == (ORIGIN_ACTOR, None)


async def test_a_divergence_restaffed_review_stays_the_operators(
    app, auth_headers, bind_runner, tmp_path
):
    """1.3d — control (D8, accepted): a divergence restaff is not a job's cause."""
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        _job, task = await _completed_review_task(db, "diverge")
        entry = _review_entry(task.id, origin_type="divergence")
        await _deliver_review(db, task.id, entries=[entry])
    row = await _review_row(task.id)
    assert (row.origin, row.job_id) == (ORIGIN_ACTOR, None)


async def test_apply_transition_validates_the_origin_and_job_pair(app):
    """1.4 — programming errors, asserted on the message."""
    task = Task(id="task-pair", project_id=PROJECT, title="t", status="pending")
    async with async_session_factory() as db:
        db.add(task)
        await db.commit()
        with pytest.raises(ValueError, match="job_id is required with origin 'job'"):
            await apply_transition(db, task, "assigned", operator(), origin=ORIGIN_JOB)
        with pytest.raises(ValueError, match="job_id is required with origin 'job'"):
            await apply_transition(
                db, task, "assigned", operator(), origin=ORIGIN_ACTOR, job_id="job-x"
            )
        with pytest.raises(ValueError, match="acts as the operator"):
            await apply_transition(
                db,
                task,
                "assigned",
                run_actor(run_id="run-x", agent="a"),
                origin=ORIGIN_JOB,
                job_id="job-x",
            )


async def test_the_transitions_route_names_the_job_and_its_kind(app, auth_headers, bind_runner):
    """1.6 — oldest first (the route's order); a loop reads `loop`, a flow reads `flow`."""
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        loop_job, loop = await _queue(db, suffix="route-loop")
        loop_task = await _task(db, loop, suffix="route-loop")
        flow_job, flow = await _queue(db, suffix="route-flow", declares_document=True)
        flow_task = await _task(db, flow, suffix="route-flow")
    with _no_spawn():
        await _fire(loop_job.id)
        await _fire(flow_job.id)
    for task, job, kind in ((loop_task, loop_job, "loop"), (flow_task, flow_job, "flow")):
        res = await app.get(
            f"/api/v1/projects/{PROJECT}/tasks/{task.id}/transitions", headers=auth_headers
        )
        assert res.status_code == 200, res.text
        rows = res.json()["transitions"]
        assert [r["sequence"] for r in rows] == sorted(r["sequence"] for r in rows)
        (moved,) = [r for r in rows if r["origin"] == "job"]
        assert (moved["job_id"], moved["job_name"], moved["job_kind"]) == (job.id, job.name, kind)
        assert all(r["job_id"] is None for r in rows if r["origin"] != "job")


def test_new_entry_carries_the_job():
    entry = new_entry(
        project_id=PROJECT, agent="a", origin_type="job", content="c", hop_depth=0, job_id="job-1"
    )
    assert entry.job_id == "job-1"
    plain = new_entry(
        project_id=PROJECT, agent="a", origin_type="operator", content="c", hop_depth=0
    )
    assert plain.job_id is None
