"""Where a change document's authoring stands: its journey step and its size.

A spec is written one step at a time (`a-spec-is-written-one-step-at-a-time`). The step is a column
on the document, not conversation state (D1), so a fresh conversation, another day or another agent
picks it up where it was left. The journey is derived from the size by the one table below (D2), so
a project-defined journey can later replace that table without a second migration.

Moving is never refused for a missing output (D3): warn, never gate. What a step left empty is
reported by the agent's advance tool and is the approval warnings' input.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import SpecDocument
from .spec_lifecycle import INTAKE_STEP, Actor, record_event

INTAKE = INTAKE_STEP
REQUIREMENTS = "requirements"
ACCEPTANCE = "acceptance"
REQUIREMENTS_AND_ACCEPTANCE = "requirements-and-acceptance"
APPROACH = "approach"
TASKS = "tasks"
DELIVERY = "delivery"

#: Every step, in the order any journey visits them. A step one journey lacks still has a place
#: here, which is how `next_step` moves forward from a step the size no longer holds.
STEP_ORDER = (
    INTAKE,
    REQUIREMENTS,
    REQUIREMENTS_AND_ACCEPTANCE,
    ACCEPTANCE,
    APPROACH,
    TASKS,
    DELIVERY,
)

SIZES = ("fix", "small", "large")

#: The journey by size (FR-2). No size yet is briefed as large (FR-12): ceremony is dropped by a
#: decision, never by default.
JOURNEYS: Dict[Optional[str], List[str]] = {
    None: [INTAKE, REQUIREMENTS, ACCEPTANCE, APPROACH, TASKS, DELIVERY],
    "large": [INTAKE, REQUIREMENTS, ACCEPTANCE, APPROACH, TASKS, DELIVERY],
    "small": [INTAKE, REQUIREMENTS_AND_ACCEPTANCE, TASKS, DELIVERY],
    "fix": [INTAKE, TASKS, DELIVERY],
}


class JourneyError(ValueError):
    """A step or size that does not exist, or a document that has no journey."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


def journey(size: Optional[str]) -> List[str]:
    return list(JOURNEYS[size if size in JOURNEYS else None])


def has_journey(document: SpecDocument) -> bool:
    """Only a change document is authored step by step; a roadmap keeps today's duty."""
    return document.kind == "change-spec"


def next_step(size: Optional[str], step: Optional[str]) -> Optional[str]:
    """The step after `step` on this size's journey, or None at its end.

    A step the journey does not hold (the size changed under it) moves to the journey's first step
    that comes after it in `STEP_ORDER` — forward, never back.
    """
    steps = journey(size)
    if step in steps:
        index = steps.index(step)
        return steps[index + 1] if index + 1 < len(steps) else None
    place = STEP_ORDER.index(step) if step in STEP_ORDER else -1
    return next((s for s in steps if STEP_ORDER.index(s) > place), None)


def _require_journey(document: SpecDocument) -> None:
    if not has_journey(document):
        raise JourneyError(
            f"a {document.kind} document has no journey; only a change document is written "
            "step by step",
            code="no_journey",
        )


async def set_step(
    session: AsyncSession, document: SpecDocument, step: str, *, actor: Actor
) -> Dict[str, Optional[str]]:
    """Move the document to `step`, recorded with the actor's run. Any step, back or forward."""
    _require_journey(document)
    if step not in STEP_ORDER:
        raise JourneyError(
            f"unknown step {step!r}; this document's journey is "
            + ", ".join(journey(document.size)),
            code="unknown_step",
        )
    move = {"from": document.step, "to": step}
    document.step = step
    await record_event(session, document, kind="journey", actor=actor, detail={"step": move})
    return move


async def set_size(
    session: AsyncSession,
    document: SpecDocument,
    size: Optional[str],
    *,
    actor: Actor,
    reason: str = "",
) -> Dict[str, Optional[str]]:
    """Record the work's size and why. The step stays where it is; the journey around it changes."""
    _require_journey(document)
    if size is not None and size not in SIZES:
        raise JourneyError(
            f"unknown size {size!r}; a size is one of: {', '.join(SIZES)}", code="unknown_size"
        )
    move = {"from": document.size, "to": size}
    document.size = size
    await record_event(
        session, document, kind="journey", actor=actor, detail={"size": move, "reason": reason}
    )
    return move
