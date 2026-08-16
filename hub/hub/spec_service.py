"""Saving a submitted payload: validate, mint, render, write, record.

One function does the whole write because the steps are not independently
useful and half of them leaving a trace would be worse than none. A payload that
fails validation must leave the file exactly as it was — no partial document —
so nothing touches disk until everything that can be refused has been.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from . import (
    requirement_links,
    spec_completeness,
    spec_digest,
    spec_documents,
    spec_identity,
    spec_index,
    spec_lifecycle,
    spec_naming,
)
from .db.models import InboundQueueEntry, SpecDocument, SpecDocumentMerge
from .project_workspace import ProjectWorkspace
from .spec_payload import PayloadError, extract_payload, payload_to_dict, validate_payload
from .spec_render import render_document
from .utils import short_id


@dataclass
class SaveResult:
    path: str
    phase: str
    identifiers: Dict[str, str] = field(default_factory=dict)
    blocking: List[Dict[str, Any]] = field(default_factory=list)
    divergence: Optional[Dict[str, str]] = None


@dataclass
class RenameResult:
    path: str
    previous_path: str


class SaveRefusedError(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """The submission cannot be stored, with the reason and where it applies."""

    def __init__(self, message: str, *, code: str, field_path: str = "") -> None:
        self.code = code
        self.field_path = field_path
        super().__init__(message)


async def save_document(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    raw_payload: Any,
    *,
    actor: spec_lifecycle.Actor,
) -> SaveResult:
    """Store a submission against an existing document.

    Incompleteness is reported, not refused: a document under discussion is
    incomplete by definition, and it is the transition to `proposed` that cares.
    What *is* refused is a submission against an approved document — silently
    rewriting what an operator approved would make the approval meaningless.

    A capability document is written only by the operator, through a merge — never by an ordinary
    submission, whoever the caller — and a document's `kind` is fixed at creation: nothing here may
    reclassify what a document *is*. Both are checked before the approved-document refusal, the
    same way that refusal is checked before anything else, because none of the three depend on the
    document's phase to make sense.
    """
    try:
        payload = validate_payload(raw_payload)
    except PayloadError as exc:
        raise SaveRefusedError(str(exc), code="payload_invalid", field_path=exc.field) from exc

    if payload.kind != document.kind:
        raise SaveRefusedError(
            f"this document is {document.kind!r}; a submission cannot change what a document is",
            code="kind_is_fixed",
        )

    if document.kind == "capability" and actor.kind != "operator":
        raise SaveRefusedError(
            "capability documents are written by the operator, through a merge",
            code="capability_write_is_the_operators",
        )

    if document.phase == spec_lifecycle.APPROVED:
        raise SaveRefusedError(
            "this document is approved; reopen it before changing what was approved",
            code="document_approved",
        )

    # Identity carries forward from whatever is on disk, so a key that already
    # holds an identifier keeps it. A file that has been replaced by hand simply
    # has no identity block, and every key is then new — which is why the
    # divergence below is reported rather than swallowed.
    existing_content = spec_documents.read_document(workspace, document.path)
    stored_before = extract_payload(existing_content) if existing_content else None
    previous_map, high_water = spec_identity.read_identity(stored_before)

    keys = [requirement.key for requirement in payload.requirements]
    identifiers, mark = spec_identity.mint(keys, previous_map, high_water)
    retired = spec_identity.retained(previous_map, keys, spec_identity.read_retired(stored_before))

    # One computation of what a requirement means, shared by the document row and
    # the index. Two would disagree eventually, and the disagreement would show
    # as one surface calling evidence stale while another called it current.
    digests = spec_digest.payload_digests(payload, identifiers)
    carried = spec_identity.carried_digests(
        digests, spec_identity.read_digests(stored_before), retired
    )

    stored = payload_to_dict(payload)
    # Hub-owned, and overwritten unconditionally. An agent that submits an
    # identity block does not get to keep it.
    stored[spec_identity.IDENTITY_FIELD] = spec_identity.identity_block(
        identifiers, mark, retired, carried
    )

    content = render_document(
        payload,
        identifiers,
        phase=document.phase,
        stored_payload=stored,
        # From the row, never from the submission. An agent that could state a rigor in a payload
        # could lower a gate that is blocking it, which is the one thing this must not permit.
        rigor=document.rigor,
    )

    divergence = spec_lifecycle.divergence(document, existing_content)

    spec_documents.write_document(workspace, document.path, content)

    await spec_lifecycle.record_content(
        session,
        document,
        actor=actor,
        content=content,
        digests=digests,
        title=payload.title,
    )

    # Reindexed in the same transaction that recorded the write. An index that
    # could be a save behind would answer "what serves this requirement?" about a
    # document that no longer exists in that form.
    await spec_index.reindex_document(
        session,
        document,
        spec_index.requirements_from_payload(stored) or [],
        actor=actor,
        source=spec_index.SOURCE_HUB,
    )

    board_served = await requirement_links.served_keys(session, document.id)
    return SaveResult(
        path=document.path,
        phase=document.phase,
        identifiers=identifiers,
        blocking=[
            finding.to_dict()
            for finding in spec_completeness.check(payload, board_served=board_served)
        ],
        divergence=({"recorded": divergence[0], "found": divergence[1]} if divergence else None),
    )


async def merge_document(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    capability_document: SpecDocument,
    source_documents: List[SpecDocument],
    raw_payload: Any,
    *,
    actor: spec_lifecycle.Actor,
    note: str = "",
) -> SaveResult:
    """Fold a finished change's content into a capability document, by explicit authored merge.

    Resolving the path arguments to documents and refusing an unfinished or mistargeted merge
    (design D5 steps 1-4) is the API handler's job, matching this file's existing split between
    "the API resolves what a path names" and "the service acts once it has documents in hand." This
    function does the write: the content lands through `save_document`, the same function every
    other content write uses, so every one of its refusals (malformed payload, kind mismatch) and
    every one of its side effects (identity minting, rendering, reindexing) apply here exactly as
    they would to any other caller — not a second, looser implementation of the same thing. One
    `SpecDocumentMerge` row per named source records that this specific fold happened and who did
    it; one `"merged"` event on the capability document is the single copy of that fact in the
    per-document history a reader already knows to check (no matching event on the source's side —
    `spec_document_merges` already answers "what did this change's merge do" by querying
    `change_document_id`).

    Committing and broadcasting `spec_updated` is the caller's job too, the same way it is for
    every other route in `spec.py` — this function only prepares the session.
    """
    result = await save_document(session, workspace, capability_document, raw_payload, actor=actor)
    for source in source_documents:
        session.add(
            SpecDocumentMerge(
                id=f"spmrg-{short_id()}",
                project_id=capability_document.project_id,
                capability_document_id=capability_document.id,
                change_document_id=source.id,
                actor_kind=actor.kind,
                actor=actor.name or "",
                run_id=actor.run_id,
                note=note,
            )
        )
        await spec_lifecycle.record_event(
            session,
            capability_document,
            kind="merged",
            actor=actor,
            detail={"change_document_id": source.id, "note": note},
        )
    return result


async def rename_document(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    subject: str,
    *,
    actor: spec_lifecycle.Actor,
) -> RenameResult:
    """Give a document the name its subject earned.

    The caller supplies prose and the Hub derives the path. It is not an
    oversight that there is no way to pass a path: `validate_spec_path` is the
    single control keeping a document from being written to an arbitrary
    location beneath `spec/`, and a rename that accepted a destination would
    expose that control to the least trusted caller in the system as its only
    guard. Deriving a slug makes a traversal, a hidden segment or a different
    filename unexpressible rather than merely rejected.

    Everything that can be refused is refused before anything moves. The
    filesystem move goes last because a transaction rolls back and a file move
    does not.
    """
    if document.phase == spec_lifecycle.APPROVED:
        raise SaveRefusedError(
            "this document is approved; its path is part of what was approved",
            code="document_approved",
        )

    new_path = spec_naming.document_path_for(subject)
    if new_path is None:
        raise SaveRefusedError(
            "that subject yields no usable name; say in words what the document is about",
            code="subject_unusable",
            field_path="subject",
        )

    previous_path = document.path
    if new_path == previous_path:
        return RenameResult(path=previous_path, previous_path=previous_path)

    occupant = await spec_lifecycle.get_document(session, document.project_id, new_path)
    if occupant is not None:
        raise SaveRefusedError(
            f"another document already occupies {new_path}",
            code="document_exists",
        )
    if spec_documents.document_exists(workspace, new_path):
        raise SaveRefusedError(
            f"a file already exists at {new_path}",
            code="path_occupied",
        )

    document.path = new_path
    # The subject is why the rename happened, so it is the document's title from here. Leaving the
    # placeholder in place meant every surface that lists documents showed a name contradicting the
    # document's own location until some later save happened to correct it.
    document.title = subject.strip() or document.title
    await _repoint_pending_input(session, document.project_id, previous_path, new_path)
    spec_documents.move_document(workspace, previous_path, new_path)
    await spec_lifecycle.record_event(
        session,
        document,
        kind="renamed",
        actor=actor,
        detail={"from": previous_path, "to": new_path, "subject": subject},
    )
    return RenameResult(path=new_path, previous_path=previous_path)


async def _repoint_pending_input(
    session: AsyncSession, project_id: str, previous_path: str, new_path: str
) -> None:
    """Point queued turns at the document's new path.

    A queue entry carries the path that was open when it was queued, because a
    busy agent's turn starts from a later scheduler call than the one that
    queued it. A rename in between would otherwise hand the agent a path that no
    longer resolves.

    Only undelivered entries. A delivered entry records what was open when its
    turn ran, and rewriting history to keep it tidy is how a record stops being
    one.
    """
    await session.execute(
        update(InboundQueueEntry)
        .where(
            InboundQueueEntry.project_id == project_id,
            InboundQueueEntry.spec_document == previous_path,
            InboundQueueEntry.delivered_at.is_(None),
        )
        .values(spec_document=new_path)
    )


async def propose(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    *,
    actor: spec_lifecycle.Actor,
) -> List[Dict[str, Any]]:
    """Move a document to `proposed`, or return what is blocking it.

    The completeness checks run against the payload the document actually
    carries, not against a claim about it. A document whose file no longer
    parses cannot be proposed at all — there is nothing to check.
    """
    content = spec_documents.read_document(workspace, document.path)
    stored = extract_payload(content) if content else None
    if stored is None:
        raise SaveRefusedError(
            "this document carries no payload to check; it has not been written by the Hub",
            code="no_payload",
        )

    try:
        payload = validate_payload(stored)
    except PayloadError as exc:
        raise SaveRefusedError(str(exc), code="payload_invalid", field_path=exc.field) from exc

    board_served = await requirement_links.served_keys(session, document.id)
    findings = spec_completeness.check(payload, board_served=board_served)
    if findings:
        return [finding.to_dict() for finding in findings]

    await spec_lifecycle.transition(
        session, document, to_phase=spec_lifecycle.PROPOSED, actor=actor
    )
    await rerender_phase(session, workspace, document)
    return []


async def rerender_phase(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
) -> None:
    """Rewrite the document so its visible status matches the phase.

    The metadata in the file is a copy for whoever reads it, never the
    authority. It is refreshed here so the two do not disagree in front of an
    operator — but if this fails, the phase in the database is still what
    counts.
    """
    content = spec_documents.read_document(workspace, document.path)
    stored = extract_payload(content) if content else None
    if stored is None:
        return
    try:
        payload = validate_payload(stored)
    except PayloadError:
        return
    identifiers, _ = spec_identity.read_identity(stored)
    rewritten = render_document(
        payload, identifiers, phase=document.phase, stored_payload=stored, rigor=document.rigor
    )
    spec_documents.write_document(workspace, document.path, rewritten)
    document.content_digest = spec_lifecycle.digest(rewritten)
