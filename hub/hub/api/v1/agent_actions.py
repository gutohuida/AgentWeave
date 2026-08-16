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
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from ...sse import sse_manager
from ...task_transitions import ENTRY_STATUSES, run_actor
from ...utils import persist_event, short_id
from .agents import AgentRequest, request_agent
from .jobs import create_job, delete_job, run_job, update_job
from .messages import create_message_for_actor
from .questions import ask_question_for_actor
from .tasks import (
    create_task_for_actor,
    get_task,
    list_tasks,
    retry_task_integration,
    task_integrations,
    update_task_for_actor,
)

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
    # The requirements this task serves, by identifier. Checked: an identifier the project does not
    # have is refused with the identifier named. Present here as well as on the operator's schema
    # because `agent-capability-plane` forbids the two surfaces from differing in what they accept.
    requirement_ids: Optional[List[str]] = None
    spec_document: Optional[str] = Field(default=None, max_length=255)
    acceptance_criteria: Optional[List[Any]] = None
    deliverables: Optional[List[Any]] = None
    notes: Optional[Any] = None

    model_config = {"extra": "forbid"}

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        # Entry statuses only, matching `TaskCreate` — and matching MCP's `create_task`, which has
        # never exposed `status` at all. HTTP was the wider of the two, which
        # `agent-capability-plane` forbids; it is levelled by narrowing here rather than by
        # widening MCP, since widening would have propagated the hole instead of closing it.
        if value not in ENTRY_STATUSES:
            raise ValueError(f"a new task must start at one of {sorted(ENTRY_STATUSES)}")
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
        spec_document_id=None,
        exclude_archived_completed=False,
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
        actor=run_actor(actor.run_id, actor.agent),
        session=session,
    )


