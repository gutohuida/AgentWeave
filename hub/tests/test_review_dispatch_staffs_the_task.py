"""A review dispatched by hand staffs the task, exactly as a flow-dispatched one does (F76).

Measured live 2026-08-27. `POST /agent/trigger {"review_task_id": …}` provisioned the reviewer's
detached checkout and staffed nothing, so the reviewer did careful work and then met four correct
refusals with no exit between them: it could not move the task (still assigned to its author),
could not record evidence, and could not report. The flow path has staffed since F45 —
`enter_selected_task` writes the assignee and applies `completed -> under_review`, in that order,
which is F70's fix. One operation, two dispatch paths, and only one left the reviewer able to
finish.

The refusal tests below need no git repository, and that is not an accident of how they are
written: design D10 puts every refusal *before* `prepare_review_turn`, because `run-task-binding`
requires that a request which is going to be refused leaves no workspace behind. A refusal that
needed a checkout to exist first would be the breach.
"""

import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import func, select

from hub.api.v1 import agent_trigger
from hub.api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly
from hub.conversations import new_conversation
from hub.db.engine import async_session_factory
from hub.db.models import (
    EvidenceFootprint,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecRequirement,
    Task,
    TaskTransition,
)
from hub.scheduler import enter_selected_task
from hub.task_transition_service import apply_transition
from hub.task_transitions import run_actor

pytestmark = pytest.mark.asyncio

AUTHOR = "rd-author"
REVIEWER = "rd-reviewer"
OTHER = "rd-other"
NOW = datetime.now(timezone.utc)


def _init_repo(path):
    """The project root as a real, disposable git repository.

    `prepare_review_turn` refuses outright when the root is not one, and the success path has to
    get past that to prove anything. The checkout itself is still conftest's stub, so no
    `git worktree` command runs and the evidence's SHA need not exist.
    """
    for args in (
        ("init", "-q", "-b", "main"),
        ("config", "user.email", "test@example.com"),
        ("config", "user.name", "test"),
    ):
        subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, timeout=30)
    (path / "seed.txt").write_text("base")
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, timeout=30)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=path, capture_output=True, timeout=30)
    return path


async def _snapshot(db, task_id):
    task = await _fresh(db, task_id)
    return task.status, task.assignee


async def _roster(app, auth_headers, bind_runner, *names):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"} for name in names}}},
        headers=auth_headers,
    )
    for name in names:
        await bind_runner(name, cli="claude")


async def _task_completed_by_author(db, *, suffix, status="completed"):
    """A task walked to *status* by AUTHOR, never constructed there.

    `agent_that_completed` reads the transition history, so a task assembled directly at
    `completed` has no recorded author and the guard this file exercises cannot fire — the test
    would pass while proving nothing.
    """
    task = Task(
        id=f"task-rd-{suffix}", project_id="proj-test", title=f"work {suffix}", status="pending"
    )
    db.add(task)
    await db.commit()
    actor = run_actor(run_id=f"run-{AUTHOR}-{task.id}", agent=AUTHOR)
    walk = {
        "assigned": ("assigned",),
        "in_progress": ("assigned", "in_progress"),
        "completed": ("assigned", "in_progress", "completed"),
    }[status]
    for step in walk:
        await apply_transition(db, task, step, actor)
    if status != "completed":
        # `apply_transition` records history and never touches `assignee`; a task being *worked*
        # is held by the agent working it, and that is the state D8 must not disturb.
        task.assignee = AUTHOR
    await db.commit()
    return task


