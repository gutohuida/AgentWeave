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


# ---------------------------------------------------------------------------------------------
# What each step asks of the agent (FR-3, FR-4, FR-7, FR-8). One duty per step, each opening with
# its marker (D4) so a test can prove a briefing holds one step and not another. Short on purpose:
# instruction adherence falls as instructions grow, and a turn is told only its own step.
# ---------------------------------------------------------------------------------------------


def marker(step: str) -> str:
    return f"[step: {step}]"


#: Appended to every step's duty but delivery's: the agent proposes advancing, the operator decides
#: (FR-4).
ASK_TO_ADVANCE = (
    "- **When this step's output is written into the document, ask before moving on.** Call "
    "`ask_user` with one question and three options: **Continue here**, **Continue in a fresh "
    "conversation**, **Stop here**. On **either** continue, call `advance_spec_step(path)` before "
    "anything else: it records the move, tells you what this step left empty, and returns the next "
    "step's instructions. A fresh conversation needs the move too, or it starts at this step again. "
    "Then, on continue here, follow those instructions in this turn; on a fresh conversation, end "
    "your turn. On stop, end your turn without advancing. Never advance without asking."
)

_ONE_QUESTION = (
    "Ask the operator **one question per `ask_user` call**, offering choices where you can; never "
    "put several questions in one call, though the tool accepts up to four. Write only this step's "
    "part of the document; later steps write the rest."
)

_REQUIREMENTS = (
    "- Write the requirements with `submit_spec_document`: each a single testable statement with "
    "its modal (MUST, SHOULD, MAY), and a rationale where the reason is not obvious. Ground each in "
    "what the code does today. A slice is about a dozen requirements or fewer."
)

_ACCEPTANCE = (
    "- Agree with the operator, for **every MUST requirement**, at least one acceptance criterion: "
    "`given`, `when`, `then`, plus `how_to_check` (the command, test, drive step or manual action "
    "that shows it) and `checked_by`: `agent` when an agent can check it unaided, `operator` when "
    "only the operator can. Write them as `acceptance_criteria` with `submit_spec_document`.\n"
    "- Name the **acceptance drive**: the one end-to-end check that fails while the behaviour cannot "
    "fire for real, and passes only when it can. Record it as a criterion."
)

STEP_DUTIES: Dict[str, str] = {
    INTAKE: (
        f"{marker(INTAKE)} **Intake: understand the request and size the work.** Do not implement "
        "anything.\n"
        "- Read the code the request touches before asking anything you could look up. "
        + _ONE_QUESTION
        + "\n"
        "- Settle the problem, who it affects, and what is out of scope. Write them as `problem` "
        "and `scope` (`in_scope`, `non_goals`) with `submit_spec_document`.\n"
        "- Size the work: **fix** (a defect with a repro, or a change you can say in one sentence), "
        "**small** (one demonstrable outcome, a few requirements), or **large** (several outcomes, "
        "a migration, security, or a contract other parts rely on). Larger than one demonstrable "
        "outcome is a `roadmap` plus the first slice's change document instead.\n"
        "- Ask the operator to confirm the size with `ask_user`: one question, the options `fix`, "
        "`small` and `large`, your recommendation first with its reason in the description. Record "
        "their answer with `set_spec_size(path, size, reason)`."
    ),
    REQUIREMENTS: (
        f"{marker(REQUIREMENTS)} **Requirements: say what must be true.** Do not implement "
        "anything.\n" + _REQUIREMENTS + "\n- " + _ONE_QUESTION
    ),
    ACCEPTANCE: (
        f"{marker(ACCEPTANCE)} **Acceptance: agree how each requirement is shown to hold.** This is "
        "the step that most decides whether the work can be trusted; take care with it.\n"
        + _ACCEPTANCE
        + "\n- "
        + _ONE_QUESTION
    ),
    REQUIREMENTS_AND_ACCEPTANCE: (
        f"{marker(REQUIREMENTS_AND_ACCEPTANCE)} **Requirements and acceptance: what must be true, "
        "and how each is shown.** Do not implement anything.\n"
        + _REQUIREMENTS
        + "\n"
        + _ACCEPTANCE
        + "\n- "
        + _ONE_QUESTION
    ),
    APPROACH: (
        f"{marker(APPROACH)} **Approach: decide how it will be built.** Write short decision records "
        "into `design`: each decision, the alternative rejected, and why. Name any hazard (a "
        "migration, live data, security) and its rollback. Do not implement anything."
    ),
    TASKS: (
        f"{marker(TASKS)} **Tasks: split the work.** Write `tasks` with `submit_spec_document`.\n"
        "- **Task 1 writes the acceptance drive and records it failing** on today's code; the other "
        "tasks depend on it. A fix's one task carries its own failing check.\n"
        "- A test and its fix are one task, so every task leaves the project's checks green.\n"
        "- For each task list in `files` the paths it will edit, and chain any two tasks that share "
        "a path with `depends_on`. Link each task to the requirements it serves.\n"
        "- Set a task's `reviewer` only where it differs from `delivery.reviewer`."
    ),
    DELIVERY: (
        f"{marker(DELIVERY)} **Delivery: say how it will be built.** Recommend a flow when the work "
        "splits into tasks: a flow starts every task whose prerequisites are met, has finished work "
        "reviewed when there is another agent, and can stop when its queue empties. If the "
        "operator wants one, ask which agent works it, who reviews, when it stops and how often it "
        "fires (every 5 minutes unless they say otherwise). Record the answer as `delivery`, and "
        "include `delivery` in every later submission. 'No flow' is a valid answer. The document is "
        "then ready for the operator to propose."
    ),
}


