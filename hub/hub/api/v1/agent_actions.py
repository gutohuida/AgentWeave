"""Least-privilege application API exposed to authenticated agent runs.

Capability routers are added here phase-by-phase. Keeping a distinct namespace makes it
impossible to accidentally apply the project-key dependency to an agent operation.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent_auth import AgentActor, get_agent_actor
from ...db.engine import get_session
from ...db.models import Question
from ...schemas.messages import MessageCreate, MessageResponse, _MESSAGE_TYPES
from ...schemas.questions import QuestionCreate, QuestionResponse
from ...schemas.jobs import JobCreate, JobResponse, JobUpdate
from ...schemas.tasks import TaskCreate, TaskResponse, TaskUpdate, _PRIORITIES, _TASK_STATUSES
from .messages import create_message_for_actor
from .agents import AgentRequest, request_agent
from .jobs import create_job, delete_job, run_job, update_job
from .questions import ask_question_for_actor
from .tasks import create_task_for_actor, get_task, list_tasks, update_task_for_actor

router = APIRouter(prefix="/agent-actions", tags=["agent-actions"])


class AgentMessageCreate(BaseModel):
    recipient: str = Field(max_length=64)
    subject: Optional[str] = Field(default=None, max_length=256)
    content: str = Field(max_length=10000)
    type: str = Field(default="message", max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=128)

    model_config = {"extra": "forbid"}

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in _MESSAGE_TYPES:
            raise ValueError(f"type must be one of {_MESSAGE_TYPES}")
        return value


class AgentTaskCreate(BaseModel):
    title: str = Field(max_length=256)
    description: str = Field(default="", max_length=10000)
    status: str = Field(default="pending", max_length=64)
    priority: str = Field(default="medium", max_length=64)
    assignee: Optional[str] = Field(default=None, max_length=64)
    requirements: Optional[List[Any]] = None
    acceptance_criteria: Optional[List[Any]] = None
    deliverables: Optional[List[Any]] = None
    notes: Optional[Any] = None

    model_config = {"extra": "forbid"}

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in _TASK_STATUSES:
            raise ValueError(f"status must be one of {_TASK_STATUSES}")
        return value

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in _PRIORITIES:
            raise ValueError(f"priority must be one of {_PRIORITIES}")
        return value


class AgentQuestionCreate(BaseModel):
    question: str = Field(max_length=10000)
    blocking: bool = False

    model_config = {"extra": "forbid"}


class BoundAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    template: str = Field(min_length=1, max_length=32)
    task: str = Field(min_length=1, max_length=100_000)

    model_config = {"extra": "forbid"}


class AgentJobCreate(BaseModel):
    name: str = Field(max_length=256)
    agent: str = Field(max_length=64)
    message: str = Field(max_length=10000)
    cron: str = Field(max_length=128)
    session_mode: str = Field(default="new", max_length=64)
    enabled: bool = True

    model_config = {"extra": "forbid"}

    @field_validator("session_mode")
    @classmethod
    def validate_session_mode(cls, value: str) -> str:
        if value not in ("new", "resume"):
            raise ValueError("session_mode must be 'new' or 'resume'")
        return value


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_peer_message(
    body: AgentMessageCreate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    message = MessageCreate(
        sender=actor.agent,
        recipient=body.recipient,
        subject=body.subject,
        content=body.content,
        type=body.type,
        task_id=body.task_id,
        run_id=actor.run_id,
    )
    return await create_message_for_actor(
        message,
        project_id=actor.project_id,
        sender=actor.agent,
        run_id=actor.run_id,
        session=session,
    )


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_shared_task(
    body: AgentTaskCreate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    task = TaskCreate(**body.model_dump(), assigner=actor.agent)
    return await create_task_for_actor(
        task,
        project_id=actor.project_id,
        assigner=actor.agent,
        created_by_run_id=actor.run_id,
        session=session,
    )


@router.get("/tasks", response_model=List[TaskResponse])
async def list_shared_tasks(
    agent: Optional[str] = Query(None),
    task_status: Optional[str] = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await list_tasks(
        agent=agent,
        task_status=task_status,
        offset=offset,
        limit=limit,
        project=(actor.project_id, actor.project_id),
        session=session,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_shared_task(
    task_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await get_task(
        task_id,
        project=(actor.project_id, actor.project_id),
        session=session,
    )


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
async def update_shared_task(
    task_id: str,
    body: TaskUpdate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await update_task_for_actor(
        task_id,
        body,
        project_id=actor.project_id,
        updated_by_run_id=actor.run_id,
        session=session,
    )


@router.post("/questions", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def ask_operator_question(
    body: AgentQuestionCreate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    question = QuestionCreate(
        from_agent=actor.agent,
        question=body.question,
        blocking=body.blocking,
    )
    return await ask_question_for_actor(
        question,
        project_id=actor.project_id,
        from_agent=actor.agent,
        created_by_run_id=actor.run_id,
        session=session,
    )


@router.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_own_question(
    question_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    question = await session.get(Question, question_id)
    if (
        question is None
        or question.project_id != actor.project_id
        or question.from_agent != actor.agent
    ):
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.post("/agents/request", status_code=status.HTTP_201_CREATED)
async def request_governed_agent(
    body: BoundAgentRequest,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await request_agent(
        AgentRequest(**body.model_dump(), run_id=actor.run_id),
        project=(actor.project_id, actor.project_id),
        session=session,
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_governed_job(
    body: AgentJobCreate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await create_job(
        JobCreate(**body.model_dump(), source="hub"),
        project=(actor.project_id, actor.project_id),
        session=session,
        agent_identity=actor.agent,
        run_identity=actor.run_id,
    )


@router.patch("/jobs/{job_id}", response_model=JobResponse)
async def update_governed_job(
    job_id: str,
    body: JobUpdate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await update_job(
        job_id,
        body,
        project=(actor.project_id, actor.project_id),
        session=session,
        agent_identity=actor.agent,
        run_identity=actor.run_id,
    )


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_governed_job(
    job_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await delete_job(
        job_id,
        project=(actor.project_id, actor.project_id),
        session=session,
        agent_identity=actor.agent,
        run_identity=actor.run_id,
    )


@router.post("/jobs/{job_id}/run")
async def run_governed_job(
    job_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    return await run_job(
        job_id,
        project=(actor.project_id, actor.project_id),
        session=session,
        agent_identity=actor.agent,
        run_identity=actor.run_id,
    )
