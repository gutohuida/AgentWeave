"""Stable AgentWeave conversation identity helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Conversation
from .utils import short_id


def new_conversation(*, project_id: str, agent: str) -> Conversation:
    now = datetime.now(timezone.utc)
    return Conversation(
        id=f"conv-{short_id()}",
        project_id=project_id,
        agent=agent,
        lifecycle="open",
        created_at=now,
        updated_at=now,
    )


async def get_open_conversation(
    db: AsyncSession, *, project_id: str, agent: str, conversation_id: str
) -> Optional[Conversation]:
    conversation = await db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.project_id != project_id
        or conversation.agent != agent
        or conversation.lifecycle != "open"
    ):
        return None
    return conversation


async def latest_open_conversation(
    db: AsyncSession, *, project_id: str, agent: str
) -> Optional[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.project_id == project_id,
            Conversation.agent == agent,
            Conversation.lifecycle == "open",
        )
        .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def conversation_for_provider_session(
    db: AsyncSession,
    *,
    project_id: str,
    agent: str,
    provider_session_id: str,
) -> Optional[Conversation]:
    result = await db.execute(
        select(Conversation).where(
            Conversation.project_id == project_id,
            Conversation.agent == agent,
            Conversation.provider_session_id == provider_session_id,
        )
    )
    return result.scalar_one_or_none()
