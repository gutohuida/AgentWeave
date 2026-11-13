# ruff: noqa: F811 -- `author_headers` is a fixture imported to be requested by name
"""Work is done when it has landed on main, not when it is approved
(`work-is-done-when-it-has-landed-on-master-not-when-it-is-approved`, task `core`).

Approval stays the reviewer's verdict; a task is done once its landing has put its work on main
(merged as a pull request, for a build landing as one; at approval, for one landing nowhere). A
build finishes, its progress counts and its flow stops by that rule.

The acceptance drive (`ac-drive`) is a disposable Hub (this suite's own database and app) over a
real git repository whose single check fails on the second task's work: before this change the
build read finished at the second approval and stayed so after its landing sent that task back.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, update

from hub import builds, landing_queue, project_checks, task_integration
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Build, Loop, Project, Task, TaskLanding, TaskTransition
from hub.scheduler import JobScheduler
from hub.task_transition_service import apply_transition
from hub.task_transitions import STATUSES, TERMINAL_STATUSES, operator

from .test_a_build_has_a_driver_a_level_and_its_people import (
    BASE,
    P,
    _approved,
    _build,
    _document,
    _roster_rows,
    _rows,
    _tasks_by_key,
    author_headers,  # noqa: F401 -- a fixture
)
from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

PY = f'"{sys.executable}"'

SCHEDULING = patch(
    "hub.turn_scheduler.schedule_agent",
    AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
)


#: The work each task's approval freezes, by task id: what its accepted evidence would name. A task
#: not here freezes a commit no batch is ever drained for, so its landing stays queued.
FROZEN: dict = {}


@pytest.fixture(autouse=True)
def _approval_freezes_work(monkeypatch):
    """Approvals wait in the queue, in a batch the gather window holds, until a test drains it or
    lands one itself; what approval freezes is `FROZEN`'s (each test's own work), so the approval
    gate is not asked for the evidence a real run would have recorded."""
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    real = landing_queue.stage

    def stage(session, task, **kwargs):
        if not kwargs.get("targets"):
            sha, branch = FROZEN.get(task.id, ("a" * 40, "work/elsewhere"))
            kwargs["targets"] = [
                task_integration.Target(
                    commit_sha=sha,
                    branch=branch,
                    evidence_id=None,
                    requirement_id=None,
                    task_id=task.id,
                )
            ]
        return real(session, task, **kwargs)

    monkeypatch.setattr(landing_queue, "stage", stage)
    FROZEN.clear()
    yield
    FROZEN.clear()
    landing_queue.cancel_timers()


async def _built(app, auth_headers, author_headers, **settings) -> dict:
    """A Fast flow build of the two-task document, its tasks by key."""
    await _roster_rows("dev", "qa")
    await _approved(app, auth_headers, author_headers, _document())
    chosen = {"driver": "flow", "level": "fast", "builders": ["dev"], **settings}
    with SCHEDULING:
        built = await _build(app, auth_headers, **chosen)
    assert built.status_code == 200, built.text
    # A project with a check lands in batches, after the gather window: an approval stays queued.
    async with async_session_factory() as db:
        (await db.get(Project, P)).checks = [
            {"name": "hub-tests", "command": f"{PY} -c pass", "timeout_seconds": 60}
        ]
        await db.commit()
    return await _tasks_by_key()


async def _approve(task_id: str) -> None:
    async with async_session_factory() as db:
        row = await db.get(Task, task_id)
        for status in ("in_progress", "completed", "approved"):
            await apply_transition(db, row, status, operator())
        await db.commit()


async def _queued_without_moving(task_id: str) -> None:
    """Approved, its landing queued and held there: nothing drains it until the test lands it."""
    await _approve(task_id)


async def _land(task_id: str) -> None:
    """The task's latest landing lands, as the queue's own end does: the row, then its announce."""
    async with async_session_factory() as db:
        landing = await landing_queue.latest_landing(db, task_id)
        landing.state, landing.landed_sha = landing_queue.LANDED, "f" * 40
        await db.commit()
        await landing_queue._announce(db, [landing.id])


async def _done(task_id: str) -> bool:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
        if task.status != "approved":
            return False
        return task_id not in await landing_queue.unlanded(db, Task.id == task_id)


async def _build_row() -> Build:
    (build,) = await _rows(Build)
    return build


async def _listed(app, auth_headers) -> dict:
    read = await app.get(f"{BASE}/builds", headers=auth_headers)
    assert read.status_code == 200, read.text
    (row,) = read.json()["builds"]
    return row


async def _fire() -> None:
    (loop,) = await _rows(Loop)
    with SCHEDULING:
        async with async_session_factory() as db:
            job = await db.get(AIJob, loop.job_id)
            await JobScheduler()._do_fire_job(job, "scheduled", db)


# --- ac-drive ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_drive_a_send_back_by_landing_leaves_the_build_running(
    app, auth_headers, author_headers, tmp_path, tmp_path_factory
):
    """Two tasks of a flow build approved; the second's work fails the project's check on main.
    The first lands and is done, the second is sent back, the build still runs, its flow is still
    enabled, and the Running tab's read lists the second as sent back with the landing's reason."""
    tasks = await _built(app, auth_headers, author_headers)
    make_repo(tmp_path)
    await set_main_branch("main")
    outside = tmp_path_factory.mktemp("check")
    script = outside / "no_bad_file.py"
    script.write_text(
        "import os, sys\n"
        "if os.path.exists('bad.txt'):\n"
        "    print('FAILED tests/test_bad.py::test_no_bad_file')\n"
        "    sys.exit(1)\n",
        encoding="utf-8",
    )
    async with async_session_factory() as db:
        (await db.get(Project, P)).checks = [
            {"name": "hub-tests", "command": f'{PY} "{script}"', "timeout_seconds": 120}
        ]
        await db.commit()
    first, second = tasks["t1"], tasks["t2"]
    # Each task's work on a branch of its own; approval freezes its tip, as accepted evidence
    # naming it would in a real run.
    for task, (filename, content) in (
        (first, ("good.txt", "good\n")),
        (second, ("bad.txt", "x\n")),
    ):
        git(tmp_path, "checkout", "-q", "main")
        branch = f"work/{task.spec_task_key}"
        FROZEN[task.id] = (commit_on_branch(tmp_path, branch, filename, content), branch)
    git(tmp_path, "checkout", "-q", "main")
    for task in (first, second):
        await _approve(task.id)
    # Approved and still queued: neither is done, and the build is not finished.
    assert (await _build_row()).state == "running"

    await landing_queue.drain(P)
    await project_checks.drain()

    async with async_session_factory() as db:
        first_landing = await landing_queue.latest_landing(db, first.id)
        second_landing = await landing_queue.latest_landing(db, second.id)
        sent_back = await db.get(Task, second.id)
    assert first_landing.state == "landed", first_landing.reason
    assert await _done(first.id)
    assert second_landing.state == "sent_back"
    assert sent_back.status == "revision_needed"
    build = await _build_row()
    assert build.state == "running"
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob, AIJob.id == loop.job_id)
    assert (job.enabled, loop.ending_state) == (True, None)

    row = await _listed(app, auth_headers)
    assert row["state"] == "running"
    assert (row["tasks_done"], row["tasks_total"]) == (1, 2)
    (shown,) = row["landings"]
    assert (shown["task_id"], shown["landing_state"]) == (second.id, "sent_back")
    assert shown["reason"] and shown["reason"] == second_landing.reason


# --- ac-done, ac-no-step -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_done_an_approved_task_is_done_once_its_landing_lands(
    app, auth_headers, author_headers
):
    tasks = await _built(app, auth_headers, author_headers)
    task = tasks["t1"]
    await _queued_without_moving(task.id)

    async with async_session_factory() as db:
        landing = await landing_queue.latest_landing(db, task.id)
    assert landing.state == "queued"
    assert not await _done(task.id)

    await _land(task.id)
    assert await _done(task.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state", ["queued", "checking", "landing", "held", "pushed", "sent_back", "not_landed"]
)
async def test_ac_done_no_other_landing_state_is_done(app, auth_headers, author_headers, state):
    tasks = await _built(app, auth_headers, author_headers)
    task = tasks["t1"]
    await _queued_without_moving(task.id)
    async with async_session_factory() as db:
        await db.execute(
            update(TaskLanding)
            .where(TaskLanding.task_id == task.id)
            .values(state=state, reason="the merge failed: a conflict")
        )
        await db.commit()
    assert not await _done(task.id)


@pytest.mark.asyncio
async def test_ac_no_step_landing_is_the_last_step(app, auth_headers, author_headers):
    """The landing landing is all it takes: no new transition is recorded, nobody is asked, and the
    set of task statuses is the one there was."""
    assert {"approved", "rejected"} == TERMINAL_STATUSES
    assert set(STATUSES) == {
        "pending",
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "revision_needed",
        "blocked",
        "approved",
        "rejected",
    }
    tasks = await _built(app, auth_headers, author_headers)
    for task in tasks.values():
        await _queued_without_moving(task.id)
    transitions = len(await _rows(TaskTransition))
    assert (await _build_row()).state == "running"

    for task in tasks.values():
        await _land(task.id)

    assert all([await _done(task.id) for task in tasks.values()])
    assert (await _build_row()).state == "finished"
    assert len(await _rows(TaskTransition)) == transitions
    async with async_session_factory() as db:
        statuses = set((await db.execute(select(Task.status))).scalars())
    assert statuses == {"approved"}


# --- ac-progress ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_progress_counts_landed_as_done_and_approved_as_landing(
    app, auth_headers, author_headers
):
    tasks = await _built(
        app,
        auth_headers,
        author_headers,
    )
    # A third task joins the build: one landed, one approved and queued, one in progress.
    async with async_session_factory() as db:
        (build,) = (await db.execute(select(Build))).scalars().all()
        db.add(
            Task(
                id="task-third",
                project_id=P,
                title="A third",
                status="in_progress",
                build_id=build.id,
                loop_id=build.loop_id,
                spec_document_id=build.document_id,
            )
        )
        await db.commit()
    await _queued_without_moving(tasks["t1"].id)
    await _land(tasks["t1"].id)
    await _queued_without_moving(tasks["t2"].id)

    row = await _listed(app, auth_headers)
    assert (row["tasks_done"], row["tasks_landing"], row["tasks_total"]) == (1, 1, 3)
    (shown,) = row["landings"]
    assert (shown["task_id"], shown["landing_state"]) == (tasks["t2"].id, "queued")


# --- ac-flow -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_flow_does_not_stop_until_its_last_task_lands(app, auth_headers, author_headers):
    tasks = await _built(app, auth_headers, author_headers)
    await _queued_without_moving(tasks["t1"].id)
    await _land(tasks["t1"].id)
    await _queued_without_moving(tasks["t2"].id)
    # Not landed: its merge failed. Approved, every task, and one is not done.
    async with async_session_factory() as db:
        await db.execute(
            update(TaskLanding)
            .where(TaskLanding.task_id == tasks["t2"].id)
            .values(state="not_landed", reason="the merge failed: a conflict")
        )
        await db.commit()

    await _fire()
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob, AIJob.id == loop.job_id)
    assert (loop.ending_state, job.enabled) == (None, True)
    assert (await _build_row()).state == "running"

    # Its retry lands: the landing's end finishes the build, and the next firing finds it drained.
    async with async_session_factory() as db:
        task = await db.get(Task, tasks["t2"].id)
        db.add(
            TaskLanding(
                id="land-retry",
                project_id=P,
                task_id=task.id,
                state=landing_queue.LANDED,
                kind="retry",
                order_key=10**12,
            )
        )
        await db.commit()
        await landing_queue._announce(db, ["land-retry"])
    assert (await _build_row()).state == "finished"
    await _fire()
    (loop,) = await _rows(Loop)
    (job,) = await _rows(AIJob, AIJob.id == loop.job_id)
    assert (loop.ending_state, job.enabled) == ("completed", False)


# --- ac-old --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac_old_a_build_finished_with_unlanded_work_runs_again(
    app, auth_headers, author_headers
):
    """The state the old rule left: every task approved, the build finished, one landing
    `not_landed`. The Hub's next evaluation (its start) shows the build running again."""
    tasks = await _built(app, auth_headers, author_headers)
    for task in tasks.values():
        await _queued_without_moving(task.id)
    await _land(tasks["t1"].id)
    async with async_session_factory() as db:
        await db.execute(
            update(TaskLanding)
            .where(TaskLanding.task_id == tasks["t2"].id)
            .values(state="not_landed", reason="the merge failed: a conflict")
        )
        await db.execute(update(Build).values(state="finished"))
        await db.commit()
    assert (await _listed(app, auth_headers))["state"] == "finished"

    assert await builds.reopen_unfinished() == 1

    row = await _listed(app, auth_headers)
    assert row["state"] == "running"
    (shown,) = row["landings"]
    assert (shown["task_id"], shown["landing_state"]) == (tasks["t2"].id, "not_landed")
    # A build whose work all landed is left finished.
    await _land(tasks["t2"].id)
    assert (await _build_row()).state == "finished"
    assert await builds.reopen_unfinished() == 0


