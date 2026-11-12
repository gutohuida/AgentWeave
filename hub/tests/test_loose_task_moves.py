"""Tasks outside a flow move freely (`tasks-outside-a-flow-move-freely`, FR-1..FR-6).

A loose task -- in no flow's or loop's queue -- is moved by hand: by the operator, and by a run the
operator started. A task in a flow, and a run a flow started, keep the map's edges.
"""

from datetime import datetime, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Run, Task
from hub.task_transition_service import (
    IllegalTransitionError,
    apply_transition,
    history_for,
)
from hub.task_transitions import operator, run_actor

pytestmark = pytest.mark.asyncio


async def _task(session, task_id: str, status: str, **fields) -> Task:
    task = Task(
        id=task_id, project_id="proj-test", title=f"Task {task_id}", status=status, **fields
    )
    session.add(task)
    await session.flush()
    return task


async def _run(session, run_id: str, agent: str, initiator: str) -> Run:
    run = Run(
        id=run_id,
        project_id="proj-test",
        agent=agent,
        status="running",
        initiator=initiator,
        started_at=datetime.now(timezone.utc),
    )
    session.add(run)
    await session.flush()
    return run


async def test_a_task_in_a_flow_keeps_its_moves(app):
    """ac-flow-unchanged"""
    async with async_session_factory() as session:
        task = await _task(session, "task-flow", "completed", loop_id="loop-flow")
        with pytest.raises(IllegalTransitionError):
            await apply_transition(session, task, "approved", operator())
        assert task.status == "completed"


async def test_the_operator_cancels_a_spec_linked_loose_task(app):
    """ac-spec-linked-loose"""
    async with async_session_factory() as session:
        task = await _task(session, "task-spec", "pending", spec_document_id="spdoc-x")
        await apply_transition(session, task, "completed", operator())
        assert task.status == "completed"
        await apply_transition(session, task, "rejected", operator())
        assert task.status == "rejected"


async def test_the_operator_moves_a_loose_task_anywhere_and_each_move_is_recorded(app):
    """ac-any-move"""
    async with async_session_factory() as session:
        task = await _task(session, "task-any", "pending")
        for target in ("completed", "pending", "rejected", "pending"):
            await apply_transition(session, task, target, operator())
            assert task.status == target
        await session.commit()
        moves = await history_for(session, "task-any")
        assert [(m.to_status, m.actor_kind) for m in moves] == [
            ("completed", "operator"),
            ("pending", "operator"),
            ("rejected", "operator"),
            ("pending", "operator"),
        ]


async def test_a_run_the_operator_started_approves_and_a_flow_run_is_refused(app):
    """ac-piloted"""
    async with async_session_factory() as session:
        await _run(session, "run-piloted", "claude", "operator")
        await _run(session, "run-flow", "claude", "autonomous")
        refused = await _task(session, "task-refused", "completed", assignee="dev")
        approved = await _task(session, "task-ok", "completed", assignee="dev")

        with pytest.raises(IllegalTransitionError):
            await apply_transition(session, refused, "approved", run_actor("run-flow", "claude"))
        await apply_transition(session, approved, "approved", run_actor("run-piloted", "claude"))
        assert refused.status == "completed"
        assert approved.status == "approved"


async def test_approving_a_loose_task_by_hand_stages_it_for_landing(app):
    """ac-approve-lands: the approval joins the landing queue, whose checks gate main."""
    from sqlalchemy import select

    from hub.db.models import TaskLanding

    async with async_session_factory() as session:
        task = await _task(session, "task-lands", "completed", assignee="dev")
        await apply_transition(session, task, "approved", operator())
        await session.commit()
        entries = (
            (await session.execute(select(TaskLanding).where(TaskLanding.task_id == task.id)))
            .scalars()
            .all()
        )
        assert entries, "approving must stage the task in the landing queue"


async def test_a_piloted_run_sends_work_back_to_its_builder(app):
    """ac-send-back"""
    async with async_session_factory() as session:
        await _run(session, "run-dev", "D", "operator")
        await _run(session, "run-a", "A", "operator")
        task = await _task(session, "task-back", "in_progress", assignee="D")
        await apply_transition(session, task, "completed", operator())
        await apply_transition(session, task, "revision_needed", run_actor("run-a", "A"))
        assert task.status == "revision_needed"
        assert task.assignee == "D"


async def test_moving_a_task_does_not_change_its_holder(app):
    """ac-mover"""
    async with async_session_factory() as session:
        task = await _task(session, "task-holder", "in_progress", assignee="D")
        await apply_transition(session, task, "completed", operator())
        assert task.assignee == "D"
        await apply_transition(session, task, "revision_needed", operator())
        await apply_transition(session, task, "pending", operator())
        assert task.assignee == "D"


async def _token_run(run_id: str, agent: str, initiator: str) -> dict[str, str]:
    from hub.agent_auth import hash_run_token

    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                initiator=initiator,
                started_at=datetime.now(timezone.utc),
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


async def test_update_task_over_the_agent_route_follows_the_runs_initiator(app):
    """ac-piloted and ac-send-back through /agent-actions/tasks, the route the MCP update_task uses."""
    piloted = await _token_run("run-api-piloted", "A", "operator")
    flow = await _token_run("run-api-flow", "A", "autonomous")
    async with async_session_factory() as session:
        await _task(session, "task-api-ok", "completed", assignee="D")
        await _task(session, "task-api-no", "completed", assignee="D")
        await _task(session, "task-api-back", "completed", assignee="D")
        await session.commit()

    refused = await app.patch(
        "/api/v1/agent-actions/tasks/task-api-no", headers=flow, json={"status": "approved"}
    )
    assert refused.status_code == 409, refused.text
    refused = await app.patch(
        "/api/v1/agent-actions/tasks/task-api-back",
        headers=flow,
        json={"status": "revision_needed", "notes": "redo"},
    )
    assert refused.status_code == 409, refused.text

    ok = await app.patch(
        "/api/v1/agent-actions/tasks/task-api-ok", headers=piloted, json={"status": "approved"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"

    back = await app.patch(
        "/api/v1/agent-actions/tasks/task-api-back",
        headers=piloted,
        json={"status": "revision_needed", "notes": "redo"},
    )
    assert back.status_code == 200, back.text
    assert back.json()["status"] == "revision_needed"
    assert back.json()["assignee"] == "D"
