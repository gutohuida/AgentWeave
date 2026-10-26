"""A flow fires when its work is handed on, not only at its next tick (`flow_advance`).

Measured on the operator's Hub (loop-df5f74816122, 2026-10-25): every `completed -> under_review`
and `revision_needed -> in_progress` hand-off waited for the `*/5` job -- e.g. task-1770fd43f256
completed 14:46:32 and entered review 14:50:02, completed 16:00:25 and entered review 16:05:00.
About twenty hand-offs at ~2.5 minutes each.
"""

import asyncio

import pytest
from sqlalchemy import select

from hub import flow_advance
from hub import scheduler as scheduler_module
from hub.db.engine import async_session_factory
from hub.db.models import Run, Task
from hub.scheduler import JobScheduler
from hub.task_transition_service import ORIGIN_JOB, apply_transition
from hub.task_transitions import operator

from .test_a_flow_does_not_hand_fresh_work_to_its_named_reviewer import _flow
from .test_agent_trigger import _init_repo

pytestmark = pytest.mark.asyncio


class _Recording:
    """Stands in for the Hub's `JobScheduler`: records which jobs were asked to fire."""

    def __init__(self):
        self.fired = []

    async def _fire_job_by_id(self, job_id):
        self.fired.append(job_id)


@pytest.fixture
def recording(app, monkeypatch):
    recorder = _Recording()
    monkeypatch.setattr(scheduler_module, "_scheduler_instance", recorder)
    monkeypatch.setattr(flow_advance, "DEBOUNCE_SECONDS", 0)
    return recorder


async def _flow_task(tmp_path, status="in_progress"):
    repo = _init_repo(tmp_path / "repo")
    async with async_session_factory() as db:
        await _flow(db, repo, delivery={})
        task = await db.get(Task, "task-f767-t-clamp")
        task.status = status
        await db.commit()
    return task.id


async def _move(task_id, *statuses, commit=True, origin=None):
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        for status in statuses:
            if origin == ORIGIN_JOB:
                await apply_transition(db, task, status, operator(), origin=ORIGIN_JOB, job_id="j")
            else:
                await apply_transition(db, task, status, operator())
        if commit:
            await db.commit()
        else:
            await db.rollback()
    await flow_advance.settled()


async def test_a_completed_flow_task_fires_its_flow_once_it_commits(recording, tmp_path):
    task = await _flow_task(tmp_path)
    await _move(task, "completed")
    assert recording.fired == ["job-f767"]


async def test_a_verdict_and_an_approval_each_fire_the_flow(recording, tmp_path):
    task = await _flow_task(tmp_path, status="under_review")
    await _move(task, "revision_needed")
    await _move(task, "in_progress", "completed", "under_review")
    await _move(task, "approved")
    assert recording.fired == ["job-f767"] * 3


async def test_a_move_rolled_back_fires_nothing(recording, tmp_path):
    task = await _flow_task(tmp_path)
    await _move(task, "completed", commit=False)
    assert recording.fired == []


async def test_the_jobs_own_moves_do_not_refire_it(recording, tmp_path):
    task = await _flow_task(tmp_path, status="completed")
    await _move(task, "under_review", origin=ORIGIN_JOB)
    assert recording.fired == []


async def test_requests_while_one_waits_join_it(recording, tmp_path, monkeypatch):
    monkeypatch.setattr(flow_advance, "DEBOUNCE_SECONDS", 0.05)
    task = await _flow_task(tmp_path)
    async with async_session_factory() as db:
        loop_id = (await db.get(Task, task)).loop_id
    for _ in range(5):
        flow_advance.request(loop_id)
    await flow_advance.settled()
    assert recording.fired == ["job-f767"]


async def test_the_end_of_a_run_bound_to_a_flow_task_fires_the_flow(recording, tmp_path):
    task = await _flow_task(tmp_path)
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-adv",
                project_id="proj-test",
                agent="builder",
                status="completed",
                turn_depth=0,
                task_id=task,
            )
        )
        await db.commit()
    flow_advance.after_run("proj-test", "run-adv")
    await flow_advance.settled()
    assert recording.fired == ["job-f767"]


async def test_a_disabled_job_or_ended_loop_is_not_fired(recording, tmp_path):
    from hub.db.models import AIJob

    task = await _flow_task(tmp_path)
    async with async_session_factory() as db:
        (await db.get(AIJob, "job-f767")).enabled = False
        await db.commit()
    await _move(task, "completed")
    assert recording.fired == []


async def test_two_firings_of_one_job_never_decide_at_once(monkeypatch):
    """The tick and an early firing are serialised by the job's lock, so neither decides on state
    the other is midway through writing."""
    scheduler = JobScheduler()
    inside = 0
    overlapped = []

    async def fire(job, trigger="scheduled", session=None):
        nonlocal inside
        inside += 1
        overlapped.append(inside > 1)
        await asyncio.sleep(0.02)
        inside -= 1
        return True

    class _Job:
        id = "job-x"
        enabled = True

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, model, job_id):
            return _Job()

    monkeypatch.setattr(scheduler_module, "async_session_factory", lambda: _Session())
    monkeypatch.setattr(scheduler, "_fire_job_internal", fire)
    await asyncio.gather(*(scheduler._fire_job_by_id("job-x") for _ in range(3)))
    assert overlapped == [False, False, False]


async def test_nothing_is_left_pending_in_the_queue_after_settling(recording, tmp_path):
    task = await _flow_task(tmp_path)
    await _move(task, "completed")
    async with async_session_factory() as db:
        assert (await db.execute(select(Task.status).where(Task.id == task))).scalar_one() == (
            "completed"
        )
    assert flow_advance._scheduled == {}
