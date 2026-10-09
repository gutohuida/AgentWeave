"""Where a change document's authoring stands: its journey step and its size.

A spec is written one step at a time (`a-spec-is-written-one-step-at-a-time`). The step is a column
on the document, not conversation state (D1), so a fresh conversation, another day or another agent
picks it up where it was left. The journey is derived from the size by the one table below (D2), and
a project replaces that table with its own `spec/journey.json` (`a-project-orders-its-own-spec-steps`):
the built-ins in their order, custom steps anywhere among them, an instruction appended to any step.

Moving is never refused for a missing output (D3): warn, never gate. What a step left empty is
reported by the agent's advance tool and is the approval warnings' input.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from . import project_workspace
from .db.models import SpecDocument
from .spec_lifecycle import INTAKE_STEP, Actor, record_event
from .spec_manifest import JOURNEY_PATH

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


# ---------------------------------------------------------------------------------------------
# The project's steps (`spec/journey.json`). The built-ins are named by key and fixed in order
# (D1); a custom step sits anywhere and joins the sizes it lists, small and large when it lists none
# (D2). A broken file is reported and the built-in table is used meanwhile (D4): no turn is refused.
# ---------------------------------------------------------------------------------------------

JOURNEY_FILE = JOURNEY_PATH
#: Per instruction text, above today's longest duty (1,805 characters with its advance protocol).
TEXT_CAP = 2000
#: The document's step column is String(48).
KEY_MAX = 48
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
#: A custom step that lists no sizes; an unsized document is briefed as large.
DEFAULT_CUSTOM_SIZES = ("small", "large")
INVALID = "journey_file_invalid"


@dataclass(frozen=True)
class Step:
    """One entry of a project's steps: a built-in by key, or a custom step with its Markdown."""

    key: str
    title: str = ""
    instructions: str = ""
    sizes: Optional[Tuple[str, ...]] = None
    append: str = ""

    @property
    def custom(self) -> bool:
        return self.key not in STEP_ORDER

    def in_journey(self, size: Optional[str]) -> bool:
        if not self.custom:
            return self.key in JOURNEYS[size if size in JOURNEYS else None]
        return (size if size in SIZES else "large") in (self.sizes or DEFAULT_CUSTOM_SIZES)

    def to_entry(self) -> Dict[str, Any]:
        """The step as the file and the routes carry it: only what it holds, in a fixed key order."""
        entry: Dict[str, Any] = {"key": self.key}
        if self.custom:
            entry["title"] = self.title
            entry["instructions"] = self.instructions
            if self.sizes:
                entry["sizes"] = list(self.sizes)
        if self.append:
            entry["append"] = self.append
        return entry


@dataclass(frozen=True)
class ProjectSteps:
    """A project's steps in file order, and what was wrong with its file, if anything."""

    steps: Tuple[Step, ...]
    diagnostics: Tuple[Dict[str, str], ...] = ()

    def order(self) -> List[str]:
        return [step.key for step in self.steps]

    def get(self, key: Optional[str]) -> Optional[Step]:
        return next((step for step in self.steps if step.key == key), None)


BUILT_IN = ProjectSteps(tuple(Step(key) for key in STEP_ORDER))


def _text(entry: Dict[str, Any], field: str, where: str, problems: List[str]) -> str:
    value = entry.get(field, "")
    if not isinstance(value, str):
        problems.append(f"{where}: {field} must be text")
        return ""
    if len(value) > TEXT_CAP:
        problems.append(f"{where}: {field} is {len(value):,} characters; the limit is {TEXT_CAP:,}")
    return value


