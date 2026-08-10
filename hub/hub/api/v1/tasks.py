"""Task endpoints — POST/GET/GET{id}/PATCH."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent_status import effective_heartbeat_status
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AgentHeartbeat, RunDivergence, Task
from ...schemas.tasks import TaskCreate, TaskResponse, TaskUpdate
from ...sse import sse_manager
from ...task_transition_service import apply_transition, guard_entry_status
from ...task_transitions import ACTOR_OPERATOR, Actor, allowed_map_for, operator
from ...utils import persist_event, short_id

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _task_response(
    task: Task,
    heartbeat: Optional[AgentHeartbeat] = None,
    *,
    has_open_divergence: bool = False,
) -> TaskResponse:
    response = TaskResponse.model_validate(task)
    effective_status, effective_message = effective_heartbeat_status(heartbeat)
    response.assignee_status = effective_status if task.assignee else None
    response.assignee_status_msg = effective_message
    response.assignee_last_seen = heartbeat.timestamp if heartbeat else None
    response.has_open_divergence = has_open_divergence
    return response


async def _tasks_with_open_divergence(
    session: AsyncSession, project_id: str, task_ids: set[str]
) -> set[str]:
    """Which of `task_ids` currently have a run that dropped them and nothing since.

    Computed rather than stored. The durable record is the divergence row; a flag on the task would
    be a second copy of the same fact, and the first thing it would do is disagree with it.
    """
    if not task_ids:
        return set()
    result = await session.execute(
        select(RunDivergence.task_id)
        .where(RunDivergence.project_id == project_id)
        .where(RunDivergence.task_id.in_(task_ids))
        .where(RunDivergence.resolved_at.is_(None))
        .distinct()
    )
    return {row[0] for row in result}


async def _latest_heartbeats_by_agent(
    session: AsyncSession,
    project_id: str,
    agent_names: set[str],
) -> dict[str, AgentHeartbeat]:
    if not agent_names:
        return {}

    result = await session.execute(
        select(AgentHeartbeat)
        .where(
            AgentHeartbeat.project_id == project_id,
            AgentHeartbeat.agent.in_(agent_names),
        )
        .order_by(AgentHeartbeat.agent, AgentHeartbeat.timestamp.desc())
    )
    heartbeats: dict[str, AgentHeartbeat] = {}
    for heartbeat in result.scalars().all():
        heartbeats.setdefault(heartbeat.agent, heartbeat)
    return heartbeats


async def create_task_for_actor(
    body: TaskCreate,
    *,
    project_id: str,
    assigner: Optional[str],
    created_by_run_id: Optional[str],
    session: AsyncSession,
) -> TaskResponse:
    # Honor a client-supplied id when present so the MCP `create_task` tool
    # can return the same id the Hub stored. Falls back to a fresh short id
    # for clients that don't supply one (e.g. direct API users).
    # A lifecycle that can be entered anywhere is not a lifecycle (design D10). Without this, a
    # caller creates a task already `approved` and never transitions at all, so no rule about
    # transitions can reach it. This is the single `Task(` construction site, so one guard covers
    # both the operator route and the agent plane.
    guard_entry_status(body.status)
    task_id = body.id or f"task-{short_id()}"
    task = Task(
        id=task_id,
        project_id=project_id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee=body.assignee,
        assigner=assigner,
        requirements=body.requirements,
        acceptance_criteria=body.acceptance_criteria,
        deliverables=body.deliverables,
        notes=body.notes,
        created_by_run_id=created_by_run_id,
    )
    session.add(task)
    try:
        await session.commit()
    except IntegrityError as e:
        # Another writer beat us to this id (extremely unlikely with an 8-hex
        # suffix, but possible across distributed CLI + Hub). Reject with 409
        # so the caller can decide whether to retry with a fresh id.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task id '{task_id}' already exists",
        ) from e
    await sse_manager.broadcast(project_id, "task_created", {"id": task.id, "title": body.title})
    await persist_event(
        session,
        project_id,
        "task_created",
        {"id": task.id, "title": body.title},
        agent=body.assignee,
    )
    await session.refresh(task)
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee} if task.assignee else set(),
    )
    return _task_response(task, heartbeats.get(task.assignee) if task.assignee else None)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await create_task_for_actor(
        body,
        project_id=project_id,
        assigner=body.assigner,
        created_by_run_id=None,
        session=session,
    )


@router.get("", response_model=List[TaskResponse])
async def list_tasks(
    agent: Optional[str] = Query(None),
    task_status: Optional[str] = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    q = select(Task).where(Task.project_id == project_id)
    if agent:
        q = q.where(Task.assignee == agent)
    if task_status:
        q = q.where(Task.status == task_status)
    q = q.order_by(Task.created_at).offset(offset).limit(limit)
    result = await session.execute(q)
    tasks = result.scalars().all()
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee for task in tasks if task.assignee},
    )
    diverged = await _tasks_with_open_divergence(session, project_id, {task.id for task in tasks})
    return [
        _task_response(
            task,
            heartbeats.get(task.assignee) if task.assignee else None,
            has_open_divergence=task.id in diverged,
        )
        for task in tasks
    ]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee} if task.assignee else set(),
    )
    diverged = await _tasks_with_open_divergence(session, project_id, {task.id})
    return _task_response(
        task,
        heartbeats.get(task.assignee) if task.assignee else None,
        has_open_divergence=task.id in diverged,
    )


async def update_task_for_actor(
    task_id: str,
    body: TaskUpdate,
    *,
    project_id: str,
    actor: Actor,
    session: AsyncSession,
) -> TaskResponse:
    """The single choke point both routes share, and therefore where the machine lives.

    `actor` is explicit rather than an `Optional[str]` run id whose absence meant "operator"
    (design D2): those are different claims, and only one of them is an authorisation.
    """
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.status is not None:
        # Raises TransitionRefusedError — an illegal move, or one this actor may not make — which the
        # exception handler turns into 409/403. Nothing has been mutated at that point, so the
        # refusal cannot leave a half-applied update behind.
        await apply_transition(session, task, body.status, actor)
    if body.priority is not None:
        task.priority = body.priority
    if body.assignee is not None:
        task.assignee = body.assignee
    if body.description is not None:
        task.description = body.description
    if body.notes is not None:
        task.notes = body.notes
    if body.divergence_policy is not None or "escalation_agent" in body.model_fields_set:
        # The operator's, not the agent's. An agent able to set its own task's policy to `surface`
        # could disarm the check that exists to catch it dropping the work — the same reason no
        # agent-facing operation binds a run (`2026-08-10-run-task-binding`, design D2).
        if not actor.is_operator:
            raise HTTPException(
                status_code=403,
                detail=(
                    "How a dropped task is answered is the operator's setting. An agent cannot "
                    "change its own task's divergence policy or escalation agent."
                ),
            )
        if body.divergence_policy is not None:
            task.divergence_policy = body.divergence_policy
        if "escalation_agent" in body.model_fields_set:
            task.escalation_agent = body.escalation_agent
    task.updated = datetime.now(timezone.utc)
    # Kept as the materialised latest writer (D4 of the proposal's impact notes). The rules read the
    # append-only history instead; this stays for existing consumers and is not what governs.
    task.updated_by_run_id = actor.run_id
    await session.commit()
    await session.refresh(task)
    await sse_manager.broadcast(project_id, "task_updated", {"id": task_id, "status": task.status})
    await persist_event(
        session,
        project_id,
        "task_updated",
        {"id": task_id, "status": task.status},
        agent=task.assignee,
    )
    await session.refresh(task)
    heartbeats = await _latest_heartbeats_by_agent(
        session,
        project_id,
        {task.assignee} if task.assignee else set(),
    )
    diverged = await _tasks_with_open_divergence(session, project_id, {task.id})
    return _task_response(
        task,
        heartbeats.get(task.assignee) if task.assignee else None,
        has_open_divergence=task.id in diverged,
    )


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    return await update_task_for_actor(
        task_id,
        body,
        project_id=project_id,
        actor=operator(),
        session=session,
    )


@router.get("/transitions/allowed")
async def allowed_transitions(
    project: Tuple[str, str] = Depends(get_project),
):
    """The operator's own view of the transition map (design D13).

    Served from the same declaration the service enforces, so the control cannot offer a move that
    is then refused, and the client never holds a second copy of the map. One fetch per session
    rather than one per card — a board of forty tasks in the same status has one answer, not forty.
    """
    return {"actor_kind": ACTOR_OPERATOR, "transitions": allowed_map_for(ACTOR_OPERATOR)}


@router.get("/divergences/recent")
async def recent_divergences(
    limit: int = Query(50, ge=1, le=500),
    open_only: bool = Query(False),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Runs that ended holding work nobody moved.

    A read of the record rather than of the SSE stream, because the operator needs to see what
    happened while they were not watching — which is the whole reason this is a table and not only
    a broadcast (design D10).

    Newest first, and `resolved_at` is included rather than filtered by default: "this was dropped
    and then picked up" is as worth seeing as "this is still dropped".
    """
    project_id, _ = project
    q = select(RunDivergence).where(RunDivergence.project_id == project_id)
    if open_only:
        q = q.where(RunDivergence.resolved_at.is_(None))
    q = q.order_by(RunDivergence.sequence.desc()).limit(limit)
    result = await session.execute(q)
    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "agent": row.agent,
            "task_id": row.task_id,
            "task_status_at_end": row.task_status_at_end,
            "run_exit_status": row.run_exit_status,
            "policy_applied": row.policy_applied,
            "outcome": row.outcome,
            "response_run_id": row.response_run_id,
            "previous_assignee": row.previous_assignee,
            "created_at": row.created_at,
            "resolved_at": row.resolved_at,
        }
        for row in result.scalars().all()
    ]
