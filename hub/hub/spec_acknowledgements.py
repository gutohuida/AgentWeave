"""Gaps a document's author or the operator chose to leave, with the reason (FR-3, FR-4, FR-11, FR-12).

`ready-means-the-same-thing-to-the-author-and-the-operator`. An acknowledgement is a row beside the
document, never part of its payload, so a save that replaces the whole payload cannot erase or forge
one. It is keyed by the gap's (code, place): a gap reworded at the same place keeps it, and it is
dropped once the gap is no longer reported (`prune`), so a gap that comes back is open again.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_completeness, spec_lifecycle
from .db.models import SpecDocument, SpecGapAcknowledgement
from .utils import short_id

#: Gaps only the operator may acknowledge: an unreviewed amendment is the operator's own review,
#: and a vault contradiction disputes what the business recorded (FR-12).
OPERATOR_ONLY_CODES = frozenset({"amendments_unreviewed", "vault_warning"})


class AcknowledgementRefusedError(Exception):
    """An acknowledgement the Hub will not record; nothing is written."""

    def __init__(self, message: str, *, code: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


Key = Tuple[str, str]


async def rows_for(
    session: AsyncSession, document: SpecDocument
) -> Dict[Key, SpecGapAcknowledgement]:
    found = (
        (
            await session.execute(
                select(SpecGapAcknowledgement).where(
                    SpecGapAcknowledgement.document_id == document.id
                )
            )
        )
        .scalars()
        .all()
    )
    return {(row.code, row.place): row for row in found}


def entry(finding: Dict[str, Any], row: SpecGapAcknowledgement) -> Dict[str, Any]:
    """A reported gap with the acknowledgement that covers it."""
    return {
        **finding,
        "reason": row.reason,
        "by": row.actor,
        "by_kind": row.actor_kind,
        "at": row.created_at.isoformat() if row.created_at else None,
    }


async def prune(
    session: AsyncSession,
    document: SpecDocument,
    rows: Dict[Key, SpecGapAcknowledgement],
    reported: Iterable[Key],
) -> None:
    """Drop the acknowledgements whose gap is no longer reported (FR-4)."""
    keep: Set[Key] = set(reported)
    gone = [row.id for key, row in rows.items() if key not in keep]
    if gone:
        await session.execute(
            delete(SpecGapAcknowledgement).where(SpecGapAcknowledgement.id.in_(gone))
        )
        for key in [key for key in rows if key not in keep]:
            rows.pop(key)


async def acknowledge(
    session: AsyncSession,
    document: SpecDocument,
    readiness: Any,
    *,
    code: str,
    where: str,
    reason: str,
    actor: spec_lifecycle.Actor,
    authors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Record `actor`'s acknowledgement of the gap (`code`, `where`) that `readiness` reports.

    Refused, writing nothing: no reason, a refusal (nothing passes it), a note (nothing gates on
    it), a gap that is not reported, a gap only the operator may clear, and, for an agent, a
    document it did not write (`authors`).
    """
    reason = (reason or "").strip()
    if not reason:
        raise AcknowledgementRefusedError(
            "an acknowledgement needs a reason: say why this gap is acceptable to leave",
            code="reason_required",
        )
    if actor.kind == "agent":
        if authors is not None and actor.name not in authors:
            raise AcknowledgementRefusedError(
                "only an agent that wrote this document may acknowledge its gaps",
                code="not_the_author",
                status=403,
            )
        if code in OPERATOR_ONLY_CODES:
            raise AcknowledgementRefusedError(
                f"{code} is the operator's to clear: only the operator can acknowledge it, "
                "from Check",
                code="operator_only",
                status=403,
            )
    if code in spec_completeness.REFUSAL_CODES or any(
        f["code"] == code and f["where"] == where for f in readiness.refusals
    ):
        raise AcknowledgementRefusedError(
            f"{code} at {where} is a refusal, which nothing passes; fix it instead",
            code="refusal_not_acknowledgeable",
        )
    if any(f["code"] == code and f["where"] == where for f in readiness.notes):
        raise AcknowledgementRefusedError(
            f"{code} at {where} is a note: it gates nothing, so there is nothing to acknowledge",
            code="note_not_acknowledgeable",
        )
    reported = [*readiness.gaps, *readiness.acknowledged]
    if not any(f["code"] == code and f["where"] == where for f in reported):
        raise AcknowledgementRefusedError(
            f"the document reports no gap {code} at {where}; read the current gaps from the "
            "last save or Check",
            code="gap_not_reported",
            status=404,
        )
    rows = await rows_for(session, document)
    row = rows.get((code, where))
    if row is None:
        row = SpecGapAcknowledgement(
            id=f"spack-{short_id()}",
            document_id=document.id,
            project_id=document.project_id,
            code=code,
            place=where,
        )
        session.add(row)
    row.reason = reason
    row.actor_kind = actor.kind
    row.actor = actor.name or actor.kind
    row.run_id = actor.run_id
    from .db.models import _now

    row.created_at = _now()
    await session.flush()
    return {
        "code": code,
        "where": where,
        "reason": row.reason,
        "by": row.actor,
        "by_kind": row.actor_kind,
        "at": row.created_at.isoformat(),
    }
