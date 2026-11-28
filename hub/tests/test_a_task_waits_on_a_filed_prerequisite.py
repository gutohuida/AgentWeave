"""A checker files a prerequisite; the task waits in `blocked` and resumes with its builder.

`a-task-that-cannot-move-waits-instead-of-being-rebuilt-and-re-reviewed`, task
`prerequisite-stops-and-releases`. In build-a24caf7d4f37 TSBVD-5 was sent back 41 times because its
real blockers, filed mid-build, could not be made its prerequisites: `create_task`'s `depends_on`
only lets a new task wait on existing ones. Now the current review round's checker files a task
naming the reviewed one in `precedes` (FR-1), which stops it (FR-2) in `blocked` naming what it
waits on, released to its builder only when every reason clears (FR-3), handed out by the next
firing with the approved work in its branch (FR-6, FR-9). A run in flight finishes; its moves are
refused (FR-8).

Driven through the agent plane with each run's own credential, as an agent's call arrives.
Named by acceptance criterion: `-k checker_files`, `-k others_cannot`, `-k ends_the_round`,
`-k goes_to_builder`, `-k started_task_stops`, `-k names_prerequisites`, `-k both_reasons`,
`-k handed_out`, `-k catch_up_conflict`, `-k in_flight`.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from hub import assigned_task_start, worktrees
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Loop, Question, Run, Task, TaskDependency, TaskTransition
from hub.scheduler import decide_firing

from .test_review_turn import _roster

P = "proj-test"
TASKS = f"/api/v1/projects/{P}/tasks"
AGENT_TASKS = "/api/v1/agent-actions/tasks"
STARTED = ("in_progress", "completed", "under_review", "revision_needed")
_T0 = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


async def _people(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "Developer", "QA", "QA2", "builder")


async def _task(task_id, status, *, assignee=None, loop_id=None, builder="Developer"):
    holder = assignee or ("QA" if status == "under_review" else "Developer")
    async with async_session_factory() as db:
        db.add(
            Task(
                id=task_id,
                project_id=P,
                title=f"Task {task_id}",
                status=status,
                assignee=holder,
                builder=builder,
                checker="QA",
                loop_id=loop_id,
            )
        )
        await db.commit()
    return task_id


async def _run(run_id, agent, task_id, *, minutes=0, status="running"):
    """A run of *agent* bound to *task_id*, and the credential its calls carry."""
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id=P,
                agent=agent,
                task_id=task_id,
                status=status,
                turn_depth=0,
                started_at=_T0 + timedelta(minutes=minutes),
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _end(run_id):
    """The run's turn is over, so it holds no writing turn on its task."""
    async with async_session_factory() as db:
        (await db.get(Run, run_id)).status = "completed"
        await db.commit()


async def _file(app, headers, waiting, **body):
    return await app.post(
        AGENT_TASKS, json={"title": "The fix", "precedes": [waiting], **body}, headers=headers
    )


async def _read(task_id):
    async with async_session_factory() as db:
        return await db.get(Task, task_id)


async def _prerequisites(task_id):
    async with async_session_factory() as db:
        return set(
            (
                await db.execute(
                    select(TaskDependency.depends_on_task_id).where(
                        TaskDependency.task_id == task_id
                    )
                )
            ).scalars()
        )


async def _send_backs(task_id):
    async with async_session_factory() as db:
        return await db.scalar(
            select(func.count())
            .select_from(TaskTransition)
            .where(TaskTransition.task_id == task_id, TaskTransition.to_status == "revision_needed")
        )


async def _approve(app, auth_headers, task_id):
    """The operator walks *task_id* to `approved`, as a prerequisite's review ends."""
    for step in ("in_progress", "completed", "under_review", "approved"):
        moved = await app.patch(f"{TASKS}/{task_id}", json={"status": step}, headers=auth_headers)
        assert moved.status_code == 200, moved.text


async def _blocked_on(app, auth_headers, bind_runner, status, waiting="task-w"):
    """W in *status*, then the checker's current run files F naming W. Returns F's id."""
    await _people(app, auth_headers, bind_runner)
    await _task(waiting, status)
    qa = await _run(f"run-qa-{waiting}", "QA", waiting)
    filed = await _file(app, qa, waiting)
    assert filed.status_code == 201, filed.text
    return filed.json()["id"], qa


@pytest.fixture
def starts(monkeypatch):
    """The background start a release asks for outside a flow, recorded instead of run: it would
    move W on to `in_progress` at a moment the test does not choose, racing what it reads."""
    asked = []
    monkeypatch.setattr(
        assigned_task_start, "request", lambda task_id, by_run=None: asked.append(task_id)
    )
    return asked


