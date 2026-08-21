"""Saving a submitted payload: validate, mint, render, write, record.

One function does the whole write because the steps are not independently
useful and half of them leaving a trace would be worse than none. A payload that
fails validation must leave the file exactly as it was — no partial document —
so nothing touches disk until everything that can be refused has been.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    spec_rigor,
)
from .db.models import InboundQueueEntry, SpecDocument, SpecDocumentMerge, SpecEditProposal
from .project_workspace import ProjectWorkspace
from .spec_manifest import Manifest
from .spec_payload import (
    PayloadError,
    SpecPayload,
    extract_payload,
    payload_to_dict,
    validate_payload,
)
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
class ProposeResult:
    """What a `contract`/`gate`-rigor submission produced, instead of a write.

    `openspec/changes/2026-08-17-authoring-rigor-and-scope` design D1: the live document is
    untouched; `proposals` names what was created (one dict per changed unit — `id`, `unit_kind`,
    `unit_key`, `change_kind`), and `unchanged` names units the submission left identical to what
    is stored (including `"metadata"` when nothing in the non-requirement bundle differed) — not an
    error, just nothing to propose.
    """

    path: str
    phase: str
    proposals: List[Dict[str, Any]] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)


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


class ProposalRefusedError(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """An accept/reject that may not happen, with the reason and a machine-readable code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


async def mint_document_path(
    session: AsyncSession, project_id: str, workspace: ProjectWorkspace
) -> str:
    """A free placeholder path, free against both the records and the disk.

    A name is only available if nothing at all occupies it: a document the
    project has recorded, or a file somebody put there by hand.

    Shared by every route that starts an exploration with no caller-supplied
    path — the operator's `POST /project/documents` and the agent's
    `POST /agent-actions/spec/documents/create` — so there is exactly one
    definition of "taken" to keep consistent.
    """
    recorded = {
        document.path for document in await spec_lifecycle.list_documents(session, project_id)
    }

    def is_taken(candidate: str) -> bool:
        return candidate in recorded or spec_documents.document_exists(workspace, candidate)

    return spec_naming.mint_placeholder_path(is_taken)


