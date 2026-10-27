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
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import Field, StringConstraints
from sqlalchemy import func, literal_column, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ... import (
    already_built,
    blocking,
    builds,
    deletion,
    loop_history,
    project_workspace,
    requirement_coverage,
    requirement_evidence,
    requirement_links,
    run_divergence,
    run_liveness,
    slice_drafting,
    spec_adoption,
    spec_conversion,
    spec_documents,
    spec_index,
    spec_journey,
    spec_lifecycle,
    spec_naming,
    spec_service,
    spec_tasks,
    task_integration,
    task_transitions,
    vault_spec_check,
)
from ... import (
    spec_payload as spec_payload_module,
)
from ...auth import get_project
from ...db.engine import get_session
from ...db.models import (
    DRIFT_STATES,
    Agent,
    AIJob,
    EvidenceFootprint,
    EvidenceReview,
    Loop,
    Project,
    RequirementDrift,
    RequirementEvidence,
    SpecDocument,
    SpecDocumentEvent,
    SpecDocumentMerge,
    SpecRequirement,
    SpecRequirementRevision,
    Task,
)
from ...schemas.common import RequestModel
from ...schemas.jobs import JobCreate
from ...spec_manifest import (
    Manifest,
    SpecPathError,
    describe_diagnostic,
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
    # The walk, the stats and the reads run off the loop (`blocking`, D1); a file unchanged since
    # the last listing is not read again (`read_listed_document`, D4).
    state = await blocking.run(spec_documents.listed_state, workspace)

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
    # F702: discovery cannot see rows, so it says a rebuild files every unfiled document. A rebuild
    # files only tracked ones; an untracked one is told to be adopted first. The code is kept.
    diagnostics = [
        (
            {**d, "message": describe_diagnostic("untracked_document", d.get("path"))}
            if d.get("code") == "unfiled_document" and d.get("path") not in tracked
            else d
        )
        for d in state.diagnostics
    ]

    return {
        "specs": specs,
        "home": state.home,
        "manifest": state.index,
        "missing": state.missing,
        "diagnostics": diagnostics,
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

#: `SpecDocumentEvent.kind` of the record Build leaves (`exploring-ends-at-an-approved-plan`, FR-6):
#: an event of its own, so approval and build are two entries in the document's history.
BUILD_REPORT = "build"

#: Where a document is read for its delivery's agent: while it is being written, and once approved,
#: where Build starts what it recommends.
_DELIVERY_PHASES = ("exploring", "approved")


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
    return spec_documents.read_payload(workspace, path)


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
        status: Dict[str, Any] = {"state": "stale", "agent": "", "reason": "unknown"}
    else:
        state = await delivery_agent_state(session, project_id, delivery.agent)
        status = (
            {"state": "ok", "agent": delivery.agent}
            if state == "ok"
            else {"state": "stale", "agent": delivery.agent, "reason": state}
        )
    # Who reviews (F508): the default by name with the same usability test as the builder, or no
    # key at all, which the approval bar reads as "any free agent". A review never falls back from
    # a stale default to someone else (`review_turn.resolve_declared_reviewer`), so it is flagged.
    if delivery.reviewer:
        status["reviewer"] = delivery.reviewer
        status["reviewer_state"] = await delivery_agent_state(
            session, project_id, delivery.reviewer
        )
    return status


async def _approval_outcome(
    session: AsyncSession, document, kind: str = APPROVAL_REPORT
) -> Optional[Dict[str, Any]]:
    """The newest approval report (or, with `kind=BUILD_REPORT`, build report), chosen by the Hub
    so the UI never picks (design D7).

    `created_at` alone ties on this machine (a 15.625 ms wall clock), so insertion order breaks
    the tie: `spec_document_events` has a `String` primary key, so it is a rowid table.
    """
    return (
        await session.execute(
            select(SpecDocumentEvent.detail)
            .where(
                SpecDocumentEvent.document_id == document.id,
                SpecDocumentEvent.kind == kind,
            )
            .order_by(
                SpecDocumentEvent.created_at.desc(),
                literal_column("spec_document_events.rowid").desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def _retirement(session: AsyncSession, document) -> Dict[str, Any]:
    """Why a capability was retired and what absorbed it, from its retiring phase event (F536)."""
    event = (
        (
            await session.execute(
                select(SpecDocumentEvent)
                .where(
                    SpecDocumentEvent.document_id == document.id,
                    SpecDocumentEvent.kind == "phase",
                )
                .order_by(SpecDocumentEvent.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    detail = (event.detail if event is not None else None) or {}
    return {
        "reason": detail.get("reason", ""),
        "absorbed_by": detail.get("absorbed_by"),
        "at": event.created_at.isoformat() if event is not None else None,
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

    document = await spec_lifecycle.get_document(session, project_id, path)
    # The file is the payload; the page is rendered from it here (FR-2). Divergence is still
    # measured against the stored bytes, which are what the Hub recorded.
    page = await spec_service.render_page(session, workspace, path, content, document)
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"{path} holds no readable spec payload",
                "code": "payload_unreadable",
            },
        )
    payload = {
        "path": path,
        "content": page,
        "updated_at": spec_documents.document_updated_at(workspace, path),
        # The version of what this read shows: an approval names it, and is refused when the
        # document has changed since (`approve-what-was-seen`).
        "content_version": spec_documents.content_version(content),
    }
    payload.update(await _divergence_fields(session, project_id, path, content))
    if document is not None:
        stored_payload = spec_documents.parse_stored(content)
        status_now = await _delivery_status(session, project_id, document, stored_payload)
        if status_now is not None:
            payload["delivery_status"] = status_now
        recommended = _recommended_build(document, stored_payload)
        if recommended is not None:
            payload["recommended_build"] = recommended
        # Every build of this document, newest first: how it was built, by whom, within what.
        payload["builds"] = [
            await builds.view(session, row) for row in await builds.builds_of(session, document.id)
        ]
        fold_state = await _fold_state(session, document)
        if fold_state is not None:
            payload["fold_state"] = fold_state
        if document.kind == "capability" and document.phase == spec_lifecycle.ARCHIVED:
            payload["retired"] = await _retirement(session, document)
        # The roadmap slice this document specifies, so the app can offer "Draft the next slice"
        # beside Approve (C1a D7). Absent on every other document.
        link = (spec_documents.parse_stored(content) or {}).get("roadmap")
        if document.kind == "change-spec" and isinstance(link, dict):
            payload["roadmap_slice"] = {
                "document": link.get("document"),
                "slice": link.get("slice"),
            }
        if document.phase == "approved":
            outcome = await _approval_outcome(session, document)
            if outcome is not None:
                payload["approval_outcome"] = outcome
            built = await _approval_outcome(session, document, BUILD_REPORT)
            if built is not None:
                payload["build_outcome"] = built
    return payload


def _recommended_build(document, payload: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """What Build and Approve and build open with (`recommend-a-build`): the delivery the document
    recommends, with the reason given for each choice, or None on a document that declares none."""
    if document.kind != "change-spec":
        return None
    delivery = _delivery_of(payload)
    if delivery is None:
        return None
    return {
        "mode": delivery.mode,
        "agent": delivery.agent,
        "reviewer": delivery.reviewer,
        "tester": delivery.tester,
        "cron": delivery.cron,
        "stop_when_queue_empties": delivery.stop_when_queue_empties,
        "stop_at": delivery.stop_at,
        # The build's settings (slice D), each resolved the way Build resolves it when left out:
        # `mode` flow/none reads as driver flow/hand, and no level as Reviewed.
        "driver": delivery.driver or ("flow" if delivery.mode == "flow" else "hand"),
        "level": delivery.level or builds.REVIEWED,
        "builders": list(delivery.builders),
        "reviewers": list(delivery.reviewers),
        "lead": delivery.lead,
        "budget_cap_usd": delivery.budget_cap_usd,
        "landing": delivery.landing or builds.LANDING_MAIN,
        "task_builders": _declared_builders(payload),
        "reasons": dict(delivery.reasons),
    }


def _declared_builders(payload: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Each declared task's builder by key (F1046), as the document names it."""
    return {
        str(entry.get("key")): entry.get("builder")
        for entry in (payload or {}).get("tasks") or []
        if isinstance(entry, dict) and entry.get("key") and not entry.get("from")
    }


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
    # Refused when sent (FR-5, approval starts nothing): the agent of a build's flow is chosen at
    # Build or Approve and build. Kept as a field so the refusal names where it goes now.
    delivery_agent: Optional[str] = Field(default=None, max_length=32)
    # At approval, the `content_version` of the document read the operator approved
    # (`approve-what-was-seen`): required with to=approved, refused with any other move.
    content_version: Optional[str] = Field(default=None, max_length=64)
    # Refused when true (`amendments-main-watch-and-the-next-slice`, D6): the next slice is offered
    # once this slice is built. Kept as a field so the refusal names where it went.
    draft_next_slice: bool = False
    # Archiving an approved change that was folded into no capability, with `reason` saying why
    # (the archive guard in `spec_lifecycle.transition`).
    no_capability_change: bool = False
    # Retiring a capability (to=archived on a current capability, F536): the current capability
    # that absorbed what it described, if any. Refused on any other move.
    absorbed_by: Optional[str] = Field(default=None, max_length=255)
    # Approving over the gaps the first attempt listed (409 `approval_warnings`). Refused on any
    # other move; a refusal (`document_incomplete`) is not a gap and is not approved over.
    approve_anyway: bool = False


_AgentName = Annotated[str, StringConstraints(min_length=1, max_length=32)]


class _BuildChoices(RequestModel):
    """What the operator chooses when they press Build (`a-build-has-a-driver-a-level-and-its-
    people`, FR-1). Each field left out takes the recommended build's value (`recommended_build`),
    and where that says nothing, today's behaviour: the delivery's flow or none, any free agent,
    no cap, no window, landing on main."""

    # The operator's choice of agent for a flow delivery (design D5b, moved here from approval): a
    # name, or "" for no flow. Used for this build only; the document is never edited.
    delivery_agent: Optional[str] = Field(default=None, max_length=32)
    driver: Optional[Literal["flow", "lead", "hand"]] = None
    level: Optional[Literal["fast", "reviewed", "gated"]] = None
    builders: Optional[List[_AgentName]] = Field(default=None, max_length=32)
    reviewers: Optional[List[_AgentName]] = Field(default=None, max_length=32)
    lead: Optional[str] = Field(default=None, max_length=32)
    budget_cap_usd: Optional[float] = Field(default=None, gt=0, le=100_000)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    landing: Optional[Literal["main", "nowhere"]] = None
    # Each task's builder as the operator left it in the dialog, by task key; "" clears it.
    task_builders: Optional[Dict[str, Annotated[str, StringConstraints(max_length=32)]]] = None


class BuildRequest(_BuildChoices):
    """Building an approved document (FR-6), with the build's settings (slice D)."""


class ApproveAndBuildRequest(_BuildChoices):
    """Approving and building in one action (FR-7): approval's fields, then Build's."""

    reason: str = Field(default="", max_length=2000)
    content_version: Optional[str] = Field(default=None, max_length=64)
    approve_anyway: bool = False
    draft_next_slice: bool = False


class MergeRequest(RequestModel):
    """The operator folding a finished change's content into a capability document.

    `from_changes` names sources by path, like every other document-scoped route in this file —
    the operator, in the UI, is looking at paths, not database ids. Empty is the operator editing
    the capability, recorded as an edit: a capability's content changes only through a merge
    (`a-finished-change-is-folded-into-its-capability`).
    """

    payload: dict = Field(description="Same shape submit_spec_document accepts.")
    from_changes: list[str] = Field(default_factory=list, max_length=16)
    note: str = Field(default="", max_length=2000)


class FoldItemRequest(RequestModel):
    key: str = Field(max_length=64, description="The change's requirement key.")
    as_key: Optional[str] = Field(default=None, max_length=64)
    statement: Optional[str] = Field(default=None, max_length=4000)
    modal: Optional[str] = Field(default=None, max_length=16)
    replaces: Optional[str] = Field(default=None, max_length=64)


class FoldAlgorithmRequest(RequestModel):
    name: str = Field(max_length=200, description="The change's algorithm name.")
    replaces: Optional[str] = Field(default=None, max_length=200)


class FoldCriterionRequest(RequestModel):
    key: str = Field(max_length=64, description="The change's criterion key.")
    replaces: str = Field(max_length=64, description="The capability criterion it replaces.")


class FoldRequest(RequestModel):
    """The operator folding an approved change into a capability document, then archiving it."""

    into: str = Field(max_length=512, description="The capability document's path.")
    # None folds every requirement verbatim under its drafted key.
    requirements: Optional[list[FoldItemRequest]] = Field(default=None, max_length=64)
    archive: bool = True
    note: str = Field(default="", max_length=2000)
    # Capability requirements (with their criteria) and single criteria the change supersedes,
    # removed in the same merge (F533).
    retire: list[str] = Field(default_factory=list, max_length=256)
    retire_criteria: list[str] = Field(default_factory=list, max_length=256)
    # F753. None folds every change algorithm; a name the capability holds collides unless it is
    # named in `replaces`.
    algorithms: Optional[list[FoldAlgorithmRequest]] = Field(default=None, max_length=64)
    retire_algorithms: list[str] = Field(default_factory=list, max_length=64)
    # Change criteria folded in place of a named capability criterion, under its key.
    criteria: list[FoldCriterionRequest] = Field(default_factory=list, max_length=256)


def _document_view(document, steps: Optional[spec_journey.ProjectSteps] = None) -> dict:
    """The document as the app shows it; `steps` are its project's (built-in when omitted)."""
    return {
        "id": document.id,
        "path": document.path,
        "title": document.title,
        "kind": document.kind,
        "phase": document.phase,
        # What happens to work that ignores this document. Reported everywhere the phase is, because
        # they answer different questions and an operator reading one will assume the other.
        "content_digest": document.content_digest,
        "explore_closed": document.explore_closed_at is not None,
        # Where a change's authoring stands (`spec_journey`): null on any other document.
        "step": document.step,
        "size": document.size,
        "journey": (
            spec_journey.journey(document.size, steps)
            if spec_journey.has_journey(document)
            else None
        ),
        "updated_at": document.updated_at.isoformat(),
    }


async def _project_document_view(session: AsyncSession, project_id: str, document) -> dict:
    """The document's view with the journey its project's `spec/journey.json` gives it (FR-9)."""
    return _document_view(document, await spec_journey.project_steps(session, project_id))


async def _fold_state(session: AsyncSession, document) -> Optional[Dict[str, Any]]:
    """Where an approved or archived change stands on its way into the corpus, computed per read.

    `folded` once any merge names it; otherwise `tasks_open` while a task it declared is undecided,
    and `ready` when it is shipped but in no capability yet.
    """
    if document.kind != "change-spec" or document.phase not in ("approved", "archived"):
        return None
    capabilities = await spec_lifecycle.merged_into(session, document)
    open_tasks = await spec_lifecycle.open_task_ids(session, document)
    if capabilities:
        state = "folded"
    elif open_tasks:
        state = "tasks_open"
    else:
        state = "ready"
    from ... import spec_reconcile

    return {
        "state": state,
        "open_tasks": open_tasks,
        "capabilities": capabilities,
        # reconcile-and-measure FR-3: the latest reconcile result, or `{"state": "none"}`.
        "reconcile": spec_reconcile.view(await spec_reconcile.latest(session, document.id)),
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


async def _approval_overrides(session: AsyncSession, documents) -> Dict[str, List[Dict[str, Any]]]:
    """For each approved document, the gaps its latest approval went over (possibly none).

    Read from the approval's phase event, so a reopened document has no entry: its next approval
    records its own.
    """
    approved = {document.id for document in documents if document.phase == "approved"}
    if not approved:
        return {}
    rows = await session.execute(
        select(SpecDocumentEvent.document_id, SpecDocumentEvent.detail)
        .where(SpecDocumentEvent.document_id.in_(approved), SpecDocumentEvent.kind == "phase")
        .order_by(SpecDocumentEvent.created_at, SpecDocumentEvent.id)
    )
    latest: Dict[str, List[Dict[str, Any]]] = {}
    for document_id, detail in rows:
        if isinstance(detail, dict) and detail.get("to") == "approved":
            latest[document_id] = list(detail.get("warnings_overridden") or [])
    return latest


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

    steps = spec_journey.load(workspace) if workspace is not None else spec_journey.BUILT_IN
    overridden = await _approval_overrides(session, documents)
    from ... import spec_amendments

    amended = await spec_amendments.counts(session, [document.id for document in documents])
    # Every file is read off the loop in one hop (`blocking`, D1), and one unchanged since the last
    # listing is not read again (`read_listed_document`, D4). A file that cannot be read is left
    # out, which leaves its view without `diverged`, as before.
    paths = [document.path for document in documents]

    def _read_all() -> Dict[str, Optional[str]]:
        found: Dict[str, Optional[str]] = {}
        for path in paths:
            with contextlib.suppress(OSError, SpecPathError, project_workspace.ProjectPathError):
                found[path] = spec_documents.read_listed_document(workspace, path)
        return found

    on_disk = await blocking.run(_read_all) if workspace is not None else {}
    views = []
    for document in documents:
        view = _document_view(document, steps)
        if document.id in overridden:
            view["approval_warnings_overridden"] = overridden[document.id]
        if document.id in amended:
            # tester-amends: what a tester changed and how much the operator has yet to review.
            view["amendments"] = amended[document.id]
        if document.path in on_disk:
            content = on_disk[document.path]
            view["diverged"] = spec_lifecycle.divergence(document, content) is not None
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
    # The commit that did the work (F529), when the locator names a file instead. Verified like a
    # locator-named commit (F71): refused, never replaced by HEAD, when the repository lacks it.
    commit: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{7,40}$")
    # What it takes to judge the piece (vis-D5): the command run, its output (kept as its last 4000
    # characters) and whether it covers the requirement `full`y or only `partial`ly.
    command: Optional[str] = Field(default=None, max_length=2000)
    output: Optional[str] = Field(default=None, max_length=200000)
    covers: Optional[str] = Field(default=None, max_length=16)


class EvidenceDecision(RequestModel):
    decision: str = Field(max_length=16)
    reason: str = Field(default="", max_length=10000)


class EvidenceOverturn(RequestModel):
    """The operator reversing a decided piece (F692). The decision is the opposite of the current
    one, so only the reason is sent, and it is required."""

    reason: str = Field(default="", max_length=10000)


class DriftResolution(RequestModel):
    resolution: str = Field(max_length=32)


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
    refused until reopened.
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
            # A capability written outside a merge is refused for what the document is, not for a
            # malformed body.
            status_code=(
                status.HTTP_409_CONFLICT
                if exc.code == "capability_written_through_merge"
                else status.HTTP_422_UNPROCESSABLE_ENTITY
            ),
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
        "divergence": result.divergence,
        "blocking": result.blocking,
        "warnings": result.warnings,
    }


class RoadmapLink(RequestModel):
    """The roadmap slice a change document built: the roadmap's path and the slice's key."""

    document: str = Field(min_length=1, max_length=255)
    slice: str = Field(min_length=1, max_length=64)


@router.put("/documents/{path:path}/roadmap")
async def link_roadmap_slice(
    path: str,
    body: RoadmapLink,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Name the roadmap slice a change document built, at any phase, archived included (vis-D9).

    Changes the `roadmap` field and nothing else, so it is not a way around the content checks; the
    same link twice is a no-op, and a different one is refused (`spec_service.link_roadmap_slice`).
    """
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    workspace = await _workspace(session, project_id)
    try:
        roadmap_path = validate_spec_path(body.document)
    except SpecPathError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    try:
        changed = await spec_service.link_roadmap_slice(
            session, workspace, document, roadmap_path, body.slice, actor=_operator()
        )
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code, "field": exc.field_path},
        ) from exc
    await session.commit()
    if changed:
        await sse_manager.broadcast(
            project_id, "spec_updated", {"path": document.path, "phase": document.phase}
        )
    return {
        "path": document.path,
        "roadmap": {"document": roadmap_path, "slice": body.slice},
        "changed": changed,
    }


class ReconcileAsk(RequestModel):
    """The agent the operator asks to reconcile a change with its code."""

    agent: str = Field(max_length=64)


@router.post("/documents/{path:path}/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def ask_reconcile(
    path: str,
    body: ReconcileAsk,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Start `agent`'s turn reconciling an approved change with its code, with the Hub's brief."""
    from ... import spec_reconcile
    from .agent_trigger import TriggerAgentRequest, trigger_agent

    project_id, _ = project
    document = await _require_document(session, project_id, path)
    if document.kind != "change-spec" or document.phase != spec_lifecycle.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "reconcile_not_approved",
                "message": "only an approved change is reconciled with its code",
            },
        )
    return await trigger_agent(
        TriggerAgentRequest(
            agent=body.agent, message=spec_reconcile.brief(document), spec_document=document.path
        ),
        project=project,
        session=session,
    )


class AlreadyBuiltClose(RequestModel):
    """The commit or commits on the main branch that already hold a document's work."""

    commits: List[str] = Field(min_length=1, max_length=already_built.MAX_COMMITS)
    # The level the tasks close at (slice D): `fast` approves them at once, their evidence
    # accepted; any other level, or none, leaves them under review for their evidence, as before.
    level: Optional[Literal["fast", "reviewed", "gated"]] = None


@router.post("/documents/{path:path}/close-already-built")
async def close_already_built(
    path: str,
    body: AlreadyBuiltClose,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Close every open task of an approved change as already built, against *commits*
    (`every-task-can-always-be-moved-on` FR-5, FR-6).

    Each open task moves to `under_review`, held by nobody, its history naming this action and the
    commits; no run starts. Each requirement each task serves gets a piece of evidence pointing at
    the commits, `awaiting` a decision; a task is approved once its pieces are accepted
    (`already_built.approve_what_was_waiting_for_this_evidence`). 409 `not_approved`,
    `no_main_branch`, `nothing_open`, `turn_running`, `move_refused`; 422 `no_commits`,
    `commit_not_on_main`. Nothing changes on a refusal.
    """
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    workspace = await _workspace(session, project_id)
    try:
        result = await already_built.close(
            session, document, body.commits, workspace=workspace, level=body.level
        )
    except already_built.AlreadyBuiltRefused as exc:
        await session.rollback()
        raise HTTPException(
            status_code=exc.http_status,
            detail={"message": str(exc), "code": exc.code, **exc.detail},
        ) from exc
    await session.commit()
    for task in result["tasks"]:
        await sse_manager.broadcast(
            project_id, "task_updated", {"id": task["id"], "status": task["status"]}
        )
    await sse_manager.broadcast(project_id, "spec_updated", {"path": document.path})
    return result


class DefectRecord(RequestModel):
    """A defect the operator records against a change, and the step that caught it."""

    summary: str = Field(max_length=2000)
    caught_by: str = Field(max_length=64)


@router.post("/documents/{path:path}/defects", status_code=status.HTTP_201_CREATED)
async def record_defect(
    path: str,
    body: DefectRecord,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Record a defect against a change, caught at a journey step or a post-approval stage."""
    from ... import spec_defects

    project_id, _ = project
    document = await _require_document(session, project_id, path)
    workspace = await _workspace(session, project_id)
    allowed = spec_defects.steps(spec_journey.load(workspace).order())
    try:
        result = await spec_defects.record(
            session,
            document,
            summary=body.summary,
            caught_by=body.caught_by,
            allowed_steps=allowed,
            actor=_operator(),
        )
    except spec_defects.DefectRefused as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "defect_invalid", "message": str(exc), "field": exc.field},
        ) from exc
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": document.path})
    return result


@router.get("/spec/defects")
async def defects_report(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Each change with defects, the step that caught each, and a count per step."""
    from ... import spec_defects

    project_id, _ = project
    documents = await spec_lifecycle.list_documents(session, project_id)
    found = await spec_defects.for_documents(session, documents)
    by_id = {document.id: document for document in documents}
    changes = [
        {
            "document_id": document_id,
            "path": by_id[document_id].path,
            "title": by_id[document_id].title,
            "phase": by_id[document_id].phase,
            "defects": defects,
            "by_step": spec_defects.by_step(defects),
        }
        for document_id, defects in found.items()
        if defects
    ]
    return {"changes": changes}


class AmendmentReviewRequest(RequestModel):
    """Which amendments the operator has reviewed: the ids, or every not-reviewed one when absent."""

    ids: Optional[List[str]] = None


class ReportResponse(RequestModel):
    """The operator's answer to a cannot-satisfy report (F700): `amend` with the criterion fields
    to change, `accept`, or `reject` with a reason."""

    response: str = Field(max_length=16)
    reason: str = Field(default="", max_length=2000)
    change: Optional[Dict[str, Any]] = None


@router.get("/documents/{path:path}/amendments")
async def list_amendments(
    path: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """A document's amendments, oldest first, each with its author, run and whether reviewed."""
    from ... import spec_amendments

    project_id, _ = project
    document = await _require_document(session, project_id, path)
    return {
        "amendments": [
            amendment.to_dict()
            for amendment in await spec_amendments.list_amendments(session, document)
        ]
    }


@router.post("/documents/{path:path}/amendments/review")
async def review_amendments(
    path: str,
    body: AmendmentReviewRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Mark amendments reviewed, per item (`ids`) or for the whole document. The operator's only."""
    from ... import spec_amendments

    project_id, _ = project
    document = await _require_document(session, project_id, path)
    try:
        marked = await spec_amendments.mark_reviewed(
            session, document, ids=body.ids, actor=_operator()
        )
    except spec_amendments.AmendmentRefused as exc:
        raise HTTPException(
            status_code=exc.status, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return {
        "marked": marked,
        "amendments": [
            amendment.to_dict()
            for amendment in await spec_amendments.list_amendments(session, document)
        ],
    }


@router.post("/documents/{path:path}/amendments/{amendment_id}/respond")
async def respond_to_report(
    path: str,
    amendment_id: str,
    body: ReportResponse,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator's answer to a cannot-satisfy report (F700): amend the criterion, accept the
    report, or reject it. Each answer does something, is recorded on the report, and is sent to the
    reporter as input."""
    from ... import spec_amendments
    from ...turn_scheduler import schedule_accepted

    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    try:
        answer = await spec_amendments.respond_to_report(
            session,
            workspace,
            document,
            amendment_id,
            response=body.response,
            reason=body.reason,
            change=body.change,
            actor=_operator(),
        )
    except spec_amendments.AmendmentRefused as exc:
        detail: Dict[str, Any] = {"message": str(exc), "code": exc.code}
        if exc.field:
            detail["field"] = exc.field
        raise HTTPException(status_code=exc.status, detail=detail) from exc
    reporter = answer.pop("reporter")
    note = answer.pop("note")
    await spec_amendments.queue_note_to_reporter(session, project_id, reporter, note)
    document_path, phase = document.path, document.phase
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": document_path, "phase": phase})
    if answer.get("task_id"):
        await sse_manager.broadcast(project_id, "task_updated", {"id": answer["task_id"]})
    # The note is committed: a failed start is logged and retried by the Hub, never this answer's
    # failure (`schedule_accepted`).
    await schedule_accepted(project_id, reporter)
    return {
        **answer,
        "amendments": [
            amendment.to_dict()
            for amendment in await spec_amendments.list_amendments(session, document)
        ],
    }


class AmendmentDecline(RequestModel):
    """Why the operator declines a proposed amendment; the proposer reads it."""

    reason: str = Field(max_length=2000)


async def _told_of_decision(session: AsyncSession, project_id: str, document, decision) -> None:
    """Queue the decision to its proposer, commit, tell every view, and start the proposer's turn
    (a failed start is retried by the Hub, never this decision's failure)."""
    from ... import spec_amendments
    from ...turn_scheduler import schedule_accepted

    if decision.proposer:
        await spec_amendments.queue_note_to_reporter(
            session, project_id, decision.proposer, decision.note
        )
    document_path, phase = document.path, document.phase
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": document_path, "phase": phase})
    if decision.task_created:
        await sse_manager.broadcast(project_id, "task_created", {"id": decision.task_created})
    if decision.proposer:
        await schedule_accepted(project_id, decision.proposer)


@router.post("/documents/{path:path}/amendments/{amendment_id}/accept")
async def accept_amendment(
    path: str,
    amendment_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator accepts a proposed amendment (`amendments-main-watch-and-the-next-slice`, D1):
    applied to the document as it stands now, or refused 409 `amendment_stale` naming why when it
    no longer applies (recorded, and the proposer told). An added task joins the running build."""
    from ... import spec_amendments

    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    try:
        decision = await spec_amendments.accept_proposal(
            session, workspace, document, amendment_id, actor=_operator()
        )
    except spec_amendments.AmendmentRefused as exc:
        raise HTTPException(
            status_code=exc.status, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await _told_of_decision(session, project_id, document, decision)
    if decision.state == spec_amendments.STALE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": decision.message, "code": "amendment_stale"},
        )
    return {
        **decision.to_dict(),
        "amendments": [
            amendment.to_dict()
            for amendment in await spec_amendments.list_amendments(session, document)
        ],
    }


@router.post("/documents/{path:path}/amendments/{amendment_id}/decline")
async def decline_amendment(
    path: str,
    amendment_id: str,
    body: AmendmentDecline,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator declines a proposed amendment with a reason; the proposer is told."""
    from ... import spec_amendments

    project_id, _ = project
    document = await _require_document(session, project_id, path)
    try:
        decision = await spec_amendments.decline_proposal(
            session, document, amendment_id, reason=body.reason, actor=_operator()
        )
    except spec_amendments.AmendmentRefused as exc:
        detail: Dict[str, Any] = {"message": str(exc), "code": exc.code}
        if exc.field:
            detail["field"] = exc.field
        raise HTTPException(status_code=exc.status, detail=detail) from exc
    await _told_of_decision(session, project_id, document, decision)
    return {
        **decision.to_dict(),
        "amendments": [
            amendment.to_dict()
            for amendment in await spec_amendments.list_amendments(session, document)
        ],
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
    # The same scope as the report (F593): no archived document in the project's rollup, and a
    # requirement served through a fold is not "no work linked".
    reported = {entry.requirement_id: entry for entry in report.requirements}
    in_scope = set(reported) | {entry.requirement_id for entry in report.diagnostics}
    unserved = [
        row
        for row in unserved
        if (document_id is not None or row.id in in_scope)
        and not (row.id in reported and reported[row.id].served_by)
    ]
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
    views = await _evidence_views(session, project_id, evidence)
    story = await _requirement_story(session, project_id, requirement)
    return {
        "requirement": {
            "id": requirement.id,
            "identifier": requirement.identifier,
            "key": requirement.key,
            "document_id": requirement.document_id,
            "state": requirement.state,
            "digest": requirement.digest,
            "anchor": requirement.anchor,
            "statement": story["statement"],
            "document": story["document"],
        },
        # How it changed (slice requirement-story): oldest first, as recorded. `statement` is null
        # on a retirement and on every revision recorded before migration 0131.
        "revisions": story["revisions"],
        # Every drift row, resolved and superseded included, oldest first.
        "drift": story["drift"],
        "tasks": [
            {"id": task.id, "title": task.title, "status": task.status, "assignee": task.assignee}
            for task in tasks
        ],
        "evidence": views,
        # Never omitted, and never without its integration answer.
        "coverage": coverage.to_dict() if coverage else None,
    }


#: How close a revision and a merge row must be to belong to one fold (one transaction).
_FOLD_WINDOW_SECONDS = 5.0


async def _requirement_story(
    session: AsyncSession, project_id: str, requirement: SpecRequirement
) -> Dict[str, Any]:
    """The requirement's current wording and document, its revisions and its drift."""
    from ... import spec_reading

    document = await session.get(SpecDocument, requirement.document_id)
    statement: Optional[str] = None
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
        payloads = await spec_reading.payloads_for_documents(
            session, workspace, [requirement.document_id]
        )
        statement = (
            spec_reading.statements_by_key(payloads.get(requirement.document_id))
            .get(requirement.key, {})
            .get("statement")
        )
    except Exception:  # noqa: BLE001 - the wording is an addition; its absence is not a failure
        statement = None
    revisions = (
        (
            await session.execute(
                select(SpecRequirementRevision)
                .where(SpecRequirementRevision.requirement_id == requirement.id)
                .order_by(SpecRequirementRevision.created_at, SpecRequirementRevision.id)
            )
        )
        .scalars()
        .all()
    )
    # A fold writes the capability through a merge in one transaction: the revision it causes and
    # the merge row are recorded within a moment of each other, and the revision's meaning (its
    # digest) is one the change declares. Both must hold for a revision to name the change it was
    # folded from; no column links them.
    merges = (
        await session.execute(
            select(SpecDocumentMerge, SpecDocument)
            .join(SpecDocument, SpecDocument.id == SpecDocumentMerge.change_document_id)
            .where(SpecDocumentMerge.capability_document_id == requirement.document_id)
        )
    ).all()

    def folded_from(revision: SpecRequirementRevision) -> Optional[Dict[str, Any]]:
        if revision.created_at is None:
            return None
        near = [
            (abs((merge.created_at - revision.created_at).total_seconds()), merge, change)
            for merge, change in merges
            if merge.created_at is not None
            and isinstance(change.requirement_digests, dict)
            and revision.digest in change.requirement_digests.values()
        ]
        near = [entry for entry in near if entry[0] <= _FOLD_WINDOW_SECONDS]
        if not near:
            return None
        _, merge, change = min(near, key=lambda entry: entry[0])
        return {"path": change.path, "title": change.title, "at": merge.created_at.isoformat()}

    drift = (
        (
            await session.execute(
                select(RequirementDrift)
                .where(RequirementDrift.requirement_id == requirement.id)
                .order_by(RequirementDrift.created_at, RequirementDrift.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "statement": statement,
        "document": (
            {"path": document.path, "title": document.title} if document is not None else None
        ),
        "revisions": [
            {
                "id": row.id,
                "classification": row.classification,
                # What it left unchanged, not only what was recorded (F833): a criterion edit is
                # stored `reworded` but reads `criteria` when the statement stood.
                "change": spec_index.change_kind(
                    row, revisions[position - 1] if position else None
                ),
                "source": row.source,
                "actor_kind": row.actor_kind,
                "actor": row.actor,
                "run_id": row.run_id,
                "statement": row.statement,
                "digest": row.digest,
                "previous_digest": row.previous_digest,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "folded_from": folded_from(row),
            }
            for position, row in enumerate(revisions)
        ],
        "drift": [
            {
                "id": row.id,
                "evidence_id": row.evidence_id,
                "state": row.state,
                "observed": row.observed,
                "resolution": row.resolution,
                "resolved_by": row.resolved_by,
                "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in drift
        ],
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
            commit=body.commit,
            workspace=workspace,
            actor=spec_lifecycle.Actor(kind="operator", name="operator"),
            main_branch=await _main_branch(session, project_id),
            command=body.command,
            output=body.output,
            covers=body.covers,
        )
    except requirement_evidence.EvidenceRefusedError as exc:
        raise HTTPException(
            status_code=exc.http_status or 409, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await session.commit()
    # **With its footprint** (finding F71). Every sibling call site in this file passes one; this
    # handler did not, so the response read `footprint: null` even when a footprint *was* captured —
    # and this is the one moment the operator is looking. The field exists precisely so a reader can
    # tell whether the evidence describes the work they think it does, as this view's own comment on
    # it says; withholding it here hid a wrong commit at the only point where noticing was cheap.
    # **With its review** (F218). `record()` auto-accepts operator-recorded evidence and writes the
    # `EvidenceReview` row in the same transaction just committed above, but this handler stopped at
    # the footprint fix and never fetched it — so this 201 read `latest_review: null` for a row the
    # very next GET already shows accepted. Same fetch-and-pass shape as `list_evidence` uses.
    [view] = await _evidence_views(session, project_id, [evidence])
    return view


#: The review states evidence can be listed by (`requirement_evidence`).
_REVIEW_STATES = (
    requirement_evidence.AWAITING,
    requirement_evidence.ACCEPTED,
    requirement_evidence.REJECTED,
    requirement_evidence.HELD,
)


@router.get("/spec/evidence")
async def list_evidence(
    identifier: Optional[str] = Query(None),
    document: Optional[str] = Query(None),
    review_state: Optional[str] = Query(None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    project_id, _ = project
    if review_state is not None and review_state not in _REVIEW_STATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"review_state must be one of {', '.join(_REVIEW_STATES)}",
                "code": "unknown_review_state",
            },
        )
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
    if review_state is not None:
        # F730: the agent route filtered by it and this one ignored it, answering every piece.
        rows = [row for row in rows if row.review_state == review_state]
    return {"evidence": await _evidence_views(session, project_id, rows)}


async def _reopen_an_approved_task(
    session: AsyncSession, project_id: str, evidence_id: str, decision: str
) -> Optional[Dict[str, Any]]:
    """Send an approved task back when the operator rejects a piece of its evidence (vis-D1), and
    say what happened to it: ``None`` when no approved task was concerned, else ``{"task",
    "reopened"}`` with a ``reason`` when it was not reopened.

    Read fresh: the integration above may have rolled back and expired every loaded row. The
    rejection has committed either way; a refused reopen is reported, never raised, because the
    operator's judgement about the evidence stands whatever the task's state allows.

    **An archived document keeps its task approved** (F730 item 8): archived has no way back, so a
    reopened task would be work against a specification that can no longer change. The rejection
    stands as the record; the task is left where it is, and the answer says why.
    """
    from ...task_transition_service import TransitionRefusedError, apply_transition

    if decision != requirement_evidence.REJECTED:
        return None
    evidence = await session.get(RequirementEvidence, evidence_id)
    task = await session.get(Task, evidence.task_id) if evidence and evidence.task_id else None
    if task is None or task.project_id != project_id or task.status != "approved":
        return None
    task_id = task.id
    requirement = await session.get(SpecRequirement, evidence.requirement_id)
    document_ids = [
        document_id
        for document_id in (
            requirement.document_id if requirement is not None else None,
            task.spec_document_id,
        )
        if document_id
    ]
    for document_id in dict.fromkeys(document_ids):
        document = await session.get(SpecDocument, document_id)
        if document is not None and document.phase == spec_lifecycle.ARCHIVED:
            return {
                "task": task_id,
                "reopened": False,
                "reason": (
                    f"{document.path} is archived and cannot reopen, so {task_id} stays approved; "
                    "the rejection is kept as the record. To redo the work, write a new change."
                ),
            }
    try:
        await apply_transition(session, task, "revision_needed", task_transitions.operator())
        await session.commit()
    except TransitionRefusedError as exc:
        await session.rollback()
        logging.getLogger(__name__).warning(
            "rejecting %s could not reopen task %s", evidence_id, task_id, exc_info=True
        )
        return {
            "task": task_id,
            "reopened": False,
            "reason": f"{task_id} could not be reopened: {exc}",
        }
    await sse_manager.broadcast(project_id, "task_updated", {"id": task_id, "status": task.status})
    return {"task": task_id, "reopened": True}


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
    evidence = await _operator_evidence(session, project_id, evidence_id)
    return await _operator_decides(session, project_id, evidence, body.decision, body.reason)


@router.post("/spec/evidence/{evidence_id}/overturn")
async def overturn_evidence(
    evidence_id: str,
    body: EvidenceOverturn,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator reversing a decided piece, with a reason (F692): an accepted piece becomes
    rejected and a rejected one accepted, with a first decision's consequences. 409 `not_decided`
    for a piece still awaiting, 422 `overturn_needs_reason` with no reason, and 409
    `evidence_stale` for accepting evidence recorded for an earlier wording."""
    project_id, _ = project
    evidence = await _operator_evidence(session, project_id, evidence_id)
    current = evidence.review_state
    if current == requirement_evidence.HELD:
        # K: a held piece is decided like an awaiting one, on the piece's own Accept / Reject.
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"{evidence.id} is held: its task was sent back without naming it as failing, "
                    "so there is no decision to reverse. Decide it as it stands: accept it, or "
                    "reject it with a reason."
                ),
                "code": "not_decided",
            },
        )
    if current not in (requirement_evidence.ACCEPTED, requirement_evidence.REJECTED):
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"{evidence.id} is {current}, not decided; accept or reject it instead",
                "code": "not_decided",
            },
        )
    opposite = (
        requirement_evidence.REJECTED
        if current == requirement_evidence.ACCEPTED
        else requirement_evidence.ACCEPTED
    )
    view = await _operator_decides(session, project_id, evidence, opposite, body.reason)
    view["overturned"] = {"from": current}
    return view


async def _operator_evidence(session: AsyncSession, project_id: str, evidence_id: str):
    evidence = await session.get(RequirementEvidence, evidence_id)
    if evidence is None or evidence.project_id != project_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence


async def _operator_decides(
    session: AsyncSession, project_id: str, evidence, decision: str, reason: str
) -> Dict[str, Any]:
    """One operator decision and everything it causes, for the decision and overturn routes."""
    evidence_id = evidence.id
    # F621: a review this decision may release, asked before it is made.
    held_review = await run_divergence.held_review_before_a_decision(session, evidence)
    try:
        review = await requirement_evidence.decide(
            session,
            evidence,
            decision=decision,
            reason=reason,
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
    # With its footprint, as every other evidence answer here has (F657, after F71).
    [view] = await _evidence_views(
        session, project_id, [evidence], latest_reviews={evidence.id: review}
    )
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
    # A task closed as already built is approved once its last piece is accepted (FR-6).
    approved = await already_built.approve_what_was_waiting_for_this_evidence(
        session, evidence_id, "the operator"
    )
    if approved is not None:
        view["approved_task"] = approved
        await sse_manager.broadcast(
            project_id, "task_updated", {"id": approved, "status": "approved"}
        )
    await run_divergence.release_held_review(session, held_review)
    # vis-D1: the operator left the evidence gate and kept the last word. Rejecting a piece whose
    # task an agent's verdict approved reopens that task (`operator-overturns`).
    reopen = await _reopen_an_approved_task(session, project_id, evidence_id, decision)
    if reopen is not None:
        # F730 item 8: what the rejection did to the approved task, said rather than left implied.
        view["task_reopen"] = reopen
    # After the integration, so a view refetching on it sees any merge the decision caused.
    await sse_manager.broadcast(project_id, "spec_updated", announced)
    return view


@router.get("/spec/evidence/{evidence_id}/diff")
async def evidence_diff(
    evidence_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The work a piece's commit carries on its line of work (`diff-of-the-work`, vis-D5).

    Measured from where that line left the main branch, so it reads the same before and after the
    work merged. 404 for an unknown piece; 200 with no files and a `reason` where there is no
    commit, no repository or nothing changed. The git calls run off the event loop.
    """
    import asyncio

    project_id, _ = project
    evidence = await session.get(RequirementEvidence, evidence_id)
    if evidence is None or evidence.project_id != project_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    footprint = (await _footprints_for(session, [evidence.id])).get(evidence.id)
    commit = footprint.commit_sha if footprint is not None and footprint.kind == "git" else None
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError as exc:
        return {
            "files": [],
            "base": None,
            "commit": commit,
            "truncated": False,
            "reason": f"the project's directory cannot be read: {exc}",
        }
    main_branch = await _main_branch(session, project_id)
    # A footprint that took the checkout's HEAD rather than a commit the recorder named, on the main
    # line, is no work of this piece's (F761); nor is one on main's own first-parent chain,
    # whichever branch the checkout was on (F852). A row from before this reads as it did.
    unnamed = footprint is not None and footprint.commit_named is False
    return await asyncio.to_thread(
        requirement_evidence.work_diff,
        workspace.root,
        commit,
        main_branch,
        unnamed_branch=footprint.branch if unnamed else None,
        unnamed=unnamed,
    )


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
    main_branch = row.main_branch if row else None
    # Footprints recorded before footprints said what they watch are rebuilt here, where their
    # merge into the main line can be found (`drift-legacy-backfill`): the operator's own act, never
    # a restart or a migration.
    rebuilt = await requirement_evidence.backfill_legacy_footprints(
        session, project_id, workspace.root, main_branch=main_branch
    )
    await requirement_evidence.refresh_reachability(
        session,
        project_id,
        workspace.root,
        main_branch=main_branch,
    )
    raised = await requirement_evidence.detect_drift(
        session, project_id, workspace, main_branch=main_branch
    )
    await session.commit()
    # D5: always -- the reachability refresh can move an integration answer when nothing is raised.
    await sse_manager.broadcast(project_id, "spec_updated", {"path": None, "drift": True})
    return {"raised": [candidate.id for candidate in raised], "rebuilt": rebuilt}


@router.get("/spec/drift")
async def list_drift(
    document: Optional[str] = Query(default=None, max_length=255),
    state: Optional[str] = Query(default=None),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Drift candidates, oldest first with ties broken by id (D9: one scan adds its candidates in one
    transaction, so `created_at` ties), optionally for one document and one state (D1)."""
    project_id, _ = project
    if state is not None and state not in DRIFT_STATES:
        raise HTTPException(
            status_code=422, detail="state must be 'candidate', 'resolved' or 'superseded'"
        )
    document_id: Optional[str] = None
    if document is not None:
        found = await spec_lifecycle.get_document(session, project_id, document)
        if found is None:
            raise HTTPException(status_code=404, detail=f"no specification document at {document}")
        document_id = found.id
    query = select(RequirementDrift).where(RequirementDrift.project_id == project_id)
    if state is not None:
        query = query.where(RequirementDrift.state == state)
    # F690: a capability requirement served by a folded change's evidence (F593) answers that
    # evidence's drift on its own page, keyed by the change requirement that holds it.
    serves: Dict[str, Dict[str, Any]] = {}
    if document_id is not None:
        report = await requirement_coverage.requirement_coverage(
            session, project_id, document_id=document_id
        )
        serves = {
            entry.served_by["requirement_id"]: {
                "identifier": entry.identifier,
                "document": document,
            }
            for entry in report.requirements
            if entry.served_by
        }
        query = query.join(
            SpecRequirement, SpecRequirement.id == RequirementDrift.requirement_id
        ).where(
            or_(
                SpecRequirement.document_id == document_id,
                RequirementDrift.requirement_id.in_(list(serves) or [""]),
            )
        )
    rows = list(
        (await session.execute(query.order_by(RequirementDrift.created_at, RequirementDrift.id)))
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
            # The requirement of the asked-for document this drift reaches through a fold (F690);
            # null where the drift is on the document's own requirement.
            "serves": serves.get(row.requirement_id),
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

    return {
        "drift": [_view(row) for row in rows],
        "unwatched": await _unwatched(session, project_id, document_id),
    }


#: Why accepted evidence is not scanned for drift (`drift-watches-the-files-its-evidence-is-about`
#: D4): it names no file, it was recorded before footprints said what they watch and could not be
#: rebuilt, or the workspace could not be resolved when it was recorded.
UNWATCHED_NAMES_NO_FILE = "names_no_file"
UNWATCHED_RECORDED_BEFORE_WATCHING = "recorded_before_watching"
UNWATCHED_NO_FOOTPRINT = "no_footprint"


async def _unwatched(
    session: AsyncSession, project_id: str, document_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Accepted, digest-current evidence drift does not watch, with the reason, ordered by when it
    was produced and then by id (the order `for_requirement` uses; F190: callers rely on it)."""
    rows = (
        await session.execute(
            select(RequirementEvidence, EvidenceFootprint, SpecRequirement)
            .join(SpecRequirement, SpecRequirement.id == RequirementEvidence.requirement_id)
            .outerjoin(EvidenceFootprint, EvidenceFootprint.evidence_id == RequirementEvidence.id)
            .where(
                RequirementEvidence.project_id == project_id,
                RequirementEvidence.review_state == "accepted",
                RequirementEvidence.digest == SpecRequirement.digest,
                *([SpecRequirement.document_id == document_id] if document_id else []),
            )
            .order_by(RequirementEvidence.produced_at, RequirementEvidence.id)
        )
    ).all()
    documents = {
        row.id: row.path
        for row in (
            await session.execute(
                select(SpecDocument).where(
                    SpecDocument.id.in_({req.document_id for _, _, req in rows} or {""})
                )
            )
        ).scalars()
    }
    listed: List[Dict[str, Any]] = []
    for evidence, footprint, requirement in rows:
        if footprint is None:
            reason = UNWATCHED_NO_FOOTPRINT
        elif footprint.watched_from is None:
            reason = UNWATCHED_RECORDED_BEFORE_WATCHING
        elif footprint.watched_from == []:
            reason = UNWATCHED_NAMES_NO_FILE
        else:
            continue
        listed.append(
            {
                "evidence_id": evidence.id,
                "requirement": {
                    "identifier": requirement.identifier,
                    "document": documents.get(requirement.document_id),
                },
                "summary": evidence.summary,
                "actor": evidence.actor,
                "reason": reason,
            }
        )
    return listed


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
            status_code=exc.http_status or 422, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": None, "drift": True})
    return {"id": candidate.id, "state": candidate.state, "resolution": candidate.resolution}


def _evidence_view(
    evidence,
    footprint=None,
    latest_review=None,
    *,
    requirement=None,
    superseded_by=None,
    for_current_wording=None,
) -> dict:
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
        # What it takes to judge the piece (vis-D5), as its recorder supplied it; null when none.
        "command": evidence.command,
        "output": evidence.output,
        "covers": evidence.covers,
        # What it demonstrates, in the document's own words, and whether a later piece replaced it
        # (`says-what-it-demonstrates`). Built by `_evidence_views`; null where it was not asked.
        "requirement": requirement,
        "superseded_by": superseded_by,
        # Whether it was recorded against what the requirement says now (F691): its digest is the
        # requirement's. False is coverage's `stale` for this piece -- its review state is about an
        # earlier wording, so a surface must not count it as the requirement's evidence. Null where
        # the requirement could not be read.
        "for_current_wording": for_current_wording,
    }


async def _evidence_views(
    session: AsyncSession, project_id: str, rows, *, latest_reviews=None
) -> List[dict]:
    """Every evidence answer's views, each with its footprint, latest review, the requirement's
    identifier and statement, and `superseded_by`. One place, so no surface carries less.

    The statement is read from the document's payload (`spec_reading`); a project whose directory
    cannot be resolved still answers, with the statement null. `superseded_by` is the newest later
    piece recorded for the same requirement and task (design D4), whether or not it is listed.
    """
    from ... import spec_reading

    rows = list(rows)
    if not rows:
        return []
    ids = [row.id for row in rows]
    prints = await _footprints_for(session, ids)
    reviews = (
        latest_reviews if latest_reviews is not None else await _latest_reviews_for(session, ids)
    )
    requirements = {
        row.id: row
        for row in (
            await session.execute(
                select(SpecRequirement).where(
                    SpecRequirement.id.in_({row.requirement_id for row in rows})
                )
            )
        )
        .scalars()
        .all()
    }
    # FR-n repeats in every document, so a piece names the document its requirement is in.
    documents = {
        row.id: {"path": row.path, "title": row.title}
        for row in (
            await session.execute(
                select(SpecDocument).where(
                    SpecDocument.id.in_({r.document_id for r in requirements.values()})
                )
            )
        )
        .scalars()
        .all()
    }
    wording: Dict[str, Dict[str, Any]] = {}
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
        payloads = await spec_reading.payloads_for_documents(
            session, workspace, [r.document_id for r in requirements.values()]
        )
        wording = {
            document_id: spec_reading.statements_by_key(payload)
            for document_id, payload in payloads.items()
        }
    except Exception:  # noqa: BLE001 - the wording is an addition; its absence is not a failure
        wording = {}
    newest: Dict[tuple, Any] = {}
    pairs = {(row.requirement_id, row.task_id) for row in rows if row.task_id}
    if pairs:
        siblings = (
            (
                await session.execute(
                    select(RequirementEvidence).where(
                        RequirementEvidence.requirement_id.in_({pair[0] for pair in pairs}),
                        RequirementEvidence.task_id.in_({pair[1] for pair in pairs}),
                    )
                )
            )
            .scalars()
            .all()
        )
        for sibling in siblings:
            pair = (sibling.requirement_id, sibling.task_id)
            current = newest.get(pair)
            if current is None or (sibling.produced_at, sibling.id) > (
                current.produced_at,
                current.id,
            ):
                newest[pair] = sibling
    views = []
    for row in rows:
        requirement = requirements.get(row.requirement_id)
        latest = newest.get((row.requirement_id, row.task_id)) if row.task_id else None
        views.append(
            _evidence_view(
                row,
                prints.get(row.id),
                reviews.get(row.id),
                requirement=(
                    {
                        "identifier": requirement.identifier,
                        "statement": wording.get(requirement.document_id, {})
                        .get(requirement.key, {})
                        .get("statement"),
                        "document": documents.get(requirement.document_id),
                    }
                    if requirement is not None
                    else None
                ),
                superseded_by=latest.id if latest is not None and latest.id != row.id else None,
                for_current_wording=(
                    row.digest == requirement.digest if requirement is not None else None
                ),
            )
        )
    return views


async def _main_branch(session: AsyncSession, project_id: str) -> Optional[str]:
    """The project's configured main line, which footprints are measured against."""
    row = await session.get(Project, project_id)
    return row.main_branch if row else None


def footprint_view(footprint, *, provisional: bool = False) -> Optional[dict]:
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
        # What drift watches, and where it came from (`drift-watches-the-files-its-evidence-is-about`
        # D4): `null` is a footprint recorded before this was recorded.
        "watched_from": footprint.watched_from,
        "watched_count": len(footprint.entries or {}),
        # An agent's footprint taken mid-turn names the commit the turn started from; the run-end
        # re-stamp corrects it (D7). Said, so `watched_count: 0` is not read as final.
        "provisional": provisional,
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
    on_disk, discovery_diagnostics = spec_documents.discover(workspace)
    rows = await spec_lifecycle.list_documents(session, project_id)
    chosen_home = body.home if body is not None else None
    if chosen_home is not None and (
        chosen_home not in on_disk or chosen_home not in {row.path for row in rows}
    ):
        # F702: refused before anything is rebuilt. Accepted, it rebuilt the requirements and then
        # answered "not written" with a diagnostic, for a home the caller simply mistyped.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": describe_diagnostic("home_missing", chosen_home),
                "code": "home_unknown",
            },
        )

    results = await spec_index.reindex_project(session, workspace, project_id)
    backfilled = await requirement_links.backfill_project(session, project_id)

    existing, _, _ = spec_documents.read_index(workspace)
    manifest, index_diagnostics = spec_documents.build_index(
        on_disk,
        [(row.path, row.title, row.kind, row.phase) for row in rows],
        existing,
        home=chosen_home,
    )

    written = None
    rerendered: List[str] = []
    rerender_skipped: List[Dict[str, Any]] = []
    index_diagnostics = list(index_diagnostics)
    for path, result in results.items():
        if result is not None:
            continue
        # F689/F702: a document whose requirements could not be read answered `null` and nothing
        # said why. The reason names the field to repair.
        try:
            problem = spec_documents.payload_problem(spec_documents.read_document(workspace, path))
        except (SpecPathError, project_workspace.ProjectPathError, OSError) as exc:
            problem = str(exc)
        if problem is not None:
            index_diagnostics.append(
                spec_documents._diag("requirements_unreadable", path=path, actual=problem)
            )
    try:
        if manifest is not None:
            spec_documents.write_index(workspace, manifest)
    except OSError as exc:
        # F434 (D6): the requirement index is still rebuilt and committed; the index file keeps
        # its previous bytes (`write_index` is atomic), and nothing is re-rendered from a manifest
        # that is not on disk -- the same as when no home is recorded.
        index_diagnostics.append(
            spec_documents._diag(
                "index_write_failed", path=spec_documents.INDEX_RELATIVE, actual=str(exc)
            )
        )
        manifest = None
    if manifest is not None:
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
    # D5: an open tab learns the corpus changed, as it does after arrange and adopt.
    await sse_manager.broadcast(project_id, "spec_updated", {"path": None})
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


@router.post("/spec/convert")
async def convert_corpus(
    to: str = Query(..., pattern="^(json|html)$"),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Convert every spec document between legacy `.html` and `spec.json`, either way.

    `a-spec-document-is-stored-as-its-payload` FR-7/8/9: the files, the rows' paths, undelivered
    queue entries, payload references and `spec/index.json`, keeping every id. `to=html` is the
    rollback (with the code reverted). A second call changes nothing. Refused with 409, changing
    nothing, while any run in the project is active, or when a target path is already held.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    try:
        result = await spec_conversion.convert(session, workspace, project_id, to)
    except spec_conversion.ConversionRefusedError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(exc), "code": exc.code, "runs": exc.runs},
        ) from exc
    except OSError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"could not write a converted document: {exc}",
                "code": "write_failed",
            },
        ) from exc
    await session.commit()
    if result.converted:
        await sse_manager.broadcast(project_id, "spec_updated", {"path": None})
    return {
        "to": result.to,
        "converted": result.converted,
        "skipped": result.skipped,
        "index": {"rewritten": result.index_rewritten},
        "queue_entries": result.queue_entries,
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
                # The first diagnostic's sentence, not only its code (F643).
                "message": "this placement is not allowed: "
                + " ".join(d.to_dict()["message"] for d in validation_diagnostics[:1]),
                "diagnostics": [d.to_dict() for d in validation_diagnostics],
            },
        )

    try:
        spec_documents.write_index(workspace, revalidated)
    except OSError as exc:
        # F434 (D6): before any re-render or database change, and the previous index stays.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": f"the index could not be written: {exc}; nothing was placed",
                "code": "index_write_failed",
            },
        ) from exc

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
    # As for one document (F612): mint for requirements a hand-placed file names without one.
    minted: Dict[str, List[str]] = {}
    for result in outcome.outcomes.values():
        if isinstance(result, spec_adoption.AdoptionResult):
            identifiers = await spec_service.mint_missing_identity(
                session, workspace, result.document, actor=_operator()
            )
            if identifiers:
                minted[result.document.path] = identifiers
    await session.commit()

    if outcome.adopted:
        # One event for the sweep rather than one per document: the rail refreshes
        # the whole tree either way, and thirty-four broadcasts would be thirty-three
        # redundant re-renders.
        await sse_manager.broadcast(project_id, "spec_updated", {"path": None, "phase": None})
    return {**outcome.to_dict(), "minted": minted}


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
            path = await spec_service.mint_document_path(
                session, project_id, workspace, kind=body.kind, title=body.title
            )
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
        session, workspace, document, payload, actor=_operator(), via="create"
    )
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": path, "phase": document.phase})
    return {
        **await _project_document_view(session, project_id, document),
        "blocking": result.blocking,
        "warnings": result.warnings,
    }


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
    "payload_invalid": status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    # The one write adoption leads to, and only for requirements the file names without an
    # identifier (F612): unminted, the index skips them and the document asserts nothing.
    minted = await spec_service.mint_missing_identity(
        session, workspace, outcome.document, actor=_operator()
    )

    await session.commit()
    await sse_manager.broadcast(
        project_id,
        "spec_updated",
        {"path": outcome.document.path, "phase": outcome.document.phase},
    )
    return {
        **await _project_document_view(session, project_id, outcome.document),
        **outcome.to_dict(),
        "minted": minted,
    }


class JourneyChange(RequestModel):
    """Move an exploring change to a step, change its size, or both."""

    step: Optional[str] = Field(default=None, max_length=48)
    size: Optional[str] = Field(default=None, max_length=16)
    reason: str = Field(default="", max_length=2000)


@router.post("/documents/journey")
async def set_journey(
    body: JourneyChange,
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator moving a change to any step, back or forward, or changing its size (FR-10).

    Takes effect from the next turn on the document: every turn is briefed from these columns.
    """
    project_id, _ = project
    document = await _require_document(session, project_id, path)
    if body.step is None and body.size is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "name a step, a size, or both", "code": "nothing_to_change"},
        )
    if not spec_journey.has_journey(document) or document.phase != spec_lifecycle.EXPLORING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"this {document.kind} is {document.phase}; only an exploring change "
                "document has a journey to move",
                "code": "no_journey",
            },
        )
    workspace = await _workspace(session, project_id)
    steps = spec_journey.load(workspace)
    try:
        if body.size is not None:
            await spec_journey.set_size(
                session, document, body.size, actor=_operator(), reason=body.reason, steps=steps
            )
        if body.step is not None:
            await spec_journey.set_step(
                session, document, body.step, actor=_operator(), steps=steps
            )
    except spec_journey.JourneyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    # FR-10: the file's hub block carries the new step and size in the same request.
    await spec_service.rerender_phase(session, workspace, document)
    await session.commit()
    await sse_manager.broadcast(project_id, "spec_updated", {"path": path, "phase": document.phase})
    return _document_view(document, steps)


def _journey_view(steps: spec_journey.ProjectSteps) -> Dict[str, Any]:
    return {
        "steps": [step.to_entry() for step in steps.steps],
        "diagnostics": list(steps.diagnostics),
    }


@router.get("/journey")
async def get_project_journey(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The project's spec steps (`a-project-orders-its-own-spec-steps` FR-6): the built-ins with no
    `spec/journey.json`; with a broken file, the built-ins and what is wrong with it (FR-7)."""
    project_id, _ = project
    return _journey_view(spec_journey.load(await _workspace(session, project_id)))


class JourneyStepBody(RequestModel):
    """One step of the saved journey. Lengths are left to `spec_journey.parse`, whose refusal
    names the step and the cap; this model names a field it does not know."""

    key: str
    title: Optional[str] = None
    instructions: Optional[str] = None
    sizes: Optional[List[str]] = None
    append: Optional[str] = None


class JourneyBody(RequestModel):
    steps: List[JourneyStepBody]


@router.put("/journey")
async def put_project_journey(
    body: JourneyBody,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Save the project's spec steps to `spec/journey.json` (FR-5, FR-6). A journey that breaks a
    rule (a text over 2,000 characters, a built-in missing or out of order, a bad custom key) is
    refused with 422 naming the step, and nothing is written. The same journey saved twice leaves
    the same bytes. Takes effect from the next turn: every briefing reads the file."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    try:
        steps = spec_journey.save(workspace, body.model_dump(exclude_unset=True))
    except spec_journey.JourneyError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"could not write {spec_journey.JOURNEY_FILE}: {exc}",
                "code": "write_failed",
            },
        ) from exc
    await sse_manager.broadcast(project_id, "journey_updated", {"steps": steps.order()})
    return _journey_view(steps)


@router.post("/documents/close-exploration")
async def close_exploration(
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator declaring exploration finished.

    Whether an exploration is complete enough to approve is a judgement,
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
    return await _project_document_view(session, project_id, document)


@router.post("/documents/check")
async def check_document(
    background: BackgroundTasks,
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Report a document's readiness and move nothing (`exploring-ends-at-an-approved-plan`, FR-1).

    `blocking` and `warnings` are exactly what the agent's save of the stored payload returns
    (`spec_service.check`), so the operator and the agent read one answer. The phase, the file and
    the history are untouched, so an agent keeps saving while the operator looks;
    `content_version` is the version that was checked. Starts the vault's spec check after the
    answer is sent, a no-op while that job is off (`vault_spec_check`).
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    try:
        found_blocking, warnings = await spec_service.check(session, workspace, document)
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code},
        ) from exc
    content = spec_documents.read_document(workspace, document.path)
    version = spec_documents.content_version(content)
    # A model run per press would be a cost the operator cannot see (F1053): only a document with
    # no blocking gap, and only a content version the newest firing has not already checked.
    if not found_blocking and not await vault_spec_check.already_checked(
        session, project_id, document.path, version
    ):
        background.add_task(
            vault_spec_check.check_in_background,
            project_id,
            document.path,
            trigger=vault_spec_check.TRIGGER,
            content_version=version,
        )
    return {
        **await _project_document_view(session, project_id, document),
        "blocking": found_blocking,
        "warnings": warnings,
        "ready": not found_blocking,
        "content_version": version,
    }


async def _refresh_index_entry(
    session: AsyncSession, workspace, project_id: str, path: str
) -> List[Dict[str, Any]]:
    """Rebuild `spec/index.json` when it lists *path*, so its status follows the Hub's phase."""
    diagnostics: List[Dict[str, Any]] = []
    existing, _, _ = spec_documents.read_index(workspace)
    if existing is None or not any(entry.path == path for entry in existing.documents):
        return diagnostics
    on_disk, _ = spec_documents.discover(workspace)
    rows = await spec_lifecycle.list_documents(session, project_id)
    manifest, index_diagnostics = spec_documents.build_index(
        on_disk, [(row.path, row.title, row.kind, row.phase) for row in rows], existing
    )
    diagnostics.extend(index_diagnostics)
    if manifest is not None:
        try:
            spec_documents.write_index(workspace, manifest)
        except OSError as exc:
            diagnostics.append({"code": "index_write_failed", "actual": str(exc)})
    return diagnostics


def _misplaced_query(request: Request, allowed: set) -> None:
    """F580: FastAPI drops a query parameter it does not declare without a word, so a body field
    sent in the query string (`approve_anyway`) was ignored. Name what was misplaced instead."""
    misplaced = sorted(set(request.query_params) - allowed)
    if misplaced:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{', '.join(misplaced)} sent as a query parameter; only "
                f"{' and '.join(sorted(allowed))} go in the query string, the rest go in the JSON "
                "request body"
            ),
        )


def _require_loaded_version(workspace, document, version: Optional[str]) -> None:
    """An approval names the content version the operator loaded, and is refused when the stored
    content differs (`approve-what-was-seen`, FR-4): with the document editable while the operator
    reads, an approval could otherwise accept text nobody read."""
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "an approval names the version of the document you read: send content_version, "
                f"the value GET /project/spec?path={document.path} returned, in the request body"
            ),
        )
    current = spec_documents.content_version(spec_documents.read_document(workspace, document.path))
    if version != current:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "the document changed since it was loaded; reload it, read what changed, "
                    "and approve again"
                ),
                "code": "document_changed",
                "loaded": version,
                "current": current,
            },
        )


def _check_delivery_agent(
    workspace, document, delivery_agent: Optional[str], driver: Optional[str] = None
) -> None:
    """D5b: `delivery_agent` is honoured only where it can be, and refused before anything moves
    rather than ignored (`RequestModel`'s rule: honour a field or name it). A build the operator
    gives a flow or a lead (slice D) has a flow for it to name, whatever the delivery says."""
    if delivery_agent is None or driver in (builds.DRIVER_FLOW, builds.DRIVER_LEAD):
        return
    chosen_for = _delivery_of(_read_payload(workspace, document.path))
    if chosen_for is None or chosen_for.mode != "flow":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "delivery_agent replaces a flow delivery's agent, and this document declares no flow"
            ),
        )


@dataclasses.dataclass
class _Moved:
    """What a phase move did, read before the commit expires the rows it touched."""

    report: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None
    created_count: int = 0
    notes: List[Dict[str, Any]] = dataclasses.field(default_factory=list)


def _already_built_offer(
    project_id: str, document, payload: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Intake recorded the work as already built: approval offers slice B's close-as-built at the
    commits it named, instead of the tasks waiting to be built (`already-built-at-intake`)."""
    raw = (payload or {}).get("already_built")
    if not isinstance(raw, dict) or raw.get("built") is not True:
        return None
    commits = [str(commit) for commit in raw.get("commits") or []]
    route = (
        f"POST /api/v1/projects/{project_id}/project/documents/{document.path}/close-already-built"
    )
    at = f" at {', '.join(commits)}" if commits else ", naming no commit"
    named = "against those commits" if commits else "naming the commits on main that hold it"
    return {
        "commits": commits,
        "route": route,
        "message": (
            f"Intake recorded this work as already built{at}. Close its tasks as already built "
            f"{named} instead of building them."
        ),
    }


async def _move_phase(
    session: AsyncSession,
    workspace,
    project_id: str,
    document,
    *,
    to: str,
    reason: str = "",
    no_capability_change: bool = False,
    absorbed_by: Optional[str] = None,
    approve_anyway: bool = False,
) -> _Moved:
    """Move the document, and at approval lay its tasks out as a plan with nothing started (FR-5).

    Approval is what turns a decomposition from a description into work: the board is
    materialised and what that did is recorded. It cannot undo the approval: the board runs in its
    own savepoint and reports a failure instead of raising. No flow is created and no run begins,
    whatever the delivery says: that is Build's (`_build`).
    """
    try:
        phase_event = await spec_lifecycle.transition(
            session,
            document,
            to_phase=to,
            actor=_operator(),
            workspace=workspace,
            reason=reason,
            no_capability_change=no_capability_change,
            absorbed_by=absorbed_by,
            approve_anyway=approve_anyway,
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
        if exc.warnings:
            detail["warnings"] = exc.warnings
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from exc

    moved = _Moved(notes=list((phase_event.detail or {}).get("notes") or []))
    if document.phase != "approved":
        return moved
    payload = _read_payload(workspace, document.path)
    outcome = await spec_tasks.materialise_quietly(session, document, payload, actor=_operator())
    report: Dict[str, Any] = {
        "created": [dataclasses.asdict(task) for task in outcome.created],
        "already_served": [
            {"key": entry.key, "requirements": list(entry.requirements)}
            for entry in outcome.already_served
        ],
        "failed": outcome.failed,
        # F535: what re-approval did to tasks that already existed. Empty on a failed board,
        # which rolled any refresh back with it.
        "refreshed": [dataclasses.asdict(task) for task in outcome.board.refreshed],
        "closed_linking_retired": [
            dataclasses.asdict(task) for task in outcome.board.closed_linking_retired
        ],
        "no_longer_declared": [
            dataclasses.asdict(task) for task in outcome.board.no_longer_declared
        ],
        # When the board failed, `_materialise_edges` did not run, and the rows there are the
        # previous approval's (design D7, R3).
        "dependencies_not_honoured": (
            []
            if outcome.failed
            else await spec_tasks.dependencies_not_honoured(session, document, payload)
        ),
    }
    offer = _already_built_offer(project_id, document, payload)
    if offer is not None:
        report["already_built"] = offer
    await spec_lifecycle.record_event(
        session, document, kind=APPROVAL_REPORT, actor=_operator(), detail=report
    )
    moved.report = report
    moved.payload = payload
    moved.created_count = len(outcome.created)
    return moved


def _defer_phase_broadcasts(
    session: AsyncSession, project_id: str, document, moved: _Moved
) -> None:
    """Staged, not sent (design D6 step 5): every frame waits for the route's one commit."""
    defer_broadcast(
        session, project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    refreshed_count = len((moved.report or {}).get("refreshed", []))
    if moved.created_count or refreshed_count:
        defer_broadcast(
            session,
            project_id,
            "task_updated",
            {"created": moved.created_count, "refreshed": refreshed_count},
        )


async def _phase_response(
    session: AsyncSession, project_id: str, document, moved: _Moved
) -> Dict[str, Any]:
    """The document, the tasks approval created and its report. Read from the values captured
    before the commit's expiry, as every other field here is."""
    response: Dict[str, Any] = {
        **await _project_document_view(session, project_id, document),
        "tasks_created": [task["id"] for task in (moved.report or {}).get("created", [])],
    }
    if moved.report is not None:
        response["approval_outcome"] = moved.report
    # F704: what approval told and did not gate on (an unclaimed roadmap slice).
    if moved.notes:
        response["approval_notes"] = moved.notes
    return response


def _unprocessable(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": code, "message": message},
    )


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _build_settings(
    session: AsyncSession,
    project_id: str,
    document,
    payload: Optional[Dict[str, Any]],
    body: _BuildChoices,
) -> builds.Settings:
    """The build the operator chose, each setting left out taken from the recommended build
    (slice D, FR-1). Refused (422) before anything moves: a lead driver naming no lead, a person
    who is not an open agent of the project, or a window that ends before it starts or has ended.
    """
    delivery = _delivery_of(payload)

    def recommended(name: str, default: Any = None) -> Any:
        value = getattr(delivery, name, None) if delivery is not None else None
        return default if value is None else value

    driver = body.driver or recommended("driver")
    if driver is None:
        flows = delivery is not None and delivery.mode == "flow" and body.delivery_agent != ""
        driver = builds.DRIVER_FLOW if flows else builds.DRIVER_HAND
    level = body.level or recommended("level") or builds.REVIEWED
    chosen_builders = body.builders if body.builders is not None else recommended("builders", [])
    chosen_reviewers = (
        body.reviewers if body.reviewers is not None else recommended("reviewers", [])
    )
    lead = (body.lead or "").strip() or recommended("lead")
    cap = body.budget_cap_usd if body.budget_cap_usd is not None else recommended("budget_cap_usd")
    landing = body.landing or recommended("landing") or builds.LANDING_MAIN
    start, end = _aware(body.window_start), _aware(body.window_end)

    if driver == builds.DRIVER_LEAD and not lead:
        raise _unprocessable("lead_missing", "a lead-driven build names its lead")
    people = [*chosen_builders, *chosen_reviewers, *([lead] if lead else [])]
    if people:
        known = await builds.open_agents(session, project_id)
        unknown = sorted({name for name in people if name not in known})
        if unknown:
            raise _unprocessable(
                "unknown_agent",
                f"not an open agent of this project: {', '.join(unknown)}. A build's builders, "
                "reviewers and lead are agents that can be given turns.",
            )
    if start is not None and end is not None and end <= start:
        raise _unprocessable("window_inverted", "the build's window ends before it starts")
    if end is not None and end <= datetime.now(timezone.utc):
        raise _unprocessable(
            "window_closed", f"the build's window ended at {end.isoformat()}; choose a later end"
        )
    return builds.Settings(
        driver=driver,
        level=level,
        builders=list(dict.fromkeys(chosen_builders)),
        reviewers=list(dict.fromkeys(chosen_reviewers)),
        lead=lead if driver == builds.DRIVER_LEAD else (lead or None),
        budget_cap_usd_micros=builds.micros_of(cap),
        window_start=start,
        window_end=end,
        landing=landing,
        task_builders=dict(body.task_builders or {}),
    )


async def _refuse_a_second_build(session: AsyncSession, document) -> None:
    """One running build per document (FR-1): a second start is refused, naming the running one."""
    running = await builds.running_build(session, document.id)
    if running is not None:
        raise _build_running(running)


def _build_running(running) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "build_running",
            "message": (
                f"build {running.id} of this document is running ({running.driver}, "
                f"{running.level}); stop it before starting another"
            ),
            "build_id": running.id,
        },
    )


@dataclasses.dataclass
class _Started:
    """What a build start leaves for after its commit."""

    job: Optional[AIJob] = None
    lead: Optional[str] = None


async def _build(
    session: AsyncSession,
    project_id: str,
    document,
    payload: Optional[Dict[str, Any]],
    delivery_agent: Optional[str],
    settings: Optional[builds.Settings] = None,
) -> Tuple[Dict[str, Any], _Started]:
    """Start building an approved document (FR-6), and record it.

    Slice D: the build is a record (`builds.Build`) of the operator's choices. Its tasks record the
    build and its level, and each declared builder that is an open agent becomes its task's
    assignee. A flow or lead driver gets the flow it hands out the work from (`_build_flow`); a
    hand-driven build starts nothing. The record is also an event of its own (`BUILD_REPORT`), so
    approval and build are two entries in the document's history.
    """
    if settings is None:
        settings = await _build_settings(
            session, project_id, document, payload, _BuildChoices(delivery_agent=delivery_agent)
        )
    started = _Started()
    build = builds.new_build(project_id, document.id, settings)
    try:
        async with session.begin_nested():
            session.add(build)
            await session.flush()
    except IntegrityError:
        # A Build that raced past `_refuse_a_second_build`: the partial unique index answers it,
        # and the answer is the check's own 409, naming the build that won.
        running = await builds.running_build(session, document.id)
        if running is None:
            raise
        raise _build_running(running) from None
    await builds.retire_previous_loops(session, document.id, build.id)
    open_tasks = (
        (
            await session.execute(
                select(Task)
                .where(
                    Task.project_id == project_id,
                    Task.spec_document_id == document.id,
                    Task.status.not_in(TERMINAL_STATUSES),
                )
                .order_by(Task.created_at, Task.id)
            )
        )
        .scalars()
        .all()
    )
    unresolved = await builds.cover_tasks(
        session,
        build,
        open_tasks,
        _declared_builders(payload),
        settings.task_builders,
    )
    if settings.driver == builds.DRIVER_HAND or document.kind != "change-spec":
        flow = (
            _hand_flow_entry(payload, delivery_agent)
            if document.kind == "change-spec"
            else (await _build_flow(session, project_id, document, payload, delivery_agent))[0]
        )
    else:
        flow, started.job = await _build_flow(
            session, project_id, document, payload, delivery_agent, settings=settings
        )
        if flow.get("state") in ("created", "existing") and flow.get("job_id"):
            build.loop_id = (
                await session.execute(select(Loop.id).where(Loop.job_id == flow["job_id"]))
            ).scalar_one_or_none()
        # The lead's first brief, now -- unless the window has not opened (or the cap is already
        # spent): then its loop's first firing inside the window briefs it.
        if (
            settings.driver == builds.DRIVER_LEAD
            and build.loop_id
            and flow.get("job_id")
            and (await builds.may_hand_out(session, build)).allowed
            and await builds.queue_brief(
                session, build, document.title or document.path, flow["job_id"]
            )
        ):
            started.lead = build.lead
    delivery = _delivery_of(payload)
    view = await builds.view(session, build)
    outcome: Dict[str, Any] = {
        "flow": flow,
        "delivery_agent": delivery_agent,
        "reviewer": delivery.reviewer if delivery is not None else None,
        "build": {**view, "unresolved_builders": unresolved},
    }
    await spec_lifecycle.record_event(
        session, document, kind=BUILD_REPORT, actor=_operator(), detail=outcome
    )
    return outcome, started


_CHOICE_FIELDS = (
    "driver",
    "level",
    "builders",
    "reviewers",
    "lead",
    "budget_cap_usd",
    "window_start",
    "window_end",
    "landing",
    "task_builders",
)


async def _joined_build(
    session: AsyncSession,
    project_id: str,
    document,
    payload: Optional[Dict[str, Any]],
    body: _BuildChoices,
    running,
) -> Tuple[Dict[str, Any], _Started]:
    """The report of an Approve and build whose document already has a running build: the tasks
    approval laid out joined it (`builds.join_running_build`) and no second build was started. A
    flow- or lead-driven build whose flow is gone gets its flow again, as the build it is."""
    delivery = _delivery_of(payload)
    started = _Started()
    flow = await _existing_flow_entry(session, project_id, document, delivery, body.delivery_agent)
    if flow is None and running.driver != builds.DRIVER_HAND and document.kind == "change-spec":
        again = builds.Settings(
            driver=running.driver,
            level=running.level,
            builders=list(running.builders or []),
            reviewers=list(running.reviewers or []),
            lead=running.lead,
            budget_cap_usd_micros=running.budget_cap_usd_micros,
            window_start=running.window_start,
            window_end=running.window_end,
            landing=running.landing,
            task_builders={},
        )
        flow, started.job = await _build_flow(
            session, project_id, document, payload, body.delivery_agent, settings=again
        )
        if started.job is not None:
            running.loop_id = (
                await session.execute(select(Loop.id).where(Loop.job_id == started.job.id))
            ).scalar_one_or_none()
    if flow is None:
        flow = _hand_flow_entry(payload, body.delivery_agent)
    view = await builds.view(session, running)
    message = f"Build {running.id} is running; the new tasks joined it."
    if any(getattr(body, name) is not None for name in _CHOICE_FIELDS):
        message += " The settings chosen here were not applied: stop it to build anew."
    outcome: Dict[str, Any] = {
        "flow": flow,
        "delivery_agent": body.delivery_agent,
        "reviewer": delivery.reviewer if delivery is not None else None,
        "build": {**view, "joined": True, "message": message, "unresolved_builders": []},
    }
    await spec_lifecycle.record_event(
        session, document, kind=BUILD_REPORT, actor=_operator(), detail=outcome
    )
    return outcome, started


def _hand_flow_entry(payload: Optional[Dict[str, Any]], delivery_agent: Optional[str]) -> Dict:
    """The report's `flow` entry for a build nobody drives: nothing is started."""
    delivery = _delivery_of(payload)
    if delivery is None:
        return {"state": "none", "messages": ["No delivery was declared."]}
    if delivery.mode == "flow" and delivery_agent == "":
        return _not_created("You chose no flow for this build.")
    if delivery.mode == "flow":
        return {
            "state": "none",
            "messages": [
                "You chose to build it by hand: no flow was started, and the tasks wait on the "
                "board with their builders assigned."
            ],
        }
    has_tasks = bool((payload or {}).get("tasks"))
    return {
        "state": "none",
        "messages": [
            (
                "The delivery says no flow: the tasks are on the board, started by hand."
                if has_tasks
                else "The delivery says no flow, and the document declares no tasks."
            )
        ],
    }


async def _finish_build(session: AsyncSession, project_id: str, started: _Started) -> None:
    """After the commit: the flow's first firing is at its next cron tick, nothing fires now
    (operator). A registration failure is logged, and the committed flow fires from the next
    restart. A lead's first brief is queued with the build, and its turn starts now."""
    if started.job is not None:
        await _hand_job_to_scheduler(session, started.job.id, started.job)
    if started.lead:
        from ...turn_scheduler import schedule_accepted

        await schedule_accepted(project_id, started.lead)


@router.post("/documents/phase")
async def set_phase(
    request: Request,
    body: Optional[PhaseRequest] = None,
    path: str = Query(...),
    to: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """An operator phase decision — approving a document, reopening one, or archiving one.

    This route requires the project credential, so an agent run cannot reach it:
    a run's token authenticates against `/agent-actions`, which has no phase
    route at all.

    Approval goes from `exploring`, names the `content_version` the operator read and is refused
    when the document changed since (FR-3, FR-4), and lays the tasks out with nothing started
    (FR-5). Building is `POST /documents/build`, or both at once `POST /documents/approve-and-build`.
    """
    # F204/F210: every field of the body is optional, so a call with no body at all is a complete
    # request; without the default FastAPI refused it as malformed before the route could run.
    body = body or PhaseRequest()
    _misplaced_query(request, {"path", "to"})

    if to == spec_lifecycle.PROPOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": spec_lifecycle.PROPOSED_RETIRED, "code": "proposed_retired"},
        )
    # F730: a phase that does not exist is a malformed request (422), as an unknown rigor is (F657),
    # not a conflict with the document's state (409).
    phases = (
        spec_lifecycle.EXPLORING,
        spec_lifecycle.APPROVED,
        spec_lifecycle.ARCHIVED,
    )
    if to not in phases:
        what = (
            "current is reached only by creating a capability document, never moved to"
            if to == spec_lifecycle.CURRENT
            else f"unknown phase {to!r}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": f"{what}: to must be one of {', '.join(phases)}",
                "code": "unknown_phase",
            },
        )

    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)

    if body.approve_anyway and to != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="approve_anyway approves over the gaps an approval lists; send it only with "
            "to=approved",
        )

    if body.draft_next_slice:
        # The request is the offer now (`amendments-main-watch-and-the-next-slice`, D6).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": slice_drafting.REQUEST_RETIRED, "code": "draft_next_slice_retired"},
        )

    if body.delivery_agent is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "delivery_agent chooses the agent of a build's flow, and approval starts nothing: "
                f"send it to POST /api/v1/projects/{project_id}/project/documents/build?path="
                f"{document.path}, or approve and build at once with "
                "/documents/approve-and-build"
            ),
        )

    if body.content_version is not None and to != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "content_version names the version an approval approves; send it only with "
                "to=approved"
            ),
        )
    if to == "approved":
        _require_loaded_version(workspace, document, body.content_version)

    retiring = document.kind == "capability" and to == spec_lifecycle.ARCHIVED
    absorbed_by = body.absorbed_by
    if absorbed_by is not None:
        if not retiring:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "absorbed_by names the capability that absorbed one being retired; send it "
                    "only with to=archived on a capability"
                ),
            )
        try:
            absorbed_by = validate_spec_path(absorbed_by)
        except SpecPathError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    moved = await _move_phase(
        session,
        workspace,
        project_id,
        document,
        to=to,
        reason=body.reason,
        no_capability_change=body.no_capability_change,
        absorbed_by=absorbed_by,
        approve_anyway=body.approve_anyway,
    )

    await spec_service.rerender_phase(session, workspace, document)
    if retiring:
        # Its requirements leave coverage now, not at the next reindex (F536).
        await spec_index.reindex_from_file(
            session, workspace, document, actor=_operator(), source=spec_index.SOURCE_HUB
        )
        await _refresh_index_entry(session, workspace, project_id, document.path)
    _defer_phase_broadcasts(session, project_id, document, moved)
    await session.commit()

    return await _phase_response(session, project_id, document, moved)


