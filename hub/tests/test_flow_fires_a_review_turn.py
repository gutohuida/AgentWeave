"""`loop-becomes-a-flow` group 4b — a flow that staffs a review delivers a review *turn*.

Design D9, added on 2026-08-24 after `a-reviewer-can-see-the-work` shipped. This change was designed
three days earlier and described firing a reviewer as an ordinary firing. It is not one, and the
difference is the whole of finding F10: an ordinary firing puts the agent in its own working
checkout, and unreviewed work exists only on the author's branch — so a reviewer given an ordinary
turn cannot see the thing it was fired to review. `review_turn.py`'s own docstring records the
circularity: *"the only way to see it was to integrate it — which is what the review was meant to
decide."*

The mechanism already existed. What did not exist was one argument: `_do_fire_job` built its queue
entry with no `review_task_id`, so everything downstream treated a staffed review as ordinary work.

**`test_a_flow_fired_reviewer_reads_a_file_that_is_not_on_main` is the assertion this group exists
for**, and it is deliberately the same assertion `test_review_turn.py` makes about a manual trigger.
Same property, different door — because the door is what group 4b adds, and a test of the plumbing
alone would pass while the reviewer still stood in the wrong directory.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import worktrees
from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, Loop, SpecDocument, Task
from hub.scheduler import JobScheduler
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

from .test_agent_trigger import _await_background_run, _fake_pty, _init_repo
from .test_review_turn import (
    _REAL_ENSURE_REVIEW_CHECKOUT,
    _author_commit,
    _reviewable_task,
    _roster,
)

pytestmark = pytest.mark.asyncio

AUTHOR = "builder"
REVIEWER = "critic"


async def _flow(db, *, suffix, agent=AUTHOR, task_id=None):
    """A flow whose job belongs to *agent*, with an optional existing task adopted into its queue.

    **It declares a document, and that is what makes it a flow** (`agent-flows:13`). Until
    `approval-waits-for-the-turn-to-end` (design D5) this built a documentless `Loop` and every test
    in this file — all of them about a flow firing a review turn — was standing in for a flow with a
    row the product does not treat as one. `decide_firing`'s review arm now reads the declaration,
    so the fixture states what the file's name already claimed.
    """
    job = AIJob(
        id=f"job-flow-{suffix}",
        project_id="proj-test",
        name=f"Flow {suffix}",
        agent=agent,
        message="keep the ledger balanced",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    db.add(
        SpecDocument(
            id=f"doc-flow-{suffix}",
            project_id="proj-test",
            path=f"spec/flow-{suffix}.html",
            title=f"Flow {suffix}",
            phase="current",
            kind="capability",
        )
    )
    await db.commit()
    loop = Loop(
        id=f"loop-flow-{suffix}",
        project_id="proj-test",
        job_id=job.id,
        purpose=f"flow {suffix}",
        spec_document_id=f"doc-flow-{suffix}",
    )
    db.add(loop)
    await db.commit()
    if task_id is not None:
        task = await db.get(Task, task_id)
        task.loop_id = loop.id
        await db.commit()
    return job, loop


async def _attribute_completion(db, task_id, agent):
    """Record *agent* as the one that completed *task_id*.

    `_reviewable_task` constructs its task directly at `completed`, which leaves no
    `TaskTransition` — and an unattributable completed task is offered to nobody
    (`task_is_claimable_by`). So the flow needs the provenance the fixture does not create. Walking
    it backwards and forwards through the machine is how a real one gets there.
    """
    task = await db.get(Task, task_id)
    actor = run_actor(run_id=f"run-{agent}-authored", agent=agent)
    task.status = "in_progress"
    await db.commit()
    await apply_transition(db, task, "completed", actor)
    await db.commit()


async def _queued_entry_for(agent):
    async with async_session_factory() as db:
        return (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .first()
        )


# ---------------------------------------------------------------------------
# 4b.1 — the entry carries `review_task_id`, and the turn is a review turn
# ---------------------------------------------------------------------------


async def test_a_flow_staffing_a_completed_task_queues_a_review(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)

    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        job, _loop = await _flow(db, suffix="queues", task_id="task-1")

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    entry = await _queued_entry_for(REVIEWER)
    assert entry is not None, "the ladder staffs the reviewer, so the entry is theirs not the job's"
    assert entry.review_task_id == "task-1"

    # And nothing was queued for the author, whose own finished work this is.
    assert await _queued_entry_for(AUTHOR) is None


# ---------------------------------------------------------------------------
# 4b.2 — the property that matters: the reviewer can see the author's work
# ---------------------------------------------------------------------------


async def test_a_flow_fired_reviewer_reads_a_file_that_is_not_on_main(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """F10's own assertion, reached through a flow firing rather than a manual trigger.

    This is the test that distinguishes group 4b from doing nothing. Without the one argument D9
    names, the reviewer is spawned in its own working checkout and `ledger.py` is not there — which
    is exactly the state that made a reviewing agent ask the author what had changed.
    """
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="def balance():\n    return 0\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)

    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        job, _loop = await _flow(db, suffix="sees", task_id="task-1")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    scheduler = JobScheduler()
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job.id)
                await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
            await _await_background_run()

    cwd = Path(fake_spawn.call_args.kwargs["cwd"])
    assert cwd == worktrees.review_path(repo, REVIEWER)
    # Not on main, and readable here. This is what the reviewer could not do before.
    assert not (repo / "ledger.py").exists()
    assert (cwd / "ledger.py").read_text() == "def balance():\n    return 0\n"


# ---------------------------------------------------------------------------
# 4b.4 — ordinary work acquires no checkout
# ---------------------------------------------------------------------------


async def test_a_firing_that_staffs_ordinary_work_carries_no_review_task_id(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The negative that keeps the positive meaningful. If every firing carried a
    `review_task_id`, every turn would build a detached checkout, and a flow doing ordinary work
    would be reviewing its own unstarted task."""
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)

    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="ordinary")
        db.add(
            Task(
                id="task-ordinary",
                project_id="proj-test",
                title="not started",
                status="pending",
                loop_id=loop.id,
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    entry = await _queued_entry_for(AUTHOR)
    assert entry is not None
    assert entry.review_task_id is None


async def test_a_plain_job_with_no_loop_still_fires(app, auth_headers, bind_runner):
    """A job without a loop makes no selection at all, and the review argument must not turn that
    into a failure. `selection` is bound before the loop branch precisely for this path — it was
    not, briefly, and a plain scheduled job would have raised `NameError` at the queue entry."""
    await _roster(app, auth_headers, bind_runner, "plain-agent")

    async with async_session_factory() as db:
        db.add(
            AIJob(
                id="job-plain",
                project_id="proj-test",
                name="Plain",
                agent="plain-agent",
                message="a standing instruction",
                cron="0 9 * * *",
                session_mode="new",
                enabled=True,
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, "job-plain")
            await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    entry = await _queued_entry_for("plain-agent")
    assert entry is not None
    assert entry.review_task_id is None


# ---------------------------------------------------------------------------
# 4b.6 — the checkout is built for the agent the ladder chose
# ---------------------------------------------------------------------------


async def test_the_checkout_belongs_to_the_agent_the_ladder_resolved(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """Review isolation is per agent, so a mismatch here builds the right checkout for the wrong
    one — the reviewer would be looking at the work in somebody else's directory, or at nothing.

    Driven with a *declared* reviewer so the ladder's answer and the job's agent are three
    different names, which is the only arrangement where getting this wrong is visible.
    """
    from hub.spec_payload import SCHEMA_VERSION, embed_payload

    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 2\n")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, "aa-idle")

    document = repo / "spec" / "ledger.html"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        embed_payload(
            {"schema_version": SCHEMA_VERSION, "tasks": [{"key": "t1", "reviewer": REVIEWER}]}
        ),
        encoding="utf-8",
    )
    await _reviewable_task(commit=sha, reviewer_declaration=REVIEWER)

    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        # The job belongs to a third agent, and `aa-idle` sorts before `critic` — so availability
        # alone would pick `aa-idle` and the job's own agent would pick neither.
        job, _loop = await _flow(db, suffix="declared", agent="aa-idle", task_id="task-1")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    scheduler = JobScheduler()
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job.id)
                await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
            await _await_background_run()

    cwd = Path(fake_spawn.call_args.kwargs["cwd"])
    assert cwd == worktrees.review_path(repo, REVIEWER)
    assert cwd != worktrees.review_path(repo, "aa-idle")


# ---------------------------------------------------------------------------
# 4.7 — a review nobody can take is surfaced, and the job keeps running
# ---------------------------------------------------------------------------


async def test_an_unstaffable_review_is_surfaced_and_the_job_stays_scheduled(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """Design D4 rung 3. A single-agent project reaches it by the general rule.

    The job must stay enabled: unstaffable is resolved by adding an agent or freeing one, and both
    are changes the next firing should pick up by itself. Stopping would set `enabled = False` and
    call `remove_job`, which resolving nothing undoes.
    """
    from hub.db.models import EventLog

    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 3\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    await _reviewable_task(commit=sha)

    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        job, _loop = await _flow(db, suffix="unstaffed", task_id="task-1")

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            fired = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert fired is False

    async with async_session_factory() as db:
        events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "review_unstaffed")))
            .scalars()
            .all()
        )
        assert len(events) == 1, "the operator learns about a review nobody can take"
        assert events[0].data["task_id"] == "task-1"
        assert "could not staff this step" in events[0].data["reason"]

        refreshed = await db.get(AIJob, job.id)
        assert refreshed.enabled is True

        loop_row = (await db.execute(select(Loop).where(Loop.job_id == job.id))).scalars().one()
        assert loop_row.stop_reason is None

    # Nothing was queued for anybody.
    assert await _queued_entry_for(AUTHOR) is None


