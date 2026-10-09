"""A tester's amendments to an approved document (`a-tester-drives-the-built-product-and-keeps-the-
spec-true`, roadmap slice tester-amends).

An approved document refuses every submission (`spec_service.save_document`). This module is the one
other way its content changes after approval: a run delivered to *test* a task of the document may
amend it with a structured operation, applied at once and recorded as an `amendment` event that
names its author and run and stays not reviewed until the operator marks it reviewed (an
`amendment_reviewed` event naming the ids). The record is Hub-owned and append-only, so the agent
that wrote an amendment cannot erase it (design D1).

The builder never amends (D2): only a run whose delivered entry was a review of a task of this
document may call `amend`, and only while the document's testing is on. A change or removal of a
criterion, and a `cannot_satisfy` report, are *relaxing* (D3): while one is not reviewed its
requirement cannot be verified, whatever evidence it holds (`requirement_coverage`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Run, SpecDocument, SpecDocumentEvent, Task
from .utils import short_id

EVENT = "amendment"
REVIEWED_EVENT = "amendment_reviewed"

ADD_TASK = "add_task"
ADD_CRITERION = "add_criterion"
CHANGE_CRITERION = "change_criterion"
REMOVE_CRITERION = "remove_criterion"
CANNOT_SATISFY = "cannot_satisfy"
OPS = (ADD_TASK, ADD_CRITERION, CHANGE_CRITERION, REMOVE_CRITERION)
# Structural, never judged by reading (D3): a change can be called a tightening by the agent it lets
# pass, so every change or removal waits for the operator; an addition never does.
RELAXING = frozenset({CHANGE_CRITERION, REMOVE_CRITERION, CANNOT_SATISFY})

CRITERION_FIELDS = ("given", "when", "then", "how_to_check", "checked_by")
TASK_FIELDS = ("key", "title", "description", "requirements", "depends_on", "files", "reviewer")
TEXT_MAX = 2000


class AmendmentRefused(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """An amendment that may not happen. `status` is the HTTP answer the route gives."""

    def __init__(self, message: str, *, code: str, status: int = 422, field: str = "") -> None:
        self.code = code
        self.status = status
        self.field = field
        super().__init__(message)


@dataclass(frozen=True)
class Amendment:
    id: str
    op: str
    target: str
    requirement: Optional[str]
    identifier: Optional[str]
    reason: str
    how_to_check: str
    author: str
    run_id: Optional[str]
    created_at: str
    reviewed: bool
    reviewed_at: Optional[str]
    reviewed_by: Optional[str]
    detail: Dict[str, Any]

    @property
    def relaxing(self) -> bool:
        return self.op in RELAXING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "op": self.op,
            "target": self.target,
            "requirement": self.requirement,
            "identifier": self.identifier,
            "reason": self.reason,
            "how_to_check": self.how_to_check,
            "author": self.author,
            "run_id": self.run_id,
            "created_at": self.created_at,
            "reviewed": self.reviewed,
            "reviewed_at": self.reviewed_at,
            "reviewed_by": self.reviewed_by,
            "relaxing": self.relaxing,
            "change": self.detail.get("change"),
            "before": self.detail.get("before"),
        }


# ---------------------------------------------------------------------------
# Who may amend
# ---------------------------------------------------------------------------


def testing_on(payload: Optional[Dict[str, Any]]) -> bool:
    """Testing is on unless the delivery says `tester: false` (D4): absent or null means on."""
    delivery = (payload or {}).get("delivery")
    return not (isinstance(delivery, dict) and delivery.get("tester") is False)


async def tested_task(
    session: AsyncSession, run_id: Optional[str], document: SpecDocument
) -> Optional[Task]:
    """The task of `document` this run was delivered to test, or None (D2).

    Read from the run's delivered queue entries (`run_task_binding.review_task_for_run`), the one
    place a review turn's task is recorded; a name match against `delivery.tester` would let the
    tester amend from a turn that was not testing anything.
    """
    from .run_task_binding import review_task_for_run

    if not run_id:
        return None
    run = await session.get(Run, run_id)
    if run is None:
        return None
    task_id = await review_task_for_run(session, run)
    if not task_id:
        return None
    task = await session.get(Task, task_id)
    if task is None or task.spec_document_id != document.id:
        return None
    return task


async def worked_task(
    session: AsyncSession, run_id: Optional[str], document: SpecDocument
) -> Optional[Task]:
    """The task of `document` this run is bound to work on, or None."""
    if not run_id:
        return None
    run = await session.get(Run, run_id)
    if run is None or not run.task_id:
        return None
    task = await session.get(Task, run.task_id)
    if task is None or task.spec_document_id != document.id:
        return None
    return task


# ---------------------------------------------------------------------------
# The operations
# ---------------------------------------------------------------------------


def _text(value: Any, field: str, *, required: bool = True) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise AmendmentRefused(f"{field} is required", code="amendment_invalid", field=field)
        return ""
    if not isinstance(value, str):
        raise AmendmentRefused(f"{field} must be text", code="amendment_invalid", field=field)
    if len(value) > TEXT_MAX:
        raise AmendmentRefused(
            f"{field} is over {TEXT_MAX} characters", code="amendment_invalid", field=field
        )
    return value.strip()


def _criteria(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    criteria = payload.get("acceptance_criteria")
    return criteria if isinstance(criteria, list) else []


def _requirement_keys(payload: Dict[str, Any]) -> Set[str]:
    return {
        r.get("key")
        for r in payload.get("requirements") or []
        if isinstance(r, dict) and isinstance(r.get("key"), str)
    }


def _criterion(payload: Dict[str, Any], key: str) -> Dict[str, Any]:
    found = next(
        (c for c in _criteria(payload) if isinstance(c, dict) and c.get("key") == key), None
    )
    if found is None:
        raise AmendmentRefused(
            f"this document has no criterion {key!r}; an amendment names only the criteria it "
            "already holds",
            code="unknown_criterion",
            field="criterion",
        )
    return found


def _known_requirement(payload: Dict[str, Any], key: Any, field: str) -> str:
    if not isinstance(key, str) or key not in _requirement_keys(payload):
        raise AmendmentRefused(
            f"this document has no requirement {key!r}; an amendment stays within the stated "
            "requirements (a new requirement is a reopen)",
            code="unknown_requirement",
            field=field,
        )
    return key


def apply(
    payload: Dict[str, Any],
    op: str,
    *,
    criterion: Optional[str] = None,
    requirement: Optional[str] = None,
    task: Optional[Dict[str, Any]] = None,
    change: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str, Optional[str], Dict[str, Any]]:
    """`payload` with the operation applied: (new payload, target, requirement key, detail).

    Pure. Refuses anything naming a requirement or criterion the document does not hold (D5).
    """
    new = dict(payload)
    criteria = [dict(c) if isinstance(c, dict) else c for c in _criteria(payload)]
    detail: Dict[str, Any] = {}

    if op == ADD_TASK:
        if not isinstance(task, dict):
            raise AmendmentRefused("add_task needs a task", code="amendment_invalid", field="task")
        key = _text(task.get("key"), "task.key")
        tasks = [t for t in payload.get("tasks") or [] if isinstance(t, dict)]
        if any(t.get("key") == key for t in tasks):
            raise AmendmentRefused(
                f"this document already has a task {key!r}", code="duplicate_key", field="task.key"
            )
        names = task.get("requirements")
        if not isinstance(names, list) or not names:
            raise AmendmentRefused(
                "add_task must name the requirements it serves",
                code="amendment_invalid",
                field="task.requirements",
            )
        for name in names:
            _known_requirement(payload, name, "task.requirements")
        known_tasks = {t.get("key") for t in tasks}
        depends_on = task.get("depends_on") or []
        if not isinstance(depends_on, list) or any(dep not in known_tasks for dep in depends_on):
            raise AmendmentRefused(
                "add_task may depend only on tasks the document holds",
                code="amendment_invalid",
                field="task.depends_on",
            )
        entry = {
            "key": key,
            "title": _text(task.get("title"), "task.title"),
            "description": _text(task.get("description"), "task.description", required=False),
            "requirements": list(names),
            "depends_on": list(depends_on),
            "files": [f for f in task.get("files") or [] if isinstance(f, str)],
            "from": None,
            "reviewer": task.get("reviewer") if isinstance(task.get("reviewer"), str) else None,
        }
        new["tasks"] = [*tasks, entry]
        detail["change"] = entry
        return new, key, names[0], detail

    if op == ADD_CRITERION:
        if not isinstance(change, dict):
            raise AmendmentRefused(
                "add_criterion needs the criterion under change",
                code="amendment_invalid",
                field="change",
            )
        key = _text(criterion or change.get("key"), "criterion")
        if any(isinstance(c, dict) and c.get("key") == key for c in criteria):
            raise AmendmentRefused(
                f"this document already has a criterion {key!r}",
                code="duplicate_key",
                field="criterion",
            )
        req = _known_requirement(payload, requirement or change.get("requirement"), "requirement")
        entry = {"key": key, "requirement": req}
        for field in ("given", "when", "then"):
            entry[field] = _text(change.get(field), f"change.{field}")
        for field in ("how_to_check", "checked_by"):
            value = _text(change.get(field), f"change.{field}", required=False)
            if value:
                entry[field] = value
        new["acceptance_criteria"] = [*criteria, entry]
        detail["change"] = entry
        return new, key, req, detail

    if op in (CHANGE_CRITERION, REMOVE_CRITERION):
        key = _text(criterion, "criterion")
        before = _criterion(payload, key)
        req = before.get("requirement") if isinstance(before.get("requirement"), str) else None
        detail["before"] = before
        if op == REMOVE_CRITERION:
            new["acceptance_criteria"] = [
                c for c in criteria if not (isinstance(c, dict) and c.get("key") == key)
            ]
            return new, key, req, detail
        if not isinstance(change, dict) or not change:
            raise AmendmentRefused(
                "change_criterion needs the fields to change",
                code="amendment_invalid",
                field="change",
            )
        unknown = sorted(set(change) - set(CRITERION_FIELDS))
        if unknown:
            raise AmendmentRefused(
                f"change_criterion may change only {', '.join(CRITERION_FIELDS)}; not {unknown[0]}",
                code="amendment_invalid",
                field=f"change.{unknown[0]}",
            )
        after = dict(before)
        for field, value in change.items():
            after[field] = _text(value, f"change.{field}")
        new["acceptance_criteria"] = [
            after if isinstance(c, dict) and c.get("key") == key else c for c in criteria
        ]
        detail["change"] = {field: after[field] for field in change}
        return new, key, req, detail

    raise AmendmentRefused(
        f"op must be one of {', '.join(OPS)}", code="amendment_invalid", field="op"
    )


# ---------------------------------------------------------------------------
# Amend, report, review
# ---------------------------------------------------------------------------


async def amend(
    session: AsyncSession,
    workspace: Any,
    document: SpecDocument,
    *,
    op: str,
    reason: Any,
    how_to_check: Any,
    actor: Any,
    criterion: Optional[str] = None,
    requirement: Optional[str] = None,
    task: Optional[Dict[str, Any]] = None,
    change: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Apply one amendment to an approved document and record it. The caller commits.

    Returns the amendment's view, plus `task_created` (the board task's id) for an `add_task`.
    """
    from . import spec_documents, spec_identity, spec_lifecycle, spec_service, spec_tasks
    from .spec_payload import PayloadError, validate_payload

    if document.phase != spec_lifecycle.APPROVED:
        raise AmendmentRefused(
            "only an approved document is amended; before approval it is written directly",
            code="amend_not_approved",
            status=409,
        )
    existing_content = spec_documents.read_document(workspace, document.path)
    stored_before = spec_documents.parse_stored(existing_content)
    if not isinstance(stored_before, dict):
        raise AmendmentRefused(
            "this document has no readable payload", code="payload_unreadable", status=409
        )

    tested = await tested_task(session, getattr(actor, "run_id", None), document)
    if actor.kind != "agent" or tested is None or not testing_on(stored_before):
        raise AmendmentRefused(
            "only a run testing a task of this document may amend it, while its testing is on; "
            "the builder never amends (report a criterion it cannot meet with report_cannot_satisfy)",
            code="amend_not_tester",
            status=403,
        )

    reason_text = _text(reason, "reason")
    check_text = _text(how_to_check, "how_to_check")
    current = {k: v for k, v in stored_before.items() if k != spec_identity.IDENTITY_FIELD}
    new_payload, target, req_key, detail = apply(
        current, op, criterion=criterion, requirement=requirement, task=task, change=change
    )
    try:
        payload = validate_payload(new_payload)
    except PayloadError as exc:
        raise AmendmentRefused(str(exc), code="payload_invalid", field=exc.field) from exc

    amendment_id = f"amd-{short_id()}"
    result = await spec_service._apply_and_write(
        session,
        workspace,
        document,
        payload,
        stored_before,
        existing_content,
        actor=actor,
        extra_detail={"amendment": amendment_id},
    )
    identifier = result.identifiers.get(req_key) if req_key else None
    event = await spec_lifecycle.record_event(
        session,
        document,
        kind=EVENT,
        actor=actor,
        detail={
            "id": amendment_id,
            "op": op,
            "target": target,
            "requirement": req_key,
            "identifier": identifier,
            "reason": reason_text,
            "how_to_check": check_text,
            "tested_task_id": tested.id,
            **detail,
        },
    )

    view: Dict[str, Any] = {
        "id": amendment_id,
        "op": op,
        "target": target,
        "requirement": req_key,
        "identifier": identifier,
        "reviewed": False,
        "event_id": event.id,
    }
    if op == ADD_TASK:
        # Takes effect at once: materialised into the document's live flow, for the implementer.
        stored_after = spec_documents.read_payload(workspace, document.path)
        created = await spec_tasks.materialise(session, document, stored_after, actor=actor)
        view["task_created"] = next(
            (row.id for row in created if row.spec_task_key == target), None
        )
    return view