@router.get("/next-slice-offers")
async def next_slice_offers(
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Every roadmap slice whose drafting is offered (`slice_drafting`, D6): a built slice whose
    next slice no document claims, not yet taken or declined. Derived on read."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    return {"offers": await slice_drafting.list_offers(session, workspace, project_id)}


class NextSliceTake(RequestModel):
    """The agent that drafts the next slice; left out, the slice document's author."""

    agent: Optional[_AgentName] = None


@router.post("/documents/next-slice/take")
async def take_next_slice_offer(
    request: Request,
    body: Optional[NextSliceTake] = None,
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Take a document's next-slice offer: one drafting turn queued to the chosen agent, carrying
    the slice's outcomes, in the conversation the slice was written in while it is open, else a new
    one (F1047). 409 when there is no offer (a second take queues nothing)."""
    from ...turn_scheduler import schedule_accepted

    body = body or NextSliceTake()
    _misplaced_query(request, {"path"})
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    try:
        taken = await slice_drafting.take_offer(session, workspace, document, agent=body.agent)
    except slice_drafting.OfferRefused as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"message": str(exc), "code": "no_offer"}
        ) from exc
    await session.commit()
    await schedule_accepted(project_id, taken["agent"])
    return {"state": "queued", **taken}


@router.post("/documents/next-slice/decline")
async def decline_next_slice_offer(
    request: Request,
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Not now: hide a document's next-slice offer for that slice. Nothing is queued."""
    _misplaced_query(request, {"path"})
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    try:
        offer = await slice_drafting.decline_offer(session, workspace, document)
    except slice_drafting.OfferRefused as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"message": str(exc), "code": "no_offer"}
        ) from exc
    await session.commit()
    return {"state": "declined", **offer}