async def _evidence_naming_a_commit(db, task_id, *, suffix):
    db.add(
        SpecDocument(
            id=f"doc-rd-{suffix}",
            project_id="proj-test",
            path=f"spec/rd-{suffix}.html",
            title="Ledger",
            phase="current",
            kind="capability",
        )
    )
    db.add(
        SpecRequirement(
            id=f"req-rd-{suffix}",
            project_id="proj-test",
            document_id=f"doc-rd-{suffix}",
            identifier="FR-1",
            key="fr-1",
            digest="d" * 64,
        )
    )
    db.add(
        RequirementEvidence(
            id=f"ev-rd-{suffix}",
            project_id="proj-test",
            requirement_id=f"req-rd-{suffix}",
            task_id=task_id,
            digest="d" * 64,
            kind="commit",
            actor_kind="agent",
            actor=AUTHOR,
            summary="all green",
            produced_at=NOW - timedelta(minutes=5),
        )
    )
    db.add(
        EvidenceFootprint(
            id=f"fp-rd-{suffix}",
            project_id="proj-test",
            evidence_id=f"ev-rd-{suffix}",
            kind="git",
            commit_sha="a" * 40,
            branch="agentweave/rd-author",
            observed_at=NOW - timedelta(minutes=5),
        )
    )
    await db.commit()


async def _dispatch_review(db, *, reviewer, task_id, suffix):
    conversation = new_conversation(project_id="proj-test", agent=reviewer, origin="operator")
    db.add(conversation)
    await db.commit()
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        return await trigger_agent_directly(
            project_id="proj-test",
            agent=reviewer,
            message=f"review {task_id}",
            conversation_id=conversation.id,
            session=db,
            review_task_id=task_id,
        )


async def _fresh(db, task_id):
    return (await db.execute(select(Task).where(Task.id == task_id))).scalars().one()


async def _transition_count(db, task_id):
    return await db.scalar(
        select(func.count()).select_from(TaskTransition).where(TaskTransition.task_id == task_id)
    )


# ---------------------------------------------------------------------------
# The finding
# ---------------------------------------------------------------------------


async def test_a_review_started_by_hand_leaves_the_reviewer_holding_the_task(
    app, auth_headers, bind_runner, tmp_path
):
    """F76 itself. Before this change the task stayed `completed`, still assigned to its author,
    and the reviewer's every exit was refused."""
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="finding")
        await _evidence_naming_a_commit(db, task.id, suffix="finding")
        await _dispatch_review(db, reviewer=REVIEWER, task_id=task.id, suffix="finding")

    async with async_session_factory() as db:
        fresh = await _fresh(db, task.id)
        assert fresh.status == "under_review"
        assert fresh.assignee == REVIEWER


async def test_dispatching_an_already_staffed_review_records_no_second_transition(
    app, auth_headers, bind_runner, tmp_path
):
    """Design D4, and the assertion that makes the idempotency claim true rather than assumed.

    A flow-dispatched review arrives here already staffed. A second `completed -> under_review`
    would be an illegal edge, and an extra transition row on every flow review would corrupt the
    append-only history `task-lifecycle-governance` requires — so it is the *row count* that is
    asserted, not merely the status.
    """
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="staffed")
        await _evidence_naming_a_commit(db, task.id, suffix="staffed")
        # Exactly what the flow does before it dispatches.
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()
        before = await _transition_count(db, task.id)
        await _dispatch_review(db, reviewer=REVIEWER, task_id=task.id, suffix="staffed")

    async with async_session_factory() as db:
        fresh = await _fresh(db, task.id)
        assert fresh.status == "under_review"
        assert fresh.assignee == REVIEWER
        assert await _transition_count(db, task.id) == before


# ---------------------------------------------------------------------------
# The refusals, all of which precede the checkout (D10)
# ---------------------------------------------------------------------------


