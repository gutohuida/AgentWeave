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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AgentOutput, Conversation, InboundQueueEntry, Message, Project

router = APIRouter(prefix="/agent", tags=["agent-chat"])

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


class ConversationResponse(BaseModel):
    id: str
    agent: str
    provider_session_id: Optional[str]
    lifecycle: str
    created_at: datetime
    updated_at: datetime


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


@router.get("/{agent}/conversations", response_model=List[ConversationResponse])
async def list_conversations(
    agent: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List the durable conversations owned by one project agent."""
    project_id, _ = project
    result = await session.execute(
        select(Conversation)
        .where(Conversation.project_id == project_id, Conversation.agent == agent)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    )
    return [
        ConversationResponse.model_validate(row, from_attributes=True) for row in result.scalars()
    ]


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