def parse(document: Any) -> Tuple[ProjectSteps, List[str]]:
    """The steps a journey document names, and every rule it breaks (FR-1, FR-2, FR-5, FR-7).

    With any problem the steps returned are the built-in table: a caller reports the problems and
    carries on (D4), or refuses to save them.
    """
    problems: List[str] = []
    entries = document.get("steps") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return BUILT_IN, [f'{JOURNEY_FILE} must be an object with a "steps" list']
    steps: List[Step] = []
    seen: set = set()
    for index, entry in enumerate(entries):
        key = entry.get("key") if isinstance(entry, dict) else None
        if not isinstance(key, str) or not key:
            problems.append(f"steps[{index}] needs a key")
            continue
        where = f"step {key!r}"
        if key in seen:
            problems.append(f"{where}: duplicate key")
        seen.add(key)
        append = _text(entry, "append", where, problems)
        if "title" not in entry and "instructions" not in entry:
            if key not in STEP_ORDER:
                problems.append(
                    f"{where} is not a built-in step ({', '.join(STEP_ORDER)}); a custom step "
                    "needs a title and instructions"
                )
            steps.append(Step(key, append=append))
            continue
        if key in STEP_ORDER:
            problems.append(f"{where} is a built-in step; it cannot carry a title or instructions")
            continue
        if len(key) > KEY_MAX or not _SLUG.match(key):
            problems.append(
                f"{where}: a custom key is a lowercase slug (a-z, 0-9, hyphens) of at most "
                f"{KEY_MAX} characters"
            )
        title = _text(entry, "title", where, problems)
        instructions = _text(entry, "instructions", where, problems)
        if not title.strip() or not instructions.strip():
            problems.append(f"{where}: a custom step needs a title and instructions")
        sizes = entry.get("sizes")
        if sizes is not None and (
            not isinstance(sizes, list) or any(size not in SIZES for size in sizes)
        ):
            problems.append(f"{where}: sizes {sizes!r} must be a list of {', '.join(SIZES)}")
            sizes = None
        steps.append(Step(key, title, instructions, tuple(sizes) if sizes else None, append))
    built_ins = [step.key for step in steps if not step.custom]
    if built_ins != list(STEP_ORDER):
        problems.append(
            "the built-in steps must all be present, in their built-in order: "
            + ", ".join(STEP_ORDER)
        )
    if problems:
        return BUILT_IN, problems
    return ProjectSteps(tuple(steps)), []


def load(workspace: project_workspace.ProjectWorkspace) -> ProjectSteps:
    """The project's steps from `spec/journey.json`; the built-in table with no file (FR-1) or,
    with its diagnostics, for a file that does not parse or breaks a rule (FR-7)."""
    try:
        file = workspace.resolve_relative(JOURNEY_FILE)
        if not file.is_file():
            return BUILT_IN
        document = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError, project_workspace.ProjectPathError) as exc:
        problems = [f"{JOURNEY_FILE} cannot be read or does not parse: {exc}"]
    else:
        steps, problems = parse(document)
        if not problems:
            return steps
    return ProjectSteps(
        BUILT_IN.steps, tuple({"code": INVALID, "message": message} for message in problems)
    )


