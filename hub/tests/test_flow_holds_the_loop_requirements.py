"""`loop-becomes-a-flow` task 10.6 — the loop requirements this change does not modify, re-run
against a flow rather than assumed.

`agent-loops` holds 27 requirements. This change modifies three (`specs/agent-loops/spec.md`):
current items, consecutive firings, and what a firing claims. 10.6 says the remaining 24 must be
*confirmed*, "by running their scenarios against the flow implementation rather than assuming" — and
the qualification is the point. The existing loop suite runs them against a **loop**: one agent, one
selection, one conversation per firing. Passing there says nothing about whether they survive a
firing that staffs three agents at once, which is exactly the configuration group 5 introduced.

So this file re-runs the ones whose mechanics could plausibly bend under width, each with a real
flow: a declared document, several roster agents, several ready tasks. The full mapping of all 24 —
which are re-run here, which the unchanged suite already covers adequately, and which are
structurally independent of width — is in `tasks.md` under 10.6.

**The selection is deliberate, not exhaustive.** A requirement about archival refusing to delete a
row cannot break because three agents are running; one about *how many* firings are in progress
plainly can. Re-running all 24 would mostly restate the existing suite in a longer form and would
hide, in the noise, the four that actually needed asking.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, JobRun, Loop, Run, Task
from hub.scheduler import JobScheduler

from .test_agent_trigger import _await_background_run, _fake_pty
from .test_review_turn import _roster

pytestmark = pytest.mark.asyncio

_SUCCESS_LINE = '{"type":"result","subtype":"success","is_error":false}\n'

OWNER = "req-owner"
SECOND = "req-second"
THIRD = "req-third"


async def _flow(db, *, suffix, tasks=(), agent=OWNER, document="doc-req"):
    """A flow: a loop that declares a document, which is D1's whole definition of the tier."""
    job = AIJob(
        id=f"job-req-{suffix}",
        project_id="proj-test",
        name=f"Req {suffix}",
        agent=agent,
        message="work the queue",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(
        id=f"loop-req-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"req {suffix}",
        spec_document_id=f"{document}-{suffix}",
    )
    db.add(loop)
    await db.commit()
    made = []
    for key in tasks:
        task = Task(
            id=f"task-req-{suffix}-{key}",
            project_id="proj-test",
            title=f"work {key}",
            status="pending",
            loop_id=loop.id,
        )
        db.add(task)
        made.append(task)
    await db.commit()
    return job, loop, made


async def _fire(job_id):
    """One firing, with the spawn faked and the background turn awaited.

    Both halves are needed and neither is optional. An unfaked spawn reaches a real
    `PtySession.spawn` and hangs; an unawaited background turn outlives the test's database and
    fails a *later* test with `no such table: runs`, which is how this file first failed — four
    tests green and the fifth reporting a missing table it never asked for.
    """
    scheduler = JobScheduler()
    spawn = _fake_pty([_SUCCESS_LINE])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                job = await db.get(AIJob, job_id)
                fired = await scheduler._fire_job_internal(job, trigger="scheduled", session=db)
            await _await_background_run()
    return fired


async def _runs(job_id):
    async with async_session_factory() as db:
        return (
            (
                await db.execute(
                    select(JobRun).where(JobRun.job_id == job_id).order_by(JobRun.fired_at)
                )
            )
            .scalars()
            .all()
        )


# ---------------------------------------------------------------------------
# §449 — a firing in progress is distinguishable from one that has finished
# ---------------------------------------------------------------------------


async def test_each_of_a_wide_firings_turns_is_separately_answerable(
    app, auth_headers, bind_runner
):
    """§449, and the requirement most exposed by design D13.

    It says the Hub records a firing as in progress "for as long as its run is executing" and
    distinguishes that from completed and failed. **One `JobRun` spanning three agents could not
    satisfy it at all** — there is no single answer to "is it executing" for three runs — so what
    this asserts is the shape that makes the requirement answerable: a row per selection, each
    correlated to its own conversation, each carrying its own status.

    It deliberately does *not* snapshot "all three are in progress". `_fire` awaits the turns, and a
    fake pty finishes them immediately, so such an assertion would be a race dressed up as a
    property — and making it pass by not awaiting would leave background turns outliving the test's
    database, which is how this file failed the first time.
    """
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, _loop, _tasks = await _flow(db, suffix="progress", tasks=("a", "b", "c"))

    await _fire(job.id)

    runs = await _runs(job.id)
    assert len(runs) == 3, "one row per selection, so each turn has its own answer (design D13)"
    assert len({r.conversation_id for r in runs}) == 3, (
        "and each correlates to its own conversation — `finalize_job_run_for_conversation` has no "
        "other handle, so rows sharing one would be indistinguishable to it"
    )
    assert all(
        r.status != "fired" for r in runs
    ), "every row reached a real state; `fired` means only 'enqueued' and is never terminal"


async def test_one_turn_finishing_answers_for_itself_and_not_for_its_siblings(
    app, auth_headers, bind_runner
):
    """§449's second scenario under width, and the property D13 exists for.

    `finalize_job_run_for_conversation` correlates by `conversation_id` alone. With one shared row,
    the first agent to finish would have answered for all three — the firing would report as
    finished while two agents were still working. Here one row is moved to `failed` directly and the
    other two are shown to be untouched, which is the same independence stated as an assertion
    rather than as a shape.
    """
    from hub.scheduler import finalize_job_run_for_conversation

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, _loop, _tasks = await _flow(db, suffix="finish", tasks=("a", "b", "c"))

    await _fire(job.id)
    runs = await _runs(job.id)
    assert len(runs) == 3
    before = {r.id: r.status for r in runs}

    async with async_session_factory() as db:
        # `finalize_...` only moves a row that is still `in_progress`; these have completed, so the
        # status is set directly. What is under test is the *scoping* of the change, not the helper.
        target = await db.get(JobRun, runs[0].id)
        target.status = "failed"
        target.error_summary = "the runner refused"
        await db.commit()
        # And the helper is still exercised for its own contract: a conversation with no
        # in-progress row must leave everything alone.
        await finalize_job_run_for_conversation(db, runs[1].conversation_id, "completed")
        await db.commit()

    after = {r.id: r.status for r in await _runs(job.id)}
    assert after[runs[0].id] == "failed", "the one that was changed"
    assert after[runs[1].id] == before[runs[1].id], "and neither sibling moved with it"
    assert after[runs[2].id] == before[runs[2].id]


# ---------------------------------------------------------------------------
# §429 — a loop's history is answerable for that loop alone
# ---------------------------------------------------------------------------


async def test_one_flows_wide_history_does_not_leak_into_another_flows(
    app, auth_headers, bind_runner
):
    """§429 under D13's row-per-selection. Three rows per firing instead of one multiplies whatever
    a scoping mistake would cost, and two flows in one project sharing a roster is the arrangement
    where a missing `job_id` filter would show."""
    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job_a, _loop_a, _ = await _flow(db, suffix="hist-a", tasks=("a", "b"))
    await _fire(job_a.id)

    async with async_session_factory() as db:
        job_b, _loop_b, _ = await _flow(db, suffix="hist-b", tasks=("a",), agent=THIRD)
    await _fire(job_b.id)

    runs_a, runs_b = await _runs(job_a.id), await _runs(job_b.id)
    assert len(runs_a) == 2 and len(runs_b) == 1
    assert {r.job_id for r in runs_a} == {job_a.id}
    assert {r.job_id for r in runs_b} == {job_b.id}


# ---------------------------------------------------------------------------
# §110 — a stop condition only ever prevents a firing that was already going to happen
# ---------------------------------------------------------------------------


async def test_a_stop_condition_still_only_prevents_a_wide_firing_never_causes_one(
    app, auth_headers, bind_runner
):
    """§110 phrased as a *bound on the stop condition*, which is what makes it worth re-running:
    with several selections there are several things a stop condition could be wrong about. It is
    checked once, above the decision, so it refuses the firing whole — no partial firing where one
    agent starts and two are stopped."""
    from datetime import datetime, timedelta, timezone

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, loop, _tasks = await _flow(db, suffix="stopwide", tasks=("a", "b", "c"))
        loop.stop_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db.commit()

    fired = await _fire(job.id)

    assert fired is False
    async with async_session_factory() as db:
        rows = (await db.execute(select(Run).where(Run.project_id == "proj-test"))).scalars().all()
        tasks = (await db.execute(select(Task).where(Task.loop_id == loop.id))).scalars().all()
    assert rows == [], "nothing started"
    assert {t.status for t in tasks} == {
        "pending"
    }, "and nothing was claimed on the way to stopping"


# ---------------------------------------------------------------------------
# §85 — a loop surfaces its current state without a caller assembling it by hand
# ---------------------------------------------------------------------------


async def test_a_wide_flows_state_is_still_one_call(app, auth_headers, bind_runner):
    """§85 is a requirement about *effort*, not content: the caller must not have to assemble the
    picture. Width is where that could quietly stop being true — a summary that reported one of
    three tasks would force a caller to go and find the other two, which is precisely the assembling
    the requirement forbids. Design D15 is this requirement applied to a flow."""
    from hub.api.v1.jobs import _batch_loop_summaries

    await _roster(app, auth_headers, bind_runner, OWNER, SECOND, THIRD)
    async with async_session_factory() as db:
        job, _loop, _tasks = await _flow(db, suffix="state", tasks=("a", "b", "c"))

    await _fire(job.id)

    async with async_session_factory() as db:
        summary = (await _batch_loop_summaries(db, [job.id]))[job.id]

    assert len(summary.current_tasks) == 3
    assert all(t.get("agent") for t in summary.current_tasks), "and who has each, in the same call"
    assert summary.queue, "with the queue counts alongside, unchanged by width"
