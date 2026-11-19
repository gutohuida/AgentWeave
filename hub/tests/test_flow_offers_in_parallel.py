"""Flows and leads hand out in parallel (`one-profile-runs-many-turns-at-once-on-different-tasks`,
task `flow-offers`: FR-4).

While the project's "profiles run in parallel" switch is on, a flow offers a claimable task to a
profile even while that profile is running or holds other tasks, one firing may start more than
one of that profile's tasks, and a lead's hand-outs to one profile run at the same time. A
provider hold on the profile still stops every new offer.

Driven through a real build over an approved document with two independent tasks and one builder,
fired by the scheduler with a spawn that hangs until the test releases it, so "both running" is a
fact the database and the spawned processes both show (ac-flow-two-offers).
"""

from __future__ import annotations

from typing import List

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, JobRun, Loop, Run
from hub.scheduler import JobScheduler, decide_firing

from .test_a_held_agent_is_busy import _hold
from .test_a_lead_hands_out_the_work import (
    HAND_OUT,
    _approved,
    _build,
    _run_headers,
    _tasks,
)
from .test_agent_trigger import _await_background_run
from .test_start_gate import _patched, _repo_project, _set_project, _Spawns

pytestmark = pytest.mark.asyncio


async def _loop() -> Loop:
    async with async_session_factory() as db:
        (loop,) = (await db.execute(select(Loop))).scalars().all()
        return loop


async def _fire() -> None:
    """One firing of the build's flow, through the scheduler's own path and the real start gate."""
    loop = await _loop()
    async with async_session_factory() as db:
        job = await db.get(AIJob, loop.job_id)
        await JobScheduler()._do_fire_job(job, "scheduled", db)


async def _dev_runs(status: str = "running") -> List[Run]:
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(Run).where(Run.agent == "dev", Run.status == status)))
            .scalars()
            .all()
        )


async def _dev_entries() -> List[InboundQueueEntry]:
    async with async_session_factory() as db:
        return list(
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == "dev")))
            .scalars()
            .all()
        )


async def _one_builder_build(app, auth_headers, bind_runner, bind_project_workspace, tmp_path, mp):
    await _repo_project(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, mp, "dev", "qa", "lead"
    )
    await _approved(app, auth_headers)


async def test_with_the_switch_on_one_firing_starts_both_tasks_for_the_one_builder(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-flow-two-offers, first clause: both tasks start for the builder in one firing, and the
    second firing, with the builder mid-turn on both, starts nothing more."""
    await _one_builder_build(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _set_project(profiles_run_in_parallel=True)
    await _build(app, auth_headers, driver="flow", builders=["dev"], level="reviewed")
    tasks = await _tasks()
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            await _fire()
            await spawns.wait_for(2)
            running = await _dev_runs()
            assert sorted(run.task_id for run in running) == sorted(
                task.id for task in tasks.values()
            )
            # Each started turn's own `JobRun` says it is under way, none failed (FR-4's dispatch).
            async with async_session_factory() as db:
                job_runs = list((await db.execute(select(JobRun))).scalars().all())
            assert [run.status for run in job_runs] == ["in_progress", "in_progress"], [
                (run.status, run.error_summary) for run in job_runs
            ]
            # Mid-turn on both: the next firing offers neither again.
            await _fire()
            assert len(await _dev_entries()) == 2
            assert len(spawns.cwds) == 2
        finally:
            spawns.release_all()
            await _await_background_run()


async def test_with_the_switch_on_a_running_builder_is_still_offered_its_other_task(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """FR-4: a profile with a running run, on other work, is offered a claimable task."""
    await _one_builder_build(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _set_project(profiles_run_in_parallel=True)
    await _build(app, auth_headers, driver="flow", builders=["dev"], level="reviewed")
    async with async_session_factory() as db:
        db.add(Run(id="run-dev-elsewhere", project_id="proj-test", agent="dev", status="running"))
        await db.commit()
    tasks = await _tasks()

    async with async_session_factory() as db:
        loop = await db.get(Loop, (await _loop()).id)
        job = await db.get(AIJob, loop.job_id)
        decision = await decide_firing(db, loop, default_agent=job.agent)

    assert sorted((s.task.id, s.agent) for s in decision.selections) == sorted(
        (task.id, "dev") for task in tasks.values()
    )
    assert decision.deferred == ()


async def test_with_the_switch_on_a_provider_hold_on_the_builder_starts_neither(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-flow-two-offers, second clause."""
    await _one_builder_build(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _set_project(profiles_run_in_parallel=True)
    await _build(app, auth_headers, driver="flow", builders=["dev"], level="reviewed")
    await _hold("dev")
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            await _fire()
        finally:
            spawns.release_all()
            await _await_background_run()
    assert spawns.cwds == []
    assert await _dev_entries() == []


async def test_with_the_switch_off_one_firing_starts_one_task_for_the_one_builder(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """FR-2's control: off, the builder takes one task a firing, as before."""
    await _one_builder_build(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _build(app, auth_headers, driver="flow", builders=["dev"], level="reviewed")
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            await _fire()
            await spawns.wait_for(1)
            assert len(await _dev_runs()) == 1
            assert len(await _dev_entries()) == 1
        finally:
            spawns.release_all()
            await _await_background_run()


async def test_with_the_switch_on_a_leads_two_hand_outs_to_one_profile_run_at_once(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """ac-flow-two-offers, third clause: the lead hands both tasks to dev, and both run."""
    await _one_builder_build(
        app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
    )
    await _set_project(profiles_run_in_parallel=True)
    await _build(app, auth_headers, driver="lead", lead="lead", builders=["dev"], level="reviewed")
    tasks = await _tasks()
    lead = await _run_headers("run-lead-parallel", "lead")
    spawns = _Spawns()
    first_patch, second_patch = _patched(spawns)
    with first_patch, second_patch:
        try:
            for task in tasks.values():
                handed = await app.post(
                    HAND_OUT.format(task.id), json={"agent": "dev", "review": False}, headers=lead
                )
                assert handed.status_code == 200, handed.text
            await spawns.wait_for(2)
            running = await _dev_runs()
            assert sorted(run.task_id for run in running) == sorted(
                task.id for task in tasks.values()
            )
        finally:
            spawns.release_all()
            await _await_background_run()
