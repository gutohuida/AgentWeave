"""Which step caught each defect of a change (`a-change-is-reconciled-with-its-code-before-it-is-
folded`, FR-4 to FR-6).

A change's defects are read from what the Hub already records, each naming the step that caught it
(D2): a tester's `add_task` amendment (test), a `cannot_satisfy` report (build when the reporting
run was working a task, test when it was testing one), a move of one of its tasks to
`revision_needed` (review), and a `missing`, `partial` or `contradicts` gap in its latest reconcile
result (reconcile). The only new record is a defect the operator writes by hand (a `defect` event),
for what was found later or elsewhere. Computed per read; nothing here is stored twice.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import SpecDocument, SpecDocumentEvent, Task, TaskTransition

EVENT = "defect"
BUILD = "build"
REVIEW = "review"
TEST = "test"
RECONCILE = "reconcile"
AFTER_FOLD = "after-fold"
#: The stages after approval a defect can be caught at, after the project's own journey steps (D4).
POST_APPROVAL_STEPS = (BUILD, REVIEW, TEST, RECONCILE, AFTER_FOLD)
SUMMARY_MAX = 2000


class DefectRefused(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    def __init__(self, message: str, *, field: str) -> None:
        self.field = field
        super().__init__(message)


def steps(journey_order: Iterable[str]) -> List[str]:
    """Every step a defect can name: the project's journey steps, then the post-approval stages."""
    ordered = [key for key in journey_order if key not in POST_APPROVAL_STEPS]
    return [*ordered, *POST_APPROVAL_STEPS]


async def record(
    session: AsyncSession,
    document: SpecDocument,
    *,
    summary: Any,
    caught_by: Any,
    allowed_steps: List[str],
    actor: Any,
) -> Dict[str, Any]:
    """The operator's defect against a change, caught at `caught_by`. The caller commits."""
    from . import spec_lifecycle

    if not isinstance(summary, str) or not summary.strip() or len(summary) > SUMMARY_MAX:
        raise DefectRefused(
            f"summary is required, at most {SUMMARY_MAX} characters", field="summary"
        )
    if caught_by not in allowed_steps:
        raise DefectRefused(
            f"caught_by must be one of {', '.join(allowed_steps)}", field="caught_by"
        )
    event = await spec_lifecycle.record_event(
        session,
        document,
        kind=EVENT,
        actor=actor,
        detail={"summary": summary.strip(), "caught_by": caught_by},
    )
    return {
        "source": "operator",
        "caught_by": caught_by,
        "summary": summary.strip(),
        "id": event.id,
    }


def _at(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


async def for_documents(
    session: AsyncSession, documents: List[SpecDocument]
) -> Dict[str, List[Dict[str, Any]]]:
    """{document id: its defects, oldest first}, for change documents."""
    from . import spec_reconcile

    changes = {d.id: d for d in documents if d.kind == "change-spec"}
    out: Dict[str, List[Dict[str, Any]]] = {document_id: [] for document_id in changes}
    if not changes:
        return out

    events = (
        await session.execute(
            select(SpecDocumentEvent)
            .where(
                SpecDocumentEvent.document_id.in_(list(changes)),
                SpecDocumentEvent.kind.in_(("amendment", EVENT)),
            )
            .order_by(SpecDocumentEvent.created_at, SpecDocumentEvent.id)
        )
    ).scalars()
    for event in events:
        detail = event.detail or {}
        if event.kind == EVENT:
            out[event.document_id].append(
                {
                    "source": "operator",
                    "caught_by": detail.get("caught_by"),
                    "summary": detail.get("summary", ""),
                    "at": _at(event.created_at),
                    "by": event.actor,
                }
            )
        elif detail.get("op") == "add_task":
            out[event.document_id].append(
                {
                    "source": "amendment",
                    "caught_by": TEST,
                    "summary": f"{detail.get('target')}: {detail.get('reason', '')}",
                    "at": _at(event.created_at),
                    "by": event.actor,
                }
            )
        elif detail.get("op") == "cannot_satisfy":
            out[event.document_id].append(
                {
                    "source": "cannot_satisfy",
                    "caught_by": BUILD if detail.get("role") == BUILD else TEST,
                    "summary": f"{detail.get('target')}: {detail.get('reason', '')}",
                    "at": _at(event.created_at),
                    "by": event.actor,
                }
            )

    sent_back = await session.execute(
        select(
            Task.spec_document_id, Task.title, TaskTransition.created_at, TaskTransition.actor_agent
        )
        .join(Task, Task.id == TaskTransition.task_id)
        .where(
            Task.spec_document_id.in_(list(changes)), TaskTransition.to_status == "revision_needed"
        )
        .order_by(TaskTransition.created_at, TaskTransition.sequence)
    )
    for document_id, title, at, agent in sent_back:
        out[document_id].append(
            {
                "source": "review",
                "caught_by": REVIEW,
                "summary": f"{title}: sent back",
                "at": _at(at),
                "by": agent or "operator",
            }
        )

    for document_id in changes:
        result = await spec_reconcile.latest(session, document_id)
        if result is None:
            continue
        for gap in (result.detail or {}).get("gaps") or []:
            if gap.get("class") in spec_reconcile.DEFECT_CLASSES:
                out[document_id].append(
                    {
                        "source": "reconcile",
                        "caught_by": RECONCILE,
                        "summary": f"{gap['class']}: {gap.get('summary', '')}",
                        "at": _at(result.created_at),
                        "by": result.actor,
                    }
                )

    for defects in out.values():
        defects.sort(key=lambda defect: defect.get("at") or "")
    return out


def by_step(defects: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for defect in defects:
        step = defect.get("caught_by") or "unknown"
        counts[step] = counts.get(step, 0) + 1
    return counts
