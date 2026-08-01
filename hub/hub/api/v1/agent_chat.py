"""Agent chat endpoints — GET /api/v1/agent/{agent}/chat/{session_id}"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AgentOutput, InboundQueueEntry, Run

router = APIRouter(prefix="/agent", tags=["agent-chat"])


class ChatMessage(BaseModel):
    id: str
    role: str  # 'user' or 'agent'
    content: str
    timestamp: datetime
    kind: Optional[
        Literal["text", "thinking", "tool_use", "tool_result", "status", "diagnostic", "error"]
    ] = None
    payload: Optional[Dict[str, Any]] = None
    run_id: Optional[str] = None
    sequence: Optional[int] = None


class ChatHistoryResponse(BaseModel):
    session_id: str
    agent: str
    messages: List[ChatMessage]


@router.get("/{agent}/chat/{session_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    agent: str,
    session_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get conversation history for a specific agent session.

    Returns messages between user and agent for the given session,
    including both direct messages and agent output.
    """
    project_id, _ = project

    # Get agent outputs for this session
    output_q = (
        select(AgentOutput)
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
            AgentOutput.session_id == session_id,
        )
        .order_by(
            AgentOutput.timestamp.asc(),
            func.coalesce(AgentOutput.sequence, -1).asc(),
            AgentOutput.id.asc(),
        )
    )
    output_result = await session.execute(output_q)
    session_outputs = output_result.scalars().all()

    # Operator input is a typed queue origin, never a magic sender name. A delivered
    # entry's run gives exact session attribution, replacing the old timestamp heuristic.
    msg_q = (
        select(InboundQueueEntry)
        .join(Run, Run.id == InboundQueueEntry.delivered_in_run_id)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.origin_type == "operator",
            Run.session_id == session_id,
        )
        .order_by(InboundQueueEntry.sequence)
    )
    msg_result = await session.execute(msg_q)
    user_messages = msg_result.scalars().all()

    messages: List[ChatMessage] = []

    for msg in user_messages:
        messages.append(
            ChatMessage(
                id=msg.id,
                role="user",
                content=msg.content,
                timestamp=msg.arrived_at,
            )
        )

    # Add agent outputs for this session
    for output in session_outputs:
        messages.append(
            ChatMessage(
                id=output.id,
                role="agent",
                content=output.content,
                timestamp=output.timestamp,
                kind=output.kind,
                payload=output.payload,
                run_id=output.run_id,
                sequence=output.sequence,
            )
        )

    # Sort by timestamp
    messages.sort(key=lambda m: m.timestamp)

    return ChatHistoryResponse(
        session_id=session_id,
        agent=agent,
        messages=messages,
    )


@router.get("/{agent}/chat", response_model=List[ChatMessage])
async def get_recent_chat(
    agent: str,
    limit: int = Query(50, ge=1, le=500),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get recent chat messages with an agent across all sessions.

    Returns the most recent messages between user and agent,
    useful for a general chat view without session filtering.
    """
    project_id, _ = project

    # Get recent typed operator queue entries for this agent.
    msg_q = (
        select(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.origin_type == "operator",
        )
        .order_by(InboundQueueEntry.sequence.desc())
        .limit(limit)
    )
    msg_result = await session.execute(msg_q)
    user_messages = msg_result.scalars().all()

    # Get recent agent outputs
    output_q = (
        select(AgentOutput)
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
        )
        .order_by(
            AgentOutput.timestamp.desc(),
            func.coalesce(AgentOutput.sequence, -1).desc(),
            AgentOutput.id.desc(),
        )
        .limit(limit)
    )
    output_result = await session.execute(output_q)
    agent_outputs = output_result.scalars().all()

    # Build chat messages
    messages: List[ChatMessage] = []

    for msg in user_messages:
        content = msg.content or ""
        messages.append(
            ChatMessage(
                id=msg.id,
                role="user",
                content=content.split("\n\n[Session:")[0] if "[Session:" in content else content,
                timestamp=msg.arrived_at,
            )
        )

    for output in agent_outputs:
        messages.append(
            ChatMessage(
                id=output.id,
                role="agent",
                content=output.content,
                timestamp=output.timestamp,
                kind=output.kind,
                payload=output.payload,
                run_id=output.run_id,
                sequence=output.sequence,
            )
        )

    # Sort by timestamp and limit
    messages.sort(key=lambda m: m.timestamp)
    return messages[-limit:]
