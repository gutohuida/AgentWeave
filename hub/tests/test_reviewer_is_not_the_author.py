"""Finding F70 — a task may not enter `under_review` still naming its author as the holder.

Found live 2026-08-27 driving a fresh project. `PATCH`ing a task from `completed` to `under_review`
without reassigning it away from the agent that completed it was accepted silently, and the row was
then wedged **permanently**: `scheduler`'s `WITH_REVIEWER_LOOP_TASK_STATUSES` branch reads
`under_review` as *a reviewer already holds this*, so nobody is ever offered the task's exits — and
because `_agents_that_are_free` counts that assignee as holding active work, the author became
unrecruitable as a reviewer for every **other** task in the project too. No error, no event, and a
project's review capacity silently down by one agent.

The fix is in two halves and both are tested here, because either alone leaves a real gap:

* `_guard_reviewer_is_not_the_author` refuses the edge, so no new wedged row can be created;
* the firing walk routes an *already* wedged row back through the reviewer ladder, so the rows that
  predate the guard — or that were written straight into the status — recover instead of staying
  stuck forever behind a guard that arrived too late to help them.

`test_a_flow_staffing_its_own_review_is_not_refused` is the regression the first half needs most.
`_enter_selected_task` used to transition *before* writing the assignee, which means the new guard
read the author and refused the flow's own correct staffing — the fix would have broken every
review the product staffs, and passed a test suite that only ever exercised the operator's door.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, InboundQueueEntry, Loop, Task
from hub.scheduler import JobScheduler
from hub.task_transition_service import (
    ActorNotPermittedError,
    apply_transition,
)
from hub.task_transitions import operator, run_actor

pytestmark = pytest.mark.asyncio

AUTHOR = "builder"
REVIEWER = "critic"


async def _completed_task(session, task_id: str, *, by: str | None, assignee: str | None) -> Task:
    """A task at `completed`, attributed to *by* through the machine rather than written directly.

    Attribution has to be real: `_agent_that_completed` reads `TaskTransition`, so a task
    constructed straight at `completed` has no author and the guard would permit it for a reason
    that has nothing to do with what is being tested. `by=None` is that case, on purpose.
    """
    task = Task(
        id=task_id,
        project_id="proj-test",
        title=f"Task {task_id}",
        status="in_progress" if by else "completed",
        assignee=assignee,
    )
    session.add(task)
    await session.flush()
    if by:
        await apply_transition(session, task, "completed", run_actor(f"run-{by}-authored", by))
    await session.commit()
    return task


# ---------------------------------------------------------------------------
# The guard: the edge that creates a wedged row
# ---------------------------------------------------------------------------


async def test_entering_review_still_assigned_to_the_author_is_refused(app):
    """F70 exactly: the move the operator made live, now refused."""
    async with async_session_factory() as session:
        task = await _completed_task(session, "task-f70", by=AUTHOR, assignee=AUTHOR)

        with pytest.raises(ActorNotPermittedError) as refusal:
            await apply_transition(session, task, "under_review", operator())

        assert task.status == "completed", "refused, not half-applied"
        message = str(refusal.value)
        assert AUTHOR in message
        assert "review it yourself" in message, "the refusal names the remedy, not just the rule"


async def test_the_refusal_binds_an_agent_run_too(app):
    """Not an operator-only rule. The state it prevents is false whoever writes it."""
    async with async_session_factory() as session:
        task = await _completed_task(session, "task-f70-run", by=AUTHOR, assignee=AUTHOR)

        with pytest.raises(ActorNotPermittedError):
            await apply_transition(
                session, task, "under_review", run_actor("run-later", "someone-else")
            )


async def test_entering_review_assigned_to_a_different_agent_is_allowed(app):
    """The ordinary case, and the one the flow itself produces."""
    async with async_session_factory() as session:
        task = await _completed_task(session, "task-f70-ok", by=AUTHOR, assignee=REVIEWER)

        await apply_transition(session, task, "under_review", operator())
        await session.commit()

        assert task.status == "under_review"


async def test_entering_review_with_no_assignee_is_allowed(app):
    """The operator taking the task off the agents' board to read it themselves.

    Nobody is claimed to hold it, so nothing is false and nothing wedges — the scheduler records an
    in-flight holder only `if task.assignee`. Refusing here would make a single-operator project
    unable to review its own work, which is the same failure `_guard_author_is_not_reviewer`
    exempts the operator to avoid.
    """
    async with async_session_factory() as session:
        task = await _completed_task(session, "task-f70-none", by=AUTHOR, assignee=None)

        await apply_transition(session, task, "under_review", operator())
        await session.commit()

        assert task.status == "under_review"


async def test_an_unattributable_completed_task_may_still_enter_review(app):
    """Refuse to *offer*, permit to *act* — the asymmetry `task_is_claimable_by` documents.

    A task completed before the transition table existed has no recorded completer. Blocking every
    move that cannot be attributed would strand legitimate work over a missing history row.
    """
    async with async_session_factory() as session:
        task = await _completed_task(session, "task-f70-anon", by=None, assignee=AUTHOR)

        await apply_transition(session, task, "under_review", operator())
        await session.commit()

        assert task.status == "under_review"


# ---------------------------------------------------------------------------
# The flow's own path must survive its own guard
# ---------------------------------------------------------------------------


async def _flow(db, *, task_id, agent=AUTHOR):
    job = AIJob(
        id="job-f70",
        project_id="proj-test",
        name="Flow f70",
        agent=agent,
        message="keep the ledger balanced",
        cron="*/5 * * * *",
        session_mode="new",
        enabled=True,
    )
    db.add(job)
    await db.commit()
    loop = Loop(id="loop-f70", project_id="proj-test", job_id=job.id, purpose="flow f70")
    db.add(loop)
    await db.commit()
    task = await db.get(Task, task_id)
    task.loop_id = loop.id
    await db.commit()
    return job


async def _fire(job_id):
    scheduler = JobScheduler()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        async with async_session_factory() as db:
            await scheduler._fire_job_internal(
                await db.get(AIJob, job_id), trigger="scheduled", session=db
            )


async def _queued_for(agent):
    async with async_session_factory() as db:
        return (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .first()
        )


async def test_a_flow_staffing_its_own_review_is_not_refused(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The regression the guard needs most.

    `_enter_selected_task` transitions to `under_review` and writes the reviewer into `assignee`.
    In the original order the transition ran first, so the guard saw the *author* still sitting in
    `assignee` and refused — breaking every review the flow staffs, while the guard's own unit
    tests (which come in through the operator's door with the assignee already set) all passed.
    """
    from .test_agent_trigger import _init_repo
    from .test_review_turn import _author_commit, _reviewable_task, _roster

    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)

    async with async_session_factory() as db:
        task = await db.get(Task, "task-1")
        task.status = "in_progress"
        task.assignee = AUTHOR
        await db.commit()
        await apply_transition(db, task, "completed", run_actor("run-authored", AUTHOR))
        await db.commit()
        job = await _flow(db, task_id="task-1")

    await _fire(job.id)

    async with async_session_factory() as db:
        task = await db.get(Task, "task-1")
        assert task.status == "under_review", "the flow's own review was refused by its own guard"
        assert task.assignee == REVIEWER

    assert (await _queued_for(REVIEWER)) is not None
    assert (await _queued_for(AUTHOR)) is None


