"""A change reconciled with its code before it is folded (`a-change-is-reconciled-with-its-code-
before-it-is-folded`, roadmap slice reconcile-and-measure).

An agent reads an approved change and the code, and records each gap between them in one of four
classes (Spec Kit's converge classes): `missing` (the spec asks, the code does not do it),
`partial` (the code does some of it), `contradicts` (the code does something else) and
`unrequested` (the code does something nobody asked for). The result is a Hub-owned `reconcile`
event with its author and run; the latest one is the change's reconcile result, shown on its way
into a capability (D1). The Hub never compares code with the spec itself.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import SpecDocument, SpecDocumentEvent

EVENT = "reconcile"
MISSING = "missing"
PARTIAL = "partial"
CONTRADICTS = "contradicts"
UNREQUESTED = "unrequested"
CLASSES = (MISSING, PARTIAL, CONTRADICTS, UNREQUESTED)
# The classes that are a defect the reconcile step caught (D3): unrequested code is a question for
# the operator, not a step's failure.
DEFECT_CLASSES = frozenset({MISSING, PARTIAL, CONTRADICTS})
TEXT_MAX = 2000
GAPS_MAX = 100


class ReconcileRefused(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    def __init__(self, message: str, *, code: str, status: int = 422, field: str = "") -> None:
        self.code = code
        self.status = status
        self.field = field
        super().__init__(message)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReconcileRefused(f"{field} is required", code="reconcile_invalid", field=field)
    if len(value) > TEXT_MAX:
        raise ReconcileRefused(
            f"{field} is over {TEXT_MAX} characters", code="reconcile_invalid", field=field
        )
    return value.strip()


def _requirement_keys(payload: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """{key or identifier: key} for the document's requirements, so either spelling is accepted."""
    from .spec_identity import read_identity

    keys = {
        r["key"]: r["key"]
        for r in (payload or {}).get("requirements") or []
        if isinstance(r, dict) and isinstance(r.get("key"), str)
    }
    identifiers, _ = read_identity(payload)
    for key, identifier in identifiers.items():
        if key in keys:
            keys[identifier] = key
    return keys


def validate_gaps(payload: Optional[Dict[str, Any]], gaps: Any) -> List[Dict[str, Any]]:
    """The gaps, checked and normalised; refuses the first bad one, naming its field."""
    if not isinstance(gaps, list):
        raise ReconcileRefused("gaps must be a list", code="reconcile_invalid", field="gaps")
    if len(gaps) > GAPS_MAX:
        raise ReconcileRefused(f"at most {GAPS_MAX} gaps", code="reconcile_invalid", field="gaps")
    known = _requirement_keys(payload)
    out: List[Dict[str, Any]] = []
    for index, gap in enumerate(gaps):
        where = f"gaps[{index}]"
        if not isinstance(gap, dict):
            raise ReconcileRefused(
                f"{where} must be an object", code="reconcile_invalid", field=where
            )
        kind = gap.get("class")
        if kind not in CLASSES:
            raise ReconcileRefused(
                f"{where}.class must be one of {', '.join(CLASSES)}",
                code="reconcile_invalid",
                field=f"{where}.class",
            )
        requirement = gap.get("requirement")
        if kind == UNREQUESTED:
            requirement = None
        elif not isinstance(requirement, str) or requirement not in known:
            raise ReconcileRefused(
                f"{where}.requirement must name one of this document's requirements: a {kind} gap "
                "is a requirement the code does not meet",
                code="reconcile_invalid",
                field=f"{where}.requirement",
            )
        else:
            requirement = known[requirement]
        out.append(
            {
                "class": kind,
                "requirement": requirement,
                "where": _text(gap.get("where"), f"{where}.where"),
                "summary": _text(gap.get("summary"), f"{where}.summary"),
            }
        )
    return out


async def record(
    session: AsyncSession,
    workspace: Any,
    document: SpecDocument,
    *,
    summary: Any,
    gaps: Any,
    actor: Any,
) -> Dict[str, Any]:
    """Record a reconcile result for an approved change. The caller commits."""
    from . import spec_documents, spec_lifecycle

    if document.kind != "change-spec" or document.phase != spec_lifecycle.APPROVED:
        raise ReconcileRefused(
            "only an approved change is reconciled with its code",
            code="reconcile_not_approved",
            status=409,
        )
    payload = spec_documents.read_payload(workspace, document.path)
    checked = validate_gaps(payload, gaps)
    event = await spec_lifecycle.record_event(
        session,
        document,
        kind=EVENT,
        actor=actor,
        detail={"summary": _text(summary, "summary"), "gaps": checked},
    )
    return view(event)


def view(event: Optional[SpecDocumentEvent]) -> Dict[str, Any]:
    """The reconcile result as `fold_state.reconcile` carries it."""
    if event is None:
        return {"state": "none"}
    detail = event.detail or {}
    gaps = list(detail.get("gaps") or [])
    counts = dict.fromkeys(CLASSES, 0)
    for gap in gaps:
        if gap.get("class") in counts:
            counts[gap["class"]] += 1
    return {
        "state": "recorded",
        "id": event.id,
        "author": event.actor,
        "run_id": event.run_id,
        "at": event.created_at.isoformat() if event.created_at else None,
        "summary": detail.get("summary", ""),
        "counts": counts,
        "gaps": gaps,
    }


async def latest(session: AsyncSession, document_id: str) -> Optional[SpecDocumentEvent]:
    result = await session.execute(
        select(SpecDocumentEvent)
        .where(SpecDocumentEvent.document_id == document_id, SpecDocumentEvent.kind == EVENT)
        .order_by(SpecDocumentEvent.created_at.desc(), SpecDocumentEvent.id.desc())
        .limit(1)
    )
    return result.scalars().first()


def brief(document: SpecDocument) -> str:
    """The reconcile turn's message: what to read, the four classes, how to record, change nothing."""
    return "\n".join(
        [
            f'Reconcile the change `{document.path}` ("{document.title}") with the code, before it '
            "is folded into a capability.",
            "",
            "1. Read the document: `read_spec_document` with `include=full`.",
            "2. Read the code it is about, and run it where its criteria say how to check.",
            "3. Class every gap between the two as one of:",
            "   - `missing`: a requirement the code does not do at all;",
            "   - `partial`: a requirement the code does only some of;",
            "   - `contradicts`: the code does something other than the requirement says;",
            "   - `unrequested`: the code does something no requirement asks for.",
            "4. Record the result once with `record_reconcile(path, summary, gaps)`, each gap "
            "`{class, requirement, where, summary}` (`requirement` is the requirement's key or "
            "FR identifier; leave it out for `unrequested`; `where` is a file, route or line). "
            "No gaps is a valid result: record it with `gaps=[]`.",
            "",
            "Change nothing: do not edit code, the spec or any task. The operator decides what "
            "follows.",
        ]
    )