async def test_an_unstaffable_review_does_not_stop_the_flow_doing_other_work(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """D4 says surface *the step*, not stop the flow.

    A queue holding an unstaffable review ahead of ordinary work — and review does sort ahead, see
    design D10 — should do the ordinary work and surface the review, rather than sit still. Sitting
    still would mean one unreviewable task halts a flow indefinitely.
    """
    from hub.db.models import EventLog

    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 4\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    await _reviewable_task(commit=sha)

    async with async_session_factory() as db:
        await _attribute_completion(db, "task-1", AUTHOR)
        job, loop = await _flow(db, suffix="carryon", task_id="task-1")
        db.add(
            Task(
                id="task-still-to-do",
                project_id="proj-test",
                title="ordinary work behind the review",
                status="pending",
                loop_id=loop.id,
            )
        )
        await db.commit()

    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            fresh_job = await db.get(AIJob, job.id)
            fired = await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)

    assert fired is True

    entry = await _queued_entry_for(AUTHOR)
    assert entry is not None
    assert entry.review_task_id is None, "the ordinary task, not the review"

    async with async_session_factory() as db:
        events = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "review_unstaffed")))
            .scalars()
            .all()
        )
        assert len(events) == 1, "and the review is still surfaced, not swallowed by the work"
        # `every-run-knows-its-task` D1/D2: the staged entry now carries `task_id`, so the run
        # it starts binds and advances the claim past `assigned` to `in_progress`.
        assert (await db.get(Task, "task-still-to-do")).status == "in_progress"


