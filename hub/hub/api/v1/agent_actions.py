"""Least-privilege application API exposed to authenticated agent runs.

Capability routers are added here phase-by-phase. Keeping a distinct namespace makes it
impossible to accidentally apply the project-key dependency to an agent operation.
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent_auth import AgentActor, get_agent_actor
from ...checkpoint_access import AccessDeniedError, recall_observation
from ...conversations import conversation_id_for_run
from ...db.engine import get_session
from ...db.models import CheckpointNote, Question
from ...schemas.jobs import JobCreate, JobResponse, JobUpdate
from ...schemas.messages import _MESSAGE_TYPES, MessageCreate, MessageResponse
from ...schemas.questions import QuestionCreate, QuestionOption, QuestionResponse
from ...schemas.tasks import (
    _PRIORITIES,
    _TASK_ID_RE,
    _TASK_STATUSES,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from ...sse import sse_manager
from ...utils import persist_event, short_id
from .agents import AgentRequest, request_agent
from .jobs import create_job, delete_job, run_job, update_job
from .messages import create_message_for_actor
from .questions import ask_question_for_actor
from .tasks import create_task_for_actor, get_task, list_tasks, update_task_for_actor

router = APIRouter(prefix="/agent-actions", tags=["agent-actions"])


class AgentMessageCreate(BaseModel):
    recipient: str = Field(max_length=64)
    subject: Optional[str] = Field(default=None, max_length=256)
    content: str = Field(max_length=10000)
    type: str = Field(default="message", max_length=64)
    task_id: Optional[str] = Field(default=None, max_length=128)
    # Which of the recipient's conversations to send into. Unset — which is the common case,
    # because a sending agent usually has no reason to know another agent's conversation ids —
    # means their most recent open one, opening a new one if they have none.
    #
    # `extra: "forbid"` below is why this field's absence was not a missing feature but a total
    # outage: `mcp_server.send_message` puts `conversation_id` in every body it builds, null
    # included, and a forbidden *key* is rejected regardless of its value. Every agent-to-agent
    # message failed 422, not only the ones naming a conversation.
    conversation_id: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value not in _MESSAGE_TYPES:
            raise ValueError(f"type must be one of {_MESSAGE_TYPES}")
        return value


class AgentTaskCreate(BaseModel):
    id: Optional[str] = Field(default=None, max_length=64)
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

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not _TASK_ID_RE.match(value):
            raise ValueError("id must be a safe task identifier")
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
    # All required — see QuestionCreate. An agent that omits them is rejected before the Hub
    # stores anything, and retries with the structure rather than silently degrading.
    options: List[QuestionOption] = Field(min_length=2, max_length=8)
    header: str = Field(min_length=1, max_length=64)
    multi_select: bool

    model_config = {"extra": "forbid"}


class AgentQuestionBatchCreate(BaseModel):
    """Several questions asked in one call, answered in one sitting.

    Capped at 4 the way Claude Code's own `AskUserQuestion` is: past a handful, stepping through
    stops feeling like being asked something and starts feeling like filling in a form. The lower
    bound is 1, not 2 — a single question is the common case and must not need a different call.
    """

    questions: List[AgentQuestionCreate] = Field(min_length=1, max_length=4)
    blocking: bool = True

    model_config = {"extra": "forbid"}


class AgentQuestionBatchResponse(BaseModel):
    batch_id: str
    questions: List[QuestionResponse]


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
        conversation_id=body.conversation_id,
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


class AgentCheckpointNotes(BaseModel):
    """What the agent knows that the record does not.

    Capped near the 1-2k tokens Anthropic recommends for distillation. The caps are not
    incidental: notes are one input to a checkpoint the Hub is otherwise authoritative for, and an
    agent allowed to write an essay here would be writing the checkpoint by the back door — which
    is exactly the arrangement this change replaces.
    """

    intent: str = Field(max_length=1500)
    suspicions: List[str] = Field(default_factory=list, max_length=8)
    warnings: List[str] = Field(default_factory=list, max_length=8)

    model_config = {"extra": "forbid"}

    @field_validator("suspicions", "warnings")
    @classmethod
    def cap_entries(cls, value: List[str]) -> List[str]:
        for entry in value:
            if len(entry) > 400:
                raise ValueError("each entry must be at most 400 characters")
        return value


@router.post("/checkpoint-notes", status_code=status.HTTP_201_CREATED)
async def submit_checkpoint_notes(
    body: AgentCheckpointNotes,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Record the agent's notes for the next checkpoint of its current conversation.

    Refused outside a conversation: notes are consumed by that conversation's next checkpoint, so
    a note with nowhere to land is better rejected loudly than stored where nothing will read it.
    """
    conversation_id = await conversation_id_for_run(session, actor.run_id)
    if not conversation_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This run is not attached to a conversation, so notes have nowhere to land.",
        )

    note = CheckpointNote(
        id=f"note-{short_id()}",
        project_id=actor.project_id,
        conversation_id=conversation_id,
        agent=actor.agent,
        run_id=actor.run_id,
        intent=body.intent,
        suspicions=list(body.suspicions),
        warnings=list(body.warnings),
    )
    session.add(note)
    await session.commit()
    await persist_event(
        session,
        actor.project_id,
        "checkpoint_notes_submitted",
        {"note_id": note.id, "conversation_id": conversation_id, "agent": actor.agent},
        agent=actor.agent,
    )
    return {"id": note.id, "conversation_id": conversation_id, "recorded": True}


