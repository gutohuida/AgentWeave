"""F1126: a landing held, requeued or carried to main by another task's merge reaches `landed`.

Seen on the operator's Hub 2026-11-02/03: SHR-2/3/4/6's landings were held while master's UI lint
was red ("they fail on main too"). Each dependent task brought the held work into its own checkout
and landed it, so all of it reached master, but the four still read waiting to land and their spec
read Building. Three defects, one test each:

- the operator's Land batch, refused because main had moved, requeued the landings and nothing
  looked at the queue again until a restart (F1126a);
- a batch held over a failure main shares stayed held after main went green (F1126b);
- work that reached main inside another task's merge was never recorded as landed (F1126c).

Real repositories, the real pytest check run by the Hub, the real routes.
"""

from __future__ import annotations

import pytest

from hub import landing_queue, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import TaskLanding
from hub.worktrees import task_branch_name

from .test_a_red_main_does_not_hold_the_night import (
    TASK,
    TASK2,
    TASKS,
    _checked,
    _configure,
    _landing,
    _loop,
    _repo,
    _reviewer_approves,
    _task,
)
from .test_task_integration import commits_on, git

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _no_gather_window(monkeypatch):
    """The queue looks at once: what is under test is whether anything makes it look at all."""
    monkeypatch.setattr(landing_queue, "BATCH_GATHER_SECONDS", 0.0)
    yield
    landing_queue.cancel_timers()


async def _held(app, tmp_path, task_id=TASK) -> str:
    """*task_id* approved over a red main with the Hub's override off: its landing is held."""
    _repo(tmp_path)
    await _loop()
    work = await _task(tmp_path, task_id, {"feature.py": "x = 1\n"})
    await _configure(auto_override=False)
    await _checked(task_id)
    approved = await _reviewer_approves(app, task_id)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    landing = await _landing(app, task_id)
    assert landing["state"] == "held" and "fail on main too" in landing["reason"], landing
    return work


def _main_goes_green(repo) -> None:
    """Somebody fixes main outside the queue (the operator's own commit)."""
    git(repo, "checkout", "-q", "main")
    (repo / "ledger.py").write_text("A = 2\nB = 2\n", encoding="utf-8")
    git(repo, "add", "ledger.py")
    git(repo, "commit", "-q", "-m", "main is green again")


async def _settled() -> None:
    """Whatever the Hub started in the background has finished; nothing is asked to look."""
    for _ in range(50):
        await landing_queue._wait_for_jobs("proj-test")
        timers = [t for t in landing_queue._timers.values() if not t.done()]
        if not timers:
            return
        for timer in timers:
            await timer


async def test_a_requeued_landing_lands_without_another_kick(app, auth_headers, tmp_path):
    """F1126a. Main moves under a held batch, the operator presses Land batch: refused (main
    moved) and requeued. On master it then sits `queued` until an unrelated approval or a
    restart; it must be checked on the new tip and land on its own."""
    work = await _held(app, tmp_path)
    _main_goes_green(tmp_path)

    refused = await app.post(
        f"{TASKS}/{TASK}/landing/land", json={"reason": "main is fixed"}, headers=auth_headers
    )
    assert refused.status_code == 409, refused.text
    await _settled()

    landing = await _landing(app, TASK)
    assert landing["state"] == "landed", landing
    assert work in commits_on(tmp_path, "main")


async def test_a_batch_held_over_a_shared_failure_lands_once_main_is_green(app, tmp_path):
    """F1126b. A batch held because main failed the same check is checked again once main moves:
    the Hub's main watch notices the move, and the landing lands with no operator action."""
    work = await _held(app, tmp_path)
    _main_goes_green(tmp_path)

    await project_checks.watch_main_once()
    await _settled()

    landing = await _landing(app, TASK)
    assert landing["state"] == "landed", landing
    assert work in commits_on(tmp_path, "main")


async def test_a_held_batch_whose_main_did_not_move_stays_held(app, tmp_path):
    """F1126b's bound: the queue looking again does not re-run a held batch on the same main."""
    await _held(app, tmp_path)
    async with async_session_factory() as session:
        before = (await landing_queue.latest_landing(session, TASK)).batch_id

    await project_checks.watch_main_once()
    landing_queue.kick("proj-test")
    await _settled()

    landing = await _landing(app, TASK)
    assert landing["state"] == "held", landing
    async with async_session_factory() as session:
        assert (await landing_queue.latest_landing(session, TASK)).batch_id == before


async def test_work_carried_to_main_by_a_dependent_is_recorded_landed(app, auth_headers, tmp_path):
    """F1126c. A's landing is held; B is built on A's work (the Hub's "bring in prerequisite
    work") and the operator lands B's batch, which carries A's commit onto main. A must then read
    landed, naming the commit that carried it -- not waiting to land with main still red."""
    work_a = await _held(app, tmp_path)
    branch_b = task_branch_name(TASK2)
    git(tmp_path, "checkout", "-q", "-b", branch_b, task_branch_name(TASK))
    (tmp_path / "other.py").write_text("y = 2\n", encoding="utf-8")
    git(tmp_path, "add", "other.py")
    git(tmp_path, "commit", "-q", "-m", "work of B, built on A's")
    git(tmp_path, "checkout", "-q", "main")
    from hub.db.models import Task

    async with async_session_factory() as session:
        session.add(
            Task(
                id=TASK2,
                loop_id="loop-red-main",
                project_id="proj-test",
                title="Work B",
                description="",
                status="completed",
                priority="medium",
                assignee="builder",
            )
        )
        await session.commit()
    await _checked(TASK2)
    approved = await _reviewer_approves(app, TASK2)
    assert approved.status_code == 200, approved.text
    await landing_queue.drain()
    assert (await _landing(app, TASK2))["state"] == "held"

    landed = await app.post(
        f"{TASKS}/{TASK2}/landing/land", json={"reason": "main is red"}, headers=auth_headers
    )
    assert landed.status_code == 200, landed.text
    assert work_a in commits_on(tmp_path, "main")
    await project_checks.watch_main_once()
    await _settled()

    landing = await _landing(app, TASK)
    assert landing["state"] == "landed", landing
    async with async_session_factory() as session:
        row = await landing_queue.latest_landing(session, TASK)
        carrier = row.landed_sha
    assert isinstance(row, TaskLanding) and carrier
    contains = git(tmp_path, "merge-base", "--is-ancestor", work_a, carrier)
    assert contains.returncode == 0, "the landing names a main commit that holds A's work"
    tasks = await app.get(TASKS, headers=auth_headers)
    by_id = {t["id"]: t for t in tasks.json()["tasks"]}
    assert by_id[TASK]["waiting_to_land"] is False