@router.post("/documents/build")
async def build_document(
    request: Request,
    body: Optional[BuildRequest] = None,
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Build an approved document as its recommended build says (FR-6), at any time after approval.

    In this slice: create and start the flow its delivery describes, or leave the tasks on the
    board, and say which in `build_outcome`. A flow already declaring the document is reported, not
    duplicated. 409 `not_approved` before approval; nothing changes on a refusal.
    """
    body = body or BuildRequest()
    _misplaced_query(request, {"path"})
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    if document.phase != spec_lifecycle.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    f"this document is {document.phase}; only an approved document is built. "
                    "Approve it, or approve and build it at once"
                ),
                "code": "not_approved",
            },
        )
    payload = _read_payload(workspace, document.path)
    settings = await _build_settings(session, project_id, document, payload, body)
    _check_delivery_agent(workspace, document, body.delivery_agent, body.driver)
    await _refuse_a_second_build(session, document)
    build, started = await _build(
        session, project_id, document, payload, body.delivery_agent, settings
    )
    defer_broadcast(
        session, project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    if started.job is not None:
        defer_broadcast(
            session, project_id, "job_created", {"id": started.job.id, "name": started.job.name}
        )
    await session.commit()
    await _finish_build(session, project_id, started)
    return {**await _project_document_view(session, project_id, document), "build_outcome": build}


@router.post("/documents/approve-and-build")
async def approve_and_build(
    request: Request,
    body: Optional[ApproveAndBuildRequest] = None,
    path: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Approve and start the build in one operator action (FR-7), with approval's refusal rules.

    Refused exactly as approving alone is (a changed document, gaps without approve_anyway, a
    refusal), with nothing created. A document intake recorded as already built is approved and
    offered close-as-built instead of being built (`already-built-at-intake`); Build still builds
    it if the operator wants it built anyway.
    """
    body = body or ApproveAndBuildRequest()
    _misplaced_query(request, {"path"})
    if body.draft_next_slice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": slice_drafting.REQUEST_RETIRED, "code": "draft_next_slice_retired"},
        )
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    _require_loaded_version(workspace, document, body.content_version)
    _check_delivery_agent(workspace, document, body.delivery_agent, body.driver)
    # A reopened document re-approved while its build still runs: approval lays the new tasks out
    # and they join that build and its flow (`spec_tasks`), so nothing second is started -- the
    # response names the running build instead (one build per document at a time, FR-1).
    running = await builds.running_build(session, document.id)
    settings = (
        await _build_settings(
            session, project_id, document, _read_payload(workspace, document.path), body
        )
        if running is None
        else None
    )

    moved = await _move_phase(
        session,
        workspace,
        project_id,
        document,
        to=spec_lifecycle.APPROVED,
        reason=body.reason,
        approve_anyway=body.approve_anyway,
    )
    started = _Started()
    offer = (moved.report or {}).get("already_built")
    if offer is not None:
        build: Dict[str, Any] = {
            "flow": {
                "state": "already_built",
                "messages": [
                    offer["message"] + " Nothing was built; Build builds it anyway.",
                ],
            },
            "delivery_agent": body.delivery_agent,
            "reviewer": None,
        }
    elif running is not None:
        build, started = await _joined_build(
            session, project_id, document, moved.payload, body, running
        )
    else:
        build, started = await _build(
            session, project_id, document, moved.payload, body.delivery_agent, settings
        )
    await spec_service.rerender_phase(session, workspace, document)
    _defer_phase_broadcasts(session, project_id, document, moved)
    if started.job is not None:
        defer_broadcast(
            session, project_id, "job_created", {"id": started.job.id, "name": started.job.name}
        )
    await session.commit()
    await _finish_build(session, project_id, started)

    response = await _phase_response(session, project_id, document, moved)
    response["build_outcome"] = build
    return response