# ---------------------------------------------------------------------------
# Recovery: a row wedged before the guard existed
# ---------------------------------------------------------------------------


async def test_a_wedged_review_is_restaffed_to_a_real_reviewer(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    """The other half. A guard added today does nothing for a row wedged yesterday.

    The task is put into the exact state F70 produced — `under_review`, assignee still the author —
    by writing the status directly, which is the one way to reach it now that the guard refuses the
    edge. The firing must not read it as staffed, and must not fall through to the ordinary-work
    arm either: that arm would find the author in `assignee` and re-staff the review as
    implementation, which is F10 arriving by a new route.
    """
    from .test_agent_trigger import _init_repo
    from .test_review_turn import _author_commit, _reviewable_task, _roster

    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    await _reviewable_task(commit=sha)

    async with async_session_factory() as db:
        task = await db.get(Task, "task-1")
        task.status = "in_progress"
        task.assignee = AUTHOR
        await db.commit()
        await apply_transition(db, task, "completed", run_actor("run-authored", AUTHOR))
        await db.commit()
        # The wedge, written past the machine because the machine now refuses to create it.
        task.status = "under_review"
        task.assignee = AUTHOR
        await db.commit()
        job = await _flow(db, task_id="task-1")

    await _fire(job.id)

    async with async_session_factory() as db:
        task = await db.get(Task, "task-1")
        assert (
            task.assignee == REVIEWER
        ), "the wedged row must be restaffed to a real reviewer, not left holding its own author"
        assert task.status == "under_review", "recovery reassigns; it travels no edge"

    entry = await _queued_for(REVIEWER)
    assert entry is not None, "a review turn is actually dispatched"
    assert entry.review_task_id == "task-1", (
        "and it is a *review* turn -- without this the reviewer is fired into its own worktree, "
        "where the author's unmerged work does not exist (F10)"
    )
    assert (await _queued_for(AUTHOR)) is None, "and never back to the author"


async def test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted(
    app, auth_headers
):
    """The remedy the refusal names has to work in one call, or the guard is a papercut.

    `update_task_for_actor` applied `status` before `assignee`, so a PATCH carrying both was refused
    on the strength of an assignee that same request was about to replace — and the operator had to
    discover that two calls were needed. The fields are now applied in the order the guard reads
    them, which is the same ordering fix `_enter_selected_task` needed.
    """
    async with async_session_factory() as session:
        await _completed_task(session, "task-f70-patch", by=AUTHOR, assignee=AUTHOR)

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f70-patch",
        json={"status": "under_review", "assignee": REVIEWER},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "under_review"
    assert body["assignee"] == REVIEWER


async def test_sending_to_review_with_no_reassignment_is_refused_over_http(app, auth_headers):
    """And the refusal reaches the operator as a 403 with the remedy in it, not a 500."""
    async with async_session_factory() as session:
        await _completed_task(session, "task-f70-http", by=AUTHOR, assignee=AUTHOR)

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f70-http",
        json={"status": "under_review"},
        headers=auth_headers,
    )

    assert response.status_code == 403, response.text
    assert "review it yourself" in response.text


