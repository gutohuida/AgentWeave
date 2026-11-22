"""A conversation's open document, which is that conversation's own.

`every-spec-entry-point-leads-into-the-journey`, FR-11 and FR-12 (design D3). The open document
used to be navigation state carried on purpose from one conversation to the next, so a second
conversation working another slice was attached to the first one's spec. It is stored on the
conversation instead (`Conversation.spec_document_id`, migration `0188`) and set by:

- the operator opening a document in the conversation (`PUT .../spec-document`);
- every operator message whose trigger carries a `spec_document` -- Explore's first message among
  them, since Explore creates its document before that message is sent;
- Draft's take and a notice's Open, built on this in later tasks;

and cleared only by stopping exploring there (`PUT .../spec-document` with `path: null`). A message
sent with no document leaves the conversation's document as it is.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_lifecycle
from .db.models import Conversation, Run, SpecDocument, SpecDocumentEvent


async def set_by_path(
    session: AsyncSession, conversation: Conversation, path: Optional[str]
) -> Optional[SpecDocument]:
    """Make the document at `path` the conversation's own, or clear it when `path` is None.

    Returns the document, or None when cleared. Raises `LookupError` for a path that names no
    document in the conversation's project, leaving the conversation as it was. Not committed.
    """
    if path is None:
        conversation.spec_document_id = None
        return None
    document = await spec_lifecycle.get_document(session, conversation.project_id, path)
    if document is None:
        raise LookupError(path)
    conversation.spec_document_id = document.id
    return document


#: Events recording how the operator answered an offer, kept beside the document's own history so
#: no table is needed. They name the conversation in `detail`; neither touches the document.
OFFER_OPENED = "offer_opened"
OFFER_DECLINED = "offer_declined"
OFFER_ANSWERS = {"open": OFFER_OPENED, "not_now": OFFER_DECLINED}


async def offers(session: AsyncSession, conversation: Conversation) -> List[Dict[str, Any]]:
    """Change documents an agent of this conversation created, still awaiting an answer.

    Derived from creation events by runs of this conversation (FR-7). A roadmap has no journey, so
    it is never offered; nor is the conversation's own open document, an archived one, or one the
    operator already answered here (Open or Not now). Oldest first. Each names the run that
    created it (`run_id`) and that run's agent (`created_by`).
    """
    created = (
        await session.execute(
            select(
                SpecDocumentEvent.document_id,
                SpecDocumentEvent.run_id,
                SpecDocumentEvent.created_at,
                Run.agent,
            )
            .join(Run, Run.id == SpecDocumentEvent.run_id)
            .where(
                SpecDocumentEvent.project_id == conversation.project_id,
                SpecDocumentEvent.kind == "created",
                SpecDocumentEvent.actor_kind == "agent",
                Run.conversation_id == conversation.id,
            )
            .order_by(SpecDocumentEvent.created_at)
        )
    ).all()
    answered = {
        row.document_id
        for row in (
            await session.execute(
                select(SpecDocumentEvent).where(
                    SpecDocumentEvent.project_id == conversation.project_id,
                    SpecDocumentEvent.kind.in_(list(OFFER_ANSWERS.values())),
                )
            )
        ).scalars()
        if (row.detail or {}).get("conversation_id") == conversation.id
    }
    out: List[Dict[str, Any]] = []
    seen = set()
    for document_id, run_id, created_at, agent in created:
        if document_id in seen or document_id in answered:
            continue
        seen.add(document_id)
        if document_id == conversation.spec_document_id:
            continue
        document = await session.get(SpecDocument, document_id)
        if (
            document is None
            or document.kind != "change-spec"
            or document.phase != spec_lifecycle.EXPLORING
        ):
            continue
        out.append(
            {
                "path": document.path,
                "title": document.title,
                "phase": document.phase,
                "step": document.step,
                # The run whose turn created it, so the offer is drawn under that turn's message
                # rather than above the composer (F1208), and the agent that ran it.
                "run_id": run_id,
                "created_by": agent,
                "created_at": created_at.isoformat() if created_at else None,
            }
        )
    return out


async def answer_offer(
    session: AsyncSession, conversation: Conversation, path: str, answer: str
) -> Optional[SpecDocument]:
    """Record the operator's `open` or `not_now` for the offered document at `path`.

    `open` makes it the conversation's own; `not_now` changes nothing but hides the offer here.
    Raises `LookupError` for an unknown path and `ValueError` for another answer. Not committed.
    """
    if answer not in OFFER_ANSWERS:
        raise ValueError(answer)
    document = await spec_lifecycle.get_document(session, conversation.project_id, path)
    if document is None:
        raise LookupError(path)
    if answer == "open":
        conversation.spec_document_id = document.id
    await spec_lifecycle.record_event(
        session,
        document,
        kind=OFFER_ANSWERS[answer],
        actor=spec_lifecycle.Actor(kind="operator"),
        detail={"conversation_id": conversation.id},
    )
    return document


async def attached(session: AsyncSession, conversation: Conversation) -> Optional[Dict[str, Any]]:
    """The conversation's document as `{path, title, phase, step}`, or None.

    An archived document, or one deleted since (its row gone, whether or not the database's
    ON DELETE SET NULL fired), reads as None: there is nothing open to work on.
    """
    if not conversation.spec_document_id:
        return None
    document = await session.get(SpecDocument, conversation.spec_document_id)
    if document is None or document.project_id != conversation.project_id:
        return None
    if document.phase == "archived":
        return None
    return {
        "path": document.path,
        "title": document.title,
        "phase": document.phase,
        "step": document.step,
    }
