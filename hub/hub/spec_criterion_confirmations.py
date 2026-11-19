"""Acceptance criteria an agent has checked against the current code
(`existing-behaviour-is-caught-before-the-build` D1-D4, D6).

A confirmation says one criterion was checked and is either new behaviour (its drive check must
fail on the pre-build code) or a guard (behaviour the code already has). It is a row beside the
document, never part of its payload (D1), and counts only while the criterion's digest is the one
it was taken against (D2), so a reworded criterion, or one whose guard flag changed, is confirmed
again. Any agent may confirm while the document is exploring; nobody may once it is approved, and
the operator never does (D3).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import spec_completeness, spec_lifecycle
from .db.models import SpecCriterionConfirmation, SpecDocument, SpecRequirement
from .spec_digest import criterion_digest, digest_of_criterion
from .spec_payload import SpecPayload
from .utils import short_id

NEW = "new"
GUARD = "guard"
KINDS = (NEW, GUARD)


class ConfirmationRefusedError(Exception):
    """A confirmation the Hub will not record; nothing is written (all or none)."""

    def __init__(self, message: str, *, code: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


async def rows_for(
    session: AsyncSession, document: SpecDocument
) -> Dict[str, SpecCriterionConfirmation]:
    """The document's confirmations by criterion key, current or not."""
    found = (
        (
            await session.execute(
                select(SpecCriterionConfirmation).where(
                    SpecCriterionConfirmation.document_id == document.id
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.criterion_key: row for row in found}


async def digests(session: AsyncSession, document: SpecDocument) -> Dict[str, str]:
    """`{criterion key: digest it was confirmed against}`, what `spec_completeness.check` takes."""
    return {key: row.criterion_digest for key, row in (await rows_for(session, document)).items()}


def _stamp(row: SpecCriterionConfirmation) -> Optional[str]:
    return row.created_at.isoformat() if row.created_at else None


def view(row: Optional[SpecCriterionConfirmation], criterion: Mapping[str, Any]) -> Any:
    """A read's `confirmation` for one stored criterion (D6): `{kind, by, at, current}` or None.

    `criterion` is the criterion as the stored payload holds it, a plain dict.
    """
    if row is None:
        return None
    digest = criterion_digest(
        criterion.get("requirement"),
        criterion.get("given"),
        criterion.get("when"),
        criterion.get("then"),
        criterion.get("guard"),
    )
    return {
        "kind": row.kind,
        "by": row.actor,
        "at": _stamp(row),
        "current": row.criterion_digest == digest,
    }


async def confirm(
    session: AsyncSession,
    document: SpecDocument,
    payload: SpecPayload,
    confirmations: List[Dict[str, Any]],
    *,
    actor: str,
    run_id: Optional[str],
) -> Dict[str, Any]:
    """Record `confirmations` ([{criterion, kind}]) for `document` as `actor`, all or none (D4).

    Refused, writing nothing: a document that is not exploring (409 `document_not_exploring`), a
    key the document has no criterion for (422 `criterion_unknown`), a kind other than new or
    guard (422 `confirmation_kind_unknown`), and a kind that disagrees with the criterion's guard
    flag (422 `confirmation_kind_mismatch`). Confirming a criterion again replaces its row.

    Answers `{path, confirmed: [{criterion, kind, by, at}], unconfirmed: [key, ...]}`, where
    `confirmed` lists every current confirmation of the document, not only these.
    """
    if document.phase != spec_lifecycle.EXPLORING:
        raise ConfirmationRefusedError(
            f"the document is {document.phase}, so its criteria cannot be confirmed; the operator "
            "reopens it to change a confirmation",
            code="document_not_exploring",
            status=409,
        )
    if not confirmations:
        raise ConfirmationRefusedError(
            "name at least one criterion to confirm", code="confirmations_empty"
        )
    criteria = {criterion.key: criterion for criterion in payload.acceptance_criteria}
    for entry in confirmations:
        key, kind = entry.get("criterion"), entry.get("kind")
        criterion = criteria.get(key)  # type: ignore[arg-type]
        if criterion is None:
            raise ConfirmationRefusedError(
                f"the document has no acceptance criterion {key!r} (its criteria: "
                f"{', '.join(criteria) or 'none'})",
                code="criterion_unknown",
            )
        if kind not in KINDS:
            raise ConfirmationRefusedError(
                f"{key!r}: kind must be 'new' or 'guard', not {kind!r}",
                code="confirmation_kind_unknown",
            )
        if (kind == GUARD) != (criterion.guard is True):
            raise ConfirmationRefusedError(
                f"{key!r} is confirmed as {kind!r} but its guard flag is "
                f"{bool(criterion.guard)!s}: "
                + (
                    "mark it guard: true and save before confirming it as a guard"
                    if kind == GUARD
                    else "a guard is confirmed as 'guard'; to make it new behaviour, clear its "
                    "guard flag and save first"
                ),
                code="confirmation_kind_mismatch",
            )

    rows = await rows_for(session, document)
    for entry in confirmations:
        key, kind = entry["criterion"], entry["kind"]
        digest = digest_of_criterion(criteria[key])
        row = rows.get(key)
        if row is None:
            row = SpecCriterionConfirmation(
                id=f"spcfm-{short_id()}",
                project_id=document.project_id,
                document_id=document.id,
                criterion_key=key,
            )
            session.add(row)
            rows[key] = row
        row.kind = kind
        row.criterion_digest = digest
        row.actor = actor
        row.run_id = run_id
        row.created_at = datetime.now(timezone.utc)
    await session.flush()

    current = {key: row.criterion_digest for key, row in rows.items()}
    unconfirmed = spec_completeness.unconfirmed_keys(payload, current)
    return {
        "path": document.path,
        "confirmed": [
            {
                "criterion": criterion.key,
                "kind": rows[criterion.key].kind,
                "by": rows[criterion.key].actor,
                "at": _stamp(rows[criterion.key]),
            }
            for criterion in payload.acceptance_criteria
            if criterion.key not in unconfirmed
        ],
        "unconfirmed": unconfirmed,
    }


async def guards(
    session: AsyncSession, document: SpecDocument, payload: SpecPayload
) -> List[Dict[str, Any]]:
    """`[{criterion, requirement}]`: each criterion marked a guard, with its requirement's minted
    identifier (FR-5, D6), in document order. A requirement not yet indexed gives its key."""
    marked = [criterion for criterion in payload.acceptance_criteria if criterion.guard is True]
    if not marked:
        return []
    identifiers = {
        row.key: row.identifier
        for row in (
            await session.execute(
                select(SpecRequirement).where(SpecRequirement.document_id == document.id)
            )
        ).scalars()
    }
    return [
        {
            "criterion": criterion.key,
            "requirement": identifiers.get(criterion.requirement, criterion.requirement),
        }
        for criterion in marked
    ]