def duty(step: Optional[str]) -> str:
    """The step's instructions with the ask-to-advance protocol, or "" for an unknown step."""
    text = STEP_DUTIES.get(step or "")
    if not text:
        return ""
    return text if step == DELIVERY else text + "\n" + ASK_TO_ADVANCE


def journey_line(size: Optional[str], step: Optional[str]) -> str:
    """One line naming the journey and the current step (FR-3)."""
    steps = [f"**{s}**" if s == step else s for s in journey(size)]
    sized = f"size {size}" if size else "not sized yet, so every step"
    return f"- Journey ({sized}): " + " → ".join(steps) + f". You are at **{step}**."


def missing(step: Optional[str], payload: Optional[Dict], size: Optional[str]) -> List[str]:
    """What `step` was meant to write and the document still lacks. Reported, never enforced (D3)."""
    payload = payload or {}
    scope = payload.get("scope") or {}
    requirements = [r for r in payload.get("requirements") or [] if isinstance(r, dict)]
    criteria = [c for c in payload.get("acceptance_criteria") or [] if isinstance(c, dict)]
    gaps: List[str] = []
    if step == INTAKE:
        if not payload.get("problem"):
            gaps.append("problem")
        if not scope.get("non_goals"):
            gaps.append("scope.non_goals")
        if size is None:
            gaps.append("size (set_spec_size)")
    if step in (REQUIREMENTS, REQUIREMENTS_AND_ACCEPTANCE) and not requirements:
        gaps.append("requirements")
    if step in (ACCEPTANCE, REQUIREMENTS_AND_ACCEPTANCE):
        covered = {c.get("requirement") for c in criteria}
        for requirement in requirements:
            if (
                requirement.get("modal") in ("MUST", "SHALL")
                and requirement.get("key") not in covered
            ):
                gaps.append(f"a criterion for {requirement.get('key')}")
        for criterion in criteria:
            for field in ("how_to_check", "checked_by"):
                if not criterion.get(field):
                    gaps.append(f"{criterion.get('key')}.{field}")
    if step == APPROACH and not payload.get("design"):
        gaps.append("design")
    if step == TASKS and not payload.get("tasks"):
        gaps.append("tasks")
    if step == DELIVERY and not payload.get("delivery"):
        gaps.append("delivery")
    return gaps
