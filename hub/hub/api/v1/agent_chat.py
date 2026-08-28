"""Project-scoped agent chat endpoints.

Returns the merged conversation timeline for one agent (task 8.3): operator
input, the agent's own output, and agent-to-agent traffic in both
directions. Every entry is placed by its recorded association — a delivered
queue entry's `Run`, an output's `session_id`, a message's `session_id` — never
inferred from timestamp proximity to other rows (spec: "Attribution is
recorded, not inferred").

Undelivered (still-queued) entries are appended regardless of which session
was requested: they have no session yet, since they will be delivered into
whichever turn drains them next (spec: "Queued entries are visible before
delivery").
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...context_readings import usable_context_reading
from ...conversations import (
    archivable,
    archive,
    backfill_titles,
    conversation_attention,
    get_conversation_by_id,
    unarchive,
)
from ...db.engine import get_session
from ...db.models import (
    CONVERSATION_TITLE_MAX_LENGTH,
    AgentOutput,
    AIJob,
    Conversation,
    EventLog,
    InboundQueueEntry,
    JobRun,
    Loop,
    Message,
    Project,
)
from ...sse import sse_manager

router = APIRouter(prefix="/agent", tags=["agent-chat"])

# Project-scoped rather than agent-scoped: navigation renders every agent's conversations at once,
# so one request beats one per expanded agent — no waterfall when an agent expands, and the
# archived count arrives with the rows rather than needing a second call to be countable.
conversations_router = APIRouter(prefix="/conversations", tags=["conversations"])

TimelineEntryKind = Literal["operator_input", "agent_output", "inbound_peer", "outbound_peer"]


class TimelineEntry(BaseModel):
    id: str
    kind: TimelineEntryKind
    content: str
    timestamp: datetime
    #: `abandoned` is the third state because the input is gone and only this says so: the Hub
    #: gave up delivering it (`inbound_queue.DELIVERY_ATTEMPT_LIMIT`) and marked the row
    #: `withdrawn`, which a queued-only timeline dropped from the thread entirely — leaving a
    #: dropped message and a delivered one looking identical to the operator (F87).
    delivery_state: Literal["delivered", "queued", "abandoned"] = "delivered"
    # The *other* agent's name — set for inbound_peer/outbound_peer only.
    participant: Optional[str] = None
    # outbound_peer only. Nullable — `subject` is required by `send_message` going forward, but
    # the column predates that requirement, so an older row has none.
    subject: Optional[str] = None
    # agent_output only.
    output_kind: Optional[
        Literal["text", "thinking", "tool_use", "tool_result", "status", "diagnostic", "error"]
    ] = None
    payload: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = None
    sequence: Optional[int] = None
    # operator_input/inbound_peer only.
    hop_depth: Optional[int] = None
    hop_budget_exceeded: Optional[bool] = None
    #: Why the Hub stopped trying, verbatim from the row. Set only with
    #: `delivery_state == "abandoned"` — an operator withdrawal reaches the same `withdrawn`
    #: state and carries no reason, which is what distinguishes the two.
    abandoned_reason: Optional[str] = None


ConversationAttention = Literal["running", "waiting", "idle"]


class ConversationLoop(BaseModel):
    """Which loop's firing created this conversation, for the row that lists it.

    A loop firing starts a *new* conversation every time (task 8.1 refuses `session_mode="resume"`
    for a loop), so an agent's conversation list fills with threads nobody typed and nothing
    distinguishes them from the ones somebody did. `label` is the loop's job name — the same
    pairing `LoopSummary.label` already uses, so a marker here and the loops index name the same
    loop the same way.
    """

    id: str
    label: str


class ConversationResponse(BaseModel):
    id: str
    agent: str
    provider_session_id: Optional[str]
    lifecycle: str
    # Null until the conversation's first message names it. A surface listing a titleless
    # conversation labels it as new — never by `id`.
    title: Optional[str] = None
    title_set_by_operator: bool = False
    origin: str = "operator"
    # Set only when a *loop* firing created this conversation. `origin == "job"` alone cannot
    # say so — a plain scheduled job has the same origin and no loop — so this is null there,
    # and the row shows no loop marker.
    loop: Optional[ConversationLoop] = None
    # How full *this* conversation's context is — not its agent's.
    #
    # `AgentSummary.context_usage` reports one reading per agent, the newest across all of that
    # agent's threads. The composer is conversation-scoped, so reading the agent's value showed
    # whichever conversation last reported, in every conversation. Measured on the trial Hub
    # 2026-08-19: agent `verifier` had three conversations reading 18.56%, 16.6% and 15.9%, and
    # all three composers showed 15.9%.
    #
    # Null when this conversation has produced no reading yet. Deliberately not falling back to
    # the agent's — that fallback is the bug.
    context_usage: Optional[Dict[str, Any]] = None
    # Whether this conversation needs the operator, without opening it. "waiting" outranks
    # "running" — a run blocked on a question is running, but stopping for the operator is the
    # part they have to see.
    attention: ConversationAttention = "idle"
    # Where this conversation stands with its checkpoint threshold: null, "due" or "dismissed".
    # The conversation surface reads it to decide whether to warn.
    checkpoint_warning: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None
    # Control id -> value (e.g. {"model": "claude-opus-5", "effort": "high"}). None/empty
    # means the conversation inherits its agent's runner and the catalog's control defaults —
    # this is what the composer reads to show the values the next message will use.
    runtime_overrides: Optional[Dict[str, str]] = None
    # The task this thread is about, if it is about one. Every turn here binds to it and is checked
    # at its end — which is what the composer has to be able to show, and what the operator has to
    # be able to let go of.
    task_id: Optional[str] = None


class ConversationRenameRequest(BaseModel):
    title: str


class ProjectConversationsResponse(BaseModel):
    """Every conversation the rail draws, plus what it needs to offer the archive.

    `archived_count` is here rather than derivable from `conversations`, because the list
    excludes archived rows by default — a "Show archived (N)" control cannot state N from a
    response that omitted them.
    """

    conversations: List[ConversationResponse]
    archived_count: int
    # The same count broken down per agent, because the agent row's menu offers "Show archived
    # (N)" for that agent alone. Only agents with at least one archived conversation appear.
    archived_by_agent: Dict[str, int] = {}


class ChatHistoryResponse(BaseModel):
    conversation_id: Optional[str] = None
    session_id: Optional[str]
    agent: str
    entries: List[TimelineEntry]


def _queue_entry_to_timeline(
    entry: InboundQueueEntry, hop_budget: Optional[int], *, delivered: bool
) -> TimelineEntry:
    kind: TimelineEntryKind = (
        "operator_input" if entry.origin_type in ("operator", "job") else "inbound_peer"
    )
    # Read from the row rather than taken as a second argument: `delivered` says which query
    # produced this entry, and abandonment is a property of the entry itself. Two callers pass
    # `delivered=False` and only rows carrying a reason are abandoned, so there is nothing for a
    # caller to get wrong.
    abandoned = not delivered and entry.abandoned_reason is not None
    return TimelineEntry(
        id=entry.id,
        kind=kind,
        content=entry.content,
        # `arrived_at`, not `withdrawn_at`, for an abandoned entry: it keeps the place in the
        # thread where the operator last saw it waiting, which is where they will look for it.
        timestamp=entry.delivered_at if delivered and entry.delivered_at else entry.arrived_at,
        delivery_state=("delivered" if delivered else "abandoned" if abandoned else "queued"),
        participant=entry.origin_agent,
        run_id=entry.delivered_in_run_id,
        sequence=entry.sequence,
        hop_depth=entry.hop_depth,
        # `None` when abandoned, for the same reason it is `None` when delivered: this flag is
        # what draws the Continue control, and `release_entry` refuses a row that is no longer
        # `queued`. Offering it would be an offer to be told no.
        hop_budget_exceeded=(
            None if delivered or abandoned or hop_budget is None else entry.hop_depth > hop_budget
        ),
        abandoned_reason=entry.abandoned_reason if abandoned else None,
    )


def _output_to_timeline(output: AgentOutput) -> TimelineEntry:
    return TimelineEntry(
        id=output.id,
        kind="agent_output",
        content=output.content,
        timestamp=output.timestamp,
        output_kind=output.kind,
        payload=output.payload,
        run_id=output.run_id,
        sequence=output.sequence,
    )


def _message_to_timeline(msg: Message) -> TimelineEntry:
    return TimelineEntry(
        id=msg.id,
        kind="outbound_peer",
        content=msg.content,
        timestamp=msg.timestamp,
        participant=msg.recipient,
        subject=msg.subject,
    )


async def _hop_budget(session: AsyncSession, project_id: str) -> Optional[int]:
    project_row = await session.get(Project, project_id)
    return project_row.hop_budget if project_row else None


async def _queued_entries_for(
    session: AsyncSession,
    project_id: str,
    agent: str,
    hop_budget: Optional[int],
    conversation_id: Optional[str] = None,
) -> List[TimelineEntry]:
    """Every entry still waiting for delivery, plus every entry the Hub gave up on.

    The waiting ones belong to whichever turn drains them next, so they cannot be scoped to a
    past session. The abandoned ones belong to nothing — that is the point of showing them
    (F87): `state == "queued"` alone removed a message the Hub dropped from the only place the
    operator would look for it, and `waiting_count` returned to zero at the same moment, so a
    dropped input and a delivered one left the conversation looking identical.

    Keyed on `abandoned_reason` rather than on `state == "withdrawn"`, because an operator
    withdrawal reaches that same state. Putting one of those back would re-show a message they
    chose to take away.
    """
    predicates = [
        InboundQueueEntry.project_id == project_id,
        InboundQueueEntry.agent == agent,
        or_(
            InboundQueueEntry.state == "queued",
            and_(
                InboundQueueEntry.state == "withdrawn",
                InboundQueueEntry.abandoned_reason.is_not(None),
            ),
        ),
    ]
    if conversation_id is not None:
        predicates.append(InboundQueueEntry.conversation_id == conversation_id)
    result = await session.execute(
        select(InboundQueueEntry).where(*predicates).order_by(InboundQueueEntry.sequence)
    )
    return [
        _queue_entry_to_timeline(entry, hop_budget, delivered=False)
        for entry in result.scalars().all()
    ]


async def _loops_by_conversation(
    session: AsyncSession, conversation_ids: List[str]
) -> Dict[str, ConversationLoop]:
    """Which loop, if any, fired each of these conversations — one query for the whole page.

    Batched rather than per row, following `_batch_loop_summaries`: the conversation list is the
    navigation rail, so a per-row query would be one round trip per thread on every render.

    The join to `Loop` is inner on purpose. `JobRun.conversation_id -> AIJob -> Loop` yields a row
    only where a loop actually exists, so a plain scheduled job — same `origin == "job"`, no
    `Loop` — falls out with nothing and its conversation gets no marker. That distinction is the
    whole reason this cannot be derived from `origin`.
    """
    if not conversation_ids:
        return {}
    result = await session.execute(
        select(JobRun.conversation_id, Loop.id, AIJob.name, JobRun.fired_at)
        .join(AIJob, AIJob.id == JobRun.job_id)
        .join(Loop, Loop.job_id == AIJob.id)
        .where(JobRun.conversation_id.in_(conversation_ids))
        # A resume-mode job fires repeatedly onto one conversation, and two jobs can in principle
        # reach the same thread. Newest firing first, then first-write-wins below, so the marker
        # is deterministic rather than whatever the database happened to return first.
        .order_by(JobRun.fired_at.desc())
    )
    loops: Dict[str, ConversationLoop] = {}
    for conversation_id, loop_id, job_name, _fired_at in result.all():
        if conversation_id not in loops:
            loops[conversation_id] = ConversationLoop(id=loop_id, label=job_name)
    return loops


async def _context_by_conversation(
    session: AsyncSession, project_id: str, conversation_ids: List[str]
) -> Dict[str, Any]:
    """The context reading belonging to each of these conversations — one query for the page.

    `context_warning` rows carry `data["conversation_id"]`, resolved when the reading is recorded
    (`output_recording.record_context_usage`). Nothing read it back per conversation until now: the
    agent roster groups the same rows by agent alone, which is a correct answer to a different
    question and the wrong one for a conversation-scoped surface.

    Filtered in Python rather than by a JSON path predicate in SQL, because `EventLog.data` is a
    plain JSON column and SQLite's JSON operators are not uniformly available across the versions
    this ships against. The row set is already bounded to one project's readings for the
    conversations on the page.
    """
    if not conversation_ids:
        return {}
    wanted = set(conversation_ids)
    result = await session.execute(
        select(EventLog)
        .where(
            EventLog.project_id == project_id,
            EventLog.event_type == "context_warning",
        )
        .order_by(EventLog.timestamp.desc())
    )
    rows_by_conversation: Dict[str, List[Any]] = {}
    for event in result.scalars().all():
        data = event.data
        if not isinstance(data, dict):
            continue
        conversation_id = data.get("conversation_id")
        if conversation_id in wanted:
            rows_by_conversation.setdefault(conversation_id, []).append(data)
    return {
        conversation_id: usable_context_reading(rows)
        for conversation_id, rows in rows_by_conversation.items()
    }


async def _to_response(
    session: AsyncSession, conversations: List[Conversation]
) -> List[ConversationResponse]:
    """Serialise conversations with their attention state, one query for the whole page."""
    await backfill_titles(session, conversations)
    conversation_ids = [row.id for row in conversations]
    attention = await conversation_attention(session, conversation_ids)
    loops = await _loops_by_conversation(session, conversation_ids)
    context = (
        await _context_by_conversation(session, conversations[0].project_id, conversation_ids)
        if conversations
        else {}
    )
    responses = []
    for row in conversations:
        response = ConversationResponse.model_validate(row, from_attributes=True)
        response.attention = attention.get(row.id, "idle")  # type: ignore[assignment]
        response.loop = loops.get(row.id)
        response.context_usage = context.get(row.id)
        responses.append(response)
    return responses


async def _owned_conversation(
    session: AsyncSession, project_id: str, agent: str, conversation_id: str
) -> Conversation:
    """Fetch a conversation, or 404 if it is not this project's and this agent's.

    404 rather than 403 for a conversation belonging to another project: whether an id exists
    elsewhere is not this caller's to learn.
    """
    conversation = await get_conversation_by_id(session, conversation_id)
    if conversation is None or conversation.project_id != project_id or conversation.agent != agent:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def _broadcast_conversation(project_id: str, conversation: Conversation) -> None:
    await sse_manager.broadcast(
        project_id,
        "conversation_updated",
        {
            "project_id": project_id,
            "agent": conversation.agent,
            "conversation_id": conversation.id,
            "lifecycle": conversation.lifecycle,
            "title": conversation.title,
        },
    )


@router.get("/{agent}/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    agent: str,
    lifecycle: Literal["open", "archived", "all"] = Query("open"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List the durable conversations owned by one project agent.

    Archived conversations are excluded by default; `?lifecycle=archived` returns exactly those,
    so a surface offering "Show archived" gets both the rows and their count from one request.
    """
    project_id, _ = project
    predicates = [Conversation.project_id == project_id, Conversation.agent == agent]
    if lifecycle != "all":
        predicates.append(Conversation.lifecycle == lifecycle)
    result = await session.execute(
        select(Conversation)
        .where(*predicates)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return await _to_response(session, list(result.scalars()))


@conversations_router.get("", response_model=ProjectConversationsResponse)
async def list_project_conversations(
    lifecycle: Literal["open", "archived", "all"] = Query("open"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Every conversation in the project, across its agents, most recent activity first.

    What navigation reads: the tree groups these by agent, the recency view lists them as they
    come. One request either way, so switching views costs nothing and expanding an agent shows
    its conversations immediately rather than starting a fetch.
    """
    project_id, _ = project
    predicates = [Conversation.project_id == project_id]
    if lifecycle != "all":
        predicates.append(Conversation.lifecycle == lifecycle)
    result = await session.execute(
        select(Conversation)
        .where(*predicates)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    archived = await session.execute(
        select(Conversation.agent, func.count())
        .where(Conversation.project_id == project_id, Conversation.lifecycle == "archived")
        .group_by(Conversation.agent)
    )
    archived_by_agent = dict(archived.all())
    return ProjectConversationsResponse(
        conversations=await _to_response(session, list(result.scalars())),
        archived_count=sum(archived_by_agent.values()),
        archived_by_agent=archived_by_agent,
    )


@router.patch("/{agent}/conversations/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    agent: str,
    conversation_id: str,
    body: ConversationRenameRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Set a conversation's title, and record that the operator set it.

    Recording who set it is what makes an operator's title survive title generation.
    """
    project_id, _ = project
    conversation = await _owned_conversation(session, project_id, agent, conversation_id)

    title = " ".join(body.title.split())
    if not title:
        raise HTTPException(status_code=400, detail="A title cannot be empty")
    if len(title) > CONVERSATION_TITLE_MAX_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"A title cannot exceed {CONVERSATION_TITLE_MAX_LENGTH} characters",
        )

    conversation.title = title
    conversation.title_set_by_operator = True
    await session.commit()
    await session.refresh(conversation)
    await _broadcast_conversation(project_id, conversation)
    return (await _to_response(session, [conversation]))[0]


@router.delete("/{agent}/conversations/{conversation_id}/task", response_model=ConversationResponse)
async def release_conversation_task(
    agent: str,
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Stop attributing this thread's turns to the task it was bound to.

    The operator's half of design D7. The other half is automatic — approving or rejecting the task
    releases every thread bound to it. Nothing else does: a binding is never dropped because the
    conversation *seems* to have moved on, since a wrong guess silently stops checking runs, and a
    mechanism that quietly stops enforcing is worse than one that never started.

    Idempotent. Releasing an unbound thread is not an error; it is the state the caller asked for.
    """
    project_id, _ = project
    conversation = await _owned_conversation(session, project_id, agent, conversation_id)

    conversation.task_id = None
    await session.commit()
    await session.refresh(conversation)
    await _broadcast_conversation(project_id, conversation)
    return (await _to_response(session, [conversation]))[0]


@router.post(
    "/{agent}/conversations/{conversation_id}/archive", response_model=ConversationResponse
)
async def archive_conversation(
    agent: str,
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Archive a conversation, or refuse with the reason it cannot be archived yet."""
    project_id, _ = project
    conversation = await _owned_conversation(session, project_id, agent, conversation_id)

    obstruction = await archivable(session, conversation)
    if obstruction is not None:
        raise HTTPException(status_code=409, detail=obstruction)

    archive(conversation)
    await session.commit()
    await session.refresh(conversation)
    await _broadcast_conversation(project_id, conversation)
    return (await _to_response(session, [conversation]))[0]


@router.post(
    "/{agent}/conversations/{conversation_id}/unarchive", response_model=ConversationResponse
)
async def unarchive_conversation(
    agent: str,
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Reopen an archived conversation. Never refused — reopening obstructs nothing."""
    project_id, _ = project
    conversation = await _owned_conversation(session, project_id, agent, conversation_id)

    unarchive(conversation)
    await session.commit()
    await session.refresh(conversation)
    await _broadcast_conversation(project_id, conversation)
    return (await _to_response(session, [conversation]))[0]


@router.get("/{agent}/chat/{conversation_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    agent: str,
    conversation_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Full merged timeline for one durable conversation."""
    project_id, _ = project

    conversation = await get_conversation_by_id(session, conversation_id)
    if conversation is None or conversation.project_id != project_id or conversation.agent != agent:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Conversation not found")

    output_q = (
        select(AgentOutput)
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
            AgentOutput.conversation_id == conversation_id,
        )
        .order_by(
            AgentOutput.timestamp.asc(),
            func.coalesce(AgentOutput.sequence, -1).asc(),
            AgentOutput.id.asc(),
        )
    )
    # Delivered operator input AND inbound peer traffic — a delivered entry's run
    # gives exact session attribution.
    delivered_q = (
        select(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.conversation_id == conversation_id,
            InboundQueueEntry.state == "delivered",
        )
        .order_by(InboundQueueEntry.sequence)
    )
    outbound_q = (
        select(Message)
        .where(
            Message.project_id == project_id,
            Message.sender == agent,
            Message.conversation_id == conversation_id,
        )
        .order_by(Message.timestamp.asc())
    )

    hop_budget, output_res, delivered_res, outbound_res = await asyncio.gather(
        _hop_budget(session, project_id),
        session.execute(output_q),
        session.execute(delivered_q),
        session.execute(outbound_q),
    )

    entries: List[TimelineEntry] = []
    entries.extend(_output_to_timeline(o) for o in output_res.scalars().all())
    entries.extend(
        _queue_entry_to_timeline(entry, hop_budget, delivered=True)
        for entry in delivered_res.scalars().all()
    )
    entries.extend(_message_to_timeline(m) for m in outbound_res.scalars().all())
    entries.sort(key=lambda e: e.timestamp)

    entries.extend(
        await _queued_entries_for(session, project_id, agent, hop_budget, conversation_id)
    )

    return ChatHistoryResponse(
        conversation_id=conversation_id,
        session_id=conversation.provider_session_id,
        agent=agent,
        entries=entries,
    )


@router.get("/{agent}/chat", response_model=ChatHistoryResponse)
async def get_recent_chat(
    agent: str,
    limit: int = Query(50, ge=1, le=500),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Recent merged timeline across all sessions, plus this agent's current queue."""
    project_id, _ = project

    output_q = (
        select(AgentOutput)
        .where(AgentOutput.project_id == project_id, AgentOutput.agent == agent)
        .order_by(
            AgentOutput.timestamp.desc(),
            func.coalesce(AgentOutput.sequence, -1).desc(),
            AgentOutput.id.desc(),
        )
        .limit(limit)
    )
    delivered_q = (
        select(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.state == "delivered",
        )
        .order_by(InboundQueueEntry.sequence.desc())
        .limit(limit)
    )
    outbound_q = (
        select(Message)
        .where(Message.project_id == project_id, Message.sender == agent)
        .order_by(Message.timestamp.desc())
        .limit(limit)
    )

    hop_budget, output_res, delivered_res, outbound_res = await asyncio.gather(
        _hop_budget(session, project_id),
        session.execute(output_q),
        session.execute(delivered_q),
        session.execute(outbound_q),
    )

    entries: List[TimelineEntry] = []
    entries.extend(_output_to_timeline(o) for o in output_res.scalars().all())
    entries.extend(
        _queue_entry_to_timeline(entry, hop_budget, delivered=True)
        for entry in delivered_res.scalars().all()
    )
    entries.extend(_message_to_timeline(m) for m in outbound_res.scalars().all())
    entries.sort(key=lambda e: e.timestamp)
    entries = entries[-limit:]

    entries.extend(await _queued_entries_for(session, project_id, agent, hop_budget))

    return ChatHistoryResponse(conversation_id=None, session_id=None, agent=agent, entries=entries)
