"""Findings F49 and F48 — the board's own derivations, which had no Python tests at all.

Both were found live on 2026-08-25, immediately after F45's fix made in-flight work the ordinary
state of a flow rather than a rare one.

**F49.** `_batch_loop_summaries` distinguishes an agent that is *mid-turn* on a task from the one
the next firing *would* give it to, and puts the answer on `agent_capacity` (`agent_role` until D8 renamed it) — `working` against `next`.
The distinction is real and only that merge knows it, which is why F26 fixed it at the source. But
the source built its lookup as `set(decision._cannot_staff)` (`in_flight` then), which is a sequence of
`(task_id, agent)` **pairs** — so the set held tuples, the membership test asked it with a bare
`task.id`, and it never matched. the capacity could not be `working` in production from the day it
shipped.

It shipped green because the only tests were five vitest cases against the *renderer*, each handed
the value by the fixture. Nothing exercised the derivation. That is finding F41's
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
from hub.db.models import AIJob, Loop, Run, Task
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


async def _running_turn(db, task, agent, *, with_task_id=True):
    """A `Run` genuinely in flight, which is what `working` is now allowed to mean (F63).

    `with_task_id=False` is not a convenience: `run.task_id` is NULL on most real runs -- measured
    on the trial database at 6 of the 10 carrying a `completed` transition -- so the agent fallback
    in `_batch_loop_summaries` is the branch production actually takes, and a fixture that always
    set `task_id` would leave it untested.
    """
    run = Run(
        id=f"run-live-{agent}-{task.id}",
        project_id="proj-test",
        agent=agent,
        status="running",
        task_id=task.id if with_task_id else None,
    )
    db.add(run)
    await db.commit()
    return run


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

    **A live `Run` was added to this fixture on 2026-08-26 for F63**, and that is a correction to
    the test rather than a convenience. It asserted `working` over a review with no run anywhere,
    which is exactly the state F63 found the board lying about — so as written it pinned the bug in
    place. F49's actual claim is that the `working` branch is *reachable*, and it still is: with a
    real run in flight this passes, and the `held` case below is what the run-less fixture means.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="working")
        await _completed_by(db, task, AUTHOR)
        await _enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await _running_turn(db, task, REVIEWER)
        await db.commit()

    res = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    assert res.status_code == 200
    current = _card(res.json(), job.id)["loop"]["current_tasks"]

    assert [(t["id"], t.get("agent"), t.get("agent_capacity")) for t in current] == [
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

    assert [(t["id"], t.get("agent"), t.get("agent_capacity")) for t in current] == [
        (task.id, REVIEWER, "next")
    ]


# ---------------------------------------------------------------------------
# F63 — `working` must mean a run exists, and `held` must exist to mean the rest
# ---------------------------------------------------------------------------


async def test_a_review_nobody_is_running_reads_as_held_not_working(app, auth_headers, bind_runner):
    """The assertion that distinguishes this fix from doing nothing.

    Found live by the operator on 2026-08-26 judging group 11's check 11.5: after a review turn
    *failed*, the card still read `working` with zero non-terminal runs in the database.

    The cause is one word meaning two things. `scheduler.decide_firing` appends an `under_review`
    task to the cannot-staff collection unconditionally whenever it has an assignee, deliberately -- that is what
    keeps a verdict-less review visible instead of vanishing from the board (F23, F45) -- so
    the collection means "this firing cannot staff anybody onto this". `_batch_loop_summaries` rendered
    that as "this agent is mid-turn on it". Both were right about their own side.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="held")
        await _completed_by(db, task, AUTHOR)
        await _enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    res = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    assert res.status_code == 200
    current = _card(res.json(), job.id)["loop"]["current_tasks"]

    assert [(t["id"], t.get("agent"), t.get("agent_capacity")) for t in current] == [
        (task.id, REVIEWER, "held")
    ]


async def test_a_run_without_a_task_id_still_reads_as_working(app, auth_headers, bind_runner):
    """The agent fallback, which is the branch production actually takes.

    `run.task_id` is NULL on most runs, so matching on it alone would report `held` about genuinely
    running work -- the same lie as F63 in the opposite direction. Deliberately paired with the test
    above: together they say `working` is about a *run existing*, not about which column carries it.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="notaskid")
        await _completed_by(db, task, AUTHOR)
        await _enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await _running_turn(db, task, REVIEWER, with_task_id=False)
        await db.commit()

    res = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    current = _card(res.json(), job.id)["loop"]["current_tasks"]

    assert [(t["id"], t.get("agent"), t.get("agent_capacity")) for t in current] == [
        (task.id, REVIEWER, "working")
    ]


async def test_a_terminal_run_does_not_keep_a_review_reading_as_working(
    app, auth_headers, bind_runner
):
    """A finished run is not a running one, which is the literal shape of what was found live.

    The review turn that produced F63 ended `failed`. A fix that asked "is there a run for this
    task" without asking "is it still going" would pass the two tests above and reproduce the bug.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        job, _loop, task = await _flow(db, suffix="terminal")
        await _completed_by(db, task, AUTHOR)
        await _enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        run = await _running_turn(db, task, REVIEWER)
        run.status = "failed"
        await db.commit()

    res = await app.get("/api/v1/projects/proj-test/jobs", headers=auth_headers)
    current = _card(res.json(), job.id)["loop"]["current_tasks"]

    assert [(t["id"], t.get("agent"), t.get("agent_capacity")) for t in current] == [
        (task.id, REVIEWER, "held")
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