@router.get("/recall/{output_id}")
async def recall(
    output_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Materialise one observation a checkpoint cited, exactly as it was recorded.

    Identity comes from the run's minted credential via `get_agent_actor` — never from the
    request, which is the rule the whole agent-actions namespace exists to keep. A caller cannot
    ask to be someone else, so the grant cannot be talked around.
    """
    try:
        return await recall_observation(session, actor.agent, actor.project_id, output_id)
    except AccessDeniedError as exc:
        # 404, not 403. Confirming that an id exists but is out of reach is itself a disclosure,
        # and "no such observation" and "not cited by a checkpoint you may read" must be
        # indistinguishable from the outside.
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
        options=list(body.options or []),
        header=body.header,
        multi_select=body.multi_select,
    )
    return await ask_question_for_actor(
        question,
        project_id=actor.project_id,
        from_agent=actor.agent,
        created_by_run_id=actor.run_id,
        session=session,
    )


@router.post(
    "/questions/batch",
    response_model=AgentQuestionBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def ask_operator_question_batch(
    body: AgentQuestionBatchCreate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Ask several questions at once, as rows sharing one batch identity.

    Validation happens before anything is written — Pydantic rejects the whole body if any entry
    is missing its structure — so a batch is never half-created, and the agent retries with a
    complete set rather than leaving the operator a partial prompt.
    """
    batch_id = f"qbatch-{short_id()}"
    total = len(body.questions)
    created = []
    for index, entry in enumerate(body.questions):
        question = QuestionCreate(
            from_agent=actor.agent,
            question=entry.question,
            blocking=body.blocking,
            options=list(entry.options or []),
            header=entry.header,
            multi_select=entry.multi_select,
        )
        created.append(
            await ask_question_for_actor(
                question,
                project_id=actor.project_id,
                from_agent=actor.agent,
                created_by_run_id=actor.run_id,
                session=session,
                batch_id=batch_id,
                batch_index=index,
                batch_size=total,
            )
        )
    return AgentQuestionBatchResponse(
        batch_id=batch_id,
        questions=[QuestionResponse.model_validate(row) for row in created],
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


class PermissionDecisionCreate(BaseModel):
    """One permission decision a run has *already* made and is reporting.

    Past tense throughout: the run answered Claude before calling this, so nothing here can
    change the outcome. See `mcp_server._report_decision`.
    """

    tool_name: str = Field(max_length=128)
    tool_use_id: str = Field(default="", max_length=128)
    allowed: bool
    reason: str = Field(default="", max_length=1000)

    model_config = {"extra": "forbid"}


@router.post("/permission-decisions", status_code=status.HTTP_202_ACCEPTED)
async def record_permission_decision(
    body: PermissionDecisionCreate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Record a run's permission decision so a refusal is visible to the operator.

    Only refusals are persisted. An allowed call is the unremarkable case and would bury the
    interesting one under a row per tool call; a refusal is the thing the operator can act on,
    and is the gap `2026-08-06-operator-in-the-loop-turns` records — an agent that hits a wall
    while the one person who could widen it never learns it happened.

    Returns 202 rather than 201: the caller is not waiting on this and discards the response.
    """
    if not body.allowed:
        await persist_event(
            session,
            project_id=actor.project_id,
            event_type="permission_denied",
            agent=actor.agent,
            data={
                "tool_name": body.tool_name,
                "tool_use_id": body.tool_use_id,
                "reason": body.reason,
                "run_id": actor.run_id,
            },
            severity="warn",
        )
        await sse_manager.broadcast(
            actor.project_id,
            "permission_denied",
            {"agent": actor.agent, "tool_name": body.tool_name, "reason": body.reason},
        )
    return {"recorded": not body.allowed}


class PermissionRequestCreate(BaseModel):
    """A run asking the operator to decide one tool call."""

    tool_name: str = Field(max_length=128)
    tool_use_id: str = Field(default="", max_length=128)
    tool_input: dict = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


@router.post("/permission-requests", status_code=status.HTTP_201_CREATED)
async def open_permission_request(
    body: PermissionRequestCreate,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Open a pending permission request and tell the operator it is waiting.

    The caller blocks on the answer, so this must not do anything slow or fallible beyond
    persisting the row and broadcasting.
    """
    from ...db.models import PermissionRequest

    request_id = f"perm-{short_id()}"
    session.add(
        PermissionRequest(
            id=request_id,
            project_id=actor.project_id,
            agent=actor.agent,
            run_id=actor.run_id,
            conversation_id=await conversation_id_for_run(session, actor.run_id),
            tool_name=body.tool_name,
            tool_use_id=body.tool_use_id,
            tool_input=body.tool_input,
            status="pending",
        )
    )
    await session.commit()
    await sse_manager.broadcast(
        actor.project_id,
        "permission_requested",
        {
            "id": request_id,
            "agent": actor.agent,
            "tool_name": body.tool_name,
            "run_id": actor.run_id,
        },
    )
    return {"id": request_id, "status": "pending"}


@router.get("/permission-requests/{request_id}")
async def poll_permission_request(
    request_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Report a request's current status to the run waiting on it.

    Scoped to the asking agent: one run must not be able to read, or wait on, another's
    pending decision.
    """
    from ...db.models import PermissionRequest

    row = (
        await session.execute(
            select(PermissionRequest).where(
                PermissionRequest.id == request_id,
                PermissionRequest.project_id == actor.project_id,
                PermissionRequest.agent == actor.agent,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such permission request")
    return {"id": row.id, "status": row.status}
