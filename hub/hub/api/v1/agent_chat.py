"""Agent chat endpoints — GET /api/v1/agent/{agent}/chat/{session_id}"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
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

    # Get agent outputs for this session
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
    session_outputs = output_result.scalars().all()

    # Build time window for this session (used for untagged messages)
    session_first_ts = min((o.timestamp for o in session_outputs), default=None)
    session_last_ts = max((o.timestamp for o in session_outputs), default=None)

    # Get all user messages to this agent
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

    # Get first-output timestamps for all OTHER sessions (used for Tier 3 attribution)
    other_starts_q = (
        select(func.min(AgentOutput.timestamp))
        .where(
            AgentOutput.project_id == project_id,
            AgentOutput.agent == agent,
            AgentOutput.session_id.isnot(None),
            AgentOutput.session_id != session_id,
        )
        .group_by(AgentOutput.session_id)
    )
    other_starts_result = await session.execute(other_starts_q)
    other_first_timestamps = [row[0] for row in other_starts_result.all() if row[0] is not None]

    messages: List[ChatMessage] = []

    for msg in user_messages:
        content = msg.content or ""

        # 1. Exact match by session_id column (post-migration resume messages)
        if msg.session_id == session_id:
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
            continue

        # 2. Fallback: content tag match (pre-migration resume messages)
        if f"[Session: {session_id}]" in content:
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
            continue

        # 3. Untagged messages (new-session messages with session_id=None).
        #    Only include if they fall within this session's time window AND no other
        #    session started closer to the message (nearest-session wins, prevents
        #    messages from previous new-sessions bleeding into the current one).
        if msg.session_id is None and "[Session:" not in content:
            if session_first_ts is not None and session_last_ts is not None:
                in_window = session_first_ts - timedelta(minutes=5) <= msg.timestamp <= session_last_ts
                # Exclude if another session started between this message and the current session
                closer_session_exists = any(
                    msg.timestamp <= other_ts < session_first_ts
                    for other_ts in other_first_timestamps
                )
                if in_window and not closer_session_exists:
                    messages.append(
                        ChatMessage(
                            id=msg.id,
                            role="user",
                            content=content,
                            timestamp=msg.timestamp,
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
