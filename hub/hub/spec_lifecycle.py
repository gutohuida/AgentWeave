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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import SPEC_KINDS, SpecDocument, SpecDocumentEvent
from .utils import short_id

if TYPE_CHECKING:
    from .project_workspace import ProjectWorkspace

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
    # A finished, shipped change becomes history. There is no transition out of `archived`.
    (APPROVED, ARCHIVED),
    # Retiring a document that produced nothing (F37).
    #
    # This was previously `approved`-only, on the reasoning that "the existing reopen transitions
    # already give the operator a way to walk a document backwards without inventing a second kind
    # of 'done'." That holds for undoing a proposal — but walking backwards ends at `exploring`,
    # and `exploring` had no exit at all. Confirmed live 2026-08-25: an agent created a second
    # document by mistake and the empty original was unreachable in every direction. `archived`
    # needs `approved`, `approved` needs `proposed`, `proposed` needs requirements the orphan does
    # not have, and there is no `DELETE`. It is not inert either — it leaves a standing spec
    # manifest drift warning that nobody can clear.
    #
    # The concern about a second meaning of "done" is answered by the guard below rather than by
    # the phase map: these two edges are refused for any document that has produced requirements or
    # tasks. So `archived` reached this way can only ever mean "this document was a mistake", never
    # "this work was abandoned" — which really would be a different thing, and still is not
    # expressible.
    (EXPLORING, ARCHIVED),
    (PROPOSED, ARCHIVED),
    # Retiring a capability that no longer describes the product (F536): operator-only, with a
    # reason, never while open work serves it. Its requirements are retired by the index
    # (`spec_index.reindex_document`); like any archived document it has no way back.
    (CURRENT, ARCHIVED),
}


