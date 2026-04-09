"""Task endpoints — POST/GET/GET{id}/PATCH."""

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import Task
from ...schemas.tasks import TaskCreate, TaskResponse, TaskUpdate
from ...sse import sse_manager
from ...utils import persist_event, short_id

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    body: TaskCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    task_id = body.id or f"task-{short_id()}"
    created_at = None
    if body.created_at:
        try:
            created_at = datetime.fromisoformat(body.created_at)
        except ValueError:
            pass
    task = Task(
        id=task_id,
        project_id=project_id,
        title=body.title,
        description=body.description,
        status=body.status,
        priority=body.priority,
        assignee=body.assignee,
        assigner=body.assigner,
        requirements=body.requirements,
        acceptance_criteria=body.acceptance_criteria,
        deliverables=body.deliverables,
        notes=body.notes,
    )
    if created_at:
        task.created_at = created_at
    session.add(task)
    await session.commit()
    await session.refresh(task)
    await sse_manager.broadcast(
        project_id, "task_created", {"id": task_id, "title": body.title}
    )
    await persist_event(
        session,
        project_id,
        "task_created",
        {"id": task_id, "title": body.title},
        agent=body.assignee,
    )
    return task


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
    return result.scalars().all()


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
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    body: TaskUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.status is not None:
        task.status = body.status
    if body.priority is not None:
        task.priority = body.priority
    if body.assignee is not None:
        task.assignee = body.assignee
    if body.description is not None:
        task.description = body.description
    if body.notes is not None:
        task.notes = body.notes
    task.updated = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(task)
    await sse_manager.broadcast(
        project_id, "task_updated", {"id": task_id, "status": task.status}
    )
    await persist_event(
        session,
        project_id,
        "task_updated",
        {"id": task_id, "status": task.status},
        agent=task.assignee,
    )
    return task
