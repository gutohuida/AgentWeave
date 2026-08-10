"""Durable per-agent inbound queue primitives."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import InboundQueueEntry, Project, Run
from .utils import short_id

DEFAULT_HOP_BUDGET = 6
DEFAULT_TURN_DELIVERY_CAP = 10


def new_entry(
    *,
    project_id: str,
    agent: str,
    origin_type: str,
    content: str,
    hop_depth: int,
    origin_agent: Optional[str] = None,
    message_id: Optional[str] = None,
    session_mode: Optional[str] = None,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    work_dir: Optional[str] = None,
    spec_document: Optional[str] = None,
    task_id: Optional[str] = None,
) -> InboundQueueEntry:
    if origin_type not in ("operator", "agent", "job", "checkpoint"):
        raise ValueError("origin_type must be 'operator', 'agent', 'job', or 'checkpoint'")
    if (origin_type == "agent") != bool(origin_agent):
        raise ValueError("agent origins require origin_agent; operator origins forbid it")
    if hop_depth < 0:
        raise ValueError("hop_depth must be non-negative")
    return InboundQueueEntry(
        id=f"entry-{short_id()}",
        project_id=project_id,
        agent=agent,
        origin_type=origin_type,
        origin_agent=origin_agent,
        content=content,
        arrived_at=datetime.now(timezone.utc),
        hop_depth=hop_depth,
        message_id=message_id,
        session_mode=session_mode,
        session_id=session_id,
        conversation_id=conversation_id,
        work_dir=work_dir,
        spec_document=spec_document,
        task_id=task_id,
        state="queued",
    )


async def project_limits(db: AsyncSession, project_id: str) -> tuple[int, int]:
    project = await db.get(Project, project_id)
    if project is None:
        raise ValueError(f"project {project_id!r} does not exist")
    return project.hop_budget, project.turn_delivery_cap


async def queued_entries(
    db: AsyncSession,
    project_id: str,
    agent: str,
    conversation_id: Optional[str] = None,
) -> List[InboundQueueEntry]:
    predicates = [
        InboundQueueEntry.project_id == project_id,
        InboundQueueEntry.agent == agent,
        InboundQueueEntry.state == "queued",
    ]
    if conversation_id is not None:
        predicates.append(InboundQueueEntry.conversation_id == conversation_id)
    result = await db.execute(
        select(InboundQueueEntry).where(*predicates).order_by(InboundQueueEntry.sequence)
    )
    return list(result.scalars().all())


def can_start(entries: Iterable[InboundQueueEntry], hop_budget: int) -> bool:
    return any(entry.hop_depth <= hop_budget for entry in entries)


def format_turn_prompt(entries: Iterable[InboundQueueEntry]) -> str:
    blocks = ["[AgentWeave inbound queue — delivered inline in arrival order]"]
    for entry in entries:
        if entry.origin_type == "operator":
            origin = "Operator"
        elif entry.origin_type == "job":
            origin = "Scheduled job"
        else:
            origin = f'Agent "{entry.origin_agent}"'
        blocks.append(f"{origin} (hop {entry.hop_depth}):\n{entry.content}")
    return "\n\n".join(blocks)


async def deliver_entries_with_run(
    db: AsyncSession,
    *,
    project_id: str,
    agent: str,
    entry_ids: List[str],
    run: Run,
) -> List[InboundQueueEntry]:
    """Atomically stamp exactly *entry_ids* delivered while creating *run*."""
    result = await db.execute(
        select(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.agent == agent,
            InboundQueueEntry.id.in_(entry_ids),
            InboundQueueEntry.state == "queued",
        )
        .order_by(InboundQueueEntry.sequence)
    )
    entries = list(result.scalars().all())
    if [entry.id for entry in entries] != entry_ids:
        raise RuntimeError("queue changed before atomic delivery")
    if run.conversation_id is not None and any(
        entry.conversation_id != run.conversation_id for entry in entries
    ):
        raise RuntimeError("one run cannot deliver entries from different conversations")
    now = datetime.now(timezone.utc)
    db.add(run)
    for entry in entries:
        entry.state = "delivered"
        entry.delivered_in_run_id = run.id
        entry.delivered_at = now
    await db.commit()
    return entries


async def return_run_entries(db: AsyncSession, run_id: str) -> List[str]:
    result = await db.execute(
        select(InboundQueueEntry).where(
            InboundQueueEntry.delivered_in_run_id == run_id,
            InboundQueueEntry.state == "delivered",
        )
    )
    entries = list(result.scalars().all())
    for entry in entries:
        entry.state = "queued"
        entry.delivered_in_run_id = None
        entry.delivered_at = None
    return [entry.id for entry in entries]


async def withdraw_entry(
    db: AsyncSession, project_id: str, entry_id: str
) -> Optional[InboundQueueEntry]:
    result = await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.project_id != project_id or entry.state != "queued":
        return None
    entry.state = "withdrawn"
    entry.withdrawn_at = datetime.now(timezone.utc)
    await db.commit()
    return entry
