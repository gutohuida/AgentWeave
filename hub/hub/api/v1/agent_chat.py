"""Agent chat endpoints — GET /api/v1/agent/{agent}/chat/{session_id}"""

from datetime import datetime
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth import get_project
from ...db.engine import get_session
from ...db.models import AgentOutput, Message

router = APIRouter(prefix="/agent", tags=["agent-chat"])


class ChatMessage(BaseModel):
    id: str
    role: str  # 'user' or 'agent'
    content: str
    timestamp: datetime


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

    # Get messages from user to this agent
    # Look for messages where session_id is in the content or metadata
    msg_q = (
        select(Message)
        .where(
            Message.project_id == project_id,
            Message.recipient == agent,
            Message.sender == "user",
        )
        .order_by(Message.timestamp.asc())
    )
    msg_result = await session.execute(msg_q)
    user_messages = msg_result.scalars().all()

    # Get agent output for this session
    output_q = (
        select(AgentOutput)
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
            AgentOutput.session_id == session_id,
        )
        .order_by(AgentOutput.timestamp.asc())
    )
    output_result = await session.execute(output_q)
    agent_outputs = output_result.scalars().all()

    # Build chat messages
    messages: List[ChatMessage] = []

    # Add user messages (those containing the session_id in content or all if no specific session)
    for msg in user_messages:
        # Include message if it's for this session or if no session filtering needed
        # For now, include all user messages to the agent as they may be relevant
        content = msg.content or ""
        # Check if this message is related to the session
        if session_id in content or not any(session_id in str(m.content) for m in user_messages):
            messages.append(
                ChatMessage(
                    id=msg.id,
                    role="user",
                    content=(
                        content.split("\n\n[Session:")[0] if "[Session:" in content else content
                    ),
                    timestamp=msg.timestamp,
                )
            )

    # Add agent outputs as agent messages
    for output in agent_outputs:
        messages.append(
            ChatMessage(
                id=output.id,
                role="agent",
                content=output.content,
                timestamp=output.timestamp,
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
    limit: int = 50,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Get recent chat messages with an agent across all sessions.

    Returns the most recent messages between user and agent,
    useful for a general chat view without session filtering.
    """
    project_id, _ = project

    # Get recent messages from user to agent
    msg_q = (
        select(Message)
        .where(
            Message.project_id == project_id,
            Message.recipient == agent,
            Message.sender == "user",
        )
        .order_by(Message.timestamp.desc())
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
        .order_by(AgentOutput.timestamp.desc())
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
                timestamp=msg.timestamp,
            )
        )

    for output in agent_outputs:
        messages.append(
            ChatMessage(
                id=output.id,
                role="agent",
                content=output.content,
                timestamp=output.timestamp,
            )
        )

    # Sort by timestamp and limit
    messages.sort(key=lambda m: m.timestamp)
    return messages[-limit:]
