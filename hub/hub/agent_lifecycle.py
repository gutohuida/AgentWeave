"""Agent archival.

An agent is archived, never deleted. That is a decision, not a deferral: an agent's name is the
attribution on every run, message and conversation it produced, so deleting the row would either
orphan that history or cascade it away. Archival keeps all of it readable and is reversible.

The shape deliberately mirrors `conversations.archivable` / `archive` / `unarchive` — the same act
at a different scope. Archiving is *refused* when work is outstanding rather than resolved by
force, because stopping a live run from a settings page destroys work with no undo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Agent, Conversation, InboundQueueEntry, Run

AGENT_LIFECYCLES = ("open", "archived")


async def archivable(db: AsyncSession, agent: Agent) -> Optional[str]:
    """Why this agent cannot be archived, or None when it can be.

    Checked against the agent's *runs and queue*, not against its conversations' lifecycles: an
    agent with ten archived conversations and one running turn is still working.
    """
    if agent.lifecycle == "archived":
        return None

    running = await db.execute(
        select(Run.id)
        .where(
            Run.project_id == agent.project_id,
            Run.agent == agent.name,
            Run.status == "running",
        )
        .limit(1)
    )
    if running.scalar_one_or_none() is not None:
        return f"{agent.name} has a run in progress. Wait for it to finish, or stop it first."

    queued = await db.execute(
        select(InboundQueueEntry.id)
        .join(Conversation, Conversation.id == InboundQueueEntry.conversation_id)
        .where(
            Conversation.project_id == agent.project_id,
            Conversation.agent == agent.name,
            InboundQueueEntry.state == "queued",
        )
        .limit(1)
    )
    if queued.scalar_one_or_none() is not None:
        return (
            f"{agent.name} has messages waiting to be delivered. Archiving it would strand them, "
            "because nothing delivers to an archived agent."
        )
    return None


def archive(agent: Agent) -> None:
    """Mark an agent archived. Callers check `archivable` first.

    Also releases the agent's charter binding (`charter_id = None`): nothing runs an archived
    agent, so a bound charter governs nothing while it only walls off the charter's deletion
    behind a name the default roster does not show (F185). `runner_id` is deliberately left
    bound — an archived agent can still be named as a runner's holder (`design.md` D3), and a
    third site (`runners.py delete_runner`) relies on being able to say so.
    """
    agent.lifecycle = "archived"
    agent.archived_at = datetime.now(timezone.utc)
    agent.charter_id = None


def unarchive(agent: Agent) -> None:
    """Reopen an archived agent. Always permitted — nothing is blocked by reopening.

    Does **not** restore the charter binding `archive` released — that release is permanent,
    not a pause. The archive/unarchive API responses say so explicitly (`agents.py`
    `archive_agent`/`unarchive_agent`).
    """
    agent.lifecycle = "open"
    agent.archived_at = None
