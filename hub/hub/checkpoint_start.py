"""Starting a new conversation from a checkpoint, for any agent of the project.

Not a cutover (`checkpoint_cutover.py`). A cutover continues *the* line of work: it is bound to
the checkpoint's own conversation and agent, archives the predecessor, and can happen once. A start
is the operator handing a written state to whichever agent they choose, as often as they like, and
it touches nothing about where the checkpoint came from — not the conversation, its runs or queue,
and not `Checkpoint.cut_over_to_conversation_id`, so an offered checkpoint can still be carried
over afterwards (`start-a-conversation-from-any-checkpoint-with-any-agent`, FR-6).

What it writes is one new conversation, recording the checkpoint in `started_from_checkpoint_id`,
and one queue entry holding the checkpoint (and the operator's message, in the same turn). The turn
is scheduled at once: the operator's confirm is the Continue (FR-5).
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from sqlalchemy import select

from .checkpoint_cutover import delivery_content
from .conversations import CONVERSATION_TITLE_MAX_LENGTH, new_conversation
from .db.models import Agent, Checkpoint, Conversation
from .inbound_queue import new_entry

logger = logging.getLogger(__name__)

_STARTED_PREFIX = "From checkpoint: "


class StartRefusedError(RuntimeError):
    """The start cannot go ahead; the message says why. Nothing has been written."""


def started_title(checkpoint: Checkpoint) -> str:
    """The new conversation's title: the checkpoint's, marked as where it started (FR-8).

    Set as the operator's, as a cutover successor's is, so the titler never replaces it; the
    operator renames it like any other.
    """
    base = (checkpoint.title or "").strip() or f"{checkpoint.agent}'s checkpoint {checkpoint.id}"
    return f"{_STARTED_PREFIX}{base}"[:CONVERSATION_TITLE_MAX_LENGTH]


def authorship_note(checkpoint: Checkpoint, reader: str) -> str:
    """What another agent reads before a checkpoint it did not write (FR-3).

    A checkpoint is written about its own agent: it lists "every task assigned to this agent", its
    questions and its overrides. Read bare by somebody else, that is taken as the reader's state.
    """
    author = checkpoint.agent
    return (
        f"The checkpoint below was written in {author}'s conversation {checkpoint.conversation_id}, "
        f'not in one of yours, {reader}. Where it says "this agent", it means {author}: the tasks '
        f"it lists are {author}'s, not yours, and so are its open questions and overrides. The "
        "operator chose to start you from it; take the state of the work from it, and act as "
        f"{reader}.\n\n"
    )


def first_input(checkpoint: Checkpoint, agent: str, message: Optional[str]) -> str:
    """The new conversation's first input: note (another agent only), checkpoint, message."""
    content = delivery_content(checkpoint)
    if agent != checkpoint.agent:
        content = authorship_note(checkpoint, agent) + content
    if message:
        content += f"\n\n---\n\nThe operator adds:\n\n{message}"
    return content


async def _open_agent(db, project_id: str, name: str) -> Agent:
    agent = (
        (await db.execute(select(Agent).where(Agent.project_id == project_id, Agent.name == name)))
        .scalars()
        .first()
    )
    if agent is None:
        raise StartRefusedError(f"There is no agent named {name!r} in this project.")
    if agent.lifecycle != "open":
        raise StartRefusedError(
            f"{name} is archived. Restore the agent, or start the conversation with an open one."
        )
    return agent


async def start_from_checkpoint(
    db,
    checkpoint: Checkpoint,
    *,
    agent: str,
    message: Optional[str] = None,
) -> Tuple[Conversation, str]:
    """Create the conversation and its first input, and commit. The caller schedules the turn.

    The checkpoint is the caller's, already checked to be in this project. Refused, writing
    nothing, when it was never written or the agent is not an open agent of the project (FR-10).
    The checkpoint-reading grant is not consulted (FR-9): the operator, who can read every
    checkpoint, is choosing what to hand over.

    The conversation carries no runtime overrides — not the original's and not the agent's latest
    (`inherit_runtime_overrides` is deliberately not called): choosing an agent is often choosing
    its model, and an inherited override would quietly undo that (FR-2).
    """
    if checkpoint.status != "ready":
        raise StartRefusedError(
            f"Checkpoint {checkpoint.id} is {checkpoint.status!r}: it was never written, so there "
            "is nothing to start from. Only a ready checkpoint can start a conversation."
        )
    chosen = await _open_agent(db, checkpoint.project_id, agent)
    text = (message or "").strip() or None

    conversation = new_conversation(
        project_id=checkpoint.project_id, agent=chosen.name, origin="operator"
    )
    conversation.title = started_title(checkpoint)
    conversation.title_set_by_operator = True
    conversation.started_from_checkpoint_id = checkpoint.id
    db.add(conversation)

    entry = new_entry(
        project_id=checkpoint.project_id,
        agent=chosen.name,
        origin_type="checkpoint",
        content=first_input(checkpoint, chosen.name, text),
        hop_depth=0,
        conversation_id=conversation.id,
        session_mode="new",
        awaits_continue=False,
    )
    db.add(entry)
    conversation_id, entry_id, checkpoint_id = conversation.id, entry.id, checkpoint.id
    await db.commit()
    logger.info("started %s for %s from checkpoint %s", conversation_id, chosen.name, checkpoint_id)
    return conversation, entry_id


async def started_from(db, checkpoint_ids: List[str]) -> dict:
    """`{checkpoint id: [conversation started from it, ...]}`, oldest first (FR-7).

    The conversation a checkpoint was carried into is not among them: that one is the carry-over,
    found by `cut_over_to_conversation_id`, and was not started this way.
    """
    if not checkpoint_ids:
        return {}
    rows = (
        (
            await db.execute(
                select(Conversation)
                .where(Conversation.started_from_checkpoint_id.in_(checkpoint_ids))
                .order_by(Conversation.sequence)
            )
        )
        .scalars()
        .all()
    )
    listed: dict = {}
    for row in rows:
        listed.setdefault(row.started_from_checkpoint_id, []).append(
            {
                "conversation_id": row.id,
                "agent": row.agent,
                "title": row.title,
                "lifecycle": row.lifecycle,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return listed