async def _assert_released(task_id, starts, builder="Developer"):
    """*task_id* went from `blocked` to `assigned` with its builder, and its start was asked for."""
    released = await _read(task_id)
    assert (released.status, released.assignee, released.blocked_reason) == (
        "assigned",
        builder,
        None,
    )
    assert released.waits_on_prerequisites is False
    async with async_session_factory() as db:
        last = (
            await db.execute(
                select(TaskTransition)
                .where(TaskTransition.task_id == task_id)
                .order_by(TaskTransition.sequence.desc())
                .limit(1)
            )
        ).scalar_one()
    assert (last.from_status, last.to_status) == ("blocked", "assigned")
    assert task_id in starts


# ---------------------------------------------------------------------------------------------
# FR-1 checker-files-prerequisite, others-cannot-add-prerequisite, filing-ends-the-round
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_checker_files_a_prerequisite_and_a_cycle_is_refused(
    app, auth_headers, bind_runner
):
    fix, _ = await _blocked_on(app, auth_headers, bind_runner, "under_review")

    assert await _prerequisites("task-w") == {fix}
    listed = (await app.get(f"{TASKS}/task-w", headers=auth_headers)).json()
    assert [row["id"] for row in listed["prerequisites"]] == [fix]

    # The same call, the new task already waiting on W through its own depends_on, closes a loop.
    await _task("task-w2", "under_review")
    qa = await _run("run-qa-w2", "QA", "task-w2")
    async with async_session_factory() as db:
        before = await db.scalar(select(func.count()).select_from(Task))
    refused = await _file(app, qa, "task-w2", depends_on=["task-w2"])
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert "cycle" in detail and "task-w2" in detail
    async with async_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Task)) == before
    assert await _prerequisites("task-w2") == set()
    assert (await _read("task-w2")).status == "under_review"


@pytest.mark.asyncio
async def test_others_cannot_add_a_prerequisite(app, auth_headers, bind_runner):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "under_review")
    await _task("task-other", "in_progress")
    builders = await _run("run-dev-w", "Developer", "task-w", minutes=0)
    earlier = await _run("run-qa-w-1", "QA", "task-w", minutes=1)
    await _run("run-qa-w-2", "QA", "task-w", minutes=2)  # the current round's
    elsewhere = await _run("run-qa-other", "QA", "task-other", minutes=3)

    for headers in (builders, earlier, elsewhere):
        refused = await _file(app, headers, "task-w")
        assert refused.status_code == 403, refused.text
        assert "current review round's checker" in refused.json()["detail"]

    assert await _prerequisites("task-w") == set()
    assert (await _read("task-w")).status == "under_review"


@pytest.mark.asyncio
async def test_filing_ends_the_round(app, auth_headers, bind_runner):
    fix, qa = await _blocked_on(app, auth_headers, bind_runner, "under_review")

    for verdict in (
        {"status": "approved"},
        {"status": "revision_needed", "reason_class": "defect"},
    ):
        moved = await app.patch(
            f"{AGENT_TASKS}/task-w", json={**verdict, "notes": "the fix is missing"}, headers=qa
        )
        assert moved.status_code == 409, moved.text
        assert fix in str(moved.json()["detail"])

    assert (await _read("task-w")).status == "blocked"
    assert await _send_backs("task-w") == 0


# ---------------------------------------------------------------------------------------------
# FR-5 fix-goes-to-builder
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_fix_goes_to_the_builder(app, auth_headers, bind_runner):
    fix, qa = await _blocked_on(app, auth_headers, bind_runner, "under_review")
    assert (await _read(fix)).builder == "Developer"

    named = await _file(app, qa, "task-w", builder="QA2")
    assert named.status_code == 201, named.text
    assert (await _read(named.json()["id"])).builder == "QA2"


# ---------------------------------------------------------------------------------------------
# FR-2 started-task-stops
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", STARTED)
async def test_a_started_task_stops(app, auth_headers, bind_runner, status, monkeypatch):
    from hub import task_integration
    from hub.requirement_evidence import ReviewTarget

    async def _reviewable(session, task, root=None):
        return ReviewTarget(commit_sha="a" * 40, branch=f"agentweave/task/{task.id}")

    monkeypatch.setattr(task_integration, "review_target", _reviewable)
    await _people(app, auth_headers, bind_runner)
    from .test_loop_lands_its_work import make_loop

    loop_id = await make_loop(app, auth_headers, name=f"Stops from {status}")
    await _task("task-w", status, loop_id=loop_id)
    qa = await _run("run-qa-w", "QA", "task-w")
    filed = await _file(app, qa, "task-w")
    assert filed.status_code == 201, filed.text
    fix = filed.json()["id"]
    await _end("run-qa-w")

    stopped = await _read("task-w")
    assert stopped.status == "blocked"
    assert stopped.waits_on_prerequisites is True
    assert fix in stopped.blocked_reason

    # One firing after the add: nobody is handed W, to build or to review.
    async with async_session_factory() as db:
        loop = await db.get(Loop, loop_id)
        decision = await decide_firing(db, loop, default_agent="builder")
    assert "task-w" not in [selection.task.id for selection in decision.selections]
    async with async_session_factory() as db:
        builder_runs = await db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.task_id == "task-w", Run.agent == "Developer")
        )
    assert builder_runs == 0


