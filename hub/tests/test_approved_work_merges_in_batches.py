"""Approved work merges in batches (`approved-work-merges-in-batches`, slice E).

The acceptance drive (`four-good-tasks-one-run`): four tasks under review in a project whose single
check counts how often it runs, on which tree. Before this change the first approval answered 409
"checks are still running" and scheduled a per-task run; every landing moved main and re-ran the
rest. Now each approval is recorded at once, the four land together, and the check runs once, on
exactly the tree main ends at.

Real git and real check processes throughout: "the queue says it landed" is not evidence.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from sqlalchemy import select

from hub import project_checks, task_integration
from hub.db import models
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Project, Task, TaskCheckRun, TaskIntegration
from hub.worktrees import task_branch_name

from .test_task_integration import commit_on_branch, git, make_repo, set_main_branch

TASKS = "/api/v1/projects/proj-test/tasks"


def queue():
    """The landing queue, imported when used: the red run on the unchanged code has none, and
    must fail on what approval answers rather than at collection."""
    return importlib.import_module("hub.landing_queue")


PY = f'"{sys.executable}"'


@pytest.fixture(autouse=True)
def _a_long_gather_window(monkeypatch):
    """The four approvals land within the window; the test drains the queue itself."""
    try:
        landing_queue = queue()
    except ImportError:
        yield
        return
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 3600.0)
    yield
    landing_queue.cancel_timers()


def counting_check(tmp_path_factory, name="count"):
    """A check that appends the tree it ran on to a file outside the repository, and passes."""
    outside = tmp_path_factory.mktemp("counter")
    counter = outside / "runs.txt"
    script = outside / "count.py"
    script.write_text(
        "import subprocess\n"
        "tree = subprocess.run(['git', 'rev-parse', 'HEAD^{tree}'], capture_output=True,"
        " text=True).stdout.strip()\n"
        f"with open(r'{counter}', 'a', encoding='utf-8') as out:\n"
        "    out.write(tree + '\\n')\n",
        encoding="utf-8",
    )
    return {"name": name, "command": f'{PY} "{script}"', "timeout_seconds": 120}, counter


def runs_in(counter):
    return counter.read_text(encoding="utf-8").split() if counter.exists() else []


async def set_checks(checks):
    async with async_session_factory() as session:
        (await session.get(Project, "proj-test")).checks = checks
        await session.commit()


async def tasks_under_review(tmp_path, count, *, status="under_review", files=None):
    """*count* tasks under review, each with one commit on its own branch touching its own file;
    approval merges each branch tip (a loop whose work needs no evidence)."""
    make_repo(tmp_path)
    await set_main_branch("main")
    async with async_session_factory() as session:
        session.add(
            AIJob(
                id="job-batch",
                project_id="proj-test",
                name="batch",
                agent="builder",
                message="work",
                cron="*/5 * * * *",
                session_mode="new",
                enabled=False,
            )
        )
        await session.flush()
        session.add(
            Loop(
                id="loop-batch",
                project_id="proj-test",
                job_id="job-batch",
                purpose="work",
                work_needs_evidence=False,
            )
        )
        await session.flush()
        ids = [f"task-ba7c40000{n:03d}" for n in range(1, count + 1)]
        for n, task_id in enumerate(ids, start=1):
            session.add(
                Task(
                    id=task_id,
                    loop_id="loop-batch",
                    project_id="proj-test",
                    title=f"Work {n}",
                    description="",
                    status=status,
                    assignee="builder",
                )
            )
        await session.commit()
    works = []
    for n, task_id in enumerate(ids, start=1):
        filename, content = (files or {}).get(n, (f"feature_{n}.py", f"x = {n}\n"))
        git(tmp_path, "checkout", "-q", "main")
        works.append(commit_on_branch(tmp_path, task_branch_name(task_id), filename, content))
    git(tmp_path, "checkout", "-q", "main")
    return ids, works


async def approve(app, auth_headers, task_id, **extra):
    return await app.patch(
        f"{TASKS}/{task_id}", json={"status": "approved", **extra}, headers=auth_headers
    )


async def merged_rows(task_id):
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(TaskIntegration).where(
                        TaskIntegration.task_id == task_id, TaskIntegration.outcome == "merged"
                    )
                )
            ).scalars()
        )


async def landings_of(task_id):
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(models.TaskLanding)
                    .where(models.TaskLanding.task_id == task_id)
                    .order_by(models.TaskLanding.created_at)
                )
            ).scalars()
        )


async def batches():
    async with async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(models.LandingBatch).order_by(models.LandingBatch.created_at)
                )
            ).scalars()
        )


def tip_tree(tmp_path):
    return git(tmp_path, "rev-parse", "main^{tree}").stdout.strip()


@pytest.mark.asyncio
async def test_four_good_tasks_land_after_one_check_run(
    app, auth_headers, tmp_path, tmp_path_factory
):
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 4)
    await set_checks([check])
    await project_checks.drain()
    before = len(runs_in(counter))

    for task_id in ids:
        approved = await approve(app, auth_headers, task_id)
        # Before this change the first approval answered 409 "checks are still running".
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

    await queue().drain()
    await project_checks.drain()

    after = runs_in(counter)[before:]
    assert len(after) == 1, f"the check ran {len(after)} times after the first approval: {after}"
    assert tip_tree(tmp_path) == after[0], "main's tree is the tree the batch was checked on"
    for task_id, work in zip(ids, works, strict=True):
        rows = await merged_rows(task_id)
        assert [row.commit_sha for row in rows] == [work], (task_id, rows)
        assert [landing.state for landing in await landings_of(task_id)] == ["landed"]
    [batch] = await batches()
    assert batch.state == "landed" and batch.task_ids == ids


@pytest.mark.asyncio
async def test_a_stale_or_missing_result_does_not_hold_approval(
    app, auth_headers, tmp_path, tmp_path_factory
):
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    # The first task has a pass on a main tip that has since moved; the second has no result.
    await project_checks.request_run("proj-test", ids[0], targets=[works[0]])
    await project_checks.drain()
    commit_on_branch(tmp_path, "main", "later.txt", "main moved\n", create=False)
    runs_before = len(runs_in(counter))

    for task_id in ids:
        approved = await approve(app, auth_headers, task_id)
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        [landing] = await landings_of(task_id)
        assert landing.state == "queued"
    await project_checks.drain()
    assert len(runs_in(counter)) == runs_before, "approving started no per-task check run"
    async with async_session_factory() as session:
        second = (
            await session.execute(select(TaskCheckRun).where(TaskCheckRun.task_id == ids[1]))
        ).all()
    assert second == []


@pytest.mark.asyncio
async def test_main_is_fast_forwarded_to_the_checked_commit(
    app, auth_headers, tmp_path, tmp_path_factory
):
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    base = git(tmp_path, "rev-parse", "main").stdout.strip()
    for task_id in ids:
        assert (await approve(app, auth_headers, task_id)).status_code == 200

    await queue().drain()

    [batch] = await batches()
    assert batch.state == "landed"
    assert batch.base_sha == base
    assert git(tmp_path, "rev-parse", "main").stdout.strip() == batch.merged_sha
    assert tip_tree(tmp_path) == runs_in(counter)[-1]
    # Main was fast-forwarded: its first-parent history is the batch's chain on the old tip.
    chain = git(tmp_path, "rev-list", "--first-parent", f"{base}..main").stdout.split()
    assert len(chain) == 2
    for task_id, work in zip(ids, works, strict=True):
        assert [row.commit_sha for row in await merged_rows(task_id)] == [work]
    assert git(tmp_path, "status", "--porcelain").stdout == "", "the checkout followed main"


@pytest.mark.asyncio
async def test_a_moved_main_rebuilds_the_batch(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    for task_id in ids:
        assert (await approve(app, auth_headers, task_id)).status_code == 200

    real = queue().run_batch_checks
    moved = {}

    async def checks_then_main_moves(*args, **kwargs):
        outcome = await real(*args, **kwargs)
        if not moved:
            # A commit added to main by hand after the batch was built and checked.
            moved["sha"] = commit_on_branch(tmp_path, "main", "by_hand.txt", "x\n", create=False)
        return outcome

    monkeypatch.setattr(queue(), "run_batch_checks", checks_then_main_moves)
    await queue().drain()

    first, second = await batches()
    assert first.state == "superseded", first.state
    assert second.state == "landed"
    assert second.base_sha == moved["sha"]
    head = git(tmp_path, "rev-parse", "main").stdout.strip()
    assert head == second.merged_sha
    assert moved["sha"] in git(tmp_path, "rev-list", "main").stdout.split()
    assert tip_tree(tmp_path) == runs_in(counter)[-1]
    assert first.merged_sha not in git(tmp_path, "rev-list", "main").stdout.split()
    for task_id in ids:
        assert len(await merged_rows(task_id)) == 1


@pytest.mark.asyncio
async def test_every_merge_goes_through_the_queue(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    """Approval, a retried integration and a mend resolution all land through one batch's checked
    commit; nothing merges into main outside the queue."""
    from hub.task_transition_service import land_resolution, retry_integration
    from hub.task_transitions import operator

    check, counter = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 3)
    await set_checks([check])
    outside = []
    real_integrate = task_integration.integrate

    def integrate_spy(*args, **kwargs):
        outside.append(args)
        return real_integrate(*args, **kwargs)

    monkeypatch.setattr(task_integration, "integrate", integrate_spy)

    # The second and third are approved over a dirty checkout: their landing is skipped.
    (tmp_path / "README.md").write_text("an operator's edit\n", encoding="utf-8")
    for task_id in ids[1:]:
        assert (await approve(app, auth_headers, task_id)).status_code == 200
    await queue().drain()
    for task_id in ids[1:]:
        [landing] = await landings_of(task_id)
        assert landing.state == "not_landed", landing.state
        assert landing.reason == task_integration.CHECKOUT_DIRTY
    git(tmp_path, "checkout", "--", "README.md")

    # One task queued, then a retried integration and a mend resolution queued behind it.
    assert (await approve(app, auth_headers, ids[0])).status_code == 200
    resolution_branch = "mend/" + ids[2]
    git(tmp_path, "checkout", "-q", "-b", resolution_branch, works[2])
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "resolve", "main")
    resolution = git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    git(tmp_path, "checkout", "-q", "main")
    async with async_session_factory() as session:
        await retry_integration(session, await session.get(Task, ids[1]), operator())
        await land_resolution(session, await session.get(Task, ids[2]), operator(), resolution)
        await session.commit()
    queued = [(await landings_of(task_id))[-1] for task_id in ids]
    assert [landing.state for landing in queued] == ["queued"] * 3
    assert queued[0].order_key < queued[1].order_key < queued[2].order_key

    await queue().drain()

    assert outside == [], "a merge into main was made outside the landing queue"
    landed = (await batches())[-1]
    assert landed.state == "landed" and landed.task_ids == ids
    assert git(tmp_path, "rev-parse", "main").stdout.strip() == landed.merged_sha
    assert tip_tree(tmp_path) == runs_in(counter)[-1]
    assert [row.commit_sha for row in await merged_rows(ids[2])] == [resolution]


@pytest.mark.asyncio
async def test_without_checks_the_approval_answers_with_its_merge(app, auth_headers, tmp_path):
    ids, works = await tasks_under_review(tmp_path, 1)

    approved = await approve(app, auth_headers, ids[0])

    assert approved.status_code == 200, approved.text
    assert approved.json()["latest_integration"]["outcome"] == "merged"
    assert works[0] in git(tmp_path, "rev-list", "main").stdout.split()
    [landing] = await landings_of(ids[0])
    assert landing.state == "landed" and landing.batch_id is None


@pytest.mark.asyncio
async def test_a_restart_mid_batch_loses_and_repeats_nothing(
    app, auth_headers, tmp_path, tmp_path_factory
):
    check, _ = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 4)
    await set_checks([check])
    for task_id in ids:
        assert (await approve(app, auth_headers, task_id)).status_code == 200
    base = git(tmp_path, "rev-parse", "main").stdout.strip()

    # Batch one (tasks 3, 4) had moved main to its checked commit when the Hub stopped, before its
    # records were written; batch two (tasks 1, 2) was still checking.
    root = tmp_path
    built = queue().build_chain(root, base, [(ids[2], [works[2]]), (ids[3], [works[3]])])
    assert built.conflict is None
    git(tmp_path, "merge", "-q", "--ff-only", built.prefixes[-1])
    async with async_session_factory() as session:
        landings = {
            landing.task_id: landing
            for landing in (await session.execute(select(models.TaskLanding))).scalars()
        }
        session.add(
            models.LandingBatch(
                id="lbat-landing01",
                project_id="proj-test",
                base_sha=base,
                state="landing",
                task_ids=ids[2:],
                prefixes=built.prefixes,
                merged_sha=built.prefixes[-1],
            )
        )
        session.add(
            models.LandingBatch(
                id="lbat-checking1",
                project_id="proj-test",
                base_sha=base,
                state="checking",
                task_ids=ids[:2],
                prefixes=[],
            )
        )
        for task_id in ids[2:]:
            landings[task_id].state, landings[task_id].batch_id = "landing", "lbat-landing01"
        for task_id in ids[:2]:
            landings[task_id].state, landings[task_id].batch_id = "checking", "lbat-checking1"
        await session.commit()

    await queue().reconcile_at_startup()

    async with async_session_factory() as session:
        checking = await session.get(models.LandingBatch, "lbat-checking1")
        landed = await session.get(models.LandingBatch, "lbat-landing01")
        assert checking.state == "interrupted"
        assert landed.state == "landed"
    for task_id in ids[:2]:
        [landing] = await landings_of(task_id)
        assert landing.state == "queued" and landing.batch_id is None
    first, second = [(await landings_of(task_id))[0] for task_id in ids[:2]]
    assert first.order_key < second.order_key, "queued again in their original order"
    for task_id, work in zip(ids[2:], works[2:], strict=True):
        assert [row.commit_sha for row in await merged_rows(task_id)] == [work]
        [landing] = await landings_of(task_id)
        assert landing.state == "landed"
    landed_tip = git(tmp_path, "rev-parse", "main").stdout.strip()
    assert landed_tip == built.prefixes[-1], "nothing was merged a second time"

    # The interrupted two land on the next drain, once.
    await queue().drain()
    for task_id, work in zip(ids, works, strict=True):
        assert [row.commit_sha for row in await merged_rows(task_id)] == [work]
    count = git(tmp_path, "rev-list", "--count", f"{base}..main", "--first-parent").stdout
    assert int(count) == 4


@pytest.mark.asyncio
async def test_every_landing_change_is_broadcast_and_the_checks_route_shows_it(
    app, auth_headers, tmp_path, tmp_path_factory
):
    """drawer-shows-landing, the Hub's half: the checks route carries the landing and its batch,
    and each state change is a `task_landing_changed` event the drawer refreshes on."""
    import json

    from hub.sse import sse_manager

    check, _ = counting_check(tmp_path_factory)
    ids, works = await tasks_under_review(tmp_path, 2)
    await set_checks([check])
    queue_ = sse_manager.subscribe("proj-test")
    try:
        for task_id in ids:
            assert (await approve(app, auth_headers, task_id)).status_code == 200
        read = await app.get(f"{TASKS}/{ids[1]}/checks", headers=auth_headers)
        assert read.json()["landing"]["state"] == "queued"
        assert read.json()["landing"]["position"] == 2
        await queue().drain()
        seen = []
        while not queue_.empty():
            event = queue_.get_nowait()
            if event.event == "task_landing_changed":
                seen.append(json.loads(event.data))
    finally:
        sse_manager.unsubscribe("proj-test", queue_)
    states = [(entry["task_id"], entry["state"]) for entry in seen]
    for task_id in ids:
        assert (task_id, "checking") in states and (task_id, "landed") in states, states
    read = await app.get(f"{TASKS}/{ids[1]}/checks", headers=auth_headers)
    landing = read.json()["landing"]
    assert landing["state"] == "landed"
    assert landing["landed_sha"] == git(tmp_path, "rev-parse", "main").stdout.strip()
    assert landing["batch"]["task_ids"] == ids and landing["batch"]["seconds"] >= 0


def test_the_hubs_lifespan_reconciles_the_landing_queue():
    import inspect

    from hub import main

    assert "landing_queue.reconcile_at_startup" in inspect.getsource(main.lifespan)
