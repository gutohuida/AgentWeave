"""`a-refusal-names-a-remedy-that-works` groups 1-3 — the remedy, the column it fits in, and once
per task.

Group 1 (D1): `own_review_remedy(task)` names what a refused actor can do about a task's own
review, by status alone. Group 2 (D2): `JobRun.error_summary` is fitted to its column at the
model, and `_wedged_review_reason` shortens the one sentence measured to overflow it. Group 3
(D3, F365): `_review_unstaffed_already_stands` compares a task's own newest `review_unstaffed`
record, not the loop's — a loop with two tasks stuck at once no longer shares one verdict between
them.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import (
    AIJob,
    EventLog,
    EvidenceFootprint,
    JobRun,
    Loop,
    RequirementEvidence,
    SpecDocument,
    SpecRequirement,
    Task,
    fit_error_summary,
)
from hub.scheduler import _wedged_review_reason, own_review_remedy
from hub.task_transition_service import apply_transition
from hub.task_transitions import operator, run_actor

# ---------------------------------------------------------------------------
# 1.2 — own_review_remedy names the right action for each status
# ---------------------------------------------------------------------------


def _task(status, title="a task"):
    return Task(id="task-remedy", project_id="proj-test", title=title, status=status)


def test_completed_names_land_it():
    """*Mutation:* swap the two branches. The test must fail."""
    remedy = own_review_remedy(_task("completed"))
    assert remedy == "Land it, on the task, to review it yourself."


def test_under_review_names_the_three_exits_never_land_it():
    """*Mutation:* swap the two branches. The test must fail."""
    remedy = own_review_remedy(_task("under_review"))
    assert remedy == "decide it yourself: approve, reject, or send it back with revision_needed."
    assert "Land it" not in remedy


# ---------------------------------------------------------------------------
# 2.3 — every JobRun.error_summary write is fitted to the column
# ---------------------------------------------------------------------------


def test_a_600_character_error_summary_is_stored_at_500_ending_ellipsis():
    """*Mutation:* remove the `@validates`. The test must fail."""
    run = JobRun(
        id="run-fit-long",
        job_id="job-fit",
        project_id="proj-test",
        status="skipped",
        trigger="scheduled",
        error_summary="x" * 600,
    )
    assert len(run.error_summary) == 500
    assert run.error_summary.endswith("…")
    assert run.error_summary[:499] == "x" * 499


def test_a_500_character_error_summary_is_stored_unchanged():
    text = "y" * 500
    run = JobRun(
        id="run-fit-exact",
        job_id="job-fit",
        project_id="proj-test",
        status="skipped",
        trigger="scheduled",
        error_summary=text,
    )
    assert run.error_summary == text


def test_none_error_summary_stays_none():
    run = JobRun(
        id="run-fit-none",
        job_id="job-fit",
        project_id="proj-test",
        status="fired",
        trigger="scheduled",
    )
    assert run.error_summary is None


def test_fit_error_summary_helper_matches_the_validator():
    assert fit_error_summary(None) is None
    assert fit_error_summary("z" * 500) == "z" * 500
    fitted = fit_error_summary("z" * 600)
    assert len(fitted) == 500
    assert fitted.endswith("…")


# ---------------------------------------------------------------------------
# 2.4 — _wedged_review_reason shortens the quoted title so the remedy survives
# ---------------------------------------------------------------------------


def test_wedged_review_reason_fits_500_at_a_32_char_reviewer_and_256_char_title():
    """*Mutation:* remove 2.2's title-shortening. The test must fail."""
    task = Task(
        id="task-wedged-remedy",
        project_id="proj-test",
        title="t" * 256,
        status="under_review",
    )
    reviewer = "r" * 32
    reason = _wedged_review_reason(task, reviewer)
    assert len(reason) <= 500, f"expected <= 500 chars, got {len(reason)}"
    assert reason.endswith(
        "review it yourself, or send it back with revision_needed."
    ), "the remedy must survive whole even once the title is cut"


# ---------------------------------------------------------------------------
# 3 — once per task, against real SQLite (F365)
# ---------------------------------------------------------------------------

AGENT1 = "f365-agent-1"
AGENT2 = "f365-agent-2"


