"""F1126: a landing requeued or carried to main by another merge reaches `landed`.

Seen on the operator's Hub 2026-11-02/03: SHR-2/3/4/6's landings were held while master's UI lint
was red ("they fail on main too"). Each dependent task brought the held work into its own checkout
and landed it, so all of it reached master, but the four still read waiting to land and their spec
read Building. Three defects then:

- the operator's Land batch, refused because main had moved, requeued the landings and nothing
  looked at the queue again until a restart (F1126a);
- a batch held over a failure main shares stayed held after main went green (F1126b);
- work that reached main inside another task's merge was never recorded as landed (F1126c).

The known-failing list retired the hold (`failures-already-known-are-on-a-list-not-re-argued`,
FR-9): no batch is held for the operator, so F1126a/b's successor is that a batch held before the
list is queued again at startup and lands. F1126c stands as it was.

Real repositories, the real pytest check run by the Hub, the real routes.
"""

from __future__ import annotations

import pytest

from hub import landing_queue
from hub.db.engine import async_session_factory
from hub.db.models import LandingBatch, TaskLanding
from hub.worktrees import task_branch_name

from .test_a_red_main_does_not_hold_the_night import (
    TASK,
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


async def _settled() -> None:
    """Whatever the Hub started in the background has finished; nothing is asked to look."""
    for _ in range(50):
        await landing_queue._wait_for_jobs("proj-test")
        timers = [t for t in landing_queue._timers.values() if not t.done()]
        if not timers:
            return
        for timer in timers:
            await timer


async def _queued_unlooked(app, monkeypatch, tmp_path, task_id=TASK) -> str:
    """*task_id* approved on a green main, its landing queued with nothing yet looking at the
    queue (the kick suppressed): returns its work."""
    work = await _task(tmp_path, task_id, {"feature.py": "x = 1\n"})
    await _checked(task_id)
    kick = landing_queue.kick
    monkeypatch.setattr(landing_queue, "kick", lambda project_id: None)
    approved = await _reviewer_approves(app, task_id)
    assert approved.status_code == 200, approved.text
    monkeypatch.setattr(landing_queue, "kick", kick)
    assert (await _landing(app, task_id))["state"] == "queued"
    return work


async def test_a_batch_held_before_the_list_is_queued_again_at_startup(app, monkeypatch, tmp_path):
    """F1126a/b's successor (`failures-already-known-are-on-a-list-not-re-argued`, FR-9): no batch
    is held for the operator any longer, and one a Hub before the list held is ended at startup
    and its landing queued again, so it is decided against the list and lands on its own."""
    _repo(tmp_path, {"ledger.py": "A = 2\nB = 2\n"})
    await _loop()
    await _configure()
    work = await _queued_unlooked(app, monkeypatch, tmp_path)
    async with async_session_factory() as session:
        row = await landing_queue.latest_landing(session, TASK)
        session.add(
            LandingBatch(
                id="lbat-held-before",
                project_id="proj-test",
                base_sha=git(tmp_path, "rev-parse", "main").stdout.strip(),
                state="held",
                task_ids=[TASK],
                prefixes=[],
                results=[],
                narrowing=[],
                error="the batch's checks fail, and they fail on main too",
            )
        )
        row.state, row.batch_id, row.reason = landing_queue.HELD, "lbat-held-before", "held"
        await session.commit()

    counts = await landing_queue.reconcile_at_startup()
    await _settled()

    assert counts["requeued"] >= 1, counts
    landing = await _landing(app, TASK)
    assert landing["state"] == "landed", landing
    assert work in commits_on(tmp_path, "main")
    async with async_session_factory() as session:
        assert (await session.get(LandingBatch, "lbat-held-before")).state == "superseded"


async def test_work_carried_to_main_is_recorded_landed(app, monkeypatch, tmp_path):
    """F1126c. A's landing is queued when its work reaches main inside another merge (here the
    operator's own, by hand). A must then read landed, naming the commit that carried it -- not
    waiting to land, and not checked or merged a second time."""
    _repo(tmp_path, {"ledger.py": "A = 2\nB = 2\n"})
    await _loop()
    await _configure()
    work_a = await _queued_unlooked(app, monkeypatch, tmp_path)
    git(tmp_path, "checkout", "-q", "main")
    git(tmp_path, "merge", "-q", "--no-ff", "-m", "carried by hand", task_branch_name(TASK))
    assert work_a in commits_on(tmp_path, "main")

    landing_queue.kick("proj-test")
    await _settled()

    landing = await _landing(app, TASK)
    assert landing["state"] == "landed", landing["reason"]
    async with async_session_factory() as session:
        row = await landing_queue.latest_landing(session, TASK)
        carrier = row.landed_sha
    assert isinstance(row, TaskLanding) and carrier
    contains = git(tmp_path, "merge-base", "--is-ancestor", work_a, carrier)
    assert contains.returncode == 0, "the landing names a main commit that holds A's work"
