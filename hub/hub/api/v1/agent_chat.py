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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...conversations import (
    archivable,
    archive,
    backfill_titles,
    conversation_attention,
    unarchive,
)
from ...db.engine import get_session
from ...db.models import (
    CONVERSATION_TITLE_MAX_LENGTH,
    AgentOutput,
    Conversation,
    InboundQueueEntry,
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
    delivery_state: Literal["delivered", "queued"] = "delivered"
    # The *other* agent's name — set for inbound_peer/outbound_peer only.
    participant: Optional[str] = None
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


ConversationAttention = Literal["running", "waiting", "idle"]


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
    # Whether this conversation needs the operator, without opening it. "waiting" outranks
    # "running" — a run blocked on a question is running, but stopping for the operator is the
    # part they have to see.
    attention: ConversationAttention = "idle"
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None
    # Control id -> value (e.g. {"model": "claude-opus-5", "effort": "high"}). None/empty
    # means the conversation inherits its agent's runner and the catalog's control defaults —
    # this is what the composer reads to show the values the next message will use.
    runtime_overrides: Optional[Dict[str, str]] = None


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
    return TimelineEntry(
        id=entry.id,
        kind=kind,
        content=entry.content,
        timestamp=entry.delivered_at if delivered and entry.delivered_at else entry.arrived_at,
        delivery_state="delivered" if delivered else "queued",
        participant=entry.origin_agent,
        run_id=entry.delivered_in_run_id,
        sequence=entry.sequence,
        hop_depth=entry.hop_depth,
        hop_budget_exceeded=(
            None if delivered or hop_budget is None else entry.hop_depth > hop_budget
        ),
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
    """Every entry still waiting for delivery, regardless of session — it belongs to
    whichever turn drains it next, so it cannot be scoped to a past session."""
    predicates = [
        InboundQueueEntry.project_id == project_id,
        InboundQueueEntry.agent == agent,
        InboundQueueEntry.state == "queued",
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


async def _to_response(
    session: AsyncSession, conversations: List[Conversation]
) -> List[ConversationResponse]:
    """Serialise conversations with their attention state, one query for the whole page."""
    await backfill_titles(session, conversations)
    attention = await conversation_attention(session, [row.id for row in conversations])
    responses = []
    for row in conversations:
        response = ConversationResponse.model_validate(row, from_attributes=True)
        response.attention = attention.get(row.id, "idle")  # type: ignore[assignment]
        responses.append(response)
    return responses


async def _owned_conversation(
    session: AsyncSession, project_id: str, agent: str, conversation_id: str
) -> Conversation:
    """Fetch a conversation, or 404 if it is not this project's and this agent's.

    404 rather than 403 for a conversation belonging to another project: whether an id exists
    elsewhere is not this caller's to learn.
    """
    conversation = await session.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.project_id != project_id
        or conversation.agent != agent
    ):
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
    archived_by_agent = {agent: count for agent, count in archived.all()}
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

    conversation = await session.get(Conversation, conversation_id)
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
