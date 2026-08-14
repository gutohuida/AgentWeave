"""Durable per-agent inbound queue primitives."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Conversation, InboundQueueEntry, Project, Run
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
    divergence_source_run_id: Optional[str] = None,
) -> InboundQueueEntry:
    if origin_type not in ("operator", "agent", "job", "checkpoint", "divergence"):
        raise ValueError(
            "origin_type must be 'operator', 'agent', 'job', 'checkpoint', or 'divergence'"
        )
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
        divergence_source_run_id=divergence_source_run_id,
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


#: Failed deliveries of one entry before the next turn starts a fresh provider session.
#:
#: Not 1: a single failure is routinely a Hub restart or a transient spawn error, and discarding a
#: live provider session costs the agent its whole provider-side context irreversibly. Strictly
#: below `DELIVERY_ATTEMPT_LIMIT`, or the fresh session is never actually tried.
RESUME_RETRY_LIMIT = 2

#: Failed deliveries before the Hub stops retrying and says so.
#:
#: Exactly one attempt on the original session, one that trips the reset, and one on a fresh
#: session — the third is what distinguishes "the session was poisoned" from "the input is
#: poisoned". Fewer, and a Hub restart could discard an operator's message; more, and an agent is
#: wedged across four failing turns before anyone is told.
DELIVERY_ATTEMPT_LIMIT = 3


async def return_run_entries(db: AsyncSession, run_id: str) -> List[str]:
    """Put a failed run's input back, unless putting it back is what keeps failing.

    Returning an entry keeps it lost-proof, and used to be unconditional. But a returned entry
    keeps its place in arrival order *and* its binding to the conversation it arrived on, and the
    scheduler adopts the oldest queued entry's conversation for the turn — so if that conversation's
    provider session cannot be resumed, every delivery re-kills the runtime and every later input,
    including a request for a fresh conversation, queues behind the one doing the killing. Observed
    live: four entries, four consecutive failures, no way through.

    So: count the attempt; at `RESUME_RETRY_LIMIT` give up on the provider session, which is what
    actually breaks the loop; at `DELIVERY_ATTEMPT_LIMIT` give up on the entry and record why.

    `conversation_id` is deliberately *not* cleared — an entry belonging to no conversation cannot
    be scheduled at all, so it would wedge silently and forever, strictly worse than today.
    `arrived_at` is deliberately not bumped: ordering is by `sequence`, so it would change nothing
    about scheduling and only hide how long the input has been stuck.

    Returns the ids that went back to `queued`, as it always has. Abandoned ids are reported
    separately by `abandoned_for_run`, so a caller that only wants the requeued set is unaffected.
    """
    result = await db.execute(
        select(InboundQueueEntry).where(
            InboundQueueEntry.delivered_in_run_id == run_id,
            InboundQueueEntry.state == "delivered",
        )
    )
    entries = list(result.scalars().all())
    requeued: List[str] = []
    for entry in entries:
        entry.delivery_attempts = (entry.delivery_attempts or 0) + 1
        entry.delivered_at = None

        if entry.delivery_attempts >= RESUME_RETRY_LIMIT and entry.conversation_id:
            # The one change that breaks the loop. Cleared rather than flagged, because
            # `session_mode` is derived from whether this is set — so clearing it makes the next
            # delivery a fresh start, and the turn after that re-binds whatever session it gets.
            conversation = await db.get(Conversation, entry.conversation_id)
            if conversation is not None and conversation.provider_session_id is not None:
                conversation.provider_session_id = None

        if entry.delivery_attempts >= DELIVERY_ATTEMPT_LIMIT:
            entry.state = "withdrawn"
            entry.withdrawn_at = datetime.now(timezone.utc)
            entry.abandoned_reason = (
                f"delivery failed {entry.delivery_attempts} times; the Hub stopped retrying"
            )
            # `delivered_in_run_id` is deliberately kept: it is the operator's breadcrumb from a
            # dropped message to the run that ate it.
            continue

        entry.state = "queued"
        entry.delivered_in_run_id = None
        requeued.append(entry.id)
    return requeued


async def abandoned_for_run(db: AsyncSession, run_id: str) -> List[InboundQueueEntry]:
    """The entries this run's failure gave up on, so the caller can report them."""
    result = await db.execute(
        select(InboundQueueEntry).where(
            InboundQueueEntry.delivered_in_run_id == run_id,
            InboundQueueEntry.state == "withdrawn",
            InboundQueueEntry.abandoned_reason.is_not(None),
        )
    )
    return list(result.scalars().all())


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