class BuildUpdate(RequestModel):
    """Raise a build's cap or move its window (slice D, FR-10): a build these stopped resumes."""

    budget_cap_usd: Optional[float] = Field(default=None, gt=0, le=100_000)
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None


async def _project_build(session: AsyncSession, project_id: str, build_id: str):
    from ...db.models import Build

    build = await session.get(Build, build_id)
    if build is None or build.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "no_build", "message": f"there is no build {build_id!r} here"},
        )
    return build


async def _after_build_change(session: AsyncSession, project_id: str, build, job) -> Dict:
    """Commit, tell the app, hand a resumed job back to (or take a paused one out of) the live
    scheduler, and answer with the build as it now reads."""
    view = await builds.view(session, build)
    defer_broadcast(session, project_id, "build_updated", {"id": build.id, "state": build.state})
    await session.commit()
    if job is not None:
        await _hand_job_to_scheduler(session, job.id, job)
    return view


@router.patch("/builds/{build_id}")
async def update_build(
    build_id: str,
    body: BuildUpdate,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Raise a build's cap, or move its window. A build stopped by its cap or its window resumes
    when the change lets it hand out work again; one the operator stopped stays stopped."""
    project_id, _ = project
    build = await _project_build(session, project_id, build_id)
    if body.budget_cap_usd is not None:
        build.budget_cap_usd_micros = builds.micros_of(body.budget_cap_usd)
    if body.window_start is not None:
        build.window_start = _aware(body.window_start)
    if body.window_end is not None:
        build.window_end = _aware(body.window_end)
    start, end = _aware(build.window_start), _aware(build.window_end)
    if start is not None and end is not None and end <= start:
        raise _unprocessable("window_inverted", "the build's window ends before it starts")
    job = None
    if build.state == builds.STOPPED and build.stop_reason != builds.STOPPED_BY_OPERATOR:
        verdict = await builds.may_hand_out(session, build)
        if verdict.stop_reason is None:
            other = await builds.running_build(session, build.document_id)
            if other is not None and other.id != build.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "build_running",
                        "message": f"build {other.id} of this document is running",
                        "build_id": other.id,
                    },
                )
            job = await builds.resume(session, build)
    return await _after_build_change(session, project_id, build, job)


@router.post("/builds/{build_id}/stop")
async def stop_build(
    build_id: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator stops a running build: nothing new is handed out, running turns finish."""
    project_id, _ = project
    build = await _project_build(session, project_id, build_id)
    if build.state != builds.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "not_running", "message": f"build {build.id} is {build.state}"},
        )
    job = await builds.stop(session, build, builds.STOPPED_BY_OPERATOR)
    view = await _after_build_change(session, project_id, build, None)
    if job is not None:
        from ...scheduler import get_scheduler

        scheduler = get_scheduler()
        if scheduler is not None:
            await scheduler.remove_job(job.id)
    return view


