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

from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import (
    project_workspace,
    requirement_coverage,
    requirement_evidence,
    requirement_links,
    spec_adoption,
    spec_documents,
    spec_index,
    spec_lifecycle,
    spec_naming,
    spec_rigor,
    spec_service,
    spec_tasks,
)
from ... import (
    spec_payload as spec_payload_module,
)
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    EVIDENCE_RETENTION_POLICIES,
    EvidenceFootprint,
    EvidenceReview,
    Project,
    RequirementDrift,
    RequirementEvidence,
    SpecEditProposal,
    SpecRequirement,
)
from ...spec_manifest import SpecPathError, validate_spec_path
from ...spec_payload import SCHEMA_VERSION
from ...sse import sse_manager

router = APIRouter(prefix="/project", tags=["spec"])

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

    return {
        "path": path,
        "content": content,
        "updated_at": spec_documents.document_updated_at(workspace, path),
    }


class DocumentCreate(BaseModel):
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

    model_config = {"extra": "forbid"}


class PhaseRequest(BaseModel):
    reason: str = Field(default="", max_length=2000)

    model_config = {"extra": "forbid"}


class MergeRequest(BaseModel):
    """The operator folding a finished change's content into a capability document.

    `from_changes` names sources by path, like every other document-scoped route in this file —
    the operator, in the UI, is looking at paths, not database ids.
    """

    payload: dict = Field(description="Same shape submit_spec_document accepts.")
    from_changes: list[str] = Field(min_length=1, max_length=16)
    note: str = Field(default="", max_length=2000)

    model_config = {"extra": "forbid"}


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
    return {"documents": [_document_view(document) for document in documents]}


class EvidenceRecord(BaseModel):
    """What the operator records to demonstrate a requirement."""

    identifier: str = Field(max_length=32)
    kind: str = Field(default="manual_observation", max_length=32)
    locator: str = Field(default="", max_length=4096)
    summary: str = Field(default="", max_length=10000)
    document: Optional[str] = Field(default=None, max_length=255)
    task_id: Optional[str] = Field(default=None, max_length=64)


class EvidenceDecision(BaseModel):
    decision: str = Field(max_length=16)
    reason: str = Field(default="", max_length=10000)


class DriftResolution(BaseModel):
    resolution: str = Field(max_length=32)


class RetentionSetting(BaseModel):
    policy: str = Field(max_length=16)


class ReindexRequest(BaseModel):
    """Optional inputs to a reindex. The body itself is optional; all fields default.

    `home` exists because the Hub refuses to choose one. `_select_home` treats a guess as
    indistinguishable from an operator's decision, so a corpus with several documents and no
    recorded home cannot be written until someone says which is home — and this is where the
    operator says it. A home already recorded in a valid index is preserved without passing
    anything.
    """

    home: Optional[str] = Field(default=None, max_length=255)


class DocumentAdopt(BaseModel):
    """Tracking a document that is already on disk.

    Carries a path and nothing else. Everything else about the document — its
    title, its kind, the phase it is in — is read from the file, because a caller
    able to state those could state them differently from what the file says, and
    the whole point of adoption is that the file is what is being believed.
    """

    path: str = Field(max_length=255)

    model_config = {"extra": "forbid"}


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


class DocumentContent(BaseModel):
    """The operator's equivalent of an agent submission's body, minus the path.

    The path is in the URL, matching every other operator document route. There is deliberately no
    actor field: identity comes from the credential, and a body that could name one would be a way
    to assert an identity the caller does not hold.
    """

    document: Any

    model_config = {"extra": "forbid"}


class RigorRequest(BaseModel):
    """The operator setting how strictly a document is enforced.

    `expected_digest` is compare-and-swap: a rigor change must not land on a
    document somebody edited underneath it, or what was promoted is not what was
    read. Optional so a caller that has not read the document can still act, and
    supplied by every UI path that has.
    """

    rigor: str = Field(max_length=16)
    reason: str = Field(default="", max_length=2000)
    expected_digest: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


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


class ProposalDecision(BaseModel):
    reason: str = Field(default="", max_length=2000)
    # The operator's own last-seen digest — a second, independent check from the proposal's own
    # `expected_digest` (design D4, round-3 clarification). Optional so a caller that has not read
    # the document can still act.
    expected_digest: Optional[str] = Field(default=None, max_length=64)

    model_config = {"extra": "forbid"}


@router.post("/documents/{path:path}/proposals/{proposal_id}/accept")
async def accept_proposal_route(
    path: str,
    proposal_id: str,
    body: ProposalDecision,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Apply one pending proposal's unit, or refuse and say why. There is no agent equivalent."""
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
        )
    except spec_service.ProposalRefusedError as exc:
        # `accept_proposal` may have marked the row `stale` before raising — that mutation must
        # survive this response, not be rolled back with everything else an exception discards.
        await session.commit()
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
    body: ProposalDecision,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Refuse a pending proposal. The live document is untouched — nothing to clean up."""
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
        "unserved": [row.identifier for row in unserved],
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
    return _evidence_view(evidence)


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
        rows = list(
            (
                await session.execute(
                    select(RequirementEvidence)
                    .where(RequirementEvidence.project_id == project_id)
                    .order_by(RequirementEvidence.produced_at)
                )
            )
            .scalars()
            .all()
        )
    prints = await _footprints_for(session, [row.id for row in rows])
    reviews = await _latest_reviews_for(session, [row.id for row in rows])
    return {
        "evidence": [_evidence_view(row, prints.get(row.id), reviews.get(row.id)) for row in rows]
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
        raise HTTPException(
            status_code=403, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await session.commit()
    return _evidence_view(evidence, latest_review=review)


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
    return {
        "drift": [
            {
                "id": row.id,
                "requirement_id": row.requirement_id,
                "evidence_id": row.evidence_id,
                "state": row.state,
                "observed": row.observed,
                "resolution": row.resolution,
            }
            for row in rows
        ]
    }


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
        "footprint": (
            {
                "kind": footprint.kind,
                "branch": footprint.branch,
                "commit_sha": footprint.commit_sha,
                "reachable_from_main": footprint.reachable_from_main,
            }
            if footprint is not None
            else None
        ),
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
                .order_by(EvidenceReview.created_at, EvidenceReview.id)
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
    body: PhaseRequest,
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
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)

    try:
        await spec_lifecycle.transition(
            session, document, to_phase=to, actor=_operator(), reason=body.reason
        )
    except spec_lifecycle.PhaseError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code},
        ) from exc

    # Approval is what turns a decomposition from a description into work. The payload has always
    # carried `tasks`, validated on save and read by the completeness check; until now nothing
    # materialised them, so an operator approving a document got an empty board and re-described
    # the decomposition by hand.
    created = []
    if document.phase == "approved":
        content = spec_documents.read_document(workspace, document.path)
        payload = spec_payload_module.extract_payload(content) if content else None
        created = await spec_tasks.materialise_quietly(
            session, document, payload, actor=_operator()
        )

    await spec_service.rerender_phase(session, workspace, document)
    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    if created:
        await sse_manager.broadcast(project_id, "task_updated", {"created": len(created)})
    return {**_document_view(document), "tasks_created": [task.id for task in created]}


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
            "merged": 0,
        }
    else:
        response = {**_document_view(document), "blocking": result.blocking, "merged": len(sources)}

    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return response