async def save_document(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    raw_payload: Any,
    *,
    actor: spec_lifecycle.Actor,
) -> Any:
    """Store a submission against an existing document — or, at `contract`/`gate` rigor, propose it.

    Incompleteness is reported, not refused: a document under discussion is
    incomplete by definition, and it is the transition to `proposed` that cares.
    What *is* refused is a submission against an approved document — silently
    rewriting what an operator approved would make the approval meaningless.

    A capability document is written only by the operator — never by an agent, whatever its run —
    and a document's `kind` is fixed at creation: nothing here may reclassify what a document *is*.
    Both are checked before the approved-document refusal, the same way that refusal is checked
    before anything else, because none of the three depend on the document's phase to make sense.

    The operator reaches this through two paths, and the check below distinguishes neither: a merge
    absorbing an approved change, and a direct write. This docstring used to say "through a merge",
    which was narrower than the check it described — it forbids non-operators, and says nothing
    about mechanism. That wording is why the operator's direct-write route went unbuilt for long
    enough that `spec-document-authority`'s own scenario ("the same submission from the operator
    succeeds") could only be exercised by calling this function in-process.

    Returns a `SaveResult` at `sketch` rigor (unchanged from before this function gained a second
    branch) or a `ProposeResult` at `contract`/`gate` — `openspec/changes/2026-08-17-authoring-rigor-and-scope`
    design D1. One tool, one payload shape; whether it applies immediately or waits for an operator
    to accept it is the document's own property, read from `document.rigor`, never the caller's
    choice.
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
            "capability documents are written by the operator",
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

    if document.rigor in (spec_rigor.CONTRACT, spec_rigor.GATE):
        return await propose_edit(session, document, payload, stored_before, actor=actor)

    return await _apply_and_write(
        session, workspace, document, payload, stored_before, existing_content, actor=actor
    )


async def _apply_and_write(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    payload: SpecPayload,
    stored_before: Optional[Dict[str, Any]],
    existing_content: Optional[str],
    *,
    actor: spec_lifecycle.Actor,
    extra_detail: Optional[Dict[str, Any]] = None,
) -> SaveResult:
    """Mint, render, write and record — the write every accepted payload goes through.

    Shared by `save_document`'s `sketch`-rigor path and `accept_proposal`'s applied unit, so a
    `contract`/`gate` document's accepted proposal gets identity minting, rendering, reindexing and
    completeness reporting exactly as a direct `sketch` write does — not a second, looser
    implementation of the same thing (the same reasoning `merge_document` already states for reusing
    this function's predecessor).
    """
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
        extra_detail=extra_detail,
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


# The non-requirement fields treated as one unit (design D2): everything a submission carries
# except the per-requirement list (which gets its own, finer-grained diff) and the Hub-owned
# identity block (which an agent's submission cannot meaningfully "change" — `_apply_and_write`
# overwrites it unconditionally regardless of what a submission echoes back). Deliberately every
# other top-level field, not a fixed enumeration: a payload field this module does not yet know
# about diffing by name would otherwise be silently dropped by a `contract`/`gate` submission —
# neither applied (the whole point of gating) nor proposed (nothing built anywhere to review it) —
# which is a worse failure than folding it into the one bundle unit that already exists.
_METADATA_EXCLUDED_KEYS = {"requirements", spec_identity.IDENTITY_FIELD}


def _metadata_bundle(payload_dict: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload_dict.items() if k not in _METADATA_EXCLUDED_KEYS}


async def propose_edit(
    session: AsyncSession,
    document: SpecDocument,
    payload: SpecPayload,
    stored_before: Optional[Dict[str, Any]],
    *,
    actor: spec_lifecycle.Actor,
) -> ProposeResult:
    """Diff a `contract`/`gate` submission against what is stored; record one proposal per change.

    Design D2. Requirement units are matched by **key** — never a minted identifier, which a
    brand-new (`add`) unit does not have until its proposal is accepted and the normal
    `_apply_and_write`/`spec_identity.mint` path finally runs. The non-requirement fields are one
    unit (`_metadata_bundle`, above). A submission identical to what is stored creates zero
    proposals and is not an error — resubmitting unchanged content is not a mistake.
    """
    submitted = payload_to_dict(payload)
    stored_requirements: Dict[str, Dict[str, Any]] = {
        entry["key"]: entry
        for entry in (stored_before or {}).get("requirements") or []
        if isinstance(entry, dict) and entry.get("key")
    }
    submitted_requirements = [
        entry for entry in submitted.get("requirements") or [] if isinstance(entry, dict)
    ]

    proposals: List[Dict[str, Any]] = []
    unchanged: List[str] = []
    seen_keys: set = set()
    previous_key: Optional[str] = None

    for entry in submitted_requirements:
        key = entry.get("key")
        if not key:
            continue
        seen_keys.add(key)
        existing = stored_requirements.get(key)
        if existing is None:
            proposals.append(
                await _create_proposal(
                    session,
                    document,
                    unit_kind="requirement",
                    unit_key=key,
                    change_kind="add",
                    position_after_key=previous_key,
                    proposed_payload=entry,
                    previous_payload=None,
                    actor=actor,
                )
            )
        elif existing != entry:
            proposals.append(
                await _create_proposal(
                    session,
                    document,
                    unit_kind="requirement",
                    unit_key=key,
                    change_kind="modify",
                    position_after_key=None,
                    proposed_payload=entry,
                    previous_payload=existing,
                    actor=actor,
                )
            )
        else:
            unchanged.append(key)
        previous_key = key

    for key, existing in stored_requirements.items():
        if key in seen_keys:
            continue
        proposals.append(
            await _create_proposal(
                session,
                document,
                unit_kind="requirement",
                unit_key=key,
                change_kind="remove",
                position_after_key=None,
                proposed_payload={},
                previous_payload=existing,
                actor=actor,
            )
        )

    metadata_new = _metadata_bundle(submitted)
    metadata_old = _metadata_bundle(stored_before or {})
    if metadata_new != metadata_old:
        proposals.append(
            await _create_proposal(
                session,
                document,
                unit_kind="metadata",
                unit_key="metadata",
                change_kind="modify",
                position_after_key=None,
                proposed_payload=metadata_new,
                previous_payload=metadata_old if stored_before else None,
                actor=actor,
            )
        )
    else:
        unchanged.append("metadata")

    return ProposeResult(
        path=document.path, phase=document.phase, proposals=proposals, unchanged=unchanged
    )


async def _create_proposal(
    session: AsyncSession,
    document: SpecDocument,
    *,
    unit_kind: str,
    unit_key: str,
    change_kind: str,
    position_after_key: Optional[str],
    proposed_payload: Dict[str, Any],
    previous_payload: Optional[Dict[str, Any]],
    actor: spec_lifecycle.Actor,
) -> Dict[str, Any]:
    proposal = SpecEditProposal(
        id=f"spprop-{short_id()}",
        document_id=document.id,
        unit_kind=unit_kind,
        unit_key=unit_key,
        change_kind=change_kind,
        position_after_key=position_after_key,
        proposed_payload=proposed_payload,
        previous_payload=previous_payload,
        expected_digest=document.content_digest,
        status="pending",
        proposer_actor_kind=actor.kind,
        proposer_actor_name=actor.name or "",
        proposer_run_id=actor.run_id,
    )
    session.add(proposal)
    await session.flush()
    return {
        "id": proposal.id,
        "unit_kind": unit_kind,
        "unit_key": unit_key,
        "change_kind": change_kind,
    }


def _apply_unit(stored_before: Dict[str, Any], proposal: SpecEditProposal) -> Dict[str, Any]:
    """The full payload dict `proposal` would produce, applied on top of `stored_before`.

    Fed into `validate_payload` and then `_apply_and_write` — accepting one unit still writes the
    whole document, because rendering has never worked any other way; this is what reconstructs
    "the whole document, with just this unit changed" from a proposal that only ever stored the
    changed unit.
    """
    if proposal.unit_kind == "metadata":
        merged: Dict[str, Any] = {
            k: v for k, v in stored_before.items() if k not in _METADATA_EXCLUDED_KEYS
        }
        merged["requirements"] = list(stored_before.get("requirements") or [])
        merged.update(proposal.proposed_payload)
        return merged

    merged = dict(stored_before)
    requirements = list(merged.get("requirements") or [])
    index = next(
        (i for i, entry in enumerate(requirements) if entry.get("key") == proposal.unit_key), None
    )
    if proposal.change_kind == "remove":
        if index is not None:
            requirements.pop(index)
    else:
        if index is not None:
            requirements[index] = proposal.proposed_payload
        elif proposal.change_kind == "add":
            insert_at = 0
            if proposal.position_after_key:
                after_index = next(
                    (
                        i
                        for i, entry in enumerate(requirements)
                        if entry.get("key") == proposal.position_after_key
                    ),
                    None,
                )
                insert_at = after_index + 1 if after_index is not None else len(requirements)
            requirements.insert(insert_at, proposal.proposed_payload)
        else:
            requirements.append(proposal.proposed_payload)
    merged["requirements"] = requirements
    return merged


async def accept_proposal(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    proposal: SpecEditProposal,
    *,
    actor: spec_lifecycle.Actor,
    expected_digest: Optional[str] = None,
) -> SaveResult:
    """Apply one pending proposal's unit to the live document, or refuse and say why.

    Design D4/D5. Operator-only, enforced here — not only at the API boundary, the same discipline
    `spec_rigor.set_rigor` and `spec_lifecycle.transition` already apply to their own operator-only
    acts. Two independent staleness checks: `expected_digest` (if the caller supplies one) is the
    operator's own last-seen digest, mirroring `RigorRequest`'s use of the same name; the proposal's
    own `expected_digest` (always checked) is D5's compare-and-swap against what the document
    actually was when this proposal was created. Either mismatch refuses rather than applies.
    """
    if actor.kind != "operator":
        raise ProposalRefusedError(
            "only the operator can accept a proposal", code="accept_is_the_operators"
        )
    if proposal.status != "pending":
        raise ProposalRefusedError(
            f"this proposal is {proposal.status}, not pending", code="proposal_not_pending"
        )
    if (
        expected_digest is not None
        and document.content_digest is not None
        and expected_digest != document.content_digest
    ):
        raise ProposalRefusedError(
            "the document changed since you read it; re-read it and decide again",
            code="stale_digest",
        )
    if document.content_digest != proposal.expected_digest:
        proposal.status = "stale"
        proposal.resolved_at = datetime.now(timezone.utc)
        proposal.resolved_by_actor_name = actor.name or ""
        raise ProposalRefusedError(
            "the document changed since this proposal was created; it is now stale, not accepted",
            code="proposal_stale",
        )

    existing_content = spec_documents.read_document(workspace, document.path)
    stored_before = extract_payload(existing_content) if existing_content else {}
    merged = _apply_unit(stored_before or {}, proposal)
    try:
        payload = validate_payload(merged)
    except PayloadError as exc:
        raise SaveRefusedError(str(exc), code="payload_invalid", field_path=exc.field) from exc

    result = await _apply_and_write(
        session,
        workspace,
        document,
        payload,
        stored_before,
        existing_content,
        actor=actor,
        extra_detail={
            "proposal_id": proposal.id,
            "proposer_actor_kind": proposal.proposer_actor_kind,
            "proposer_actor_name": proposal.proposer_actor_name,
        },
    )
    proposal.status = "accepted"
    proposal.resolved_at = datetime.now(timezone.utc)
    proposal.resolved_by_actor_name = actor.name or ""
    return result


async def reject_proposal(
    session: AsyncSession,
    proposal: SpecEditProposal,
    *,
    actor: spec_lifecycle.Actor,
    reason: str = "",
) -> None:
    """Refuse a pending proposal, leaving the live document untouched — "no residue" is automatic.

    Design D4/F2: the live document was never written for this proposal, so there is nothing on
    the document itself to clean up.
    """
    if actor.kind != "operator":
        raise ProposalRefusedError(
            "only the operator can reject a proposal", code="reject_is_the_operators"
        )
    if proposal.status != "pending":
        raise ProposalRefusedError(
            f"this proposal is {proposal.status}, not pending", code="proposal_not_pending"
        )
    proposal.status = "rejected"
    proposal.resolved_at = datetime.now(timezone.utc)
    proposal.resolved_by_actor_name = actor.name or ""
    proposal.resolution_reason = reason


async def merge_document(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    capability_document: SpecDocument,
    source_documents: List[SpecDocument],
    raw_payload: Any,
    *,
    actor: spec_lifecycle.Actor,
    note: str = "",
) -> SaveResult | ProposeResult:
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

    At `contract`/`gate` rigor `save_document` proposes instead of writing (a `ProposeResult`, not
    a `SaveResult`) — nothing folded yet, only recorded for the operator to accept or reject. No
    `SpecDocumentMerge` row is written for that outcome: the table's job is to audit folds that
    actually happened, and a pending proposal is not one. The caller distinguishes the two return
    types the same way `agent_actions.py:1155` already does for a plain `save_document` call.

    Committing and broadcasting `spec_updated` is the caller's job too, the same way it is for
    every other route in `spec.py` — this function only prepares the session.
    """
    result = await save_document(session, workspace, capability_document, raw_payload, actor=actor)
    if isinstance(result, ProposeResult):
        return result
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


async def rerender_corpus(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    manifest: Manifest,
    rows: List[SpecDocument],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Re-render every document whose corpus navigation or map no longer matches its file.

    corpus-aware-documents §4. Every document in the manifest is a candidate — what stays
    bounded (design D2) is the *write*, not the read: each candidate's freshly rendered bytes
    are compared against what its file already holds, and only a real difference is written.
    Comparing rendered bytes rather than manifest structure alone is deliberate: a structural
    diff (parent, order) would miss a child's summary being filled in after the fact (design
    D8, §6.7's content backlog) — that edits no manifest field, so a structure-only comparison
    would leave a parent's map showing "no summary yet" forever. Reindex already reads every
    document once for the requirement index (`spec_index.reindex_project`) and again for
    `corpus_summaries`; rendering every candidate for a byte comparison costs no new order of
    I/O, and it is operator-triggered, not on a hot path.

    Driven from each file's own embedded payload (design D6), never the database, so this works
    identically for a document the Hub created and one that arrived by clone. A document whose
    file carries no readable payload is skipped and reported, never guessed at (design D6).
    """
    summaries = spec_documents.corpus_summaries(workspace, manifest)
    by_path = {row.path: row for row in rows}
    actor = spec_lifecycle.Actor(kind="system", name="reindex")

    rerendered: List[str] = []
    skipped: List[Dict[str, Any]] = []

    for entry in manifest.documents:
        current = spec_documents.read_document(workspace, entry.path)
        if current is None:
            skipped.append({"path": entry.path, "reason": "file_missing"})
            continue
        stored = extract_payload(current)
        if stored is None:
            skipped.append({"path": entry.path, "reason": "no_readable_payload"})
            continue
        try:
            payload = validate_payload(stored)
        except PayloadError:
            skipped.append({"path": entry.path, "reason": "no_readable_payload"})
            continue

        identifiers, _ = spec_identity.read_identity(stored)
        # A path filed in the manifest always has a row today (`build_index` only files
        # documents that are both on disk and known to the Hub) — the fallback below is
        # defensive, not reachable through that route, so a future caller that files a
        # rowless document does not lose its phase and rigor rather than crashing.
        document = by_path.get(entry.path)
        phase = document.phase if document is not None else entry.status
        rigor = document.rigor if document is not None else "sketch"
        context = spec_documents.build_corpus_context(manifest, entry.path, summaries)
        rendered = render_document(
            payload,
            identifiers,
            phase=phase,
            stored_payload=stored,
            rigor=rigor,
            corpus=context,
        )
        if rendered == current:
            continue

        spec_documents.write_document(workspace, entry.path, rendered)
        rerendered.append(entry.path)

        # A document with no row has no digest to update and nothing to attribute the event
        # to — it is re-rendered too (design D7), just without either.
        if document is not None:
            document.content_digest = spec_lifecycle.digest(rendered)
            await spec_lifecycle.record_event(
                session,
                document,
                kind="rerendered",
                actor=actor,
                detail={"path": entry.path},
            )

    return rerendered, skipped