class _FlowWouldBeEmptyError(Exception):
    """A flow approval would create owning no open task: an outcome, not a fault (design D6 3a)."""


_NO_TASKS = "No flow was started: it has no open tasks to work. Start a flow… once there is work."


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


async def _build_flow(
    session: AsyncSession,
    project_id: str,
    document,
    payload: Optional[Dict[str, Any]],
    delivery_agent: Optional[str],
    *,
    settings: Optional[builds.Settings] = None,
) -> Tuple[Dict[str, Any], Optional[AIJob]]:
    """Create the flow a change document's delivery asks for, or say why none was (design D6).

    Returns the report's `flow` entry and the job, when one was created. Everything read after a
    savepoint rolled back is a plain value captured before it: rolling back expires what was
    touched inside, and reading that raises `MissingGreenlet` (measured, R2).

    *settings* is the build this flow serves (slice D): a flow or lead driver the operator chose
    has a flow even where the delivery declares none (stopping when its queue empties), its job's
    agent is the lead, else the operator's `delivery_agent`, else the first builder, else the
    delivery's agent.
    """
    if document.kind != "change-spec":
        return {
            "state": "not_applicable",
            "messages": ["Only a change document declares a delivery, so no flow was started."],
        }, None

    delivery = _delivery_of(payload)
    if settings is not None and (delivery is None or delivery.mode != "flow"):
        delivery = spec_payload_module.Delivery(mode="flow", stop_when_queue_empties=True)
    existing = await _existing_flow_entry(session, project_id, document, delivery, delivery_agent)
    if existing is not None:
        return existing, None

    if delivery is None:
        return {"state": "none", "messages": ["No delivery was declared."]}, None
    if delivery.mode != "flow":
        # Which, said for what the document has: "the tasks are on the board" read oddly for a
        # document that declares none (F657).
        has_tasks = bool((payload or {}).get("tasks"))
        return {
            "state": "none",
            "messages": [
                (
                    "The delivery says no flow: the tasks are on the board, started by hand."
                    if has_tasks
                    else "The delivery says no flow, and the document declares no tasks."
                )
            ],
        }, None
    if delivery_agent == "":
        return _not_created("You chose no flow for this build."), None

    agent = delivery_agent if delivery_agent is not None else delivery.agent
    if settings is not None and settings.driver == builds.DRIVER_LEAD:
        agent = settings.lead
    elif settings is not None and delivery_agent is None and settings.builders:
        agent = settings.builders[0]
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
                message=(
                    f'Lead the build of "{title}": hand its tasks out with hand_out_task.'
                    if settings is not None and settings.driver == builds.DRIVER_LEAD
                    else f'Work the next task of "{title}".'
                ),
                cron=delivery.cron,
                purpose="",
                stop_at=stop_at,
                stop_when_queue_empties=delivery.stop_when_queue_empties,
                spec_document_id=document.id,
            )
            job, loop = await build_flow_rows(
                session,
                project_id,
                request,
                created_by_run_id=None,
                by=loop_history.by_operator(),
                door=loop_history.DOOR_APPROVAL,
            )
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
    if document.phase != spec_lifecycle.CURRENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"{path} is retired; nothing is merged into a retired capability",
                "code": "capability_retired",
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

    # Built BEFORE committing, so a failure here fails loudly instead of 500ing after the write is
    # already durable.
    response = {
        **await _project_document_view(session, project_id, document),
        "blocking": result.blocking,
        "warnings": result.warnings,
        "divergence": result.divergence,
        # F730: whether the payload was written. `merged` counts the changes folded, so an
        # operator edit naming none answered `merged: 0` and read as nothing having happened.
        "applied": True,
        "merged": len(sources),
    }

    await session.commit()
    await sse_manager.broadcast(
        project_id, "spec_updated", {"path": document.path, "phase": document.phase}
    )
    return response