async def test_naming_the_author_as_its_own_reviewer_is_refused_before_the_turn(
    app, auth_headers, bind_runner
):
    """Design D5. The refusal is the guard's own sentence, so the operator meets the same words
    here as they would attempting the transition directly."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="author")
        await _evidence_naming_a_commit(db, task.id, suffix="author")
        before = await _snapshot(db, task.id)
        with pytest.raises(TriggerAgentError) as excinfo:
            await _dispatch_review(db, reviewer=AUTHOR, task_id=task.id, suffix="author")

    assert excinfo.value.status_code == 403
    assert "the agent recorded as completing it" in excinfo.value.detail

    async with async_session_factory() as db:
        # The staffing writes the assignee before the guard reads it, so what must be proven is
        # that the staged write did not survive -- not merely that the status is still `completed`.
        assert await _snapshot(db, task.id) == before
        assert (await db.execute(select(Run.id))).first() is None


async def test_a_task_that_is_not_awaiting_review_is_refused_and_keeps_its_holder(
    app, auth_headers, bind_runner
):
    """Design D8, found in round 2 — and without the guard this does not merely fail.

    `enter_selected_task` writes the assignee *before* its status branch, and that branch has no
    `else`. So staffing an `in_progress` task would take it from the agent working it and travel no
    transition at all. Reachable from this path and only this path: the flow's ladder selects only
    reviewable tasks, while the operator names an id directly and the route's other check asks
    whether evidence names a commit — which is true here, deliberately, because that is exactly why
    it is not a sufficient guard.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="live", status="in_progress")
        await _evidence_naming_a_commit(db, task.id, suffix="live")
        with pytest.raises(TriggerAgentError) as excinfo:
            await _dispatch_review(db, reviewer=REVIEWER, task_id=task.id, suffix="live")

    assert excinfo.value.status_code == 409
    assert "in_progress" in excinfo.value.detail

    async with async_session_factory() as db:
        fresh = await _fresh(db, task.id)
        assert fresh.status == "in_progress"
        assert fresh.assignee == AUTHOR, "the agent working it must keep it"
        assert (await db.execute(select(Run.id))).first() is None


async def test_a_review_already_held_by_another_reviewer_is_not_silently_taken(
    app, auth_headers, bind_runner
):
    """Design D9. The `under_review` branch is idempotent in status but not in assignee, so this
    would replace the holder and travel no transition — a handover the task's own history could
    not explain."""
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, OTHER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="held")
        await _evidence_naming_a_commit(db, task.id, suffix="held")
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()
        with pytest.raises(TriggerAgentError) as excinfo:
            await _dispatch_review(db, reviewer=OTHER, task_id=task.id, suffix="held")

    assert excinfo.value.status_code == 409
    assert REVIEWER in excinfo.value.detail

    async with async_session_factory() as db:
        fresh = await _fresh(db, task.id)
        assert fresh.assignee == REVIEWER
        assert fresh.status == "under_review"


@pytest.mark.parametrize(
    "case",
    ["author", "not_awaiting_review", "held_by_another"],
)
async def test_a_refused_review_never_reaches_the_provisioning(
    app, auth_headers, bind_runner, case
):
    """Design D10, and the assertion that actually pins the ordering.

    `run-task-binding` requires that a request which is going to be refused leaves no workspace
    behind, so every refusal must be raised *before* `prepare_review_turn`. Nothing else in this
    file discriminates that: conftest stubs the checkout to a no-op returning the repo root, so
    there is no artefact on disk to look for, and moving the staffing below the provisioning leaves
    every other test in this file passing.

    So the provisioning itself is the witness. If it was called at all, the checkout would have
    been created for a request that was refused.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, OTHER)
    async with async_session_factory() as db:
        if case == "not_awaiting_review":
            task = await _task_completed_by_author(db, suffix=case, status="in_progress")
            reviewer = REVIEWER
        else:
            task = await _task_completed_by_author(db, suffix=case)
            reviewer = AUTHOR if case == "author" else OTHER
        await _evidence_naming_a_commit(db, task.id, suffix=case)
        if case == "held_by_another":
            await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
            await db.commit()

        with patch.object(
            agent_trigger.review_turn, "prepare_review_turn", autospec=True
        ) as provisioning:
            with pytest.raises(TriggerAgentError):
                await _dispatch_review(db, reviewer=reviewer, task_id=task.id, suffix=case)

    provisioning.assert_not_called()


async def test_a_review_refused_by_the_provisioning_leaves_the_task_unstaffed(
    app, auth_headers, bind_runner
):
    """Design D10's other half. The staffing is staged before the checkout is provisioned, so a
    refusal *from* that provisioning must abandon it rather than leave the task in review for a
    turn that never happened — which is the F70 wedge reached by a new route, and is precisely how
    `test_a_review_needs_something_to_review.py`'s live finding presented.

    Here the task has no evidence at all, so `prepare_review_turn` refuses after the staffing has
    already been staged. Nothing may persist.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="norepo")
        before = await _snapshot(db, task.id)
        with pytest.raises(TriggerAgentError) as excinfo:
            await _dispatch_review(db, reviewer=REVIEWER, task_id=task.id, suffix="norepo")

    assert excinfo.value.status_code == 409

    async with async_session_factory() as db:
        assert (
            await _snapshot(db, task.id) == before
        ), "staged staffing must not survive a refusal raised after it"
        assert (await db.execute(select(Run.id))).first() is None