@pytest.mark.asyncio
async def test_ac_old_the_builds_firing_reopens_it_too(app, auth_headers, author_headers):
    tasks = await _built(app, auth_headers, author_headers)
    for task in tasks.values():
        await _queued_without_moving(task.id)
    async with async_session_factory() as db:
        await db.execute(update(Build).values(state="finished"))
        await db.commit()

    await _fire()

    assert (await _build_row()).state == "running"


# --- ac-pr ---------------------------------------------------------------------------------------


async def _lands(landing: str) -> None:
    async with async_session_factory() as db:
        await db.execute(update(Build).values(landing=landing, pr_number=7))
        await db.commit()


async def db_build() -> Build:
    async with async_session_factory() as db:
        (build,) = (await db.execute(select(Build))).scalars().all()
        return build


@pytest.mark.asyncio
async def test_ac_pr_a_pull_request_task_is_done_once_the_pr_merges(
    app, auth_headers, author_headers
):
    from hub import pull_requests

    tasks = await _built(app, auth_headers, author_headers)
    await _lands(builds.LANDING_PULL_REQUEST)
    for task in tasks.values():
        await _queued_without_moving(task.id)
    # The landing queue pushed both to the build's PR (`pull_requests.land`), stood in for here:
    # what the queue's own attempt wrote (this project has no GitHub remote) is written over.
    await landing_queue._wait_for_jobs(P)
    async with async_session_factory() as db:
        await db.execute(
            update(TaskLanding).values(
                state=pull_requests.PUSHED, targets=[{"commit_sha": "a" * 40, "branch": "b"}]
            )
        )
        await db.commit()
    assert not [await _done(task.id) for task in tasks.values() if await _done(task.id)]
    assert (await db_build()).state == builds.RUNNING

    # GitHub answers merged, stubbed at the pull_requests seam: what the Hub's ask hands `_apply`.
    await pull_requests._apply(
        (await db_build()).id, {"state": pull_requests.MERGED, "merge_commit": "c" * 40}
    )

    assert all([await _done(task.id) for task in tasks.values()])
    assert (await db_build()).state == builds.FINISHED


@pytest.mark.asyncio
async def test_ac_pr_a_task_of_a_build_landing_nowhere_is_done_at_approval(
    app, auth_headers, author_headers
):
    tasks = await _built(app, auth_headers, author_headers)
    await _lands(builds.LANDING_NOWHERE)
    first, second = tasks.values()
    await _queued_without_moving(first.id)
    async with async_session_factory() as db:
        landing = await landing_queue.latest_landing(db, first.id)
    assert landing.state == "queued", "not landed: there is nowhere for it to land"
    assert await _done(first.id)

    await _queued_without_moving(second.id)
    assert (await db_build()).state == builds.FINISHED