@router.delete("/documents/{path:path}")
async def delete_document(
    path: str,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """Delete a specification document and everything it produced (F532, `deletion`).

    Refused, writing nothing, for a capability, an archived or folded document, one with a run in
    progress on its tasks, and one whose flow is running. The rows go in one transaction; the file
    goes after it commits (a transaction rolls back, a file delete does not), and `spec/index.json`
    is rebuilt without it when it listed the document.
    """
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    document = await _require_document(session, project_id, path)
    try:
        deleted = await deletion.delete_document(session, document)
    except deletion.DeletionRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"message": str(exc), "code": exc.code}
        ) from exc
    await persist_event(
        session,
        project_id,
        "spec_document_deleted",
        {"path": deleted.path, "tasks": deleted.tasks},
        commit=False,
    )
    # Announced once the rows are committed (F335). The file and the index follow; a reader that
    # refetches in between sees the document gone from the Hub, which is what decides.
    defer_broadcast(session, project_id, "spec_updated", {"path": deleted.path})
    await session.commit()

    # F828: the tasks' checkouts and branches go with them unless they hold work.
    kept_work = deletion.discard_checkouts(workspace.root, deleted.tasks)
    for entry in kept_work:
        await persist_event(session, project_id, "task_checkout_kept", entry, severity="warn")

    diagnostics: List[Dict[str, Any]] = []
    try:
        spec_documents.delete_document_file(workspace, deleted.path)
    except OSError as exc:
        diagnostics.append({"code": "file_delete_failed", "path": deleted.path, "actual": str(exc)})
    existing, _, _ = spec_documents.read_index(workspace)
    if existing is not None and any(entry.path == deleted.path for entry in existing.documents):
        on_disk, _ = spec_documents.discover(workspace)
        rows = await spec_lifecycle.list_documents(session, project_id)
        manifest, index_diagnostics = spec_documents.build_index(
            on_disk, [(row.path, row.title, row.kind, row.phase) for row in rows], existing
        )
        diagnostics.extend(index_diagnostics)
        if manifest is not None:
            try:
                spec_documents.write_index(workspace, manifest)
            except OSError as exc:
                diagnostics.append({"code": "index_write_failed", "actual": str(exc)})
    return {
        "path": deleted.path,
        "deleted": True,
        "tasks": deleted.tasks,
        "requirements": deleted.requirements,
        "kept_work": kept_work,
        "diagnostics": diagnostics,
    }