# ---------------------------------------------------------------------------
# What the operator actually sees over HTTP (D11, found by driving it)
# ---------------------------------------------------------------------------


async def _post_review(app, auth_headers, agent, task_id):
    return await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": agent, "message": f"review {task_id}", "review_task_id": task_id},
        headers=auth_headers,
    )


async def test_the_operator_gets_a_refusal_not_an_acknowledgement(app, auth_headers, bind_runner):
    """Driven live 2026-08-28, and the drive is the only reason this is known.

    The dispatch-time guards are correct and leave the task untouched, but `turn_scheduler` catches
    `TriggerAgentError` and records it as the entry's `waiting_reason` — so the route answered
    `200 {"success": true, "status": "queued"}` with the refusal's own sentence in a field named
    for something else. An operator who asked for a review that can never happen was told it
    succeeded. Every assertion here is on the *status code*, because the sentence was already
    right and the sentence was not the problem.
    """
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, OTHER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="http-author")
        await _evidence_naming_a_commit(db, task.id, suffix="http-author")

    response = await _post_review(app, auth_headers, AUTHOR, task.id)
    assert response.status_code == 403, response.json()
    assert "recorded as completing it" in response.json()["detail"]

    async with async_session_factory() as db:
        assert await _snapshot(db, task.id) == ("completed", None)


async def test_the_operator_is_refused_at_once_for_a_task_not_awaiting_review(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="http-live", status="in_progress")
        await _evidence_naming_a_commit(db, task.id, suffix="http-live")

    response = await _post_review(app, auth_headers, REVIEWER, task.id)
    assert response.status_code == 409, response.json()
    assert "in_progress" in response.json()["detail"]

    async with async_session_factory() as db:
        assert await _snapshot(db, task.id) == ("in_progress", AUTHOR)


async def test_the_operator_is_refused_at_once_for_a_review_someone_else_holds(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER, OTHER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="http-held")
        await _evidence_naming_a_commit(db, task.id, suffix="http-held")
        await enter_selected_task(db, task, agent=REVIEWER, is_review=True)
        await db.commit()

    response = await _post_review(app, auth_headers, OTHER, task.id)
    assert response.status_code == 409, response.json()
    assert REVIEWER in response.json()["detail"]

    async with async_session_factory() as db:
        assert await _snapshot(db, task.id) == ("under_review", REVIEWER)


async def test_a_dispatchable_review_is_not_refused_by_the_route(
    app, auth_headers, bind_runner, tmp_path
):
    """The guard must refuse the three cases and nothing else — a route check that refused a
    legitimate review would close the path this change exists to open."""
    _init_repo(tmp_path)
    await _roster(app, auth_headers, bind_runner, AUTHOR, REVIEWER)
    async with async_session_factory() as db:
        task = await _task_completed_by_author(db, suffix="http-ok")
        await _evidence_naming_a_commit(db, task.id, suffix="http-ok")

    response = await _post_review(app, auth_headers, REVIEWER, task.id)
    assert response.status_code == 200, response.json()

    async with async_session_factory() as db:
        assert await _snapshot(db, task.id) == ("under_review", REVIEWER)