class PhaseError(RuntimeError):
    """A transition that may not happen, with the reason stated."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "phase_refused",
        blocking: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.code = code
        # Set only for `document_incomplete`: every reason the move is not yet possible.
        self.blocking: List[Dict[str, Any]] = list(blocking or [])
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


async def approved_document_paths(session: AsyncSession, project_id: str) -> set:
    """Paths of this project's currently-`approved` documents.

    Current phase, not "ever approved" — `first_approved_at` answers that question for the rename
    rule (design D6), a different question. An import needs the referenced document's task to
    exist *now*; that is only guaranteed while the document is approved, which is when
    `materialise()` runs. Used by `spec_completeness.check()` to decide whether an import names
    something real.
    """
    result = await session.execute(
        select(SpecDocument.path).where(
            SpecDocument.project_id == project_id, SpecDocument.phase == APPROVED
        )
    )
    return set(result.scalars().all())


async def create_document(
    session: AsyncSession,
    project_id: str,
    path: str,
    *,
    actor: Actor,
    title: str = "",
    kind: str = "change-spec",
    phase: Optional[str] = None,
) -> SpecDocument:
    """A new document, in `exploring` — or in `current`, if it is a capability document.

    Explore is the one phase that would otherwise precede its own document,
    which is why the entry point creates the document rather than setting a mode
    on the conversation: without it, "propose" and "approve" have no subject.

    A capability document has no exploration to close and nothing to propose — it describes
    current, shipped behaviour and is written directly by the operator (`spec_service.py`), either
    by merging an approved change into it or by writing its content outright. It is created at
    `current` and this is the only place a document's phase is ever set there.

    `phase`, when given, is the phase a document already has — read from a file being adopted
    (`spec_adoption`), where the file is the only account of a lifecycle this machine never
    walked. Every ordinary creation omits it and is unaffected.

    **This is not a way to promote a document.** It is reachable only where no row exists, which
    is the one moment there is nothing to promote: the alternative for an adopted `approved`
    document is `transition()`, and that would require walking it through `proposed` and calling
    `approve` — inventing a history that did not happen in order to record one that did. A row
    that already exists is refused above, before this argument is reached.
    """
    # Same reason the `phase` check below exists, for the column beside it: `kind` carries a CHECK
    # constraint (`ck_spec_documents_kind`), so an unrecognised value reached the flush and came
    # back as an unhandled `IntegrityError` — `500 Internal Server Error`, with nothing in it to
    # act on. Found by driving the surface 2026-08-28 (F112), and the near-miss is the likely
    # input: `"change"` is what a caller guesses from a path of `spec/changes/…` and a default
    # reported as `"change-spec"`, and it was the case that produced the 500.
    if kind not in SPEC_KINDS:
        raise PhaseError(
            f"unknown document kind {kind!r}; a document is one of: {', '.join(SPEC_KINDS)}",
            code="unknown_kind",
        )
    if phase is not None:
        if phase not in (EXPLORING, PROPOSED, APPROVED, ARCHIVED, CURRENT):
            raise PhaseError(f"unknown phase {phase!r}", code="unknown_phase")
        # `current` and `capability` imply each other, and the database says so in
        # a cross-column check. Stated here too so the refusal names the problem
        # rather than surfacing as an IntegrityError from the flush below.
        if (kind == "capability") != (phase == CURRENT):
            raise PhaseError(
                f"a {kind} document cannot be in {phase}; current is where capability "
                "documents live and nowhere else",
                code="phase_not_holdable",
            )

    existing = await get_document(session, project_id, path)
    if existing is not None:
        raise PhaseError(f"a document already exists at {path}", code="document_exists")

    document = SpecDocument(
        id=f"spdoc-{short_id()}",
        project_id=project_id,
        path=path,
        title=title,
        kind=kind,
        phase=phase or (CURRENT if kind == "capability" else EXPLORING),
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
    workspace: ProjectWorkspace,
    reason: str = "",
    no_capability_change: bool = False,
    absorbed_by: Optional[str] = None,
) -> SpecDocumentEvent:
    """Move a document between phases, or refuse and say why.

    **Archiving an approved change is a close-out.** It is refused while a task the document
    declared is still open, and until a merge names the change or the operator states, with a
    reason, that it changes no capability (`no_capability_change`): `archived` has no way back, and
    a shipped change whose requirements live in no capability must not become history (F509).

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

    if to_phase == ARCHIVED and document.phase in (EXPLORING, PROPOSED):
        # What keeps the two edges added for F37 meaning "this document was a mistake" rather than
        # becoming a way to bury work that exists. Imported here rather than at module scope: this
        # module is the one every phase write passes through, and `Task` reaches back into it.
        from .db.models import SpecRequirement, Task

        produced = await session.scalar(
            select(SpecRequirement.id).where(SpecRequirement.document_id == document.id).limit(1)
        ) or await session.scalar(
            select(Task.id).where(Task.spec_document_id == document.id).limit(1)
        )
        if produced is not None:
            raise PhaseError(
                "this document has produced requirements or tasks, so archiving it from "
                f"{document.phase} would retire work that still exists. Approve it and archive "
                "that, or reopen it and decide about the work first.",
                code="archive_would_orphan_work",
            )

    if to_phase == ARCHIVED and document.phase == CURRENT:
        await _check_retirement(session, document, reason=reason, absorbed_by=absorbed_by)

    if to_phase == ARCHIVED and document.phase == APPROVED and document.kind == "change-spec":
        open_tasks = await open_task_ids(session, document)
        if open_tasks:
            raise PhaseError(
                "this change still has open tasks (" + ", ".join(open_tasks) + "); approve or "
                "reject each before archiving it",
                code="archive_tasks_open",
            )
        if not await merged_into(session, document) and not (
            no_capability_change and reason.strip()
        ):
            raise PhaseError(
                "this change has not been folded into a capability. Fold it, or archive it "
                "stating no_capability_change with a reason",
                code="archive_not_folded",
            )

    if to_phase in (PROPOSED, APPROVED):
        # Required `workspace`: a caller with none cannot move a document at all, rather than
        # moving it unchecked (F207). Imported here because `spec_service` imports this module.
        from . import spec_service

        blocking = await spec_service.phase_blockers(session, workspace, document, to_phase)
        if blocking:
            raise PhaseError(
                f"this document cannot move to {to_phase} yet: "
                + ", ".join(b["code"] for b in blocking),
                code="document_incomplete",
                blocking=blocking,
            )

    previous = document.phase
    document.phase = to_phase
    if to_phase == EXPLORING:
        # Reopening genuinely reopens: the next proposal needs the operator to
        # say again that exploration is done.
        document.explore_closed_at = None
    if to_phase == APPROVED and document.first_approved_at is None:
        # Set once, never reset. `explore_closed_at` above answers "is exploration closed right
        # now"; this answers "has this path ever been signed off on" — see the column's own
        # comment in db/models.py. A later archive-then-reopen must not clear it.
        document.first_approved_at = datetime.now(timezone.utc)

    detail: Dict[str, Any] = {"from": previous, "to": to_phase, "reason": reason}
    if previous == CURRENT:
        detail["absorbed_by"] = absorbed_by
    return await record_event(session, document, kind="phase", actor=actor, detail=detail)


