"""Project specification documents, read from the project working directory.

The Hub reads a registered project's files directly through ``ProjectWorkspace``,
so a document's only copy is the file on disk. There is nothing to push and
nothing to reconcile: the cache these endpoints used to serve
(``project_specs``) and the multi-source snapshot that reconciled it
(``project_spec_snapshots``) were both built for a Hub that could not see the
filesystem, and both are gone.

The Hub remains the security boundary. It resolves every path through the
project workspace — which refuses absolute paths, traversal, control characters
and symlink escapes — and re-validates it against the repo-relative spec path
contract, rather than trusting a caller's classification.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field
from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import (
    project_workspace,
    requirement_coverage,
    requirement_evidence,
    requirement_links,
    run_liveness,
    spec_adoption,
    spec_documents,
    spec_index,
    spec_lifecycle,
    spec_naming,
    spec_rigor,
    spec_service,
    spec_tasks,
    task_integration,
    task_transitions,
)
from ... import (
    spec_payload as spec_payload_module,
)
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    EVIDENCE_RETENTION_POLICIES,
    Agent,
    AIJob,
    EvidenceFootprint,
    EvidenceReview,
    Loop,
    Project,
    RequirementDrift,
    RequirementEvidence,
    Run,
    SpecDocument,
    SpecDocumentEvent,
    SpecEditProposal,
    SpecRequirement,
    Task,
)
from ...inbound_queue import new_entry
from ...schemas.common import RequestModel
from ...schemas.jobs import JobCreate
from ...spec_manifest import (
    Manifest,
    SpecPathError,
    dump_manifest,
    load_manifest,
    validate_spec_path,
)
from ...spec_payload import SCHEMA_VERSION
from ...sse import defer_broadcast, sse_manager
from ...task_transitions import TERMINAL_STATUSES
from ...utils import persist_event
from .jobs import _hand_job_to_scheduler, build_flow_rows

router = APIRouter(prefix="/project", tags=["spec"])

logger = logging.getLogger(__name__)

#: What a document is called before it has been written into. Not the path, and
#: not the placeholder — a reader looking at the title is looking for the
#: subject, and the honest answer at this moment is that there isn't one yet.
UNTITLED = "Untitled exploration"


async def _workspace(session: AsyncSession, project_id: str):
    try:
        return await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Project workspace is unavailable: {exc}",
                "code": exc.code,
                "directory_state": exc.directory_state,
            },
        ) from exc


@router.get("/specs")
async def list_specs(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """List the project's specification documents with the index's own state.

    An unreadable or absent index never silences the documents around it — the
    tree is what discovery found, and the index's condition is reported
    alongside it rather than in place of it.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    state = spec_documents.compute_state(workspace)

    # Archiving is a phase transition (`POST .../documents/phase?to=archived`), and it does not
    # relocate the file — a document archived this way stays wherever it was filed. The index-based
    # tree above cannot see that: it only knows a path, not what the Hub's own record says about it.
    # Without this, an archived document reads as an ordinary current one everywhere the tree is
    # drawn, which is the defect the operator actually reported.
    #
    # `id` rides along the same lookup for the same reason `phase` does: the panel shell keys a
    # `spec:` tab by document id where one exists (design D4, `2026-08-18-one-shell-three-panels`),
    # so it can survive a rename the tab strip is open across. A document discovery found on disk
    # but never created through the Hub (no `spec_documents` row) has no id — the UI falls back to
    # keying that tab by path, which is the only identity such a document has ever had.
    tracked = {
        document.path: document
        for document in await spec_lifecycle.list_documents(session, project_id)
    }
    specs = [
        {
            **entry,
            "phase": tracked[entry["path"]].phase if entry["path"] in tracked else None,
            "document_id": tracked[entry["path"]].id if entry["path"] in tracked else None,
        }
        for entry in state.specs
    ]

    return {
        "specs": specs,
        "home": state.home,
        "manifest": state.index,
        "missing": state.missing,
        "diagnostics": state.diagnostics,
    }


async def _divergence_fields(
    session: AsyncSession, project_id: str, path: str, content: Optional[str]
) -> Dict[str, Any]:
    """Whether what is being served still matches what the Hub recorded (F29).

    `spec_lifecycle.divergence` existed with exactly one caller, on the **save** path
    (`spec_service.py:236`), so tampering was noticed only when somebody tried to write and never
    when somebody read. Measured 2026-08-25: an approved document was edited on disk to say
    `TAMPERED BEHIND THE HUB`, and every reader — the operator in the Spec view, and any agent
    calling `read_spec_document` — received that text with nothing marking it.

    That inverts the guarantee the phase machine is built to provide. `spec_lifecycle`'s docstring
    opens on the rule that an agent cannot approve a document, enforced by reading the phase from a
    row rather than from the file the agent can write. The row is indeed authoritative for the
    phase; the **content** was still served from the file, unchecked. Approval therefore attached
    to a path rather than to the bytes anyone subsequently read.

    Marked, never refused. Editing an approved document on the way to a new revision is a
    legitimate thing to be doing, and refusing the read would break it — the rule this module
    already states is that the Hub surfaces both versions and waits for the operator.

    Returns `{}` for a document the Hub has no row for, or one that was never written: there is
    nothing recorded to differ from, which is not the same as agreeing.
    """
    document = await spec_lifecycle.get_document(session, project_id, path)
    if document is None:
        return {}
    found = spec_lifecycle.divergence(document, content)
    if found is None:
        return {"diverged": False}
    recorded_digest, found_digest = found
    return {
        "diverged": True,
        "divergence": {
            "recorded": recorded_digest,
            "found": found_digest,
            "phase": document.phase,
            "detail": (
                f"This file no longer matches what the Hub recorded for it at phase "
                f"'{document.phase}'. It was changed outside the Hub, so what you are reading is "
                f"not what was submitted — and, if this document is approved, not what was "
                f"approved."
            ),
        },
    }


#: `SpecDocumentEvent.kind` of the record approval leaves (design D7). Named for storage only: the
#: API field is `approval_outcome`, because tasks already answer an unrelated `approval_report`.
APPROVAL_REPORT = "approval_report"

#: Where a document is read for its delivery's agent: while it is being written and decided.
_DELIVERY_PHASES = ("exploring", "proposed")


async def delivery_agent_state(session: AsyncSession, project_id: str, name: str) -> str:
    """`ok`, `archived` or `unknown`: the one definition of a usable delivery agent (design D5).

    Not `_check_agent_exists`, which accepts any name on an empty roster and any name legacy
    session data knows, so a delivery the page calls stale could still become a flow that fails
    every five minutes (F33). Only an open `Agent` row is usable.
    """
    lifecycle = (
        await session.execute(
            select(Agent.lifecycle).where(Agent.project_id == project_id, Agent.name == name)
        )
    ).scalar_one_or_none()
    if lifecycle is None:
        return "unknown"
    return "ok" if lifecycle == "open" else "archived"


def _delivery_of(payload: Optional[Dict[str, Any]]) -> Optional[spec_payload_module.Delivery]:
    """The payload's delivery, or None when it has none or it does not validate."""
    raw = (payload or {}).get("delivery")
    if not isinstance(raw, dict):
        return None
    try:
        return spec_payload_module.Delivery.model_validate(raw)
    except Exception:  # noqa: BLE001 - an unreadable delivery is reported as absent, never a 500
        return None


def _read_payload(workspace, path: str) -> Optional[Dict[str, Any]]:
    content = spec_documents.read_document(workspace, path)
    return spec_payload_module.extract_payload(content) if content else None


