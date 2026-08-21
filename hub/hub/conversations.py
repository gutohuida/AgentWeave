"""Stable AgentWeave conversation identity helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import (
    CONVERSATION_ORIGINS,
    CONVERSATION_TITLE_MAX_LENGTH,
    Conversation,
    InboundQueueEntry,
    PermissionRequest,
    Question,
    Run,
)
from .utils import short_id


def title_from_message(text: str, *, limit: int = CONVERSATION_TITLE_MAX_LENGTH) -> str:
    """Name a conversation from its first message. Pure — no database, no model.

    Truncates at a word boundary, so a title never ends mid-word. Returns "" when the message
    has no text to name it with; the caller leaves the title unset rather than storing a blank.

    One case has no clean answer: a single "word" longer than the limit (a URL, a pasted blob).
    Backing off to a word boundary would return nothing at all, so it is cut at the limit —
    storing something readable beats storing nothing.
    """
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    cut = collapsed[:limit]
    boundary = cut.rfind(" ")
    if boundary <= 0:
        return cut
    return cut[:boundary].rstrip()


#: The one posture that is never carried into a conversation the operator did not open. Removing
#: every check is a deliberate choice for a thread being watched; reaching runs started by a peer
#: or a job, by a route the operator cannot see, is not what choosing it meant.
UNINHERITED_PERMISSION_MODE = "bypassPermissions"


async def inherit_runtime_overrides(session: AsyncSession, conversation: Conversation) -> None:
    """Carry the agent's most recent runtime overrides into a conversation that states none.

    Overrides are held per conversation, and a trigger naming no conversation opens a new one. The
    operator's interface always names one; a job and a peer message do not. Without this, an
    operator sets a posture, an agent hands work to another agent, that agent replies — and the run
    which follows has a posture nobody chose, silently, in the middle of configured work.

    This gives a starting point, not a shared setting: the values are copied, so changing one
    conversation's overrides later leaves the other's alone. `checkpoint_cutover` already does the
    same thing at the handoff boundary, for the same stated reason.
    """
    if conversation.runtime_overrides:
        return
    result = await session.execute(
        select(Conversation.runtime_overrides)
        .where(
            Conversation.project_id == conversation.project_id,
            Conversation.agent == conversation.agent,
            Conversation.id != conversation.id,
            Conversation.runtime_overrides.is_not(None),
        )
        # `sequence`, not `created_at`: two conversations created inside the same clock tick
        # (Windows' default timer granularity is ~15.6ms) tie on `created_at`, and the tie is
        # broken arbitrarily by whatever order SQLite happens to return matching rows in — not by
        # which one is actually more recent. `sequence` is monotonic and gapless-enough to answer
        # "most recent" correctly even inside one tick.
        .order_by(Conversation.sequence.desc())
        .limit(1)
    )
    previous = result.scalars().first()
    if not previous:
        return
    inherited = {
        key: value
        for key, value in previous.items()
        if not (key == "permission_mode" and value == UNINHERITED_PERMISSION_MODE)
    }
    conversation.runtime_overrides = inherited or None


def new_conversation(*, project_id: str, agent: str, origin: str) -> Conversation:
    """Build an unsaved conversation.

    `origin` is required rather than defaulted: a conversation's provenance can only be known
    where it is created, and a default would silently record every peer- and job-created
    conversation as something the operator started.
    """
    if origin not in CONVERSATION_ORIGINS:
        raise ValueError(f"origin must be one of {CONVERSATION_ORIGINS}, got {origin!r}")
    now = datetime.now(timezone.utc)
    conversation_id = f"conv-{short_id()}"
    return Conversation(
        id=conversation_id,
        project_id=project_id,
        agent=agent,
        lifecycle="open",
        origin=origin,
        # Its own lineage until a checkpoint cutover says otherwise
        # (`checkpoint_cutover.py`, conversations-continue phase 2).
        lineage_id=conversation_id,
        created_at=now,
        updated_at=now,
    )


def name_conversation(conversation: Conversation, text: str) -> None:
    """Name an unnamed conversation from the message being queued into it.

    A no-op once the conversation has a title, so it is safe to call on every queued entry and
    so neither a later message nor a generated title can displace what named the thread.
    """
    if conversation.title:
        return
    title = title_from_message(text)
    if title:
        conversation.title = title


async def get_conversation_by_id(
    db: AsyncSession, conversation_id: Optional[str]
) -> Optional[Conversation]:
    """Look a conversation up by its stable `conv-` id.

    Not `session.get(Conversation, conversation_id)`: the primary key is `sequence`, an
    autoincrement integer, not `id` — `session.get()` looks up by primary key, so it would compare
    a `conv-…` string against an integer column and never match. Every call site that used to read
    `db.get(Conversation, ...)` reads this instead.
    """
    if conversation_id is None:
        return None
    result = await db.execute(select(Conversation).where(Conversation.id == conversation_id))
    return result.scalar_one_or_none()


async def get_open_conversation(
    db: AsyncSession, *, project_id: str, agent: str, conversation_id: str
) -> Optional[Conversation]:
    conversation = await get_conversation_by_id(db, conversation_id)
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
        # `sequence`, not `created_at`, breaks an `updated_at` tie: see the reasoning on the
        # `.order_by(Conversation.sequence.desc())` call above, in `inherit_runtime_overrides`.
        .order_by(Conversation.updated_at.desc(), Conversation.sequence.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def peer_bound_conversation(
    db: AsyncSession,
    *,
    project_id: str,
    recipient: str,
    sender_conversation_id: Optional[str],
    sender: str,
) -> Optional[Conversation]:
    """The open conversation a peer message from this sender is bound to, if one exists.

    Keyed on the *sender's* conversation, so a sender's separate lines of work reach separate
    recipient threads and a second message on the same line reaches the same one. The Hub and the
    scheduler have no source conversation, so their traffic keys on the sender's identity instead
    — one stable thread per system sender, rather than falling back to recency.

    Filters on `open` and takes the newest: a binding whose thread the operator archived resolves
    to the successor bound to the same sender, not to the archived one.
    """
    conditions = [
        Conversation.project_id == project_id,
        Conversation.agent == recipient,
        Conversation.lifecycle == "open",
    ]
    if sender_conversation_id:
        conditions.append(Conversation.bound_sender_conversation_id == sender_conversation_id)
    else:
        # Both halves matter: without the NULL check a senderless message could resolve onto a
        # thread bound to one of that sender's conversations, which is a different binding.
        conditions.append(Conversation.bound_sender_agent == sender)
        conditions.append(Conversation.bound_sender_conversation_id.is_(None))
    result = await db.execute(
        select(Conversation).where(*conditions).order_by(Conversation.sequence.desc()).limit(1)
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


async def backfill_titles(db: AsyncSession, conversations: List[Conversation]) -> None:
    """Name any conversation that predates titling, from its first message.

    Lazy rather than a data migration (design.md's migration plan): a migration would have to
    reproduce `title_from_message` in SQL, and a conversation whose entries were pruned has no
    title to derive either way. Untitled rows are listed as new, never as their identifier.

    One query for the whole page, and it commits only when something was actually named.
    """
    untitled = [c.id for c in conversations if not c.title]
    if not untitled:
        return

    rows = await db.execute(
        select(InboundQueueEntry.conversation_id, InboundQueueEntry.content)
        .where(InboundQueueEntry.conversation_id.in_(untitled))
        .order_by(InboundQueueEntry.conversation_id, InboundQueueEntry.arrived_at)
    )
    first_message: Dict[str, str] = {}
    for conversation_id, content in rows:
        if conversation_id and conversation_id not in first_message:
            first_message[conversation_id] = content

    named = False
    for conversation in conversations:
        if conversation.title:
            continue
        title = title_from_message(first_message.get(conversation.id, ""))
        if title:
            conversation.title = title
            named = True
    if named:
        await db.commit()


async def conversation_id_for_run(db: AsyncSession, run_id: Optional[str]) -> Optional[str]:
    """The conversation a run belongs to, for stamping onto a row the run creates.

    Read once at creation rather than joined at read time — see design.md, "Attention state is
    denormalised onto the three blocking tables".
    """
    if not run_id:
        return None
    result = await db.execute(select(Run.conversation_id).where(Run.id == run_id))
    return result.scalar_one_or_none()


async def archivable(db: AsyncSession, conversation: Conversation) -> Optional[str]:
    """Why this conversation cannot be archived, or None when it can be.

    Two obstructions, both refused rather than resolved. Stopping a live run from a row menu
    destroys work with no undo. An undelivered queue entry is worse than a preference:
    `latest_open_conversation` filters on `open`, so archiving strands the entry permanently —
    the next peer message opens a fresh conversation and nothing ever delivers the old one.
    """
    if conversation.lifecycle == "archived":
        return None

    running = await db.execute(
        select(Run.id)
        .where(Run.conversation_id == conversation.id, Run.status == "running")
        .limit(1)
    )
    if running.scalar_one_or_none() is not None:
        return "This conversation has a run in progress. Wait for it to finish, or stop it first."

    queued = await db.execute(
        select(InboundQueueEntry.id)
        .where(
            InboundQueueEntry.conversation_id == conversation.id,
            InboundQueueEntry.state == "queued",
        )
        .limit(1)
    )
    if queued.scalar_one_or_none() is not None:
        return (
            "This conversation has messages waiting to be delivered. Archiving it would strand "
            "them, because nothing delivers into an archived conversation."
        )
    return None


async def conversation_attention(
    db: AsyncSession, conversation_ids: Iterable[str]
) -> Dict[str, str]:
    """Map each conversation id to "running", "waiting" or "idle".

    Waiting outranks running: a run blocked on a question is still a running process, but what
    the operator needs to see is that it stopped for them.
    """
    ids: List[str] = list(conversation_ids)
    if not ids:
        return {}

    attention: Dict[str, str] = dict.fromkeys(ids, "idle")

    running = await db.execute(
        select(Run.conversation_id).where(Run.conversation_id.in_(ids), Run.status == "running")
    )
    for cid in running.scalars():
        if cid:
            attention[cid] = "running"

    waiting_queries = (
        select(Question.conversation_id).where(
            Question.conversation_id.in_(ids), Question.answered.is_(False)
        ),
        select(PermissionRequest.conversation_id).where(
            PermissionRequest.conversation_id.in_(ids), PermissionRequest.status == "pending"
        ),
    )
    for query in waiting_queries:
        result = await db.execute(query)
        for cid in result.scalars():
            if cid:
                attention[cid] = "waiting"

    return attention


def archive(conversation: Conversation) -> None:
    """Mark a conversation archived. Callers check `archivable` first."""
    conversation.lifecycle = "archived"
    conversation.archived_at = datetime.now(timezone.utc)


def unarchive(conversation: Conversation) -> None:
    """Reopen an archived conversation. Always permitted — nothing is blocked by reopening."""
    conversation.lifecycle = "open"
    conversation.archived_at = None