# ---------------------------------------------------------------------------------------------
# FR-3 blocked-names-prerequisites, both-reasons-clear
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("status", STARTED)
async def test_blocked_names_its_prerequisites_until_the_last_is_approved(
    app, auth_headers, bind_runner, status, starts
):
    first, qa = await _blocked_on(app, auth_headers, bind_runner, status)
    second = await _file(app, qa, "task-w", title="The second fix")
    assert second.status_code == 201, second.text
    second = second.json()["id"]
    assert first in (await _read("task-w")).blocked_reason
    assert second in (await _read("task-w")).blocked_reason

    await _approve(app, auth_headers, first)
    waiting = await _read("task-w")
    assert waiting.status == "blocked"
    assert second in waiting.blocked_reason and first not in waiting.blocked_reason

    await _approve(app, auth_headers, second)
    await _assert_released("task-w", starts)


@pytest.mark.asyncio
async def test_the_blocked_reason_names_no_status_that_goes_stale(app, auth_headers, bind_runner):
    """TTCMW-6: `blocked_reason` is written when the wait begins and is not rewritten as F moves,
    so a status in it went on saying `pending` while F was assigned, completed, under review."""
    fix, _qa = await _blocked_on(app, auth_headers, bind_runner, "in_progress")
    expected = f"Waiting on prerequisites: 'The fix' ({fix})."
    assert (await _read("task-w")).blocked_reason == expected

    for moved in ("assigned", "in_progress", "completed", "under_review"):
        async with async_session_factory() as db:
            (await db.get(Task, fix)).status = moved
            await db.commit()
        assert (await _read("task-w")).blocked_reason == expected

    # The stop's history row is a record of that moment, and keeps the status F had then.
    async with async_session_factory() as db:
        note = await db.scalar(
            select(TaskTransition.note).where(
                TaskTransition.task_id == "task-w", TaskTransition.to_status == "blocked"
            )
        )
    assert note == f"Stopped: Waiting on prerequisites: 'The fix' ({fix}, pending)."


async def _question(question_id, task_id):
    async with async_session_factory() as db:
        db.add(
            Question(
                id=question_id,
                project_id=P,
                from_agent="Developer",
                question="Which way should the fix go?",
                blocking=True,
                blocked_task_id=task_id,
            )
        )
        await db.commit()


async def _answer(app, auth_headers, question_id):
    answered = await app.patch(
        f"/api/v1/projects/{P}/questions/{question_id}",
        json={"answer": "this way"},
        headers=auth_headers,
    )
    assert answered.status_code == 200, answered.text


@pytest.mark.asyncio
async def test_both_reasons_clear_question_first(app, auth_headers, bind_runner, starts):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "blocked")
    await _question("q-w", "task-w")
    qa = await _run("run-qa-w", "QA", "task-w")
    filed = await _file(app, qa, "task-w")
    assert filed.status_code == 201, filed.text
    fix = filed.json()["id"]
    both = await _read("task-w")
    assert both.waits_on_prerequisites and "Which way" in both.blocked_reason
    assert fix in both.blocked_reason

    await _answer(app, auth_headers, "q-w")
    waiting = await _read("task-w")
    assert waiting.status == "blocked"
    assert fix in waiting.blocked_reason and "Which way" not in waiting.blocked_reason

    await _approve(app, auth_headers, fix)
    await _assert_released("task-w", starts)


@pytest.mark.asyncio
async def test_both_reasons_clear_prerequisite_first(app, auth_headers, bind_runner, starts):
    fix, _ = await _blocked_on(app, auth_headers, bind_runner, "in_progress")
    # The builder's run, still going, then asks the operator (a block on a blocked task).
    await _question("q-w", "task-w")

    await _approve(app, auth_headers, fix)
    waiting = await _read("task-w")
    assert waiting.status == "blocked"
    assert "Which way" in waiting.blocked_reason and fix not in waiting.blocked_reason

    await _answer(app, auth_headers, "q-w")
    await _assert_released("task-w", starts)


# ---------------------------------------------------------------------------------------------
# FR-8 in-flight-run-finishes
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_run_in_flight_finishes_and_its_moves_are_refused(app, auth_headers, bind_runner):
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "in_progress")
    builder = await _run("run-dev-w", "Developer", "task-w")
    qa = await _run("run-qa-w", "QA", "task-w", minutes=1)

    filed = await _file(app, qa, "task-w")
    assert filed.status_code == 201, filed.text
    fix = filed.json()["id"]

    async with async_session_factory() as db:
        assert (await db.get(Run, "run-dev-w")).status == "running"  # not ended
    completed = await app.patch(
        f"{AGENT_TASKS}/task-w", json={"status": "completed"}, headers=builder
    )
    assert completed.status_code == 409, completed.text
    assert fix in str(completed.json()["detail"])
    assert (await _read("task-w")).status == "blocked"