async def _delivery_status(
    session: AsyncSession, project_id: str, document, payload: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Computed on every read, never written into the file (design D5): agent state changes
    independently of the document, and a rewrite off a transition registers as divergence."""
    if document.kind != "change-spec" or document.phase not in _DELIVERY_PHASES:
        return None
    delivery = _delivery_of(payload)
    if delivery is None:
        return {"state": "absent"}
    if delivery.mode != "flow":
        return {"state": "none"}
    if not delivery.agent:
        return {"state": "stale", "agent": "", "reason": "unknown"}
    state = await delivery_agent_state(session, project_id, delivery.agent)
    if state == "ok":
        return {"state": "ok", "agent": delivery.agent}
    return {"state": "stale", "agent": delivery.agent, "reason": state}


async def _approval_outcome(session: AsyncSession, document) -> Optional[Dict[str, Any]]:
    """The newest approval report, chosen by the Hub so the UI never picks (design D7).

    `created_at` alone ties on this machine (a 15.625 ms wall clock), so insertion order breaks
    the tie: `spec_document_events` has a `String` primary key, so it is a rowid table.
    """
    return (
        await session.execute(
            select(SpecDocumentEvent.detail)
            .where(
                SpecDocumentEvent.document_id == document.id,
                SpecDocumentEvent.kind == APPROVAL_REPORT,
            )
            .order_by(
                SpecDocumentEvent.created_at.desc(),
                literal_column("spec_document_events.rowid").desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("/spec")
async def get_spec(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Return one document's content; 404 when there is no such file."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)

    try:
        content = spec_documents.read_document(workspace, path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except project_workspace.ProjectPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"could not read document: {exc}"
        ) from exc

    if content is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="spec not found")

    payload = {
        "path": path,
        "content": content,
        "updated_at": spec_documents.document_updated_at(workspace, path),
    }
    payload.update(await _divergence_fields(session, project_id, path, content))
    document = await spec_lifecycle.get_document(session, project_id, path)
    if document is not None:
        status_now = await _delivery_status(
            session, project_id, document, spec_payload_module.extract_payload(content)
        )
        if status_now is not None:
            payload["delivery_status"] = status_now
        if document.phase == "approved":
            outcome = await _approval_outcome(session, document)
            if outcome is not None:
                payload["approval_outcome"] = outcome
    return payload


class DocumentCreate(RequestModel):
    """Starting an exploration.

    Only what identifies the document. Explore is the one phase that would
    otherwise precede its own document, and asking for requirements up front is
    exactly the structure the operator has not worked out yet.

    `path` is optional, and omitting it is the ordinary case: a document created
    at the start of an exploration is created before anyone knows what it is
    about, so the Hub mints a name that says nothing rather than deriving one
    from the operator's opening sentence. An explicit path is still honoured —
    it remains the only way to create a document at a chosen location.
    """

    path: Optional[str] = Field(default=None, max_length=255)
    title: str = Field(default="", max_length=512)
    kind: str = Field(default="change-spec", max_length=32)


class PhaseRequest(RequestModel):
    reason: str = Field(default="", max_length=2000)
    # At approval, the operator's choice of agent for a flow delivery whose agent is stale (design
    # D5b): a name, or "" for no flow. Used for this flow only; the document is never edited.
    delivery_agent: Optional[str] = Field(default=None, max_length=32)
    # At approval of a roadmap slice, queue a turn asking the slice's author to draft the next one
    # (C1a D4). Honoured only with to=approved; on any other document the response says why nothing
    # was queued.
    draft_next_slice: bool = False


class MergeRequest(RequestModel):
    """The operator folding a finished change's content into a capability document.

    `from_changes` names sources by path, like every other document-scoped route in this file —
    the operator, in the UI, is looking at paths, not database ids.
    """

    payload: dict = Field(description="Same shape submit_spec_document accepts.")
    from_changes: list[str] = Field(min_length=1, max_length=16)
    note: str = Field(default="", max_length=2000)


def _document_view(document) -> dict:
    return {
        "id": document.id,
        "path": document.path,
        "title": document.title,
        "kind": document.kind,
        "phase": document.phase,
        # What happens to work that ignores this document. Reported everywhere the phase is, because
        # they answer different questions and an operator reading one will assume the other.
        "rigor": document.rigor or spec_rigor.SKETCH,
        "content_digest": document.content_digest,
        "explore_closed": document.explore_closed_at is not None,
        "updated_at": document.updated_at.isoformat(),
    }


def _operator() -> spec_lifecycle.Actor:
    """The operator, established by the project credential this route already required.

    Named rather than taken from a request body — an actor a caller can state is
    an actor a caller can invent.
    """
    return spec_lifecycle.Actor(kind="operator", name="operator")


async def _require_document(session: AsyncSession, project_id: str, path: str):
    try:
        safe = validate_spec_path(path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    document = await spec_lifecycle.get_document(session, project_id, safe)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
    return document


@router.get("/documents")
async def list_documents(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Every document this project tracks, with the phase it is in."""
    project_id, _ = project
    documents = await spec_lifecycle.list_documents(session, project_id)

    # F29: a diverged document must be identifiable here too, not only when one is opened —
    # otherwise the operator has to open all of them to find the one that was changed behind the
    # Hub. Reading each file to hash it, rather than trusting mtime, because a touched-but-identical
    # file is not divergence and reporting it as such would teach the reader to ignore the flag.
    #
    # Measured before adding it: 30 documents averaging 16 KB cost 18.9 ms. Affordable here because
    # this query is not polled — `useSpecDocuments` sets no `refetchInterval` and is invalidated by
    # mutations, and this project's live state goes over SSE rather than polling. If it ever
    # becomes a hot path, this is the line to make conditional.
    try:
        workspace = await _workspace(session, project_id)
    except HTTPException:
        # The workspace being unavailable is its own reported condition elsewhere; it must not turn
        # listing the documents into an error.
        workspace = None

    views = []
    for document in documents:
        view = _document_view(document)
        if workspace is not None:
            with contextlib.suppress(OSError, SpecPathError, project_workspace.ProjectPathError):
                on_disk = spec_documents.read_document(workspace, document.path)
                view["diverged"] = spec_lifecycle.divergence(document, on_disk) is not None
        views.append(view)
    return {"documents": views}


class EvidenceRecord(RequestModel):
    """What the operator records to demonstrate a requirement."""

    identifier: str = Field(max_length=32)
    kind: str = Field(default="manual_observation", max_length=32)
    locator: str = Field(default="", max_length=4096)
    summary: str = Field(default="", max_length=10000)
    document: Optional[str] = Field(default=None, max_length=255)
    task_id: Optional[str] = Field(default=None, max_length=64)


class EvidenceDecision(RequestModel):
    decision: str = Field(max_length=16)
    reason: str = Field(default="", max_length=10000)


class DriftResolution(RequestModel):
    resolution: str = Field(max_length=32)


class RetentionSetting(RequestModel):
    policy: str = Field(max_length=16)


class ReindexRequest(RequestModel):
    """Optional inputs to a reindex. The body itself is optional; all fields default.

    `home` exists because the Hub refuses to choose one. `_select_home` treats a guess as
    indistinguishable from an operator's decision, so a corpus with several documents and no
    recorded home cannot be written until someone says which is home — and this is where the
    operator says it. A home already recorded in a valid index is preserved without passing
    anything.
    """

    home: Optional[str] = Field(default=None, max_length=255)


class DocumentAdopt(RequestModel):
    """Tracking a document that is already on disk.

    Carries a path and nothing else. Everything else about the document — its
    title, its kind, the phase it is in — is read from the file, because a caller
    able to state those could state them differently from what the file says, and
    the whole point of adoption is that the file is what is being believed.
    """

    path: str = Field(max_length=255)


async def _requirement(session: AsyncSession, project_id: str, identifier: str, document: str):
    document_row = None
    if document:
        document_row = await spec_lifecycle.get_document(session, project_id, document)
        if document_row is None:
            raise HTTPException(status_code=404, detail=f"no specification document at {document}")
    row, why = await spec_index.resolve(
        session,
        project_id,
        identifier,
        document_id=document_row.id if document_row else None,
    )
    if why == "ambiguous":
        raise HTTPException(
            status_code=422,
            detail=(
                f"{identifier} is declared by more than one document in this project; "
                "name the document it belongs to"
            ),
        )
    if row is None:
        raise HTTPException(status_code=404, detail=f"this project has no requirement {identifier}")
    return row


class DocumentContent(RequestModel):
    """The operator's equivalent of an agent submission's body, minus the path.

    The path is in the URL, matching every other operator document route. There is deliberately no
    actor field: identity comes from the credential, and a body that could name one would be a way
    to assert an identity the caller does not hold.
    """

    document: Any


class RigorRequest(RequestModel):
    """The operator setting how strictly a document is enforced.

    `expected_digest` is compare-and-swap: a rigor change must not land on a
    document somebody edited underneath it, or what was promoted is not what was
    read. Optional so a caller that has not read the document can still act, and
    supplied by every UI path that has.
    """

    rigor: str = Field(max_length=16)
    reason: str = Field(default="", max_length=2000)
    expected_digest: Optional[str] = Field(default=None, max_length=64)


@router.post("/documents/{path:path}/rigor")
async def set_document_rigor(
    path: str,
    body: RigorRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Raise or lower a document's rigor.

    There is deliberately no agent equivalent of this route, and adding one would
    undo the change: an agent blocked by a gate that can lower the document has
    not been gated, it has been inconvenienced.
    """
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    workspace = await _workspace(session, project_id)
    content = spec_documents.read_document(workspace, document.path)

    try:
        await spec_rigor.set_rigor(
            session,
            document,
            body.rigor,
            actor=_operator(),
            reason=body.reason,
            expected_digest=body.expected_digest,
            content=content,
        )
    except spec_rigor.RigorRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code, "blocking": exc.blocking},
        ) from exc

    # The file states the rigor for whoever opens it, so it is rewritten to agree with the row.
    # If this fails the row is still what governs — the copy in the document was never the gate.
    await spec_service.rerender_phase(session, workspace, document)
    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "rigor": document.rigor}
    )
    return _document_view(document)


@router.put("/documents/{path:path}/content")
async def write_document_content(
    path: str,
    body: DocumentContent,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Write a document's content as the operator, without an agent and without a merge.

    This reaches a branch of `spec_service.save_document` that has always existed and has never
    been callable: the service refuses a capability write from any actor that is not the operator,
    and `spec-document-authority` already requires that the same submission *from* the operator
    succeeds. The only caller was the agent route, which binds the actor to a run and so can never
    be the operator — leaving that requirement exercisable only by importing the module in a test.

    `PUT`, because the payload names a document that already exists and writing it twice must leave
    the same content. An import that stops halfway is then safe to re-run.

    No rule is relaxed for the operator. Every refusal comes from the service, unchanged: an
    invalid payload names its field, a mismatched `kind` is refused, an approved document is
    refused until reopened, and a document at `contract` or `gate` rigor records a pending proposal
    instead of being written — the operator accepts their own proposal, which is not a bypass.
    """
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    workspace = await _workspace(session, project_id)

    try:
        result = await spec_service.save_document(
            session,
            workspace,
            document,
            body.document,
            # Established from the credential the route already required, never from the body.
            # There is no run id: an operator is not acting under one.
            actor=_operator(),
        )
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code, "field": exc.field_path},
        ) from exc

    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": result.path, "phase": result.phase}
    )

    if isinstance(result, spec_service.ProposeResult):
        # Same shape the agent route returns at `contract`/`gate` rigor, and different from a write
        # on purpose, so a caller cannot mistake "pending" for "live".
        return {
            "path": result.path,
            "phase": result.phase,
            "proposals": result.proposals,
            "unchanged": result.unchanged,
            "already_pending": result.already_pending,
        }
    return {
        "path": result.path,
        "phase": result.phase,
        "identifiers": result.identifiers,
        "divergence": result.divergence,
        "blocking": result.blocking,
    }