@pytest.fixture
def live_scheduler(monkeypatch):
    """A `JobScheduler` the manual-run route can find.

    `run_job` refuses with 503 when `get_scheduler()` is None, so a test of the route that omitted
    this would never reach the firing at all. Copied from `test_a_review_nobody_is_doing.py`.
    """
    import hub.scheduler as scheduler_module
    from hub.scheduler import JobScheduler

    instance = JobScheduler()
    monkeypatch.setattr(scheduler_module, "get_scheduler", lambda: instance)
    return instance


async def _roster(app, auth_headers, bind_runner, *names):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    for name in names:
        await bind_runner(name, cli="claude")


async def _flow(db, *, suffix, agent=AGENT1):
    """A flow and its job, declaring a document — load-bearing (the review arm belongs to
    `agent-flows`, which a documentless loop is unaffected by; copied from
    `test_a_flow_names_what_it_cannot_staff.py::_flow`)."""
    job = AIJob(
        id=f"job-f365-{suffix}",
        project_id="proj-test",
        name=f"F365 {suffix}",
        agent=agent,
        message="keep the queue moving",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    db.add(
        SpecDocument(
            id=f"doc-f365-{suffix}",
            project_id="proj-test",
            path=f"spec/f365-{suffix}.html",
            title=f"Doc {suffix}",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()
    loop = Loop(
        id=f"loop-f365-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"f365 {suffix}",
        spec_document_id=f"doc-f365-{suffix}",
    )
    db.add(loop)
    await db.commit()
    return job, loop


async def _operator_completed(db, loop, *, suffix, agent):
    """A task *agent* worked and the operator marked `completed` — fixture (b)'s shape from
    `test_a_flow_names_what_it_cannot_staff.py`. The transitions and `assignee` name *agent*, and
    `completion_attribution.agent` is `None` (an operator move), which is what routes the review
    arm's exclusion through `agents_that_may_have_authored` rather than a single named author —
    the branch group 3's fix and evidence-widening both act on."""
    task = Task(
        id=f"task-f365-{suffix}",
        project_id="proj-test",
        title=f"work {suffix}",
        status="pending",
        loop_id=loop.id,
    )
    db.add(task)
    await db.commit()
    actor = run_actor(run_id=f"run-f365-{suffix}", agent=agent)
    for status in ("assigned", "in_progress"):
        await apply_transition(db, task, status, actor)
    task.assignee = agent
    await apply_transition(db, task, "completed", operator())
    await db.commit()
    return task


async def _evidence(db, task_id, *, suffix, agent, document_id, commit="c" * 40):
    """Evidence naming a commit, recorded by *agent* — satisfies `commit_for_task_review`'s gate,
    and (via `agents_that_recorded_evidence_for`) adds *agent* to the task's exclusion."""
    db.add(
        SpecRequirement(
            id=f"req-f365-{suffix}",
            project_id="proj-test",
            document_id=document_id,
            identifier=f"FR-{suffix}",
            key=f"fr-{suffix}",
            digest="d" * 64,
        )
    )
    db.add(
        RequirementEvidence(
            id=f"ev-f365-{suffix}",
            project_id="proj-test",
            requirement_id=f"req-f365-{suffix}",
            task_id=task_id,
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor=agent,
            summary="all green",
        )
    )
    db.add(
        EvidenceFootprint(
            id=f"fp-f365-{suffix}",
            project_id="proj-test",
            evidence_id=f"ev-f365-{suffix}",
            kind="git",
            commit_sha=commit,
            branch=f"agentweave/{agent}",
        )
    )
    await db.commit()


async def _review_unstaffed_events(db, task_id):
    rows = (
        (await db.execute(select(EventLog).where(EventLog.event_type == "review_unstaffed")))
        .scalars()
        .all()
    )
    return [row for row in rows if (row.data or {}).get("task_id") == task_id]


async def test_two_unstaffable_tasks_each_get_exactly_one_review_unstaffed(
    app, auth_headers, bind_runner, live_scheduler
):
    """3.2 (was 3.2). One loop, two tasks neither can be staffed, five firings through the real
    route. Exactly one `review_unstaffed` per task — not one per task per tick, and not F365's
    shape either, where two tasks' events alternate so the loop's newest record is always the
    *other* task's and the per-task check never matches (measured live: 347 of 357).

    Both tasks are worked and evidenced by the same single-agent roster, so both reach the
    exclusion branch (D3) on the first firing and repeat the identical reason on every firing
    after — the shape F365 was filed against.

    *Mutation:* revert to the loop-newest query (drop the `task_id` filter). The test must fail,
    while `test_an_unchanged_wedge_is_recorded_once_not_once_per_tick`
    (`hub/tests/test_a_review_nobody_is_doing.py`, one task, five firings) still passes against
    the mutant, which shows why it never caught this.
    """
    await _roster(app, auth_headers, bind_runner, AGENT1)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="twostuck")
        a = await _operator_completed(db, loop, suffix="twostuck-a", agent=AGENT1)
        b = await _operator_completed(db, loop, suffix="twostuck-b", agent=AGENT1)
        await _evidence(
            db, a.id, suffix="twostuck-a", agent=AGENT1, document_id="doc-f365-twostuck"
        )
        await _evidence(
            db, b.id, suffix="twostuck-b", agent=AGENT1, document_id="doc-f365-twostuck"
        )

    for _ in range(5):
        res = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)
        assert res.status_code != 500, res.text

    async with async_session_factory() as db:
        a_events = await _review_unstaffed_events(db, a.id)
        b_events = await _review_unstaffed_events(db, b.id)

    assert len(a_events) == 1, f"expected 1 event for task a, got {len(a_events)}"
    assert len(b_events) == 1, f"expected 1 event for task b, got {len(b_events)}"
    assert "has worked on this task" in a_events[0].data["reason"]
    assert "has worked on this task" in b_events[0].data["reason"]


async def test_a_changed_reason_is_recorded_again_for_only_the_task_that_changed(
    app, auth_headers, bind_runner, live_scheduler
):
    """3.3 (was 3.3, staging corrected in this split). Two tasks; between firings, one task's
    reason changes and the other's does not.

    Not by freeing a holding — `_agents_that_are_free` (`4b59ee0`) no longer varies availability
    or the fixed rung-3 sentence on a bare holding. Staged instead by varying one task's
    `excluded_because` reach: task `a` starts with no evidence at all, so it is refused before
    `resolve_reviewer` is ever asked (`commit_for_task_review` unresolved) — a different sentence
    entirely. Recording evidence for `a` by `AGENT2`, a **non-author** of `a`, both resolves that
    gate and (via `agents_that_recorded_evidence_for`) adds `AGENT2` to `a`'s exclusion, so the
    now-full two-agent roster is still unstaffed on the next firing, with the exclusion-branch
    reason instead. Task `b` is worked by `AGENT1` too (independent of `AGENT2`, the agent whose
    exclusion changed) and never gets evidence, so its reason never moves.

    *Mutation:* drop the task filter (revert to the loop-newest query). The test must fail.
    """
    await _roster(app, auth_headers, bind_runner, AGENT1, AGENT2)
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="changedonly")
        a = await _operator_completed(db, loop, suffix="changedonly-a", agent=AGENT1)
        b = await _operator_completed(db, loop, suffix="changedonly-b", agent=AGENT1)

    first = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)
    assert first.status_code != 500, first.text

    async with async_session_factory() as db:
        await _evidence(
            db, a.id, suffix="changedonly-a", agent=AGENT2, document_id="doc-f365-changedonly"
        )

    second = await app.post(f"/api/v1/projects/proj-test/jobs/{job.id}/run", headers=auth_headers)
    assert second.status_code != 500, second.text

    async with async_session_factory() as db:
        a_events = await _review_unstaffed_events(db, a.id)
        b_events = await _review_unstaffed_events(db, b.id)

    assert len(b_events) == 1, "task b's reason never changed -- one record, not two"
    assert "no recorded evidence" in b_events[0].data["reason"]

    assert len(a_events) == 2, "task a's reason changed once -- a second record, not a suppression"
    assert "no recorded evidence" in a_events[0].data["reason"]
    assert "has worked on this task" in a_events[1].data["reason"]
    assert a_events[0].data["reason"] != a_events[1].data["reason"]