@router.get("/tasks/{task_id}/integrations")
async def read_shared_task_integrations(
    task_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """What approving this task did to the repository, for the agent that has to act on it.

    Offered alongside the retry below rather than after it: an agent that can retry but cannot read
    the outcome is retrying blind, and would have no way to tell a merge from a fifth skip.
    """
    return await task_integrations(
        task_id,
        project=(actor.project_id, actor.project_id),
        session=session,
    )


@router.post("/tasks/{task_id}/integrations/retry")
async def retry_shared_task_integration(
    task_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Attempt the merge again for an approved task whose work is not in the product.

    Reachable by an agent because one skip reason — nothing accepted names a commit — is one an
    agent can genuinely clear, by having a granted peer accept its evidence.
    """
    return await retry_task_integration(
        task_id,
        project=(actor.project_id, actor.project_id),
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


@router.post("/permission-requests/{request_id}/expire")
async def expire_permission_request(
    request_id: str,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Report that this run has stopped waiting on a decision.

    Not a decision — `record_permission_decision` reports those. This says only that nobody is
    listening any more, so the operator must not keep being offered a card whose answer can no
    longer reach anyone.

    `decided_at` is deliberately left NULL. The model states that it is what distinguishes an
    answer from a timeout, and it can only do that if a timeout does not set it: after this,
    `decided_at is not None` means exactly "a human answered this".

    Idempotent on an already-terminal row, and silent about it. The run reports and the run's end
    sweeps (design D1), so arriving second is the normal case, not an error.
    """
    from ...db.models import PermissionRequest

    row = (
        await session.execute(
            select(PermissionRequest).where(
                PermissionRequest.id == request_id,
                PermissionRequest.project_id == actor.project_id,
                PermissionRequest.run_id == actor.run_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such permission request")

    if row.status == "pending":
        row.status = "expired"
        await session.commit()
        await sse_manager.broadcast(
            actor.project_id,
            "permission_decided",
            {"id": row.id, "agent": row.agent, "status": row.status},
        )
    return {"id": row.id, "status": row.status}


class EvidenceRecord(BaseModel):
    """Evidence an agent produced, for the requirement it demonstrates.

    There is no actor field, and there will not be one: identity comes from the
    run credential this request carried. The same rule `submit_spec_document`
    follows, for the same reason.
    """

    identifier: str = Field(max_length=32)
    kind: str = Field(default="test_result", max_length=32)
    locator: str = Field(default="", max_length=4096)
    summary: str = Field(default="", max_length=10000)
    document: Optional[str] = Field(default=None, max_length=255)
    task_id: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


class EvidenceDecision(BaseModel):
    decision: str = Field(max_length=16)
    reason: str = Field(default="", max_length=10000)

    model_config = {"extra": "forbid"}


async def _resolve_requirement(session, project_id: str, identifier: str, document: str):
    from ... import spec_index, spec_lifecycle

    document_row = None
    if document:
        document_row = await spec_lifecycle.get_document(session, project_id, document)
        if document_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no specification document at {document}.",
            )
    row, why = await spec_index.resolve(
        session, project_id, identifier, document_id=document_row.id if document_row else None
    )
    if why == "ambiguous":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{identifier} is declared by more than one document in this project. "
                "Name the document it belongs to."
            ),
        )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"this project has no requirement {identifier}.",
        )
    return row


@router.post("/spec/evidence", status_code=status.HTTP_201_CREATED)
async def record_evidence(
    body: EvidenceRecord,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Record evidence for a requirement. It enters `awaiting`, never `accepted`.

    A run reporting that it verified something produces a record awaiting review.
    A careful agent and a careless one report success in the same words with the
    same authority, and the record has to be able to tell them apart.
    """
    from ... import project_workspace, requirement_evidence, spec_lifecycle

    requirement = await _resolve_requirement(
        session, actor.project_id, body.identifier, body.document or ""
    )
    try:
        workspace = await project_workspace.resolve_project_workspace(session, actor.project_id)
    except project_workspace.ProjectWorkspaceError:
        workspace = None

    try:
        evidence = await requirement_evidence.record(
            session,
            requirement,
            kind=body.kind,
            locator=body.locator,
            summary=body.summary,
            task_id=body.task_id,
            workspace=workspace,
            actor=spec_lifecycle.Actor(kind="agent", name=actor.agent, run_id=actor.run_id),
        )
    except requirement_evidence.EvidenceRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    await session.commit()
    await sse_manager.broadcast(
        actor.project_id,
        "spec_updated",
        {"evidence": evidence.id, "requirement": requirement.identifier},
    )
    return {
        "id": evidence.id,
        "identifier": requirement.identifier,
        "review_state": evidence.review_state,
        "digest": evidence.digest,
    }


@router.get("/spec/evidence")
async def list_evidence_for_agent(
    identifier: Optional[str] = Query(None),
    document: Optional[str] = Query(None),
    review_state: Optional[str] = Query(None),
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """The evidence this project holds, so an agent asked to judge it can find it.

    Deciding names a specific piece of evidence. Without a way to discover what exists, an agent
    granted acceptance has nothing to act on and the grant is decorative — which is why this ships
    with the tools rather than after them.

    **Who produced each row is part of the answer.** An agent may not decide evidence it produced
    itself, so one that cannot see the producer learns that rule by being refused once per row.
    """
    from ...db.models import RequirementEvidence, SpecRequirement
    from .spec import _evidence_view, _footprints_for, _latest_reviews_for

    if identifier:
        requirement = await _resolve_requirement(
            session, actor.project_id, identifier, document or ""
        )
        query = select(RequirementEvidence).where(
            RequirementEvidence.requirement_id == requirement.id
        )
    else:
        query = select(RequirementEvidence).where(
            RequirementEvidence.project_id == actor.project_id
        )
    if review_state:
        query = query.where(RequirementEvidence.review_state == review_state)

    rows = list(
        (await session.execute(query.order_by(RequirementEvidence.produced_at))).scalars().all()
    )
    prints = await _footprints_for(session, [row.id for row in rows])
    reviews = await _latest_reviews_for(session, [row.id for row in rows])

    # The `FR-n` the agent actually reasons in. `_evidence_view` carries `requirement_id`, which is
    # a database id and names nothing an agent has ever seen.
    identifiers = dict(
        (
            await session.execute(
                select(SpecRequirement.id, SpecRequirement.identifier).where(
                    SpecRequirement.id.in_([row.requirement_id for row in rows] or [""])
                )
            )
        ).all()
    )
    return {
        "evidence": [
            {
                **_evidence_view(row, prints.get(row.id), reviews.get(row.id)),
                "identifier": identifiers.get(row.requirement_id),
            }
            for row in rows
        ]
    }


@router.post("/spec/evidence/{evidence_id}/decision")
async def decide_evidence(
    evidence_id: str,
    body: EvidenceDecision,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Accept or reject evidence, if the operator granted this agent that capability.

    Refused twice over for an agent deciding about its own work: the check is on
    agent identity rather than run identity, because every turn is a new run and
    a run-based check is satisfied by an agent simply continuing.
    """
    from ... import requirement_evidence, spec_lifecycle
    from ...db.models import RequirementEvidence

    evidence = await session.get(RequirementEvidence, evidence_id)
    if evidence is None or evidence.project_id != actor.project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    try:
        await requirement_evidence.decide(
            session,
            evidence,
            decision=body.decision,
            reason=body.reason,
            actor=spec_lifecycle.Actor(kind="agent", name=actor.agent, run_id=actor.run_id),
        )
    except requirement_evidence.EvidenceRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    await session.commit()
    return {"id": evidence.id, "review_state": evidence.review_state}


class SpecDocumentRename(BaseModel):
    """The document, and what it turned out to be about.

    `subject` is prose and the Hub derives the path from it. There is
    deliberately no destination field: path validation is the only control
    keeping a document from being written to an arbitrary location beneath
    `spec/`, and a rename accepting a path would put the least trusted caller in
    the system behind that one guard.
    """

    path: str = Field(max_length=255)
    subject: str = Field(max_length=512)

    model_config = {"extra": "forbid"}


@router.get("/spec/documents")
async def read_spec_document(
    path: str = Query(..., max_length=255),
    include: str = Query("requirements", pattern="^(requirements|full)$"),
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Read the specification an agent was told to implement.

    Documents are written into the *project* directory, while a working agent's checkout is an
    isolated one branched before the document existed. The turn context hands an agent a path and a
    phase and no content, so until this route existed an implementing agent was told which document
    governed it and had no way to open it — and implemented from another agent's paraphrase instead,
    with no way for anyone to detect divergence from what was approved.

    A query parameter rather than a path segment, mirroring the operator's `GET /project/spec`: an
    agent-supplied path then cannot be reinterpreted as extra routing.

    Readable in **every phase**. Reading is not authoring, and every gate in this area governs
    writing or approving. A reviewer needs a proposed document and a builder needs an approved one;
    a refusal that depends on state is one an agent concludes it does not have at all.
    """
    from ... import project_workspace, spec_lifecycle, spec_payload, spec_reading
    from ...db.models import SpecRequirement
    from ...spec_documents import read_document
    from ...spec_manifest import SpecPathError, validate_spec_path

    try:
        resolved = validate_spec_path(path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        workspace = await project_workspace.resolve_project_workspace(session, actor.project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    document = await spec_lifecycle.get_document(session, actor.project_id, resolved)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no specification document at {resolved}.",
        )

    content = read_document(workspace, document.path)
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"the document at {resolved} is registered but its file is missing.",
        )

    payload = spec_payload.extract_payload(content)
    rows = (
        (
            await session.execute(
                select(SpecRequirement).where(SpecRequirement.document_id == document.id)
            )
        )
        .scalars()
        .all()
    )
    requirements, diagnostics = spec_reading.requirement_view(payload, list(rows))

    view = {
        "path": document.path,
        "title": document.title,
        "kind": document.kind,
        # Returned rather than enforced, so an agent can judge how settled this is instead of
        # guessing — or being refused and concluding the capability is absent.
        "phase": document.phase,
        "rigor": document.rigor,
        "explore_closed": document.explore_closed_at is not None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
        "summary": (payload or {}).get("summary"),
        "problem": (payload or {}).get("problem"),
        "scope": (payload or {}).get("scope"),
        "requirements": requirements,
        "open_questions": (payload or {}).get("open_questions"),
        "diagnostics": diagnostics,
    }
    if include == "full":
        for extra in ("design", "tasks", "algorithms", "evidence", "lifecycle"):
            view[extra] = (payload or {}).get(extra)
    return view


@router.post("/spec/documents/rename")
async def rename_spec_document(
    body: SpecDocumentRename,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Rename a document once the interview has established what it is about."""
    from ... import project_workspace, spec_lifecycle, spec_service
    from ...spec_manifest import SpecPathError, validate_spec_path

    try:
        path = validate_spec_path(body.path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        workspace = await project_workspace.resolve_project_workspace(session, actor.project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    document = await spec_lifecycle.get_document(session, actor.project_id, path)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no specification document at {path}.",
        )

    try:
        result = await spec_service.rename_document(
            session,
            workspace,
            document,
            body.subject,
            actor=spec_lifecycle.Actor(kind="agent", name=actor.agent, run_id=actor.run_id),
        )
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code, "field": exc.field_path},
        ) from exc

    await session.commit()
    await sse_manager.broadcast(
        actor.project_id,
        "spec_updated",
        {
            "path": result.path,
            "previous_path": result.previous_path,
            "phase": document.phase,
        },
    )
    return {"path": result.path, "previous_path": result.previous_path}


class SpecDocumentSubmission(BaseModel):
    """A payload plus the document it belongs to.

    The document must already exist. An agent does not start an exploration —
    the operator does, and the document is what "propose" and "approve" later
    refer to. There is deliberately no phase or approval field here: the tool
    surface offers no way to express either.
    """

    path: str = Field(max_length=255)
    document: Any

    model_config = {"extra": "forbid"}


@router.post("/spec/documents")
async def submit_spec_document(
    body: SpecDocumentSubmission,
    actor: AgentActor = Depends(get_agent_actor),
    session: AsyncSession = Depends(get_session),
):
    """Store a submitted specification payload and return what still blocks a proposal.

    Saving an incomplete document is not an error — a document under discussion is incomplete,
    and refusing it would make exploring impossible. `blocking` says what a proposal would refuse.
    """
    from ... import project_workspace, spec_lifecycle, spec_service
    from ...spec_manifest import SpecPathError, validate_spec_path

    try:
        path = validate_spec_path(body.path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        workspace = await project_workspace.resolve_project_workspace(session, actor.project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    document = await spec_lifecycle.get_document(session, actor.project_id, path)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"no specification document at {path}. The operator starts an exploration; "
                "you fill it in."
            ),
        )

    try:
        result = await spec_service.save_document(
            session,
            workspace,
            document,
            body.document,
            # Identity is the run's, never the request body's.
            actor=spec_lifecycle.Actor(kind="agent", name=actor.agent, run_id=actor.run_id),
        )
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code, "field": exc.field_path},
        ) from exc

    await session.commit()
    await sse_manager.broadcast(
        actor.project_id, "spec_updated", {"path": result.path, "phase": result.phase}
    )
    return {
        "path": result.path,
        "phase": result.phase,
        "identifiers": result.identifiers,
        "blocking": result.blocking,
        "divergence": result.divergence,
    }