async def report_cannot_satisfy(
    session: AsyncSession,
    workspace: Any,
    document: SpecDocument,
    *,
    criterion: Any,
    reason: Any,
    actor: Any,
) -> Dict[str, Any]:
    """Record that a criterion cannot be satisfied (D6). Blocks the builder's task in progress."""
    from . import spec_documents, spec_identity, spec_lifecycle
    from .task_transition_service import TransitionRefusedError, apply_transition
    from .task_transitions import STATUS_BLOCKED, allowed_targets, run_actor

    run_id = getattr(actor, "run_id", None)
    worked = await worked_task(session, run_id, document)
    tested = await tested_task(session, run_id, document)
    if actor.kind != "agent" or (worked is None and tested is None):
        raise AmendmentRefused(
            "only a run working or testing a task of this document may report a criterion it "
            "cannot satisfy",
            code="cannot_satisfy_not_bound",
            status=403,
        )
    payload = spec_documents.read_payload(workspace, document.path) or {}
    key = _text(criterion, "criterion")
    found = _criterion(payload, key)
    reason_text = _text(reason, "reason")
    req_key = found.get("requirement") if isinstance(found.get("requirement"), str) else None
    identifiers, _ = spec_identity.read_identity(payload)
    identifier = identifiers.get(req_key) if req_key else None

    amendment_id = f"amd-{short_id()}"
    task = worked or tested
    await spec_lifecycle.record_event(
        session,
        document,
        kind=EVENT,
        actor=actor,
        detail={
            "id": amendment_id,
            "op": CANNOT_SATISFY,
            "target": key,
            "requirement": req_key,
            "identifier": identifier,
            "reason": reason_text,
            "how_to_check": found.get("how_to_check") or "",
            "task_id": task.id if task else None,
            # Which step caught it, for the defects report: the builder's run, or the tester's.
            "role": "build" if worked is not None else "test",
            "before": found,
        },
    )
    blocked = False
    mover = run_actor(run_id, actor.name)
    if worked is not None and STATUS_BLOCKED in allowed_targets(worked.status, mover.kind):
        try:
            await apply_transition(session, worked, STATUS_BLOCKED, mover)
            worked.blocked_reason = f"cannot satisfy criterion {key}: {reason_text}"
            blocked = True
        except TransitionRefusedError:
            blocked = False
    return {
        "id": amendment_id,
        "op": CANNOT_SATISFY,
        "target": key,
        "requirement": req_key,
        "identifier": identifier,
        "reviewed": False,
        "task_blocked": blocked,
        "task_id": task.id if task else None,
    }