def _fold_refused(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"message": str(exc), "code": getattr(exc, "code", "fold_refused")},
    )


@router.get("/documents/{path:path}/fold-draft")
async def fold_draft(
    path: str,
    into: str = Query(...),
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """What folding this change into `into` would write: the capability's payload with the change's
    requirements appended under drafted keys, and the keys that collide. Writes nothing."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    change = await _require_document(session, project_id, path)
    capability = await _require_document(session, project_id, into)
    try:
        draft = spec_service.fold_draft(
            workspace,
            change,
            capability,
            folded_into=await spec_lifecycle.merged_into(session, change),
        )
    except spec_service.FoldRefusedError as exc:
        raise _fold_refused(exc) from exc
    return {
        "into": capability.path,
        "payload": draft.payload,
        "requirements": draft.requirements,
        "algorithms": draft.algorithms,
        "collisions": draft.collisions,
        "warnings": draft.warnings,
        "capability_requirements": draft.capability_requirements,
        "capability_criteria": draft.capability_criteria,
        "capability_algorithms": draft.capability_algorithms,
    }


@router.post("/documents/{path:path}/fold")
async def fold_document(
    path: str,
    body: FoldRequest,
    project: Tuple[str, str] = Depends(get_project),
    session: AsyncSession = Depends(get_session),
):
    """The operator closing a finished change: fold it into a capability through the merge (one
    `spec_document_merges` row, one `merged` event) and, unless `archive` is false, archive it in
    the same transaction. Every refusal happens before anything is written."""
    project_id, _ = project
    workspace = await _workspace(session, project_id)
    change = await _require_document(session, project_id, path)
    capability = await _require_document(session, project_id, body.into)
    items = (
        None
        if body.requirements is None
        else [spec_service.FoldItem(**item.model_dump()) for item in body.requirements]
    )
    try:
        result, archived = await spec_service.fold(
            session,
            workspace,
            change,
            capability,
            items,
            actor=_operator(),
            archive=body.archive,
            note=body.note,
            retire=body.retire,
            retire_criteria=body.retire_criteria,
            algorithms=(
                None
                if body.algorithms is None
                else [spec_service.FoldAlgorithm(**a.model_dump()) for a in body.algorithms]
            ),
            retire_algorithms=body.retire_algorithms,
            criteria=[spec_service.FoldCriterion(**c.model_dump()) for c in body.criteria],
        )
    except (spec_service.FoldRefusedError, spec_lifecycle.PhaseError) as exc:
        raise _fold_refused(exc) from exc
    except spec_service.SaveRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": str(exc), "code": exc.code, "field": exc.field_path},
        ) from exc

    response: Dict[str, Any] = {
        **await _project_document_view(session, project_id, change),
        "capability": _document_view(capability),
        "archived": archived,
        "fold_state": await _fold_state(session, change),
    }
    response.update(
        merged=1,
        blocking=result.blocking,
        warnings=result.warnings,
        standing_warnings=result.standing_warnings,
    )
    await session.commit()
    for document in (capability, change):
        await sse_manager.broadcast(
            project_id, "spec_updated", {"path": document.path, "phase": document.phase}
        )
    return response
