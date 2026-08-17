"""Document phase, attributed history, and divergence detection.

The rule this module exists to make true: **an agent cannot approve a
document.** Not "is instructed not to" — cannot. There is no argument, payload
field or document content that reaches `approve`, because approval is a function
only an operator actor can call, and the phase is read from a database row
rather than from the file the agent can write.

That is the property the skill-based gate never had. `aw-spec-apply.md` enforced
approval by telling the agent to grep the document's own status metadata and
stop if it did not say `approved` — the agent checking its own permission slip,
in a file the agent could edit.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import SpecDocument, SpecDocumentEvent
from .utils import short_id

EXPLORING = "exploring"
PROPOSED = "proposed"
APPROVED = "approved"
ARCHIVED = "archived"
# A capability document's phase, and the only phase `transition()` never accepts as a `to_phase` —
# the one door into `current` is document creation (`create_document`, below), not this function.
CURRENT = "current"

# Every legal move. A transition not in this table does not happen, including
# any that would move a document backwards without an explicit decision.
TRANSITIONS = {
    (EXPLORING, PROPOSED),
    (PROPOSED, APPROVED),
    # Sending an approved or proposed document back for more work is the
    # operator's call, and it is a decision worth recording rather than a
    # silent edit.
    (PROPOSED, EXPLORING),
    (APPROVED, EXPLORING),
    # A finished, shipped change becomes history. Scoped to `approved` only — an abandoned
    # exploration or proposal is a different situation, and the existing reopen transitions
    # already give the operator a way to walk a document backwards without inventing a second
    # kind of "done." There is no transition out of `archived`.
    (APPROVED, ARCHIVED),
}


class PhaseError(RuntimeError):
    """A transition that may not happen, with the reason stated."""

    def __init__(self, message: str, *, code: str = "phase_refused") -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class Actor:
    """Who is acting, established from a credential rather than a request body."""

    kind: str  # "operator" | "agent" | "system"
    name: str = ""
    run_id: Optional[str] = None

    @property
    def origin(self) -> str:
        if self.kind == "agent":
            return "submission"
        if self.kind == "operator":
            return "control"
        return "lifecycle"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def record_event(
    session: AsyncSession,
    document: SpecDocument,
    *,
    kind: str,
    actor: Actor,
    detail: Optional[Dict[str, Any]] = None,
) -> SpecDocumentEvent:
    """Append one event. There is no update and no delete — by construction, not by policy."""
    event = SpecDocumentEvent(
        id=f"spev-{short_id()}",
        document_id=document.id,
        project_id=document.project_id,
        kind=kind,
        actor_kind=actor.kind,
        actor=actor.name or "",
        origin=actor.origin,
        run_id=actor.run_id,
        detail=detail or {},
    )
    session.add(event)
    return event


async def get_document(session: AsyncSession, project_id: str, path: str) -> Optional[SpecDocument]:
    result = await session.execute(
        select(SpecDocument).where(SpecDocument.project_id == project_id, SpecDocument.path == path)
    )
    return result.scalars().first()


async def list_documents(session: AsyncSession, project_id: str) -> List[SpecDocument]:
    result = await session.execute(
        select(SpecDocument).where(SpecDocument.project_id == project_id)
    )
    return list(result.scalars().all())


async def create_document(
    session: AsyncSession,
    project_id: str,
    path: str,
    *,
    actor: Actor,
    title: str = "",
    kind: str = "change-spec",
) -> SpecDocument:
    """A new document, in `exploring` — or in `current`, if it is a capability document.

    Explore is the one phase that would otherwise precede its own document,
    which is why the entry point creates the document rather than setting a mode
    on the conversation: without it, "propose" and "approve" have no subject.

    A capability document has no exploration to close and nothing to propose — it describes
    current, shipped behaviour and is written directly, through a merge (`spec_service.py`). It is
    created at `current` and this is the only place a document's phase is ever set there.
    """
    existing = await get_document(session, project_id, path)
    if existing is not None:
        raise PhaseError(f"a document already exists at {path}", code="document_exists")

    document = SpecDocument(
        id=f"spdoc-{short_id()}",
        project_id=project_id,
        path=path,
        title=title,
        kind=kind,
        phase=CURRENT if kind == "capability" else EXPLORING,
    )
    session.add(document)
    await session.flush()
    await record_event(session, document, kind="created", actor=actor, detail={"path": path})
    return document


async def record_content(
    session: AsyncSession,
    document: SpecDocument,
    *,
    actor: Actor,
    content: str,
    digests: Dict[str, str],
    title: str,
    extra_detail: Optional[Dict[str, Any]] = None,
) -> SpecDocumentEvent:
    """Note that the document's content was rewritten, and by whom.

    `digests` comes from `spec_digest.payload_digests` — the same values the
    requirement index stores, computed once by the caller. Recomputing them here
    from a different input is how the row and the index would come to disagree
    about whether a requirement changed.

    Takes no `kind` — a document's kind is fixed at creation (`create_document`) and the caller
    (`spec_service.save_document`) has already refused a payload whose `kind` disagrees with
    `document.kind` before this function is ever reached, so there is nothing left for it to vary.

    `extra_detail`, when given, is merged into the event's `detail` dict alongside `requirements`.
    Additive only — every existing caller passes nothing and is unaffected. The one caller that
    does (`spec_service.accept_proposal`, `openspec/changes/2026-08-17-authoring-rigor-and-scope`
    design D4) uses it to cite the `SpecEditProposal` this write came from, rather than growing this
    function a second `accepter` parameter: the proposal row already carries full proposer and
    accepter identity, and `SpecDocumentEvent.actor` staying "who wrote the file" — the accepter, for
    an accepted proposal, consistent with every other content-write event — needs no schema change.
    """
    document.title = title
    document.content_digest = digest(content)
    document.requirement_digests = dict(digests)
    detail: Dict[str, Any] = {"requirements": sorted(digests)}
    if extra_detail:
        detail.update(extra_detail)
    return await record_event(
        session,
        document,
        kind="content",
        actor=actor,
        detail=detail,
    )


async def transition(
    session: AsyncSession,
    document: SpecDocument,
    *,
    to_phase: str,
    actor: Actor,
    reason: str = "",
) -> SpecDocumentEvent:
    """Move a document between phases, or refuse and say why.

    **Approval is an operator act.** An agent reaching this function with
    `to_phase="approved"` is refused here as well as at the API boundary,
    because a rule enforced in one place is a rule that survives exactly as long
    as nobody adds a second caller.

    **So is archiving**, the same shape and the same reasoning. `current` is deliberately absent
    from the phases this function accepts as a `to_phase` at all — a capability document is created
    at `current` (`create_document`) and never moves there, or anywhere, through this function.
    """
    if to_phase not in (EXPLORING, PROPOSED, APPROVED, ARCHIVED):
        raise PhaseError(f"unknown phase {to_phase!r}", code="unknown_phase")

    if document.phase == to_phase:
        raise PhaseError(f"the document is already {to_phase}", code="phase_unchanged")

    if (document.phase, to_phase) not in TRANSITIONS:
        raise PhaseError(
            f"a document cannot move from {document.phase} to {to_phase}",
            code="illegal_transition",
        )

    if to_phase == APPROVED and actor.kind != "operator":
        raise PhaseError(
            "only the operator can approve a document",
            code="approval_is_the_operators",
        )

    if to_phase == ARCHIVED and actor.kind != "operator":
        raise PhaseError(
            "only the operator can archive a document",
            code="archive_is_the_operators",
        )

    if to_phase == PROPOSED and document.explore_closed_at is None:
        raise PhaseError(
            "exploration has not been closed; the operator decides when it is complete",
            code="explore_not_closed",
        )

    previous = document.phase
    document.phase = to_phase
    if to_phase == EXPLORING:
        # Reopening genuinely reopens: the next proposal needs the operator to
        # say again that exploration is done.
        document.explore_closed_at = None

    return await record_event(
        session,
        document,
        kind="phase",
        actor=actor,
        detail={"from": previous, "to": to_phase, "reason": reason},
    )


async def close_exploration(session: AsyncSession, document: SpecDocument, *, actor: Actor) -> None:
    """The operator declaring exploration finished.

    Whether an exploration is "complete enough to propose from" is not
    mechanically checkable, and pretending otherwise would put a model in the
    path of a gate. So this is a decision, made by a person, recorded. The
    mechanical half — does the document validate — is checked separately.
    """
    if actor.kind != "operator":
        raise PhaseError(
            "only the operator can declare exploration complete",
            code="explore_close_is_the_operators",
        )
    document.explore_closed_at = datetime.now(timezone.utc)
    await record_event(
        session, document, kind="phase", actor=actor, detail={"explore_closed": True}
    )


def divergence(document: SpecDocument, content_on_disk: Optional[str]) -> Optional[Tuple[str, str]]:
    """`(recorded, found)` when the file no longer matches what the Hub wrote.

    Reporting only. Resolving a divergence means choosing whose version wins,
    and that is the operator's decision — the Hub surfacing both and waiting is
    the whole rule.
    """
    if document.content_digest is None or content_on_disk is None:
        return None
    found = digest(content_on_disk)
    if found == document.content_digest:
        return None
    return document.content_digest, found