# ---------------------------------------------------------------------------
# 4b.3 — a review that cannot be prepared is refused, never downgraded
# ---------------------------------------------------------------------------


async def test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    """A completed task with no evidence naming a commit: nothing to check out.

    **The downgrade this forbids is unreachable rather than merely not taken**, and that is the
    point worth pinning. `trigger_agent_directly` raises out of its `ReviewTurnRefused` handler
    before a workspace is chosen at all, so there is no branch in which a refused review carries on
    into `resolve_agent_workspace` and quietly becomes an ordinary turn. A reviewer silently placed
    somewhere it cannot see the work would report on what it *can* see, and the operator would read
    that as a review — which is why D9 rejected downgrading explicitly.

    **What changed, and why the assertions below are stronger than the ones they replace.** This
    test used to require that the firing *dispatched* the doomed review anyway — that a queued
    entry existed naming the task — on the reasoning that the operator should see what was
    attempted. Driving a real loop on 2026-08-28 showed what that costs. The selection is staged
    before the turn is dispatched, so `enter_selected_task` had already moved the task
    `completed -> under_review` and written a reviewer into `assignee` by the time the refusal
    happened. The task was left wedged with a reviewer who never ran, and every subsequent firing
    repeated it, once a minute, each one recorded `failed`. See
    `test_a_review_needs_something_to_review.py`.

    So `decide_firing` now declines the step up front and reports it as `unstaffed` with the reason
    — which reaches the loop card and the stall sentence (F64), where a queued entry and a failed
    `JobRun` did not. The refusal in `prepare_review_turn` is untouched and still governs the
    operator's own `review_task_id` trigger; this only stops the *flow* attempting an impossible
    review on every tick.
    """
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)

    async with async_session_factory() as db:
        db.add(
            Task(
                id="task-no-evidence",
                project_id="proj-test",
                title="finished, but nothing says where",
                status="pending",
            )
        )
        await db.commit()
        await _attribute_completion(db, "task-no-evidence", AUTHOR)
        job, _loop = await _flow(db, suffix="unpreparable", task_id="task-no-evidence")

    fake_spawn = _fake_pty(['{"type":"result","subtype":"success","is_error":false}\n'])
    scheduler = JobScheduler()
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            async with async_session_factory() as db:
                fresh_job = await db.get(AIJob, job.id)
                await scheduler._fire_job_internal(fresh_job, trigger="scheduled", session=db)
            await _await_background_run()

    assert fake_spawn.call_args is None, (
        "a review that cannot be prepared must not fall through to an ordinary turn -- an agent "
        "placed where it cannot see the work reports on what it can see, and that reads as a review"
    )

    # Nothing was dispatched at all, and nothing was mutated on the way to finding that out.
    assert await _queued_entry_for(REVIEWER) is None
    async with async_session_factory() as db:
        task = await db.get(Task, "task-no-evidence")
        assert task.status == "completed"
        assert task.assignee != REVIEWER
