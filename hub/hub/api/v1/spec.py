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

from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ... import (
    project_workspace,
    requirement_coverage,
    requirement_evidence,
    requirement_links,
    spec_documents,
    spec_index,
    spec_lifecycle,
    spec_naming,
    spec_rigor,
    spec_service,
)
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    EVIDENCE_RETENTION_POLICIES,
    Project,
    RequirementDrift,
    RequirementEvidence,
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
    return {
        "specs": state.specs,
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


async def _mint_document_path(session: AsyncSession, project_id: str, workspace) -> str:
    """A free placeholder path, free against both the records and the disk.

    A name is only available if nothing at all occupies it: a document the
    project has recorded, or a file somebody put there by hand.
    """
    recorded = {
        document.path for document in await spec_lifecycle.list_documents(session, project_id)
    }

    def is_taken(candidate: str) -> bool:
        return candidate in recorded or spec_documents.document_exists(workspace, candidate)

    return spec_naming.mint_placeholder_path(is_taken)


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
        "evidence": [_evidence_view(row) for row in evidence],
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
    return {"evidence": [_evidence_view(row) for row in rows]}


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
        await requirement_evidence.decide(
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
    return _evidence_view(evidence)


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


def _evidence_view(evidence) -> dict:
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
        # A record whose artifact is gone reports that state rather than disappearing.
        "artifact_removed": evidence.artifact_removed_at is not None,
        "produced_at": evidence.produced_at.isoformat(),
    }


@router.post("/spec/reindex")
async def reindex(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Rebuild the requirement index from the files, then retry unresolved references.

    The operator's, not an agent's. Two things need it: a project whose documents
    predate the index, and a document edited outside the Hub. Both are cases where
    the index is behind the files, and neither can be detected without reading
    them — so this is offered rather than guessed at on a timer.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    results = await spec_index.reindex_project(session, workspace, project_id)
    backfilled = await requirement_links.backfill_project(session, project_id)
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
    }


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
            path = await _mint_document_path(session, project_id, workspace)
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

    await spec_service.rerender_phase(session, workspace, document)
    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return _document_view(document)