@router.get("/documents/{path:path}/rigor-history")
async def rigor_history(
    path: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Every rigor change, with who made it. Demotion is legitimate *because* this exists."""
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    events = await spec_rigor.history_for(session, document.id)
    return {
        "events": [
            {
                "id": event.id,
                "from": event.from_rigor,
                "to": event.to_rigor,
                "actor_kind": event.actor_kind,
                "actor": event.actor,
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
            }
            for event in events
        ]
    }


def _proposal_view(proposal: SpecEditProposal) -> dict:
    return {
        "id": proposal.id,
        "unit_kind": proposal.unit_kind,
        "unit_key": proposal.unit_key,
        "change_kind": proposal.change_kind,
        "position_after_key": proposal.position_after_key,
        "proposed_payload": proposal.proposed_payload,
        "previous_payload": proposal.previous_payload,
        "status": proposal.status,
        # The document version it was made against: two identical proposals on different versions
        # are not duplicates, and the older one is refused as stale on accept (design D4).
        "expected_digest": proposal.expected_digest,
        "proposer_actor_kind": proposal.proposer_actor_kind,
        "proposer_actor_name": proposal.proposer_actor_name,
        "created_at": proposal.created_at.isoformat(),
        "resolved_at": proposal.resolved_at.isoformat() if proposal.resolved_at else None,
        "resolved_by_actor_name": proposal.resolved_by_actor_name,
        "resolution_reason": proposal.resolution_reason,
    }


async def _require_proposal(
    session: AsyncSession, document_id: str, proposal_id: str
) -> SpecEditProposal:
    proposal = await session.get(SpecEditProposal, proposal_id)
    if proposal is None or proposal.document_id != document_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="proposal not found")
    return proposal


@router.get("/documents/{path:path}/proposals")
async def list_proposals(
    path: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Pending proposals for one document — F2's in-position render reads this per document."""
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    result = await session.execute(
        select(SpecEditProposal)
        .where(SpecEditProposal.document_id == document.id, SpecEditProposal.status == "pending")
        .order_by(SpecEditProposal.created_at)
    )
    return {"proposals": [_proposal_view(row) for row in result.scalars().all()]}


class ProposalDecision(RequestModel):
    reason: str = Field(default="", max_length=2000)
    # The operator's own last-seen digest — a second, independent check from the proposal's own
    # `expected_digest` (design D4, round-3 clarification). Optional so a caller that has not read
    # the document can still act.
    expected_digest: Optional[str] = Field(default=None, max_length=64)


@router.post("/documents/{path:path}/proposals/{proposal_id}/accept")
async def accept_proposal_route(
    path: str,
    proposal_id: str,
    body: Optional[ProposalDecision] = None,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Apply one pending proposal's unit, or refuse and say why. There is no agent equivalent."""
    # F204/F210: every field of the body is optional, so a call with no body at all is a complete
    # request; without the default FastAPI refused it as malformed before the route could run.
    body = body or ProposalDecision()
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    proposal = await _require_proposal(session, document.id, proposal_id)
    workspace = await _workspace(session, project_id)

    try:
        result = await spec_service.accept_proposal(
            session,
            workspace,
            document,
            proposal,
            actor=_operator(),
            expected_digest=body.expected_digest,
            reason=body.reason,
        )
    except spec_service.ProposalRefusedError as exc:
        # `accept_proposal` may have marked the row `stale` before raising — that mutation must
        # survive this response, not be rolled back with everything else an exception discards.
        # And it leaves the pending list, so every view is told (F431).
        await session.commit()
        if exc.code == "proposal_stale":
            await sse_manager.broadcast(project_id, "spec_updated", {"path": document.path})
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code, "field": exc.field_path},
        ) from exc

    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": result.path, "phase": result.phase}
    )
    return {
        "path": result.path,
        "phase": result.phase,
        "identifiers": result.identifiers,
        "blocking": result.blocking,
        "proposal": _proposal_view(proposal),
    }


