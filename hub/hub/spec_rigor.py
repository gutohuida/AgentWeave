"""What happens to work that ignores a document, and who is allowed to change it.

**An agent cannot touch rigor.** Not promote, not demote — and demotion is the
dangerous direction. If an agent blocked by a gate can lower the document, the
gate is decorative: a speed bump the blocked party removes. Promotion is refused
for a quieter reason: an agent that could raise rigor could block another agent's
work, which is a decision about how the project is run.

Enforced the way approval is: **there is no argument and no route**, not an
instruction telling agents not to. That distinction is the entire lesson of the
charter-enforced gate this replaces — a charter instructing an agent to enforce a
gate on itself.

Two more rules earn their place:

**Promotion refuses a broken document.** Rigor is a claim about enforceability,
and a document that cannot be read cannot be enforced. Promoting one creates a
gate whose failures are diagnostics rather than judgements.

**Demotion keeps everything.** Links, revisions, evidence and reviews all
survive. Lowering rigor to unblock something urgent and raising it again must not
destroy the record, or the demotion becomes a laundering step.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import DEFAULT_SPEC_RIGOR, SPEC_RIGORS, SpecDocument, SpecRigorEvent
from .spec_lifecycle import Actor, digest
from .utils import short_id

SKETCH = "sketch"
CONTRACT = "contract"
GATE = "gate"

# Ordered, so "is this a promotion?" is a comparison rather than a table of pairs.
ORDER = {SKETCH: 0, CONTRACT: 1, GATE: 2}

# The metadata name the document itself carries, readable by anyone opening the file.
RIGOR_META = "aw-spec-rigor"


class RigorRefusedError(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """A rigor change that may not happen, with the reason and what would fix it."""

    def __init__(self, message: str, *, code: str, blocking: Optional[List[str]] = None) -> None:
        self.code = code
        self.blocking = blocking or []
        super().__init__(message)


def is_promotion(from_rigor: str, to_rigor: str) -> bool:
    return ORDER.get(to_rigor, 0) > ORDER.get(from_rigor, 0)


async def set_rigor(
    session: AsyncSession,
    document: SpecDocument,
    to_rigor: str,
    *,
    actor: Actor,
    reason: str = "",
    expected_digest: Optional[str] = None,
    content: Optional[str] = None,
) -> SpecRigorEvent:
    """Change a document's rigor, or refuse and say why.

    `expected_digest` is compare-and-swap against the document's current content:
    a rigor change must not silently land on a document somebody edited
    underneath it, because what was promoted would then not be what was read.
    Callers that pass nothing get no such protection, which is why the operator
    route always passes it.
    """
    if to_rigor not in SPEC_RIGORS:
        raise RigorRefusedError(
            f"rigor must be one of {', '.join(SPEC_RIGORS)}", code="unknown_rigor"
        )

    # Checked here as well as at the route. A rule enforced in one place is a rule that survives
    # exactly as long as nobody adds a second caller — the same reasoning as `spec_lifecycle.transition`.
    if actor.kind != "operator":
        raise RigorRefusedError(
            "how strictly a document is enforced is the operator's decision. An agent cannot "
            "raise it and, more to the point, cannot lower one that is blocking it.",
            code="rigor_is_the_operators",
        )

    current = document.rigor or DEFAULT_SPEC_RIGOR
    if (
        expected_digest is not None
        and document.content_digest is not None
        and expected_digest != document.content_digest
    ):
        raise RigorRefusedError(
            "the document changed since you read it; re-read it and decide again",
            code="stale_digest",
        )

    if current == to_rigor:
        raise RigorRefusedError(f"the document is already {to_rigor}", code="rigor_unchanged")

    if is_promotion(current, to_rigor):
        blocking = promotion_blockers(content)
        if blocking:
            raise RigorRefusedError(
                "this document cannot be enforced as it stands: " + "; ".join(blocking),
                code="document_not_enforceable",
                blocking=blocking,
            )

    document.rigor = to_rigor
    event = SpecRigorEvent(
        id=f"rig-{short_id()}",
        project_id=document.project_id,
        document_id=document.id,
        from_rigor=current,
        to_rigor=to_rigor,
        actor_kind=actor.kind,
        actor=actor.name or "",
        reason=reason,
        digest=document.content_digest,
    )
    session.add(event)
    return event


def promotion_blockers(content: Optional[str]) -> List[str]:
    """What stops this document being enforceable, in words the operator can act on.

    Demotion never consults this: a document that has stopped parsing is exactly
    the one an operator most needs to be able to stop enforcing.
    """
    from .spec_identity import read_identity
    from .spec_payload import PayloadError, extract_payload, validate_payload

    if content is None:
        return ["the document has no content the Hub can read"]

    stored = extract_payload(content)
    if stored is None:
        return ["the document carries no payload; it was not written by the Hub"]

    try:
        payload = validate_payload(stored)
    except PayloadError as exc:
        return [f"the document does not parse ({exc})"]

    blockers: List[str] = []
    identifiers, _ = read_identity(stored)

    unresolved = [
        requirement.key
        for requirement in payload.requirements
        if requirement.key not in identifiers
    ]
    if unresolved:
        blockers.append(
            "these requirements hold no identifier yet: " + ", ".join(sorted(unresolved))
        )

    seen: Dict[str, int] = {}
    for identifier in identifiers.values():
        seen[identifier] = seen.get(identifier, 0) + 1
    duplicated = sorted(name for name, count in seen.items() if count > 1)
    if duplicated:
        blockers.append("these identifiers are used more than once: " + ", ".join(duplicated))

    if not payload.requirements:
        blockers.append("the document states no requirements, so there is nothing to enforce")

    return blockers


async def history_for(session: AsyncSession, document_id: str) -> List[SpecRigorEvent]:
    result = await session.execute(
        select(SpecRigorEvent)
        .where(SpecRigorEvent.document_id == document_id)
        .order_by(SpecRigorEvent.created_at, SpecRigorEvent.id)
    )
    return list(result.scalars().all())


@dataclass(frozen=True)
class PolicySnapshot:
    """What governed one decision, reduced to something comparable later."""

    entries: List[Dict[str, Any]]

    @property
    def digest(self) -> str:
        return digest(json.dumps(sorted_entries(self.entries), sort_keys=True))


def sorted_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(entries, key=lambda entry: (entry.get("identifier", ""), entry.get("state", "")))


def policy_digest(entries: List[Dict[str, Any]]) -> str:
    """A stable digest of the rigor and coverage that governed a transition."""
    return hashlib.sha256(
        json.dumps(sorted_entries(entries), sort_keys=True).encode("utf-8")
    ).hexdigest()