async def _events(
    session: AsyncSession, document_ids: Iterable[str], kinds: Tuple[str, ...]
) -> List[SpecDocumentEvent]:
    ids = list(document_ids)
    if not ids:
        return []
    result = await session.execute(
        select(SpecDocumentEvent)
        .where(SpecDocumentEvent.document_id.in_(ids), SpecDocumentEvent.kind.in_(kinds))
        .order_by(SpecDocumentEvent.created_at, SpecDocumentEvent.id)
    )
    return list(result.scalars().all())


def _reviews(events: List[SpecDocumentEvent]) -> Dict[str, SpecDocumentEvent]:
    reviewed: Dict[str, SpecDocumentEvent] = {}
    for event in events:
        if event.kind == REVIEWED_EVENT:
            for amendment_id in (event.detail or {}).get("ids") or []:
                reviewed.setdefault(amendment_id, event)
    return reviewed


async def list_amendments(session: AsyncSession, document: SpecDocument) -> List[Amendment]:
    """Every amendment of `document`, oldest first, each with whether it has been reviewed."""
    events = await _events(session, [document.id], (EVENT, REVIEWED_EVENT))
    reviewed = _reviews(events)
    out: List[Amendment] = []
    for event in events:
        if event.kind != EVENT:
            continue
        detail = dict(event.detail or {})
        review = reviewed.get(detail.get("id", ""))
        out.append(
            Amendment(
                id=detail.get("id", event.id),
                op=detail.get("op", ""),
                target=detail.get("target", ""),
                requirement=detail.get("requirement"),
                identifier=detail.get("identifier"),
                reason=detail.get("reason", ""),
                how_to_check=detail.get("how_to_check", ""),
                author=event.actor,
                run_id=event.run_id,
                created_at=event.created_at.isoformat() if event.created_at else "",
                reviewed=review is not None,
                reviewed_at=review.created_at.isoformat() if review and review.created_at else None,
                reviewed_by=review.actor if review else None,
                detail=detail,
            )
        )
    return out