@router.post("/documents/{path:path}/proposals/{proposal_id}/reject")
async def reject_proposal_route(
    path: str,
    proposal_id: str,
    body: Optional[ProposalDecision] = None,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Refuse a pending proposal. The live document is untouched — nothing to clean up."""
    # F204/F210: every field of the body is optional, so a call with no body at all is a complete
    # request; without the default FastAPI refused it as malformed before the route could run.
    body = body or ProposalDecision()
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    proposal = await _require_proposal(session, document.id, proposal_id)

    try:
        await spec_service.reject_proposal(session, proposal, actor=_operator(), reason=body.reason)
    except spec_service.ProposalRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    await session.commit()
    # A rejected row leaves the pending list; every view is told, as accept tells them (F428).
    await sse_manager.broadcast(project_id, "spec_updated", {"path": document.path})
    return {"proposal": _proposal_view(proposal)}


class ProposalWithdrawal(RequestModel):
    note: str = Field(default="", max_length=2000)


@router.post("/documents/{path:path}/proposals/{proposal_id}/withdraw")
async def withdraw_proposal_route(
    path: str,
    proposal_id: str,
    body: Optional[ProposalWithdrawal] = None,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Take a pending proposal off the list without judging it -- for duplicates and proposals
    nobody is pursuing (`a-pending-proposal-can-be-withdrawn`, D3). The document is untouched."""
    body = body or ProposalWithdrawal()
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    proposal = await _require_proposal(session, document.id, proposal_id)

    try:
        await spec_service.withdraw_proposal(session, proposal, actor=_operator(), note=body.note)
    except spec_service.ProposalRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": document.path})
    return {"proposal": _proposal_view(proposal)}


@router.get("/spec/coverage")
async def coverage(
    document: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Coverage for a document, or for the whole project.

    Both come from `requirement_coverage`. A second implementation for the
    project total is exactly the thing this change exists to prevent.
    """
    project_id, _ = project
    document_id = None
    if document:
        row = await spec_lifecycle.get_document(session, project_id, document)
        if row is None:
            raise HTTPException(status_code=404, detail=f"no specification document at {document}")
        document_id = row.id
    report = await requirement_coverage.requirement_coverage(
        session, project_id, document_id=document_id
    )
    unserved = await requirement_links.unserved(session, project_id, document_id=document_id)
    return {
        **report.to_dict(),
        # Objects, not bare identifiers (F212). Identifiers are minted per document
        # (`spec_index.resolve`), so `FR-1` names one requirement only when one document declares
        # it — a fixture project answered 34 entries all reading `FR-1`, and feeding the most
        # repeated one back into `GET /spec/requirements/{identifier}` earned a 422 asking which
        # document was meant. `requirement_id` is included because it is unambiguous everywhere,
        # which the pair still is not across projects.
        "unserved": [
            {
                "identifier": row.identifier,
                "document_id": row.document_id,
                "requirement_id": row.id,
            }
            for row in unserved
        ],
    }


@router.get("/spec/requirements")
async def list_requirements(
    document: Optional[str] = Query(None),
    include_retired: bool = Query(True),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The project's requirements, with their state and where they sit."""
    project_id, _ = project
    document_id = None
    if document:
        row = await spec_lifecycle.get_document(session, project_id, document)
        if row is None:
            raise HTTPException(status_code=404, detail=f"no specification document at {document}")
        document_id = row.id

    query = select(SpecRequirement).where(SpecRequirement.project_id == project_id)
    if document_id is not None:
        query = query.where(SpecRequirement.document_id == document_id)
    if not include_retired:
        query = query.where(SpecRequirement.state == spec_index.ACTIVE)
    rows = list((await session.execute(query.order_by(SpecRequirement.identifier))).scalars().all())
    return {
        "requirements": [
            {
                "id": row.id,
                "identifier": row.identifier,
                "key": row.key,
                "document_id": row.document_id,
                "state": row.state,
                "digest": row.digest,
                "anchor": row.anchor,
            }
            for row in rows
        ]
    }


@router.get("/spec/requirements/{identifier}")
async def requirement_detail(
    identifier: str,
    document: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """One requirement, and everything pointing at it.

    The other half of a navigation that only went one way: a task already showed
    the requirements it serves, and nothing showed a requirement its work.
    """
    project_id, _ = project
    requirement = await _requirement(session, project_id, identifier, document or "")
    tasks = await requirement_links.tasks_for_requirement(session, requirement.id)
    evidence = await requirement_evidence.for_requirement(session, requirement.id)
    report = await requirement_coverage.requirement_coverage(
        session, project_id, document_id=requirement.document_id, include_retired=True
    )
    coverage = next(
        (entry for entry in report.requirements if entry.requirement_id == requirement.id), None
    )
    prints = await _footprints_for(session, [row.id for row in evidence])
    reviews = await _latest_reviews_for(session, [row.id for row in evidence])
    return {
        "requirement": {
            "id": requirement.id,
            "identifier": requirement.identifier,
            "key": requirement.key,
            "document_id": requirement.document_id,
            "state": requirement.state,
            "digest": requirement.digest,
            "anchor": requirement.anchor,
        },
        "tasks": [
            {"id": task.id, "title": task.title, "status": task.status, "assignee": task.assignee}
            for task in tasks
        ],
        "evidence": [
            _evidence_view(row, prints.get(row.id), reviews.get(row.id)) for row in evidence
        ],
        # Never omitted, and never without its integration answer.
        "coverage": coverage.to_dict() if coverage else None,
    }


@router.post("/spec/evidence", status_code=status.HTTP_201_CREATED)
async def record_evidence(
    body: EvidenceRecord,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator recording an observation. Accepted on arrival — there is nobody else to await."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    requirement = await _requirement(session, project_id, body.identifier, body.document or "")
    try:
        evidence = await requirement_evidence.record(
            session,
            requirement,
            kind=body.kind,
            locator=body.locator,
            summary=body.summary,
            task_id=body.task_id,
            workspace=workspace,
            actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        )
    except requirement_evidence.EvidenceRefusedError as exc:
        raise HTTPException(
            status_code=409, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await session.commit()
    # **With its footprint** (finding F71). Every sibling call site in this file passes one; this
    # handler did not, so the response read `footprint: null` even when a footprint *was* captured —
    # and this is the one moment the operator is looking. The field exists precisely so a reader can
    # tell whether the evidence describes the work they think it does, as this view's own comment on
    # it says; withholding it here hid a wrong commit at the only point where noticing was cheap.
    prints = await _footprints_for(session, [evidence.id])
    # **With its review** (F218). `record()` auto-accepts operator-recorded evidence and writes the
    # `EvidenceReview` row in the same transaction just committed above, but this handler stopped at
    # the footprint fix and never fetched it — so this 201 read `latest_review: null` for a row the
    # very next GET already shows accepted. Same fetch-and-pass shape as `list_evidence` uses.
    reviews = await _latest_reviews_for(session, [evidence.id])
    return _evidence_view(evidence, prints.get(evidence.id), reviews.get(evidence.id))


@router.get("/spec/evidence")
async def list_evidence(
    identifier: Optional[str] = Query(None),
    document: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    if identifier:
        requirement = await _requirement(session, project_id, identifier, document or "")
        rows = await requirement_evidence.for_requirement(session, requirement.id)
    else:
        query = select(RequirementEvidence).where(RequirementEvidence.project_id == project_id)
        if document:
            # F448, the operator twin of F416: `document` alone used to be dropped, so a read
            # scoped to one document returned the whole project's evidence with a 200.
            document_row = await spec_lifecycle.get_document(session, project_id, document)
            if document_row is None:
                raise HTTPException(
                    status_code=404, detail=f"no specification document at {document}"
                )
            query = query.join(
                SpecRequirement, RequirementEvidence.requirement_id == SpecRequirement.id
            ).where(SpecRequirement.document_id == document_row.id)
        rows = list(
            (await session.execute(query.order_by(RequirementEvidence.produced_at))).scalars().all()
        )
    prints = await _footprints_for(session, [row.id for row in rows])
    reviews = await _latest_reviews_for(session, [row.id for row in rows])
    return {
        "evidence": [_evidence_view(row, prints.get(row.id), reviews.get(row.id)) for row in rows]
    }


async def _decision_announcement(session: AsyncSession, evidence) -> Dict[str, Any]:
    """The `spec_updated` payload for a decided piece: the shape the record route already sends."""
    requirement = await session.get(SpecRequirement, evidence.requirement_id)
    return {
        "evidence": evidence.id,
        "requirement": requirement.identifier if requirement is not None else None,
    }


@router.post("/spec/evidence/{evidence_id}/decision")
async def decide_evidence(
    evidence_id: str,
    body: EvidenceDecision,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator accepting or rejecting. An agent uses its own plane, and cannot reach this."""
    project_id, _ = project
    evidence = await session.get(RequirementEvidence, evidence_id)
    if evidence is None or evidence.project_id != project_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    try:
        review = await requirement_evidence.decide(
            session,
            evidence,
            decision=body.decision,
            reason=body.reason,
            actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        )
    except requirement_evidence.EvidenceRefusedError as exc:
        # 403 for the two capability refusals; the refusal itself overrides that where it is a
        # validation error rather than an authorisation one (F8).
        raise HTTPException(
            status_code=exc.http_status or 403, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await session.commit()
    # Built before the integration below, which rolls back when it fails and expires every loaded
    # row: the decision has committed, and the answer must not depend on what the merge did (F426).
    view = _evidence_view(evidence, latest_review=review)
    # Captured here for the same reason: the broadcast below goes after the integration, and reading
    # `evidence.id` then is the 500 F426 fixed.
    announced = await _decision_announcement(session, evidence)
    # After the commit, and wrapped inside: accepting is a judgement about the evidence, and a
    # repository failure must not reverse it. This is what makes the approval refusal's instruction
    # — "accept the evidence" — actually land the work, rather than asking for something and then
    # ignoring it being done.
    await task_integration.integrate_what_was_waiting_for_this_evidence(
        session, evidence, task_transitions.operator()
    )
    # After the integration, so a view refetching on it sees any merge the decision caused.
    await sse_manager.broadcast(project_id, "spec_updated", announced)
    return view


@router.get("/spec/evidence/{evidence_id}/reviews")
async def evidence_reviews(
    evidence_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    evidence = await session.get(RequirementEvidence, evidence_id)
    if evidence is None or evidence.project_id != project_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    reviews = await requirement_evidence.reviews_for(session, evidence_id)
    return {
        "reviews": [
            {
                "id": review.id,
                "decision": review.decision,
                "actor_kind": review.actor_kind,
                "actor": review.actor,
                "run_id": review.run_id,
                "reason": review.reason,
                "created_at": review.created_at.isoformat(),
            }
            for review in reviews
        ]
    }


@router.post("/spec/drift/detect")
async def detect_drift(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    # The operator's explicit scan is also the moment to re-answer reachability: it is what
    # eventually notices a merge they performed by hand in a terminal, which nothing else observes.
    row = await session.get(Project, project_id)
    await requirement_evidence.refresh_reachability(
        session,
        project_id,
        workspace.root,
        main_branch=row.main_branch if row else None,
    )
    raised = await requirement_evidence.detect_drift(session, project_id, workspace)
    await session.commit()
    return {"raised": [candidate.id for candidate in raised]}


@router.get("/spec/drift")
async def list_drift(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    rows = list(
        (
            await session.execute(
                select(RequirementDrift)
                .where(RequirementDrift.project_id == project_id)
                .order_by(RequirementDrift.created_at)
            )
        )
        .scalars()
        .all()
    )
    # F216: the operator asked "say which one was wrong" was handed `spreq-…` and `ev-…`. What they
    # have seen is the requirement's `FR-n` in a document, and the evidence's summary and author.
    requirements = {
        row.id: row
        for row in (
            await session.execute(
                select(SpecRequirement).where(
                    SpecRequirement.id.in_({row.requirement_id for row in rows} or {""})
                )
            )
        ).scalars()
    }
    documents = {
        row.id: row.path
        for row in (
            await session.execute(
                select(SpecDocument).where(
                    SpecDocument.id.in_({req.document_id for req in requirements.values()} or {""})
                )
            )
        ).scalars()
    }
    evidence = {
        row.id: row
        for row in (
            await session.execute(
                select(RequirementEvidence).where(
                    RequirementEvidence.id.in_({row.evidence_id for row in rows} or {""})
                )
            )
        ).scalars()
    }

    def _view(row: RequirementDrift) -> Dict[str, Any]:
        requirement = requirements.get(row.requirement_id)
        item = evidence.get(row.evidence_id)
        return {
            "id": row.id,
            "requirement_id": row.requirement_id,
            "evidence_id": row.evidence_id,
            "state": row.state,
            "observed": row.observed,
            "resolution": row.resolution,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "requirement": (
                {
                    "identifier": requirement.identifier,
                    "document": documents.get(requirement.document_id),
                }
                if requirement is not None
                else None
            ),
            "evidence": (
                {
                    "summary": item.summary,
                    "locator": item.locator,
                    "actor": item.actor,
                    "actor_kind": item.actor_kind,
                }
                if item is not None
                else None
            ),
        }

    return {"drift": [_view(row) for row in rows]}


@router.post("/spec/drift/{drift_id}/resolve")
async def resolve_drift(
    drift_id: str,
    body: DriftResolution,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    candidate = await session.get(RequirementDrift, drift_id)
    if candidate is None or candidate.project_id != project_id:
        raise HTTPException(status_code=404, detail="Drift candidate not found")
    try:
        await requirement_evidence.resolve_drift(
            session,
            candidate,
            resolution=body.resolution,
            actor=spec_lifecycle.Actor(kind="operator", name="operator"),
        )
    except requirement_evidence.EvidenceRefusedError as exc:
        raise HTTPException(
            status_code=422, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await session.commit()
    return {"id": candidate.id, "state": candidate.state, "resolution": candidate.resolution}


@router.put("/spec/evidence-retention")
async def set_retention(
    body: RetentionSetting,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """How long artifacts are kept. `never` is a first-class choice, not a loophole."""
    project_id, _ = project
    if not requirement_evidence.retention_is_valid(body.policy):
        raise HTTPException(
            status_code=422,
            detail=f"policy must be one of {list(EVIDENCE_RETENTION_POLICIES)}",
        )
    row = await session.get(Project, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    row.evidence_retention = body.policy
    await session.commit()
    return {"policy": row.evidence_retention}


def _evidence_view(evidence, footprint=None, latest_review=None) -> dict:
    return {
        # Still being recorded: the run that recorded it is running, so its commit is about to be
        # replaced and a decision is held (`recording_run_live`). A registry lookup, no query.
        "recording_run_live": bool(evidence.run_id and run_liveness.run_is_live(evidence.run_id)),
        "id": evidence.id,
        "requirement_id": evidence.requirement_id,
        "digest": evidence.digest,
        "kind": evidence.kind,
        "locator": evidence.locator,
        "summary": evidence.summary,
        "actor_kind": evidence.actor_kind,
        "actor": evidence.actor,
        "run_id": evidence.run_id,
        "task_id": evidence.task_id,
        "review_state": evidence.review_state,
        # The reason behind that state, inline. Without this, a caller who lists evidence and sees
        # review_state: rejected must make one more GET per row (/spec/evidence/{id}/reviews) to
        # learn why - the same silent-signal shape the merge-outcome and rejected-evidence fixes
        # closed elsewhere on this task response.
        "latest_review": (
            {
                "decision": latest_review.decision,
                "reason": latest_review.reason,
                "actor_kind": latest_review.actor_kind,
                "actor": latest_review.actor,
                "created_at": latest_review.created_at.isoformat(),
            }
            if latest_review is not None
            else None
        ),
        # A record whose artifact is gone reports that state rather than disappearing.
        "artifact_removed": evidence.artifact_removed_at is not None,
        "produced_at": evidence.produced_at.isoformat(),
        # **What this evidence is about**, which is how somebody accepting it can tell whether it
        # describes the work they think it does. A reviewer who could see `branch: master` on a
        # builder's evidence would have caught the 2026-08-13 defect by eye, months before any test
        # was written for it. Null where no footprint was captured.
        "footprint": footprint_view(footprint),
    }


def footprint_view(footprint) -> Optional[dict]:
    """One shape for a footprint, wherever a response reports one.

    Extracted so the agent's own recording response and every operator-facing view report the same
    fields: a reader learning what `footprint` means from one of them has learned it for all.

    `outside_workspace_writes` is *on* the footprint rather than beside it because it is a statement
    about this tree — `commit_sha` and `branch` describe the directory the run was given, and a
    non-empty list here says that directory is missing some of the run's work. Null is "not
    observed" and `[]` is "observed, and nothing left the workspace"; collapsing the two into
    "clean" is the confinement claim the product does not make.
    """
    if footprint is None:
        return None
    return {
        "kind": footprint.kind,
        "branch": footprint.branch,
        "commit_sha": footprint.commit_sha,
        "reachable_from_main": footprint.reachable_from_main,
        "outside_workspace_writes": footprint.outside_workspace_writes,
    }


async def _footprints_for(session: AsyncSession, evidence_ids) -> dict:
    """`{evidence_id: footprint}` for a page of evidence, in one query."""
    wanted = [row for row in evidence_ids if row]
    if not wanted:
        return {}
    rows = (
        (
            await session.execute(
                select(EvidenceFootprint).where(EvidenceFootprint.evidence_id.in_(wanted))
            )
        )
        .scalars()
        .all()
    )
    return {row.evidence_id: row for row in rows}


async def _latest_reviews_for(session: AsyncSession, evidence_ids) -> dict:
    """`{evidence_id: latest EvidenceReview}` for a page of evidence, in one query.

    Reviews are append-only and ordered ascending, so the last one seen per id is
    the one `review_state` itself reflects - the same rule `decide()` uses.
    """
    wanted = [row for row in evidence_ids if row]
    if not wanted:
        return {}
    rows = (
        (
            await session.execute(
                select(EvidenceReview)
                .where(EvidenceReview.evidence_id.in_(wanted))
                .order_by(EvidenceReview.sequence)
            )
        )
        .scalars()
        .all()
    )
    latest = {}
    for row in rows:
        latest[row.evidence_id] = row
    return latest


@router.post("/spec/reindex")
async def reindex(
    body: Optional[ReindexRequest] = None,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Rebuild the requirement index and `spec/index.json` from the files.

    The operator's, not an agent's. Two things need it: a project whose documents
    predate the index, and a document edited outside the Hub. Both are cases where
    the index is behind the files, and neither can be detected without reading
    them — so this is offered rather than guessed at on a timer.

    Two indexes are rebuilt here, and they are not the same thing. The *requirement*
    index is database rows, and it does not travel. `spec/index.json` is a file, and it
    is the only record of the corpus's home, hierarchy and ordering that survives the
    project being copied to another machine. This route wrote only the first until
    2026-08-20, which is why every corpus read as `unindexed`.

    The manifest write is skipped, not failed, when there is no home to record — the
    requirement index is still worth rebuilding, and `index.diagnostics` says why nothing
    was written.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    results = await spec_index.reindex_project(session, workspace, project_id)
    backfilled = await requirement_links.backfill_project(session, project_id)

    on_disk, discovery_diagnostics = spec_documents.discover(workspace)
    rows = await spec_lifecycle.list_documents(session, project_id)
    existing, _, _ = spec_documents.read_index(workspace)
    manifest, index_diagnostics = spec_documents.build_index(
        on_disk,
        [(row.path, row.title, row.kind, row.phase) for row in rows],
        existing,
        home=body.home if body is not None else None,
    )

    written = None
    rerendered: List[str] = []
    rerender_skipped: List[Dict[str, Any]] = []
    if manifest is not None:
        spec_documents.write_index(workspace, manifest)
        written = {
            "path": spec_documents.INDEX_RELATIVE,
            "documents": len(manifest.documents),
            "home": manifest.home,
        }
        # corpus-aware-documents §4: a rebuilt manifest can change what a document's own
        # navigation or map should say even when neither `results` nor `written` above name
        # it — a sibling being added changes nothing about *this* document's requirements or
        # the index file, only what its parent's map now lists.
        rerendered, rerender_skipped = await spec_service.rerender_corpus(
            session, workspace, manifest, rows
        )

    await session.commit()
    return {
        "documents": {
            path: (
                None
                if result is None
                else {
                    "created": result.created,
                    "reworded": result.reworded,
                    "retired": result.retired,
                    "restored": result.restored,
                    "unchanged": result.unchanged,
                }
            )
            for path, result in results.items()
        },
        "references": backfilled,
        "index": {
            "written": written,
            "diagnostics": list(discovery_diagnostics) + list(index_diagnostics),
        },
        "corpus": {
            "rerendered": rerendered,
            "skipped": rerender_skipped,
        },
    }


class ArrangeRequest(RequestModel):
    """Setting a document's place in the corpus (design D3).

    An editorial judgement about what the project *is* — deliberately not something a document's
    own payload can state (D3's rejection of a `parent` field on the payload). `parent: null`
    unparents the document; omitting `parent` also unparents it, since there is no third state.
    """

    path: str = Field(max_length=255)
    parent: Optional[str] = Field(default=None, max_length=255)


@router.post("/spec/documents/arrange")
async def arrange_document(
    body: ArrangeRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Set or clear a document's parent in the corpus hierarchy.

    Operator-only — the agent capability plane has no equivalent. Validated by round-tripping the
    candidate manifest through `load_manifest` (`dump_manifest` the candidate, then re-parse it):
    unknown parent, self-parent and cycle are `load_manifest`'s own structural rules
    (`spec_manifest.py:236-274`), reused here rather than reimplemented.
    """
    project_id, _ = project
    try:
        path = validate_spec_path(body.path)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    parent = body.parent
    if parent is not None:
        try:
            parent = validate_spec_path(parent)
        except SpecPathError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    workspace = await _workspace(session, project_id)
    manifest, state, diagnostics = spec_documents.read_index(workspace)
    if manifest is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            # F208: name the route that builds the index, and the input it refuses to guess.
            detail={
                "message": (
                    f"no usable index to arrange ({state}). Build one with POST /spec/reindex, "
                    'passing {"home": "<document path>"} if it answers that no home is recorded, '
                    "then arrange again."
                ),
                "diagnostics": diagnostics,
            },
        )

    by_path = manifest.by_path()
    if path not in by_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{path} is not in the index"
        )

    candidate = Manifest(
        version=manifest.version,
        home=manifest.home,
        documents=tuple(
            dataclasses.replace(doc, parent=parent) if doc.path == path else doc
            for doc in manifest.documents
        ),
    )
    revalidated, validation_diagnostics = load_manifest(dump_manifest(candidate))
    if revalidated is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "this placement is not allowed",
                "diagnostics": [d.to_dict() for d in validation_diagnostics],
            },
        )

    spec_documents.write_index(workspace, revalidated)

    rows = await spec_lifecycle.list_documents(session, project_id)
    rerendered, skipped = await spec_service.rerender_corpus(session, workspace, revalidated, rows)
    await session.commit()

    await sse_manager.broadcast(project_id, "spec_updated", {"path": path, "parent": parent})

    return {
        "path": path,
        "parent": parent,
        "corpus": {"rerendered": rerendered, "skipped": skipped},
    }


@router.post("/spec/adopt")
async def adopt_corpus(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Adopt every adoptable document beneath `spec/`, and say what happened to each.

    Filed under `/spec/` rather than `/documents/` for the same reason `reindex`
    is: this operates on the corpus, not on a document. It reports in reindex's
    shape — a per-path map plus a diagnostics list — so the two read alike.

    Never fails as a whole. A hand-written file with no payload is one skipped
    path with a stated reason, not a failed recovery of the other thirty-three
    (design D5).
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)

    outcome = await spec_adoption.adopt_corpus(session, workspace, project_id, actor=_operator())
    await session.commit()

    if outcome.adopted:
        # One event for the sweep rather than one per document: the rail refreshes
        # the whole tree either way, and thirty-four broadcasts would be thirty-three
        # redundant re-renders.
        await sse_manager.broadcast(project_id, "spec_updated", {"path": None, "phase": None})
    return outcome.to_dict()


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentCreate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Start an exploration: an empty document, in `exploring`, that later phases refer to."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)

    if body.path is None:
        try:
            path = await spec_service.mint_document_path(session, project_id, workspace)
        except spec_naming.NamingExhaustedError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": str(exc), "code": "naming_exhausted"},
            ) from exc
    else:
        try:
            path = validate_spec_path(body.path)
        except SpecPathError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    try:
        document = await spec_lifecycle.create_document(
            session, project_id, path, actor=_operator(), title=body.title, kind=body.kind
        )
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    payload = {
        # A payload's title may not be empty, and the document has no real one
        # yet — the agent mints that when it submits. What this must not do is
        # fall back to the path, which used to yield the literal "spec" and
        # would now yield a placeholder, putting a name that means nothing where
        # a reader looks for the subject.
        "schema_version": SCHEMA_VERSION,
        "kind": document.kind,
        "title": body.title or UNTITLED,
    }
    result = await spec_service.save_document(
        session, workspace, document, payload, actor=_operator()
    )
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": path, "phase": document.phase})
    return {**_document_view(document), "blocking": result.blocking}


#: What adoption refuses for, mapped to the status each refusal deserves. A path
#: the caller malformed is theirs to fix (400); a file that is missing or says
#: nothing usable about itself is a state of the world (422); a document already
#: tracked is a conflict with a record that exists (409).
_ADOPTION_REFUSAL_STATUS = {
    "unsafe_document_path": status.HTTP_400_BAD_REQUEST,
    "document_exists": status.HTTP_409_CONFLICT,
    "file_missing": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "file_unreadable": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "payload_absent": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "payload_unreadable": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "payload_identity_missing": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


@router.post("/documents/adopt", status_code=status.HTTP_201_CREATED)
async def adopt_document(
    body: DocumentAdopt,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Track a document that already exists on disk, without writing to it.

    The operator's, like every route in this file — `get_project` resolves an
    operator credential and nothing else, so a run-scoped token cannot reach it.
    Adoption states what a project's corpus *is*, and a document is not something
    a run should be able to bring into existence by writing a file next to itself.

    Distinct from `POST /documents` rather than a flag on it, and deliberately:
    creation renders a starter file over the path it is given, so pointing it at
    an existing document destroys that document. Two routes whose names differ
    cannot be confused by a missing parameter (design D1).
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)

    outcome = await spec_adoption.adopt(
        session, workspace, project_id, body.path, actor=_operator()
    )
    if isinstance(outcome, spec_adoption.AdoptionRefusal):
        raise HTTPException(
            status_code=_ADOPTION_REFUSAL_STATUS.get(
                outcome.code, status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
            detail={"message": outcome.message, **outcome.to_dict()},
        )

    await session.commit()
    await sse_manager.broadcast(
        project_id,
        "spec_updated",
        {"path": outcome.document.path, "phase": outcome.document.phase},
    )
    return {**_document_view(outcome.document), **outcome.to_dict()}


@router.post("/documents/close-exploration")
async def close_exploration(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator declaring exploration finished.

    Whether an exploration is complete enough to propose from is a judgement,
    not a computation. Making it an operator action keeps every model out of the
    path of a gate.
    """
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    try:
        await spec_lifecycle.close_exploration(session, document, actor=_operator())
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    await session.commit()
    return _document_view(document)


@router.post("/documents/propose")
async def propose_document(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Move a document to `proposed`, or report every check that refuses it."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)

    try:
        blocking = await spec_service.propose(session, workspace, document, actor=_operator())
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    await session.commit()
    if blocking:
        return {**_document_view(document), "blocking": blocking}
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return {**_document_view(document), "blocking": []}


@router.post("/documents/phase")
async def set_phase(
    body: Optional[PhaseRequest] = None,
    path: str = Query(...),
    to: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """An operator phase decision — approving a document, or reopening one.

    This route requires the project credential, so an agent run cannot reach it:
    a run's token authenticates against `/agent-actions`, which has no phase
    route at all.
    """
    # F204/F210: every field of the body is optional, so a call with no body at all is a complete
    # request; without the default FastAPI refused it as malformed before the route could run.
    body = body or PhaseRequest()
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)

    if body.draft_next_slice and to != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "draft_next_slice starts the next roadmap slice at approval; send it only with "
                "to=approved"
            ),
        )

    # D5b: `delivery_agent` is honoured only where it can be, and refused before anything moves
    # rather than ignored (`RequestModel`'s rule: honour a field or name it).
    if body.delivery_agent is not None:
        if to != "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "delivery_agent chooses the agent of an approval's flow; send it only with "
                    "to=approved"
                ),
            )
        chosen_for = _delivery_of(_read_payload(workspace, document.path))
        if chosen_for is None or chosen_for.mode != "flow":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "delivery_agent replaces a flow delivery's agent, and this document declares "
                    "no flow"
                ),
            )

    try:
        await spec_lifecycle.transition(
            session,
            document,
            to_phase=to,
            actor=_operator(),
            workspace=workspace,
            reason=body.reason,
        )
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    except spec_lifecycle.PhaseError as exc:
        detail: Dict[str, Any] = {"message": str(exc), "code": exc.code}
        if exc.blocking:
            detail["blocking"] = exc.blocking
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc

    # Approval is what turns a decomposition from a description into work: the board is
    # materialised, the delivery's flow is created, and what both did is recorded. Neither can undo
    # the approval: each runs in its own savepoint and reports a failure instead of raising.
    report: Optional[Dict[str, Any]] = None
    created_job: Optional[AIJob] = None
    created_count = 0
    payload: Optional[Dict[str, Any]] = None
    if document.phase == "approved":
        payload = _read_payload(workspace, document.path)
        outcome = await spec_tasks.materialise_quietly(
            session, document, payload, actor=_operator()
        )
        created_count = len(outcome.created)
        flow, created_job = await _approval_flow(
            session, project_id, document, payload, body.delivery_agent
        )
        report = {
            "created": [dataclasses.asdict(task) for task in outcome.created],
            "already_served": [
                {"key": entry.key, "requirements": list(entry.requirements)}
                for entry in outcome.already_served
            ],
            "failed": outcome.failed,
            # When the board failed, `_materialise_edges` did not run, and the rows there are the
            # previous approval's (design D7, R3).
            "dependencies_not_honoured": (
                []
                if outcome.failed
                else await spec_tasks.dependencies_not_honoured(session, document, payload)
            ),
            "flow": flow,
            "delivery_agent": body.delivery_agent,
        }
        await spec_lifecycle.record_event(
            session, document, kind=APPROVAL_REPORT, actor=_operator(), detail=report
        )

    await spec_service.rerender_phase(session, workspace, document)
    # Staged, not sent (design D6 step 5): `job_created` is persisted uncommitted inside the flow's
    # savepoint, so every frame here waits for the one commit below, in today's order.
    defer_broadcast(
        session, project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    if created_count:
        defer_broadcast(session, project_id, "task_updated", {"created": created_count})
    if created_job is not None:
        defer_broadcast(
            session, project_id, "job_created", {"id": created_job.id, "name": created_job.name}
        )
    await session.commit()
    if created_job is not None:
        # First firing at the next cron tick; nothing fires now (operator). A registration failure
        # is logged, and the committed flow fires from the next restart.
        await _hand_job_to_scheduler(session, created_job.id, created_job)

    response = {
        **_document_view(document),
        "tasks_created": [task["id"] for task in (report or {}).get("created", [])],
    }
    if report is not None:
        response["approval_outcome"] = report
    if body.draft_next_slice and document.phase == "approved":
        # After the commit: the approval stands whatever happens here, and the response says it.
        response["next_slice"] = await _draft_next_slice(
            session, project_id, workspace, document, payload, response["tasks_created"]
        )
    return response


def _next_slice_outcome(
    state: str, slice_key: Optional[str] = None, agent: Optional[str] = None
) -> Dict[str, Any]:
    return {"state": state, "slice": slice_key, "agent": agent}


async def _draft_next_slice(
    session: AsyncSession,
    project_id: str,
    workspace,
    document: SpecDocument,
    payload: Optional[Dict[str, Any]],
    tasks_created: List[str],
) -> Dict[str, Any]:
    """Queue one operator turn asking the approved slice's author to draft the next slice (C1a D4).

    The author is the agent recorded on the document's `created` event, in the conversation of the
    run that created it. The entry carries the roadmap as its spec document, so the turn is a
    specification turn: it loses file-write tools (`agent_trigger.py`, F4) and is told the roadmap
    is planned, not implemented. Origin `operator`, because the operator asked in this request.

    Never raises. A failure to queue is reported in the outcome; a failure to schedule leaves the
    committed entry for the next drain, so it still reports `queued`.
    """
    link = (payload or {}).get("roadmap")
    if document.kind != "change-spec" or not isinstance(link, dict):
        return _next_slice_outcome("not_a_slice")
    roadmap_path, approved_key = str(link.get("document")), str(link.get("slice"))
    slices = spec_service.roadmap_slices(workspace, roadmap_path)
    keys = [str(item["key"]) for item in slices]
    position = keys.index(approved_key) if approved_key in keys else len(keys)
    if position + 1 >= len(keys):
        return _next_slice_outcome("last_slice")
    approved_slice, following = slices[position], slices[position + 1]
    next_key = str(following["key"])

    created = (
        await session.execute(
            select(SpecDocumentEvent)
            .where(
                SpecDocumentEvent.document_id == document.id, SpecDocumentEvent.kind == "created"
            )
            .order_by(SpecDocumentEvent.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if created is None or created.actor_kind != "agent" or not created.actor:
        return _next_slice_outcome("no_author", next_key)
    agent = created.actor
    run = await session.get(Run, created.run_id) if created.run_id else None
    if run is None or not run.conversation_id:
        return _next_slice_outcome("no_conversation", next_key, agent)

    roadmap_row = await spec_lifecycle.get_document(session, project_id, roadmap_path)
    content = _next_slice_message(
        roadmap_path=roadmap_path,
        roadmap_title=roadmap_row.title if roadmap_row is not None else roadmap_path,
        approved_path=document.path,
        approved_slice=approved_slice,
        tasks_created=tasks_created,
        following=following,
    )
    try:
        session.add(
            new_entry(
                project_id=project_id,
                agent=agent,
                origin_type="operator",
                content=content,
                hop_depth=0,
                conversation_id=run.conversation_id,
                spec_document=roadmap_path,
            )
        )
        await session.commit()
    except Exception:  # noqa: BLE001 -- the approval is committed; say the turn was not queued
        await session.rollback()
        logger.warning(
            "could not queue the next slice of %s to %s", roadmap_path, agent, exc_info=True
        )
        return _next_slice_outcome("not_queued", next_key, agent)

    from ... import turn_scheduler

    try:
        await turn_scheduler.schedule_agent(project_id, agent)
    except Exception:  # noqa: BLE001 -- the entry is durable; the next drain delivers it
        logger.warning("could not schedule %s for the next slice", agent, exc_info=True)
    return _next_slice_outcome("queued", next_key, agent)


def _next_slice_message(
    *,
    roadmap_path: str,
    roadmap_title: str,
    approved_path: str,
    approved_slice: Dict[str, Any],
    tasks_created: List[str],
    following: Dict[str, Any],
) -> str:
    """The fixed Hub text of the drafting turn (C1a D4)."""
    tasks = ", ".join(tasks_created) if tasks_created else "none were created by this approval"
    link = f'{{"document": "{roadmap_path}", "slice": "{following["key"]}"}}'
    lines = [
        f"The operator approved `{approved_path}`, slice `{approved_slice['key']}` "
        f"({approved_slice.get('title', '')}) of the roadmap {roadmap_title!r} "
        f"(`{roadmap_path}`), and asked you to draft the next slice.",
        f"The approved slice's tasks: {tasks}.",
        f"The next slice is `{following['key']}`: {following.get('title', '')}.",
        f"- Intent: {following.get('intent') or '(not stated)'}",
        f"- Done when: {following.get('done') or '(not stated)'}",
        "Before drafting, read the roadmap with `read_spec_document`, and how the approved "
        "slice's tasks are going (their notes and evidence): what building it taught you belongs "
        "in this slice.",
        "Then create a change document with `create_spec_document` and submit it with "
        f"`roadmap: {link}`. Keep it to about a dozen requirements or fewer, as a few tasks. Do "
        "not implement anything.",
    ]
    return "\n".join(lines)


class _FlowWouldBeEmptyError(Exception):
    """A flow approval would create owning no open task: an outcome, not a fault (design D6 3a)."""


_NO_TASKS = "No flow was started: the approval gave it no tasks. Start a flow… once there is work."


def _not_created(message: str, agent: Optional[str] = None) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"state": "not_created", "messages": [message]}
    if agent:
        entry["agent"] = agent
    return entry


async def _existing_flow_entry(
    session: AsyncSession,
    project_id: str,
    document,
    delivery: Optional[spec_payload_module.Delivery],
    delivery_agent: Optional[str],
) -> Optional[Dict[str, Any]]:
    """The report entry for a flow already declaring the document, or None when there is none.

    Looked up whatever the delivery says (R3): a re-approval after a reopen, or a `mode: none`
    document given a flow by Start a flow… since. Its state is named, because an ended flow does
    not build anything, whatever it still claims.
    """
    existing = (
        await session.execute(
            select(Loop, AIJob)
            .join(AIJob, AIJob.id == Loop.job_id)
            .where(
                Loop.project_id == project_id,
                Loop.spec_document_id == document.id,
                Loop.archived_at.is_(None),
            )
        )
    ).first()
    if existing is None:
        return None
    loop, job = existing
    if loop.ending_state:
        flow_state = "ended"
        said = (
            f"The flow {job.name} declares this document but has ended; the new tasks wait for "
            "it. Archive it and start a flow."
        )
    elif not job.enabled:
        flow_state = "disabled"
        said = (
            f"The flow {job.name} declares this document but is disabled; the new tasks wait "
            "for it."
        )
    else:
        flow_state = "running"
        said = f"The flow {job.name} already builds this document."
    messages = [said]
    if delivery_agent is not None:
        chosen = delivery_agent or "no flow"
        messages.append(
            f"The agent you chose, {chosen}, was not applied: the flow {job.name} already "
            "declares this document."
        )
    if (
        delivery is not None
        and delivery.mode == "flow"
        and delivery.agent
        and job.agent != delivery.agent
    ):
        messages.append(f"The flow {job.name} runs as {job.agent}, not {delivery.agent}.")
    return {
        "state": "existing",
        "job_id": job.id,
        "name": job.name,
        "agent": job.agent,
        "flow_state": flow_state,
        "messages": messages,
    }


async def _approval_flow(
    session: AsyncSession,
    project_id: str,
    document,
    payload: Optional[Dict[str, Any]],
    delivery_agent: Optional[str],
) -> Tuple[Dict[str, Any], Optional[AIJob]]:
    """Create the flow a change document's delivery asks for, or say why none was (design D6).

    Returns the report's `flow` entry and the job, when one was created. Everything read after a
    savepoint rolled back is a plain value captured before it: rolling back expires what was
    touched inside, and reading that raises `MissingGreenlet` (measured, R2).
    """
    if document.kind != "change-spec":
        return {
            "state": "not_applicable",
            "messages": ["Only a change document declares a delivery, so no flow was started."],
        }, None

    delivery = _delivery_of(payload)
    existing = await _existing_flow_entry(session, project_id, document, delivery, delivery_agent)
    if existing is not None:
        return existing, None

    if delivery is None:
        return {"state": "none", "messages": ["No delivery was declared."]}, None
    if delivery.mode != "flow":
        return {
            "state": "none",
            "messages": ["The delivery says no flow: the tasks are on the board, started by hand."],
        }, None
    if delivery_agent == "":
        return _not_created("You chose no flow at approval."), None

    agent = delivery_agent if delivery_agent is not None else delivery.agent
    if not agent:
        return _not_created("The delivery names no agent, so no flow was started."), None
    agent_state = await delivery_agent_state(session, project_id, agent)
    if agent_state == "archived":
        return _not_created(f"{agent} is archived, so no flow was started.", agent), None
    if agent_state == "unknown":
        return (
            _not_created(
                f"{agent} is not an agent on this project, so no flow was started.", agent
            ),
            None,
        )
    if not delivery.stop_when_queue_empties and not delivery.stop_at:
        return (
            _not_created("The delivery sets no stop condition, so no flow was started.", agent),
            None,
        )
    stop_at: Optional[datetime] = None
    if delivery.stop_at:
        stop_at = datetime.fromisoformat(delivery.stop_at)
        if stop_at <= datetime.now(timezone.utc):
            message = (
                f"The delivery's stop time, {delivery.stop_at}, has passed, so no flow was started."
            )
            return _not_created(message, agent), None

    title = document.title or document.path
    try:
        async with session.begin_nested():
            # Built inside the guarded block (R3): a `ValidationError` outside it would be a 500
            # after the transition.
            request = JobCreate(
                name=title[:256],
                agent=agent,
                message=f'Work the next task of "{title}".',
                cron=delivery.cron,
                purpose="",
                stop_at=stop_at,
                stop_when_queue_empties=delivery.stop_when_queue_empties,
                spec_document_id=document.id,
            )
            job, loop = await build_flow_rows(session, project_id, request, created_by_run_id=None)
            if loop is None:  # `purpose=""` opts in, so this cannot happen
                raise RuntimeError("the flow's loop was not created")
            # A loop whose queue was never filled fires a turn on every tick and never stops
            # (`_loop_stall_reason`, `_loop_stop_reason`), so a flow with nothing to do is not made.
            open_tasks = (
                await session.execute(
                    select(func.count())
                    .select_from(Task)
                    .where(Task.loop_id == loop.id, Task.status.not_in(TERMINAL_STATUSES))
                )
            ).scalar_one()
            if open_tasks == 0:
                raise _FlowWouldBeEmptyError()
            # Inside the savepoint, so the row commits with the flow or not at all (R3).
            await persist_event(
                session,
                project_id,
                "job_created",
                {"id": job.id, "name": job.name, "agent": agent},
                agent=agent,
                commit=False,
            )
            job_id, job_name = job.id, job.name
    except _FlowWouldBeEmptyError:
        return _not_created(_NO_TASKS, agent), None
    except HTTPException as exc:
        reason = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _not_created(f"No flow was started: {reason}", agent), None
    except Exception:
        logger.exception("could not create the flow for %s", document.path)
        return _not_created("The flow could not be created.", agent), None

    return {
        "state": "created",
        "job_id": job_id,
        "name": job_name,
        "agent": agent,
        "flow_state": "running",
        "messages": [f"The flow {job_name} was started as {agent}; it fires at its next tick."],
    }, job


@router.post("/documents/{path:path}/merge")
async def merge_document(
    path: str,
    body: MergeRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The corpus absorbs a finished change: fold its content into a capability document.

    An explicit authored merge, not automatic requirement migration — the operator supplies the
    payload the capability document ends up with, citing which finished changes it draws from. Every
    refusal happens before anything is written, the same discipline `rename_document` already
    follows.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)

    if document.kind != "capability":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"{path} is not a capability document",
                "code": "not_a_capability",
            },
        )

    sources = []
    for source_path in body.from_changes:
        try:
            safe_source_path = validate_spec_path(source_path)
        except SpecPathError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        source = await spec_lifecycle.get_document(session, project_id, safe_source_path)
        if source is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"no specification document at {safe_source_path}",
            )
        if source.phase not in (spec_lifecycle.APPROVED, spec_lifecycle.ARCHIVED):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"{source_path} is {source.phase!r}; a merge names a finished change",
                    "code": "source_not_finished",
                },
            )
        sources.append(source)

    try:
        result = await spec_service.merge_document(
            session, workspace, document, sources, body.payload, actor=_operator(), note=body.note
        )
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code, "field": exc.field_path},
        ) from exc

    # `document.rigor` decides which shape `save_document` returned (spec_service.py:148); build
    # the response for whichever it was BEFORE committing, so a shape this handler forgets to
    # support fails loudly here instead of 500ing after the write is already durable.
    if isinstance(result, spec_service.ProposeResult):
        response = {
            **_document_view(document),
            "proposals": result.proposals,
            "unchanged": result.unchanged,
            "already_pending": result.already_pending,
            "merged": 0,
        }
    else:
        response = {**_document_view(document), "blocking": result.blocking, "merged": len(sources)}

    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return response