def dump(steps: ProjectSteps) -> str:
    """The file's text for these steps: stable key order, indented, LF, one trailing newline, so
    saving the same journey twice leaves identical bytes (FR-5)."""
    document = {"steps": [step.to_entry() for step in steps.steps]}
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def save(workspace: project_workspace.ProjectWorkspace, document: Any) -> ProjectSteps:
    """Validate `document` and write it to `spec/journey.json`; nothing is written when it breaks a
    rule (FR-5). Atomic: written beside the file and moved over it, so a failed write leaves the
    saved journey as it was. Raises `JourneyError` (code `journey_invalid`) naming every problem,
    and `OSError` when the file cannot be written."""
    steps, problems = parse(document)
    if problems:
        raise JourneyError("; ".join(problems), code="journey_invalid")
    target = workspace.resolve_relative(JOURNEY_FILE)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        temporary.write_text(dump(steps), encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise
    return steps


async def project_steps(session: AsyncSession, project_id: str) -> ProjectSteps:
    """The project's steps, or the built-in table when its directory is unavailable."""
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError:
        return BUILT_IN
    return load(workspace)


def journey(size: Optional[str], steps: Optional[ProjectSteps] = None) -> List[str]:
    """The steps a document of this size visits, in the project's order (FR-2)."""
    return [step.key for step in (steps or BUILT_IN).steps if step.in_journey(size)]


def has_journey(document: SpecDocument) -> bool:
    """Only a change document is authored step by step; a roadmap keeps today's duty."""
    return document.kind == "change-spec"


def next_step(
    size: Optional[str], step: Optional[str], steps: Optional[ProjectSteps] = None
) -> Optional[str]:
    """The step after `step` on this size's journey, or None at its end.

    A step the journey does not hold (the size changed under it) moves to the journey's first step
    that comes after it in the project's order — forward, never back. A step the project no longer
    has at all is refused (FR-8): there is no forward from it, so the operator names where to resume.
    """
    steps = steps or BUILT_IN
    path = journey(size, steps)
    if step in path:
        index = path.index(step)
        return path[index + 1] if index + 1 < len(path) else None
    order = steps.order()
    if step is not None and step not in order:
        raise JourneyError(
            f"the step {step!r} was removed from this project's journey; name the step to resume "
            "at with `to`, one of: " + ", ".join(path),
            code="step_not_in_journey",
        )
    place = order.index(step) if step is not None else -1
    return next((s for s in path if order.index(s) > place), None)


def skipped(
    size: Optional[str], step: Optional[str], steps: Optional[ProjectSteps] = None
) -> List[str]:
    """The steps of this size's journey after `step`, which a document there never reached.

    A step the journey does not hold counts from its place in the project's order, as `next_step`
    does; one the project no longer has at all leaves the whole journey ahead. No step, nothing.
    """
    if step is None:
        return []
    steps = steps or BUILT_IN
    path = journey(size, steps)
    if step in path:
        return path[path.index(step) + 1 :]
    order = steps.order()
    if step not in order:
        return path
    return [s for s in path if order.index(s) > order.index(step)]


def _require_journey(document: SpecDocument) -> None:
    if not has_journey(document):
        raise JourneyError(
            f"a {document.kind} document has no journey; only a change document is written "
            "step by step",
            code="no_journey",
        )


async def set_step(
    session: AsyncSession,
    document: SpecDocument,
    step: str,
    *,
    actor: Actor,
    steps: Optional[ProjectSteps] = None,
) -> Dict[str, Optional[str]]:
    """Move the document to `step`, recorded with the actor's run. Any of the project's steps, back
    or forward."""
    _require_journey(document)
    if step not in (steps or BUILT_IN).order():
        raise JourneyError(
            f"unknown step {step!r}; this document's journey is "
            + ", ".join(journey(document.size, steps)),
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


#: A custom step's output is named in its own Markdown (D3); this line covers Markdown that does not.
WRITE_WHERE = (
    "- Write this step's result where the instructions above say. When they name no place, choose "
    "a section of the document or a file, and tell the operator where you wrote it."
)


def duty(step: Optional[str], steps: Optional[ProjectSteps] = None) -> str:
    """The step's instructions, the project's appended instruction for that step and no other
    (FR-4), and the ask-to-advance protocol; "" for a step the project does not have."""
    entry = (steps or BUILT_IN).get(step)
    if entry is None:
        return ""
    if entry.custom:
        text = f"{marker(entry.key)} **{entry.title}.**\n{entry.instructions}\n{WRITE_WHERE}"
    else:
        text = STEP_DUTIES[entry.key]
    if entry.append:
        text += "\n- **This project adds to this step:** " + entry.append
    return text if step == DELIVERY else text + "\n" + ASK_TO_ADVANCE


def removed(step: str, size: Optional[str], steps: Optional[ProjectSteps] = None) -> str:
    """The briefing for a document whose step the project removed (FR-8)."""
    return (
        f"{marker(step)} **The step {step!r} was removed from this project's journey.** Do not "
        "continue it. Call `ask_user` with one question: which step to resume at, offering this "
        f"journey's steps ({', '.join(journey(size, steps))}). Then call "
        "`advance_spec_step(path, to=<their choice>)` and follow the instructions it returns."
    )


def journey_line(
    size: Optional[str], step: Optional[str], steps: Optional[ProjectSteps] = None
) -> str:
    """One line naming the journey and the current step (FR-3)."""
    named = [f"**{s}**" if s == step else s for s in journey(size, steps)]
    sized = f"size {size}" if size else "not sized yet, so every step"
    return f"- Journey ({sized}): " + " → ".join(named) + f". You are at **{step}**."


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