async def mark_reviewed(
    session: AsyncSession,
    document: SpecDocument,
    *,
    ids: Optional[List[str]],
    actor: Any,
) -> List[str]:
    """Mark amendments reviewed: the named ids, or every not-reviewed one when `ids` is None.

    Returns the ids newly marked. An id the document does not hold is refused (404), so a typo is
    not a silent no-op.
    """
    from . import spec_lifecycle

    amendments = await list_amendments(session, document)
    known = {a.id: a for a in amendments}
    if ids is None:
        wanted = [a.id for a in amendments if not a.reviewed]
    else:
        missing = [i for i in ids if i not in known]
        if missing:
            raise AmendmentRefused(
                f"this document has no amendment {missing[0]}", code="unknown_amendment", status=404
            )
        wanted = [i for i in ids if not known[i].reviewed]
    if wanted:
        await spec_lifecycle.record_event(
            session, document, kind=REVIEWED_EVENT, actor=actor, detail={"ids": wanted}
        )
    return wanted


async def unreviewed_relaxing(
    session: AsyncSession, document_ids: Iterable[str]
) -> Set[Tuple[str, str]]:
    """(document id, requirement identifier) pairs held back by a not-reviewed relaxing amendment."""
    events = await _events(session, document_ids, (EVENT, REVIEWED_EVENT))
    reviewed = _reviews(events)
    held: Set[Tuple[str, str]] = set()
    for event in events:
        detail = event.detail or {}
        if (
            event.kind == EVENT
            and detail.get("op") in RELAXING
            and detail.get("identifier")
            and detail.get("id") not in reviewed
        ):
            held.add((event.document_id, detail["identifier"]))
    return held


async def counts(session: AsyncSession, document_ids: Iterable[str]) -> Dict[str, Dict[str, int]]:
    """{document id: {"total", "unreviewed"}} for the documents holding any amendment; one query."""
    events = await _events(session, document_ids, (EVENT, REVIEWED_EVENT))
    reviewed = _reviews(events)
    out: Dict[str, Dict[str, int]] = {}
    for event in events:
        if event.kind != EVENT:
            continue
        entry = out.setdefault(event.document_id, {"total": 0, "unreviewed": 0})
        entry["total"] += 1
        if (event.detail or {}).get("id") not in reviewed:
            entry["unreviewed"] += 1
    return out