async def _check_retirement(
    session: AsyncSession, document: SpecDocument, *, reason: str, absorbed_by: Optional[str]
) -> None:
    """What retiring a capability needs (F536): a reason, a real absorber, and no open work.

    Open work is a task neither approved nor rejected that links one of the capability's active
    requirements: retiring would leave it serving requirements nobody holds any more.
    """
    from .db.models import SpecRequirement, Task, TaskRequirementLink

    if not reason.strip():
        raise PhaseError(
            "retiring a capability needs a reason: say why it no longer describes the product",
            code="retire_needs_reason",
        )
    if absorbed_by is not None:
        absorber = await get_document(session, document.project_id, absorbed_by)
        if (
            absorber is None
            or absorber.id == document.id
            or absorber.kind != "capability"
            or absorber.phase != CURRENT
        ):
            raise PhaseError(
                f"{absorbed_by} is not another current capability, so it cannot have absorbed "
                "this one",
                code="absorber_invalid",
            )
    rows = await session.execute(
        select(Task.id)
        .join(TaskRequirementLink, TaskRequirementLink.task_id == Task.id)
        .join(SpecRequirement, SpecRequirement.id == TaskRequirementLink.requirement_id)
        .where(
            SpecRequirement.document_id == document.id,
            SpecRequirement.state == "active",
            Task.status.notin_(_TASK_DONE),
        )
        .order_by(Task.created_at, Task.id)
    )
    open_tasks = list(dict.fromkeys(rows.scalars()))
    if open_tasks:
        raise PhaseError(
            "open tasks still serve this capability's requirements ("
            + ", ".join(open_tasks)
            + "); approve, reject or relink each before retiring it",
            code="capability_has_open_work",
        )


#: Task statuses after which a task asks nothing more of anyone.
_TASK_DONE = ("approved", "rejected")


async def open_task_ids(session: AsyncSession, document: SpecDocument) -> List[str]:
    """The tasks a document declared that are neither approved nor rejected, oldest first."""
    from .db.models import Task

    rows = await session.execute(
        select(Task.id)
        .where(Task.spec_document_id == document.id, Task.status.notin_(_TASK_DONE))
        .order_by(Task.created_at, Task.id)
    )
    return list(rows.scalars())


async def merged_into(session: AsyncSession, document: SpecDocument) -> List[str]:
    """Paths of the capability documents a merge has folded this change into, in merge order."""
    from .db.models import SpecDocumentMerge

    rows = await session.execute(
        select(SpecDocument.path, SpecDocumentMerge.created_at)
        .join(SpecDocumentMerge, SpecDocumentMerge.capability_document_id == SpecDocument.id)
        .where(SpecDocumentMerge.change_document_id == document.id)
        .order_by(SpecDocumentMerge.created_at)
    )
    return list(dict.fromkeys(path for path, _ in rows))


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
