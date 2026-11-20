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

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_lifecycle
from .db.models import Conversation, SpecDocument


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