# ---------------------------------------------------------------------------------------------
# FR-9 release-is-handed-out, catch-up-conflict-goes-to-builder; FR-6 approved-work-in-branch
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_released_task_is_handed_out_to_its_builder(app, auth_headers, bind_runner):
    await _people(app, auth_headers, bind_runner)
    from .test_loop_lands_its_work import make_loop

    loop_id = await make_loop(app, auth_headers, name="Released")
    await _task("task-w", "under_review", loop_id=loop_id)
    qa = await _run("run-qa-w", "QA", "task-w")
    filed = await _file(app, qa, "task-w")
    assert filed.status_code == 201, filed.text
    await _end("run-qa-w")

    await _approve(app, auth_headers, filed.json()["id"])

    async with async_session_factory() as db:
        decision = await decide_firing(db, await db.get(Loop, loop_id), default_agent="builder")
    picks = [(s.task.id, s.agent, s.is_review) for s in decision.selections]
    assert ("task-w", "Developer", False) in picks, decision


_REAL_ENSURE_TASK_WORKTREE = worktrees.ensure_task_worktree


@pytest.mark.asyncio
@pytest.mark.parametrize("conflicting", [False, True], ids=["clean", "conflict"])
async def test_the_released_turn_has_the_fix_or_names_the_conflict(
    app, auth_headers, bind_runner, tmp_path, monkeypatch, conflicting
):
    """W started and committed f.txt; its checker filed F; F's f.txt was approved. W's next turn,
    with its builder, has F's commit in its branch, or (conflicting) is told to merge it, naming
    F and the commit."""
    from .test_a_conflicting_prerequisite_is_the_authors_to_merge import _commit_in, _turn
    from .test_loop_lands_its_work import commit_on_task_branch, loop_task, make_loop
    from .test_task_integration import drive_to, git, make_repo, set_main_branch

    make_repo(tmp_path)
    await set_main_branch("main")
    await _people(app, auth_headers, bind_runner)
    monkeypatch.setattr(worktrees, "ensure_task_worktree", _REAL_ENSURE_TASK_WORKTREE)
    loop = await make_loop(app, auth_headers, name="FR-9 loop")
    waiting = await loop_task(app, auth_headers, loop, title="W")
    async with async_session_factory() as db:
        row = await db.get(Task, waiting)
        row.assignee, row.builder, row.checker = "builder", "builder", "QA"
        await db.commit()
    started = await drive_to(app, auth_headers, waiting, "in_progress")
    assert started.status_code == 200, started.text
    worktrees.seed_repo_excludes(tmp_path)
    checkout = _REAL_ENSURE_TASK_WORKTREE(tmp_path, waiting, "main")
    _commit_in(checkout, "w.txt" if not conflicting else "f.txt", "W's own work\n")

    qa = await _run("run-qa-fr9", "QA", waiting)
    filed = await _file(app, qa, waiting, builder="Developer")
    assert filed.status_code == 201, filed.text
    fix = filed.json()["id"]
    await _end("run-qa-fr9")
    assert (await _read(waiting)).status == "blocked"

    fix_commit = commit_on_task_branch(tmp_path, fix, "f.txt", "F's fix\n")
    git(tmp_path, "checkout", "-q", "main")
    await _approve(app, auth_headers, fix)
    assert (await _read(waiting)).status == "assigned"
    assert (await _read(waiting)).assignee == "builder"

    response, prompt = await _turn(app, auth_headers, waiting, "carry on with W")
    assert prompt is not None, response.text
    contained = subprocess.run(
        ["git", "-C", str(checkout), "merge-base", "--is-ancestor", fix_commit, "HEAD"],
        capture_output=True,
    )
    if conflicting:
        assert contained.returncode != 0
        assert f"git merge --no-ff {fix_commit}" in prompt
        assert fix in prompt
    else:
        assert contained.returncode == 0, "W's branch lacks F's approved commit"


@pytest.mark.asyncio
async def test_the_operator_dependency_route_is_unchanged(app, auth_headers, bind_runner):
    """The operator's route still adds an edge without stopping started work (non-goal)."""
    await _people(app, auth_headers, bind_runner)
    await _task("task-w", "in_progress")
    await _task("task-f", "pending")
    added = await app.post(
        f"{TASKS}/task-w/dependencies", json={"depends_on": "task-f"}, headers=auth_headers
    )
    assert added.status_code == 201, added.text
    assert (await _read("task-w")).status == "in_progress"
