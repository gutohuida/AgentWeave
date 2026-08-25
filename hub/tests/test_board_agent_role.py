"""Findings F49 and F48 — the board's own derivations, which had no Python tests at all.

Both were found live on 2026-08-25, immediately after F45's fix made in-flight work the ordinary
state of a flow rather than a rare one.

**F49.** `_batch_loop_summaries` distinguishes an agent that is *mid-turn* on a task from the one
the next firing *would* give it to, and puts the answer on `agent_role` — `working` against `next`.
The distinction is real and only that merge knows it, which is why F26 fixed it at the source. But
the source built its lookup as `set(decision.in_flight)`, and `in_flight` is a sequence of
`(task_id, agent)` **pairs** — so the set held tuples, the membership test asked it with a bare
`task.id`, and it never matched. `agent_role` could not be `working` in production from the day it
shipped.

It shipped green because the only tests were five vitest cases against the *renderer*, each handed
an `agent_role` value by the fixture. Nothing exercised the derivation. That is finding F41's
lesson for the third time in this change, and this module is the missing half.

**F48.** A loop firing that declines because every candidate is already being worked records
nothing at all — deliberately, since the agents' own running rows carry the fact (F23). The manual
`POST /jobs/{id}/run` route read the *latest* `JobRun` to explain a `False` return, found some
earlier firing rather than a fresh one, and answered `500 Failed to fire job` for a loop in perfect
health. The operator pressing Run while a review was out was told their flow had broken.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Loop, Task
from hub.scheduler import JobScheduler, _enter_selected_task
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

AUTHOR = "board-author"
REVIEWER = "board-reviewer"


async def _flow(db, *, suffix):
    job = AIJob(
        id=f"job-board-{suffix}",
        project_id="proj-test",
        name=f"Board {suffix}",
        agent=AUTHOR,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-board-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"board {suffix}",
    )
    db.add(loop)
    await db.commit()
    task = Task(
        id=f"task-board-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status="pending",
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    return job, loop, task


async def _completed_by(db, task, agent):
    actor = run_actor(run_id=f"run-{agent}-{task.id}", agent=agent)
    for status in ("assigned", "in_progress", "completed"):
        await apply_transition(db, task, status, actor)
    await db.commit()


@pytest.fixture
def live_scheduler(monkeypatch):
    """A `JobScheduler` the manual-run route can find.

    `run_job` refuses with 503 when `get_scheduler()` is None, which every existing test of that
    route hits before reaching the firing at all — which is precisely why F48 survived: no test
    had ever driven the route far enough to see what it says about a firing that declined.
    `_fire_job_internal` needs no `start()`; the other scheduler tests construct one the same way.
    """
    import hub.scheduler as scheduler_module

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


def _card(payload, job_id):
    jobs = payload if isinstance(payload, list) else payload.get("jobs", [])
    return next(j for j in jobs if j["id"] == job_id)


# ---------------------------------------------------------------------------
# F49 — `working` must be reachable
# ---------------------------------------------------------------------------


async def test_a_task_being_reviewed_reads_as_working_not_next(app, auth_headers, bind_runner):
    """The assertion that distinguishes this fix from doing nothing.

    A task a reviewer already holds is in-flight, so the board must say `working`. Before the fix
    it said `next` — "this is who *would* take it" — about work already taken.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="working")
        await _completed_by(db, task, AUTHOR)
        await _enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    res = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    assert res.status_code == 200
    current = _card(res.json(), job.id)["loop"]["current_tasks"]

    assert [(t["id"], t.get("agent"), t.get("agent_role")) for t in current] == [
        (task.id, REVIEWER, "working")
    ]


async def test_a_task_awaiting_review_still_reads_as_next(app, auth_headers, bind_runner):
    """The other side of the same distinction, so the fix cannot be "call everything working".

    Nobody has this task yet — the next firing would give it to the reviewer — and that is exactly
    what `next` means. F26 exists because these two rendered identically.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="next")
        await _completed_by(db, task, AUTHOR)

    res = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    current = _card(res.json(), job.id)["loop"]["current_tasks"]

    assert [(t["id"], t.get("agent"), t.get("agent_role")) for t in current] == [
        (task.id, REVIEWER, "next")
    ]


# ---------------------------------------------------------------------------
# F48 — pressing Run on a loop whose work is all in flight
# ---------------------------------------------------------------------------


async def test_running_a_loop_whose_work_is_all_in_flight_is_not_a_failure(
    app, auth_headers, bind_runner, live_scheduler
):
    """409 and a sentence, not 500 and "Failed to fire job".

    Reachable before F45 and ordinary after it: every dispatched review parks a task in flight, so
    an operator pressing Run while a review is out hit this on the common path.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="inflight")
        await _completed_by(db, task, AUTHOR)
        await _enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    res = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)

    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert "already being worked" in detail
    assert "nothing is wrong" in detail


async def test_no_job_run_row_is_written_for_a_declined_firing(
    app, auth_headers, bind_runner, live_scheduler
):
    """F23's rule, which is *why* F48 existed: the decline records nothing, so there was no fresh
    row for the route to read. Pinned here so a future fix that starts writing one has to come
    back and reconsider the 409 above rather than silently changing what it means."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="norow")
        await _completed_by(db, task, AUTHOR)
        await _enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    async with async_session_factory() as db:
        before = len((await db.execute(select(AIJob).where(AIJob.id == job.id))).scalars().all())
    assert before == 1

    await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)

    async with async_session_factory() as db:
        fresh = (await db.execute(select(AIJob).where(AIJob.id == job.id))).scalar_one()
        assert fresh.run_count == 0, "a declined firing must not count as a run"