async def test_a_refused_review_move_does_not_leave_the_assignee_changed(app, auth_headers):
    """The half-applied-update guarantee, which now rests on rollback rather than on not writing.

    `update_task_for_actor` writes the assignee before the transition, so a refused PATCH *does*
    stage a change. It must never survive: the session is closed without a commit and the
    transaction rolls back. Asserted rather than assumed, because the comment that used to say
    "nothing has been mutated at that point" was load-bearing and is no longer literally true.
    """
    async with async_session_factory() as session:
        await _completed_task(session, "task-f70-rollback", by=AUTHOR, assignee=AUTHOR)

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f70-rollback",
        # A reviewer that is still the author: the assignee write happens, the transition refuses.
        json={"status": "under_review", "assignee": AUTHOR, "priority": "high"},
        headers=auth_headers,
    )
    assert response.status_code == 403, response.text

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f70-rollback")
        assert task.status == "completed"
        assert task.assignee == AUTHOR
        assert task.priority != "high", "no field of a refused update survives, not just the status"


# ---------------------------------------------------------------------------
# Finding F78 — the refusal's *other* remedy, which had no test and did not work
# ---------------------------------------------------------------------------


async def test_clearing_the_assignee_lets_the_operator_review_it_themselves(app, auth_headers):
    """F78, found live 2026-08-27 driving `proj-46b602c1f3cb` to integration.

    `_guard_reviewer_is_not_the_author` names two remedies: *"Assign a different reviewer, or clear
    the assignee to review it yourself."* Only the first had a test, and only the first worked.
    `TaskUpdate.assignee` is `Optional[str] = None`, and `update_task_for_actor` read it as
    ``if body.assignee is not None`` — so `{"assignee": null}` was indistinguishable from the field
    being omitted. The operator followed the refusal's own instruction, got `200 OK` back with the
    author still in the response body, and was refused again by the same guard.

    Silence is what makes it worse than a papercut: a refusal would have sent the operator to the
    other remedy. A success that changes nothing sends them nowhere.

    `escalation_agent` in the same schema already solves exactly this with `model_fields_set`, and
    says so in a comment — *"clearing an escalation agent is a thing the operator must be able to
    do"*. The pattern was in the file; it just had not been applied to the field a hard refusal
    depends on.
    """
    async with async_session_factory() as session:
        await _completed_task(session, "task-f78-clear", by=AUTHOR, assignee=AUTHOR)

    cleared = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f78-clear",
        json={"assignee": None},
        headers=auth_headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert (
        cleared.json()["assignee"] is None
    ), "the response must not report the assignee the request just cleared"

    async with async_session_factory() as session:
        task = await session.get(Task, "task-f78-clear")
        assert task.assignee is None, "cleared to NULL, not to a second falsy spelling"

    reviewed = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f78-clear",
        json={"status": "under_review"},
        headers=auth_headers,
    )
    assert reviewed.status_code == 200, (
        "the remedy the guard names must actually reach review: " + reviewed.text
    )
    assert reviewed.json()["status"] == "under_review"


async def test_clearing_and_sending_to_review_in_one_patch_is_accepted(app, auth_headers):
    """And in one call, for the same reason the reassignment remedy has to work in one call.

    The assignee is written before the transition (F70's ordering fix), so the guard reads the
    cleared value rather than the one the request is replacing.
    """
    async with async_session_factory() as session:
        await _completed_task(session, "task-f78-onecall", by=AUTHOR, assignee=AUTHOR)

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f78-onecall",
        json={"status": "under_review", "assignee": None},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "under_review"
    assert body["assignee"] is None


async def test_an_omitted_assignee_still_leaves_the_holder_alone(app, auth_headers):
    """The half of the old behaviour that was correct, and that the fix must not trade away.

    `null` now means *clear it*, so "unset" has to mean something different — a PATCH about the
    priority cannot silently unassign the agent holding the task. This is the mutation check for
    the fix: switch it back to `if body.assignee is not None` and F78's two tests fail; switch it
    to an unconditional write and this one does.
    """
    async with async_session_factory() as session:
        await _completed_task(session, "task-f78-untouched", by=AUTHOR, assignee=AUTHOR)

    response = await app.patch(
        "/api/v1/projects/proj-test/tasks/task-f78-untouched",
        json={"priority": "high"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["assignee"] == AUTHOR
    async with async_session_factory() as session:
        task = await session.get(Task, "task-f78-untouched")
        assert task.assignee == AUTHOR
        assert task.priority == "high"
