"""Saving a submitted payload: validate, mint, render, write, record.

One function does the whole write because the steps are not independently
useful and half of them leaving a trace would be worse than none. A payload that
fails validation must leave the file exactly as it was — no partial document —
so nothing touches disk until everything that can be refused has been.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select, update
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
    KEY_RE,
    PayloadError,
    SpecPayload,
    payload_to_dict,
    validate_payload,
)
from .spec_render import SliceOf, render_document
from .utils import short_id


@dataclass
class SaveResult:
    path: str
    phase: str
    identifiers: Dict[str, str] = field(default_factory=dict)
    blocking: List[Dict[str, Any]] = field(default_factory=list)
    divergence: Optional[Dict[str, str]] = None
    warnings: List[Dict[str, Any]] = field(default_factory=list)


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
    # Units this submission repeated exactly -- the same proposer, content, change, position and
    # document version as a proposal still pending -- named instead of proposed a second time
    # (`a-pending-proposal-can-be-withdrawn`, D1).
    already_pending: List[Dict[str, Any]] = field(default_factory=list)


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
    via: str = "write",
) -> Any:
    """Store a submission against an existing document — or, at `contract`/`gate` rigor, propose it.

    `via` names the path a capability write came by: `"merge"` (`merge_document`) or `"create"`
    (the creation scaffold). A capability's content changes only through a merge, so a direct
    operator write (`"write"`, the default) to one is refused, naming the merge route
    (`a-finished-change-is-folded-into-its-capability`); every other kind is unaffected.

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
    # The kind first, from the raw submission: since validation became kind-aware (C1a D1), a
    # payload of the wrong kind would otherwise be refused for that kind's shape rules, sending the
    # author to fix fields when the document itself is the wrong one.
    raw_kind = raw_payload.get("kind") if isinstance(raw_payload, dict) else None
    if isinstance(raw_kind, str) and raw_kind != document.kind:
        raise SaveRefusedError(
            f"this document is {document.kind!r}; a submission cannot change what a document is",
            code="kind_is_fixed",
        )

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

    if document.kind == "capability" and via == "write":
        raise SaveRefusedError(
            "a capability document's content changes only through a merge: POST "
            f"/project/documents/{document.path}/merge, naming the finished changes it folds in "
            "(or none, for an edit)",
            code="capability_written_through_merge",
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
    stored_before = spec_documents.parse_stored(existing_content)

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

    divergence = spec_lifecycle.divergence(document, existing_content)

    # Stored as the payload plus the row's hub block (FR-1); the page is rendered when it is read.
    content = spec_documents.write_payload(workspace, document.path, stored, hub_block(document))

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
    approved_paths = await spec_lifecycle.approved_document_paths(session, document.project_id)
    roadmaps = await roadmap_states(session, workspace, document.project_id, payload)
    return SaveResult(
        path=document.path,
        phase=document.phase,
        identifiers=identifiers,
        blocking=[
            finding.to_dict()
            for finding in spec_completeness.check(
                payload,
                board_served=board_served,
                approved_document_paths=approved_paths,
                roadmaps=roadmaps,
            )
        ],
        divergence=({"recorded": divergence[0], "found": divergence[1]} if divergence else None),
        warnings=[
            f.to_dict()
            for f in (
                *spec_completeness.overlap_warnings(payload),
                *spec_completeness.undeclared_files_warnings(payload),
                *spec_completeness.test_only_task_warnings(payload),
                *spec_completeness.reviewer_undeclared_warnings(payload),
            )
        ],
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
    # The document's pending proposals, read once (D1): a repeat of one of this proposer's is
    # named rather than proposed again, and whatever of theirs this submission neither repeats nor
    # replaces is superseded at the end (D2).
    pending = list(
        (
            await session.execute(
                select(SpecEditProposal)
                .where(
                    SpecEditProposal.document_id == document.id,
                    SpecEditProposal.status == "pending",
                )
                .order_by(SpecEditProposal.created_at)
            )
        ).scalars()
    )
    mine = [
        row
        for row in pending
        if row.proposer_actor_kind == actor.kind and row.proposer_actor_name == (actor.name or "")
    ]
    already_pending: List[Dict[str, Any]] = []
    kept_ids: set = set()

    async def _propose(**unit: Any) -> None:
        repeat = next(
            (
                row
                for row in mine
                if row.unit_kind == unit["unit_kind"]
                and row.unit_key == unit["unit_key"]
                and row.change_kind == unit["change_kind"]
                and row.position_after_key == unit["position_after_key"]
                and row.proposed_payload == unit["proposed_payload"]
                and row.expected_digest == document.content_digest
            ),
            None,
        )
        if repeat is not None:
            kept_ids.add(repeat.id)
            already_pending.append(
                {
                    "id": repeat.id,
                    "unit_kind": repeat.unit_kind,
                    "unit_key": repeat.unit_key,
                    "change_kind": repeat.change_kind,
                }
            )
            return
        created = await _create_proposal(session, document, actor=actor, **unit)
        kept_ids.add(created["id"])
        proposals.append(created)
        # A revision replaces this proposer's earlier word on the unit (D2).
        for row in mine:
            if (
                row.id not in kept_ids
                and row.unit_kind == unit["unit_kind"]
                and row.unit_key == unit["unit_key"]
            ):
                await _leave_pending(
                    session,
                    row,
                    status="superseded",
                    resolved_by=actor.name or "",
                    reason=f"superseded by {created['id']}",
                )
                kept_ids.add(row.id)  # decided now, whether or not the race was ours

    for entry in submitted_requirements:
        key = entry.get("key")
        if not key:
            continue
        seen_keys.add(key)
        existing = stored_requirements.get(key)
        if existing is None:
            await _propose(
                unit_kind="requirement",
                unit_key=key,
                change_kind="add",
                position_after_key=previous_key,
                proposed_payload=entry,
                previous_payload=None,
            )
        elif existing != entry:
            await _propose(
                unit_kind="requirement",
                unit_key=key,
                change_kind="modify",
                position_after_key=None,
                proposed_payload=entry,
                previous_payload=existing,
            )
        else:
            unchanged.append(key)
        previous_key = key

    for key, existing in stored_requirements.items():
        if key in seen_keys:
            continue
        await _propose(
            unit_kind="requirement",
            unit_key=key,
            change_kind="remove",
            position_after_key=None,
            proposed_payload={},
            previous_payload=existing,
        )

    metadata_new = _metadata_bundle(submitted)
    metadata_old = _metadata_bundle(stored_before or {})
    if metadata_new != metadata_old:
        await _propose(
            unit_kind="metadata",
            unit_key="metadata",
            change_kind="modify",
            position_after_key=None,
            proposed_payload=metadata_new,
            previous_payload=metadata_old if stored_before else None,
        )
    else:
        unchanged.append("metadata")

    # A submission is the proposer's whole document, so it is their current word on every unit.
    # Whatever of theirs it neither repeated nor replaced -- a unit put back as stored, or one no
    # longer mentioned -- they took back (D2, operator review). Without this a `remove` from v1
    # stayed pending after v2 restored the unit, and accepting it deleted what they brought back.
    for row in mine:
        if row.id not in kept_ids:
            await _leave_pending(
                session,
                row,
                status="superseded",
                resolved_by=actor.name or "",
                reason="superseded: the proposer's latest submission leaves this unit as stored",
            )

    return ProposeResult(
        path=document.path,
        phase=document.phase,
        proposals=proposals,
        unchanged=unchanged,
        already_pending=already_pending,
    )


async def _leave_pending(
    session: AsyncSession,
    proposal: SpecEditProposal,
    *,
    status: str,
    resolved_by: str,
    reason: Optional[str] = None,
) -> bool:
    """Move `proposal` out of `pending`, if it is still there. True when this call moved it.

    A conditional UPDATE whose row count is checked, never an attribute write on a row loaded
    earlier (design D7): two requests deciding the same proposal each held it as `pending`, and the
    later write won, turning `accepted` into `rejected`. The shape `questions.py` uses for the same
    race. The row is refreshed either way, so the caller reads what now stands.
    """
    values: Dict[str, Any] = {
        "status": status,
        "resolved_at": datetime.now(timezone.utc),
        "resolved_by_actor_name": resolved_by,
    }
    if reason is not None:
        values["resolution_reason"] = reason
    result = await session.execute(
        update(SpecEditProposal)
        .where(SpecEditProposal.id == proposal.id, SpecEditProposal.status == "pending")
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    await session.refresh(proposal)
    return result.rowcount == 1


def _not_pending(proposal: SpecEditProposal) -> ProposalRefusedError:
    return ProposalRefusedError(
        f"this proposal is {proposal.status}, not pending", code="proposal_not_pending"
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
    reason: str = "",
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
        if not await _leave_pending(
            session, proposal, status="stale", resolved_by=actor.name or ""
        ):
            raise _not_pending(proposal)
        raise ProposalRefusedError(
            "the document changed since this proposal was created; it is now stale, not accepted",
            code="proposal_stale",
        )

    existing_content = spec_documents.read_document(workspace, document.path)
    stored_before = spec_documents.parse_stored(existing_content) or {}
    merged = _apply_unit(stored_before or {}, proposal)
    try:
        payload = validate_payload(merged)
    except PayloadError as exc:
        raise SaveRefusedError(str(exc), code="payload_invalid", field_path=exc.field) from exc

    # Claimed before anything is written, so losing the race to another decision writes no file
    # (D7). `resolution_reason` is kept, as `reject_proposal` keeps its own (F209): the route
    # declared and size-limited this field and then dropped it, leaving *why* a spec change was let
    # in as the one half of the pair the corpus did not record. A write refused below rolls this
    # claim back with the rest of the transaction.
    if not await _leave_pending(
        session, proposal, status="accepted", resolved_by=actor.name or "", reason=reason
    ):
        raise _not_pending(proposal)

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
    if proposal.status != "pending" or not await _leave_pending(
        session, proposal, status="rejected", resolved_by=actor.name or "", reason=reason
    ):
        raise _not_pending(proposal)


async def withdraw_proposal(
    session: AsyncSession,
    proposal: SpecEditProposal,
    *,
    actor: spec_lifecycle.Actor,
    note: str = "",
) -> None:
    """Take a pending proposal off the list without judging it (design D3).

    For twins and proposals nobody is pursuing: a reject records that the edit is wrong, which
    nobody decided. Operator-only, like accept and reject. The live document is untouched.
    """
    if actor.kind != "operator":
        raise ProposalRefusedError(
            "only the operator can withdraw a proposal", code="withdraw_is_the_operators"
        )
    if proposal.status != "pending" or not await _leave_pending(
        session, proposal, status="withdrawn", resolved_by=actor.name or "", reason=note
    ):
        raise _not_pending(proposal)


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
    result = await save_document(
        session, workspace, capability_document, raw_payload, actor=actor, via="merge"
    )
    if isinstance(result, ProposeResult):
        return result
    if not source_documents:
        # A merge naming no change is the operator editing the capability: recorded as one, so
        # every change to a capability's content has a history entry saying where it came from.
        await spec_lifecycle.record_event(
            session,
            capability_document,
            kind="merged",
            actor=actor,
            detail={"change_document_id": None, "edit": True, "note": note},
        )
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


class FoldRefusedError(Exception):
    """A fold the Hub will not perform; raised before anything is written."""

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


@dataclass
class FoldItem:
    """One change requirement to fold, and what the operator changed about it on the way in."""

    key: str
    as_key: Optional[str] = None
    statement: Optional[str] = None
    modal: Optional[str] = None
    replaces: Optional[str] = None


@dataclass
class FoldDraft:
    payload: Dict[str, Any]
    #: One entry per folded requirement: `from` (the change's key), `key` (the capability's), the
    #: text it lands with, and `replaces` when it overwrites an existing capability requirement.
    requirements: List[Dict[str, Any]]
    collisions: List[str]
    #: What the capability holds before the fold, in its order, for choosing what to retire:
    #: `{key, statement}` per requirement, `{key, requirement, then}` per criterion.
    capability_requirements: List[Dict[str, Any]] = field(default_factory=list)
    capability_criteria: List[Dict[str, Any]] = field(default_factory=list)


def fold_key(change_path: str, key: str) -> str:
    """`<change-slug>-<key>`, the slug trimmed from the right so the whole is a valid payload key."""
    slug = change_path.rstrip("/").split("/")[-2]
    room = 64 - len(key) - 1
    if room < 1:
        return key
    return f"{slug[:room].rstrip('-')}-{key}"


def _read(workspace: ProjectWorkspace, document: SpecDocument) -> Dict[str, Any]:
    payload = spec_documents.read_payload(workspace, document.path)
    if payload is None:
        raise FoldRefusedError(f"{document.path} has no readable content", code="fold_unreadable")
    return payload


def fold_draft(
    workspace: ProjectWorkspace,
    change: SpecDocument,
    capability: SpecDocument,
    items: Optional[List[FoldItem]] = None,
    retire: Sequence[str] = (),
    retire_criteria: Sequence[str] = (),
) -> FoldDraft:
    """The capability's payload with the change's requirements appended, and what collides.

    Pure: reads both files and writes nothing. `items` chooses and edits what is folded; `None`
    folds every requirement verbatim under `fold_key`. A draft key the capability already holds is
    a collision, reported and left out of the payload, unless the item names it in `replaces`.
    Criteria follow their requirement, re-pointed at its new key.

    `retire` removes capability requirements the change supersedes, their criteria with them, and
    `retire_criteria` removes single criteria (F533): amending a criterion is retiring the old one
    and folding the new. Both name what the capability holds today, and a requirement cannot be
    replaced and retired in one fold.
    """
    if capability.kind != "capability":
        raise FoldRefusedError(
            f"{capability.path} is not a capability document", code="fold_target_not_capability"
        )
    if capability.phase != spec_lifecycle.CURRENT:
        raise FoldRefusedError(
            f"{capability.path} is retired; nothing is folded into a retired capability",
            code="capability_retired",
        )
    source = _read(workspace, change)
    target = _read(workspace, capability)
    by_key = {r["key"]: r for r in source.get("requirements") or []}
    if items is None:
        items = [FoldItem(key=key) for key in by_key]
    existing = {r["key"] for r in target.get("requirements") or []}
    existing_criteria = {c["key"] for c in target.get("acceptance_criteria") or []}

    requirements = [dict(r) for r in target.get("requirements") or []]
    criteria = [dict(c) for c in target.get("acceptance_criteria") or []]
    folded: List[Dict[str, Any]] = []
    collisions: List[str] = []
    renamed: Dict[str, str] = {}
    for item in items:
        original = by_key.get(item.key)
        if original is None:
            raise FoldRefusedError(
                f"{change.path} has no requirement {item.key!r}", code="fold_unknown_requirement"
            )
        if item.replaces is not None and item.replaces not in existing:
            raise FoldRefusedError(
                f"{capability.path} has no requirement {item.replaces!r} to replace",
                code="fold_replaces_unknown",
            )
        key = item.replaces or item.as_key or fold_key(change.path, item.key)
        if not KEY_RE.match(key):
            raise FoldRefusedError(
                f"{key!r} is not a valid requirement key (lowercase letters, digits and hyphens, "
                "at most 64)",
                code="fold_key_invalid",
            )
        entry = {**original, "key": key}
        if item.statement is not None:
            entry["statement"] = item.statement
        if item.modal is not None:
            entry["modal"] = item.modal
        folded.append(
            {
                "from": item.key,
                "key": key,
                "statement": entry["statement"],
                "modal": entry.get("modal"),
                "replaces": item.replaces,
            }
        )
        if item.replaces is not None:
            requirements = [entry if r["key"] == key else r for r in requirements]
        elif key in existing or key in renamed.values():
            collisions.append(key)
            continue
        else:
            requirements.append(entry)
        renamed[item.key] = key

    for criterion in source.get("acceptance_criteria") or []:
        new_requirement = renamed.get(criterion.get("requirement"))
        if new_requirement is None:
            continue
        key = fold_key(change.path, criterion["key"])
        if key in existing_criteria:
            collisions.append(key)
            continue
        criteria.append({**criterion, "key": key, "requirement": new_requirement})

    unknown = [key for key in retire if key not in existing] + [
        key for key in retire_criteria if key not in existing_criteria
    ]
    if unknown:
        raise FoldRefusedError(
            f"{capability.path} has nothing to retire under " + ", ".join(unknown),
            code="fold_retire_unknown",
        )
    replaced = {item.replaces for item in items if item.replaces is not None}
    both = [key for key in retire if key in replaced]
    if both:
        raise FoldRefusedError(
            ", ".join(both) + " is both replaced and retired by this fold; choose one",
            code="fold_retire_replaced",
        )
    retired = set(retire)
    requirements = [r for r in requirements if r["key"] not in retired]
    criteria = [
        c
        for c in criteria
        if c["key"] not in set(retire_criteria) and c.get("requirement") not in retired
    ]

    return FoldDraft(
        payload={**target, "requirements": requirements, "acceptance_criteria": criteria},
        requirements=folded,
        collisions=collisions,
        capability_requirements=[
            {"key": r["key"], "statement": r.get("statement", "")}
            for r in target.get("requirements") or []
        ],
        capability_criteria=[
            {"key": c["key"], "requirement": c.get("requirement"), "then": c.get("then", "")}
            for c in target.get("acceptance_criteria") or []
        ],
    )


async def fold(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    change: SpecDocument,
    capability: SpecDocument,
    items: Optional[List[FoldItem]],
    *,
    actor: spec_lifecycle.Actor,
    archive: bool = True,
    note: str = "",
    retire: Sequence[str] = (),
    retire_criteria: Sequence[str] = (),
) -> Tuple[SaveResult | ProposeResult, bool]:
    """Fold a finished change into a capability through the merge, then archive the change.

    Every refusal is decided before the merge writes anything. Returns the merge's result and
    whether the change was archived: at `contract`/`gate` rigor the merge only proposes, nothing
    was folded yet, and the change stays approved for the archive guard to keep honest.
    """
    if change.kind != "change-spec" or change.phase != spec_lifecycle.APPROVED:
        raise FoldRefusedError(
            f"{change.path} is {change.phase!r}; only an approved change is folded",
            code="fold_change_not_approved",
        )
    open_tasks = await spec_lifecycle.open_task_ids(session, change)
    if open_tasks:
        raise FoldRefusedError(
            "this change still has open tasks (" + ", ".join(open_tasks) + "); a change is "
            "folded once its work is decided",
            code="fold_tasks_open",
        )
    draft = fold_draft(workspace, change, capability, items, retire, retire_criteria)
    if draft.collisions:
        raise FoldRefusedError(
            f"{capability.path} already has " + ", ".join(draft.collisions) + "; rename the folded "
            "requirement, or name the one it replaces",
            code="fold_key_collision",
        )
    result = await merge_document(
        session, workspace, capability, [change], draft.payload, actor=actor, note=note
    )
    if isinstance(result, ProposeResult) or not archive:
        return result, False
    await spec_lifecycle.transition(
        session,
        change,
        to_phase=spec_lifecycle.ARCHIVED,
        actor=actor,
        workspace=workspace,
        reason=f"folded into {capability.path}",
    )
    # The file's status line is a copy for its reader; the phase route refreshes it after every
    # transition, and a fold that archives must too.
    await rerender_phase(session, workspace, change)
    return result, True


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
    if document.first_approved_at is not None:
        # Not `phase == APPROVED`: approval has two exits, archive and reopen, and both unfreeze
        # the path if this checked current phase alone — which the refusal's own reason ("its path
        # is part of what was approved") does not intend. `first_approved_at` is set once and never
        # reset (`spec_lifecycle.transition`), so this is monotone: once ever-approved, always
        # refused, even after archiving or reopening (design D6).
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


def roadmap_slices(workspace: ProjectWorkspace, path: str) -> List[Dict[str, Any]]:
    """A roadmap's stored slices, in order, or [] when its file has none to read."""
    try:
        content = spec_documents.read_document(workspace, path)
    except Exception:  # noqa: BLE001 -- an unreadable roadmap holds no slice, which is the finding
        return []
    stored = spec_documents.parse_stored(content)
    slices = (stored or {}).get("slices") or []
    return [item for item in slices if isinstance(item, dict) and item.get("key")]


def slice_of(workspace: ProjectWorkspace, payload: SpecPayload) -> Optional[SliceOf]:
    """The line a slice document renders under its title, from the roadmap's own file (C1a D7).

    From the file and not the database, so every render path (save, phase, corpus) can supply it
    and all of them agree. A roadmap that cannot be read still names the key and the path.
    """
    if payload.roadmap is None:
        return None
    path, key = payload.roadmap.document, payload.roadmap.slice
    try:
        content = spec_documents.read_document(workspace, path)
    except Exception:  # noqa: BLE001 -- the line degrades to the key and the path
        content = None
    stored = spec_documents.parse_stored(content) or {}
    named = next(
        (
            item
            for item in stored.get("slices") or []
            if isinstance(item, dict) and item.get("key") == key
        ),
        {},
    )
    return SliceOf(
        key=key,
        title=str(named.get("title") or ""),
        roadmap_path=path,
        roadmap_title=str(stored.get("title") or path),
    )


async def roadmap_states(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    project_id: str,
    payload: SpecPayload,
) -> Dict[str, spec_completeness.RoadmapState]:
    """The state of the roadmap a slice document names, for `spec_completeness.check` (C1a D3).

    Empty when the payload names none, or names a path that is not a roadmap of this project — the
    check then reports it as missing.
    """
    if payload.roadmap is None:
        return {}
    row = await spec_lifecycle.get_document(session, project_id, payload.roadmap.document)
    if row is None or row.kind != "roadmap":
        return {}
    keys = tuple(str(item["key"]) for item in roadmap_slices(workspace, row.path))
    return {row.path: spec_completeness.RoadmapState(row.phase, row.title, keys)}


async def phase_blockers(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    to_phase: str,
) -> List[Dict[str, Any]]:
    """Every reason `to_phase` may not be reached yet, or [] (F207, F113).

    'Not yet' only: a move the phase map forbids, or an actor who may not make it, is not a
    blocker — `transition()` refuses those first, as the authority it already is.

    A document whose file carries no payload, or one that no longer validates, raises
    `SaveRefusedError`: there is nothing to check.
    """
    if to_phase not in (spec_lifecycle.PROPOSED, spec_lifecycle.APPROVED):
        return []

    stored = spec_documents.read_payload(workspace, document.path)
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
    approved_paths = await spec_lifecycle.approved_document_paths(session, document.project_id)
    roadmaps = await roadmap_states(session, workspace, document.project_id, payload)
    findings = spec_completeness.check(
        payload,
        board_served=board_served,
        approved_document_paths=approved_paths,
        roadmaps=roadmaps,
    )
    if to_phase == spec_lifecycle.APPROVED:
        # A document whose import source was reopened after it was proposed is approved anyway and
        # the reference recorded as `document_not_approved` (task-dependencies, settled).
        # A document proposed before this change (or one whose delivery answer is incomplete) is
        # approved anyway: an absent or incomplete delivery just means no flow is created, and the
        # approval report says so (D4) — it is not a reason to refuse approval.
        excluded_at_approval = {
            "import_not_approved",
            "delivery_unanswered",
            "delivery_flow_incomplete",
        }
        findings = [f for f in findings if f.code not in excluded_at_approval]

    # No `explore_not_closed` here any more: the journey step replaced the operator's "exploration
    # is complete" boolean (`a-spec-is-written-one-step-at-a-time` FR-11).
    return [finding.to_dict() for finding in findings]


async def propose(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
    *,
    actor: spec_lifecycle.Actor,
) -> List[Dict[str, Any]]:
    """Move a document to `proposed`, or return what is blocking it.

    The checks run inside `transition()` against the payload the document actually carries, so
    this is the same answer whoever asks. A document whose file no longer parses cannot be
    proposed at all — there is nothing to check.
    """
    try:
        await spec_lifecycle.transition(
            session,
            document,
            to_phase=spec_lifecycle.PROPOSED,
            actor=actor,
            workspace=workspace,
        )
    except spec_lifecycle.PhaseError as exc:
        if exc.code == "document_incomplete":
            return exc.blocking
        raise
    await rerender_phase(session, workspace, document)
    return []


async def rerender_phase(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    document: SpecDocument,
) -> None:
    """Rewrite the file's hub block so it matches the row's phase, rigor, step and size.

    The block in the file is a copy for whoever reads it, never the authority. It is refreshed
    here so the two do not disagree — but if this fails, the row is still what counts. Called
    after a phase move, a rigor change and a journey move (FR-10).
    """
    content = spec_documents.read_document(workspace, document.path)
    stored = spec_documents.parse_stored(content)
    if stored is None:
        return
    rewritten = spec_documents.serialize(stored, hub_block(document))
    if rewritten != content:
        spec_documents.write_document(workspace, document.path, rewritten)
    document.content_digest = spec_lifecycle.digest(rewritten)


def hub_block(document: SpecDocument) -> Dict[str, Any]:
    """The row's copy for the stored file (FR-1): phase, rigor, step and size."""
    return {
        "phase": document.phase,
        # From the row, never from a submission. An agent that could state a rigor in a payload
        # could lower a gate that is blocking it, which is the one thing this must not permit.
        "rigor": document.rigor or "sketch",
        "step": document.step,
        "size": document.size,
    }


async def render_page(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    path: str,
    content: str,
    document: Optional[SpecDocument],
) -> Optional[str]:
    """The page a stored document shows, rendered on read (FR-2), or ``None`` with no payload.

    The same render a save produced before storage moved to JSON, with the corpus navigation a
    reindex used to write in when the index files the document. Phase and rigor come from the row
    where there is one, else from the file's hub block.
    """
    stored = spec_documents.parse_stored(content)
    if stored is None:
        return None
    try:
        payload = validate_payload(stored)
    except PayloadError:
        return None
    identifiers, _ = spec_identity.read_identity(stored)
    hub = spec_documents.parse_hub(content)
    phase = document.phase if document is not None else hub.get("phase") or spec_lifecycle.EXPLORING
    rigor = (document.rigor if document is not None else hub.get("rigor")) or "sketch"
    corpus = None
    manifest, _, _ = spec_documents.read_index(workspace)
    if manifest is not None and path in manifest.by_path():
        summaries = spec_documents.corpus_summaries(workspace, manifest)
        corpus = spec_documents.build_corpus_context(manifest, path, summaries)
    return render_document(
        payload,
        identifiers,
        phase=phase,
        stored_payload=stored,
        rigor=rigor,
        corpus=corpus,
        slice_of=slice_of(workspace, payload),
    )


async def rerender_corpus(
    session: AsyncSession,
    workspace: ProjectWorkspace,
    manifest: Manifest,
    rows: List[SpecDocument],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Rewrite every document whose stored file no longer matches what the Hub would write.

    corpus-aware-documents §4, after `a-spec-document-is-stored-as-its-payload`: corpus
    navigation and child maps are rendered when a document is read (FR-2), so they are never
    stale in a file. What a rebuild can still find stale is the file's hub block (a phase moved
    while the write failed) or its layout (a file written by hand). Each candidate's bytes are
    compared against what the Hub would write and only a real difference is written (design D2).

    Driven from each file's own payload (design D6), never the database, so this works
    identically for a document the Hub created and one that arrived by clone. A document whose
    file carries no readable payload is skipped and reported, never guessed at (design D6).
    """
    by_path = {row.path: row for row in rows}
    actor = spec_lifecycle.Actor(kind="system", name="reindex")

    rerendered: List[str] = []
    skipped: List[Dict[str, Any]] = []

    for entry in manifest.documents:
        current = spec_documents.read_document(workspace, entry.path)
        if current is None:
            skipped.append({"path": entry.path, "reason": "file_missing"})
            continue
        stored = spec_documents.parse_stored(current)
        if stored is None:
            skipped.append({"path": entry.path, "reason": "no_readable_payload"})
            continue
        try:
            validate_payload(stored)
        except PayloadError:
            skipped.append({"path": entry.path, "reason": "no_readable_payload"})
            continue

        # The page's corpus navigation is rendered on read now (FR-2), so what a rebuild can find
        # stale in the file is its hub block or its layout. A path filed in the manifest always
        # has a row today (`build_index` only files documents that are both on disk and known to
        # the Hub); a rowless one keeps the block it carries.
        document = by_path.get(entry.path)
        hub = hub_block(document) if document is not None else spec_documents.parse_hub(current)
        rendered = spec_documents.serialize(stored, hub)
        if rendered == current:
            continue

        try:
            spec_documents.write_document(workspace, entry.path, rendered)
        except OSError as exc:
            # F434 (D6): one file that cannot be written is reported and the rest go on. Its
            # digest does not advance and no event is recorded, because nothing new was written.
            skipped.append({"path": entry.path, "reason": "write_failed", "message": str(exc)})
            continue
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
