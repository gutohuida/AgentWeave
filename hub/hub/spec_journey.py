"""Where a change document's authoring stands: its journey step and its size.

A spec is written one step at a time (`a-spec-is-written-one-step-at-a-time`). The step is a column
on the document, not conversation state (D1), so a fresh conversation, another day or another agent
picks it up where it was left. The journey is derived from the size by the one table below (D2), and
a project replaces that table with its own `spec/journey.json` (`a-project-orders-its-own-spec-steps`):
the built-ins in their order, custom steps anywhere among them, an instruction appended to any step.

Moving is never refused for a missing output (D3): warn, never gate. What a step left empty is
reported by the agent's advance tool and is the approval warnings' input.\n"""

from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from . import hub_writes, project_workspace
from .db.models import SpecDocument
from .spec_lifecycle import INTAKE_STEP, Actor, record_event
from .spec_manifest import JOURNEY_PATH

INTAKE = INTAKE_STEP
REQUIREMENTS = "requirements"
ACCEPTANCE = "acceptance"
REQUIREMENTS_AND_ACCEPTANCE = "requirements-and-acceptance"
APPROACH = "approach"
TASKS = "tasks"
#: The last step: it recommends a build, with a reason for each choice, and the operator decides
#: when they press Build (`exploring-ends-at-an-approved-plan`, FR-10). It was called `delivery`;
#: that name is still read wherever a step is named (`OLD_NAMES`), so a project's
#: `spec/journey.json` written before the rename keeps working, and migration 0149 moved the
#: documents standing at it.
BUILD = "build"

#: Step names a project file, a stored document or a caller may still use, and the step each is now.
OLD_NAMES: Dict[str, str] = {"delivery": BUILD}

#: Every step, in the order any journey visits them. A step one journey lacks still has a place
#: here, which is how `next_step` moves forward from a step the size no longer holds.
STEP_ORDER = (
    INTAKE,
    REQUIREMENTS,
    REQUIREMENTS_AND_ACCEPTANCE,
    ACCEPTANCE,
    APPROACH,
    TASKS,
    BUILD,
)

SIZES = ("fix", "small", "large")

#: The journey by size (FR-2). No size yet is briefed as large (FR-12): ceremony is dropped by a
#: decision, never by default.
JOURNEYS: Dict[Optional[str], List[str]] = {
    None: [INTAKE, REQUIREMENTS, ACCEPTANCE, APPROACH, TASKS, BUILD],
    "large": [INTAKE, REQUIREMENTS, ACCEPTANCE, APPROACH, TASKS, BUILD],
    "small": [INTAKE, REQUIREMENTS_AND_ACCEPTANCE, TASKS, BUILD],
    "fix": [INTAKE, TASKS, BUILD],
}


def current_name(step: Optional[str]) -> Optional[str]:
    """The step's name today: an old name (`OLD_NAMES`) read as the step it became."""
    return OLD_NAMES.get(step, step) if step is not None else None


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
        key = current_name(key)
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
        # A built-in's old name is that built-in (`OLD_NAMES`): a file written before a rename is
        # still valid, and saving it again writes the current name.
        key = OLD_NAMES.get(key, key)
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
    hub_writes.record(workspace.root, JOURNEY_FILE, dump(steps).encode("utf-8"))
    return steps


async def project_steps(session: AsyncSession, project_id: str) -> ProjectSteps:
    """The project's steps, or the built-in table when its directory is unavailable."""
    try:
        workspace = await project_workspace.resolve_project_workspace(session, project_id)
    except project_workspace.ProjectWorkspaceError:
        return BUILT_IN
    return load(workspace)


async def open_roster(session: AsyncSession, project_id: str) -> Roster:
    """The project's open agents with the model each runs, by name."""
    from sqlalchemy import select

    from .db.models import Agent, Runner

    agents = (
        (
            await session.execute(
                select(Agent).where(Agent.project_id == project_id, Agent.lifecycle == "open")
            )
        )
        .scalars()
        .all()
    )
    runners = {
        row.id: row
        for row in (await session.execute(select(Runner).where(Runner.project_id == project_id)))
        .scalars()
        .all()
    }
    return sorted(
        (
            row.name,
            (runners[row.runner_id].model or "") if row.runner_id in runners else "",
        )
        for row in agents
    )


async def open_pools(session: AsyncSession, project_id: str) -> Pools:
    """Every open agent's pool entries, by agent name, default first then in the operator's order."""
    from sqlalchemy import select

    from .db.models import Agent, AgentPoolEntry, Runner

    rows = (
        await session.execute(
            select(Agent.name, AgentPoolEntry, Runner.model)
            .join(AgentPoolEntry, AgentPoolEntry.agent_id == Agent.id)
            .join(Runner, Runner.id == AgentPoolEntry.runner_id)
            .where(Agent.project_id == project_id, Agent.lifecycle == "open")
            .order_by(Agent.name, AgentPoolEntry.position, AgentPoolEntry.created_at)
        )
    ).all()
    pools: Pools = {}
    for name, entry, model in rows:
        pools.setdefault(name, []).append(
            (entry.runner_id, model or "", entry.effort or "", bool(entry.is_default))
        )
    return pools


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
    step = current_name(step)
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
    step = current_name(step)
    path = journey(size, steps)
    if step in path:
        return path[path.index(step) + 1 :]
    order = steps.order()
    if step not in order:
        return path
    return [s for s in path if order.index(s) > order.index(step)]


def _has_requirements(payload: Any) -> bool:
    return bool(payload.requirements) and bool(payload.scope.non_goals)


def _has_acceptance(payload: Any) -> bool:
    criteria = payload.acceptance_criteria
    obliged = [r for r in payload.requirements if r.modal.upper() in ("MUST", "SHALL")]
    covered = {c.requirement for c in criteria}
    return (
        all(r.key in covered for r in obliged)
        and all(c.how_to_check and c.checked_by for c in criteria)
        and bool(criteria or not obliged)
    )


def _has_tasks(payload: Any) -> bool:
    return bool(payload.tasks) and all(
        t.requirements or getattr(t, "from_", None) for t in payload.tasks
    )


#: What each built-in step produces, as a test of the payload (steps-follow-content). A step not
#: here (intake) asks nothing: a document past it has had its problem and scope written.
_OUTPUT: Dict[str, Any] = {
    REQUIREMENTS: _has_requirements,
    ACCEPTANCE: lambda p: _has_requirements(p) and _has_acceptance(p),
    REQUIREMENTS_AND_ACCEPTANCE: lambda p: _has_requirements(p) and _has_acceptance(p),
    APPROACH: lambda p: bool((p.design or "").strip()),
    TASKS: _has_tasks,
    BUILD: lambda p: p.delivery is not None,
}


def step_by_content(
    payload: Any, document: SpecDocument, steps: Optional[ProjectSteps] = None
) -> Optional[str]:
    """The furthest step whose output, and every earlier step's, is in `payload` (FR-13), or None
    when the document should not move.

    Only an exploring change document moves, and only forward. The walk stops at the first built-in
    step whose output is missing and at the first custom step, whose output the Hub cannot read.
    """
    from .spec_lifecycle import EXPLORING

    if not has_journey(document) or document.phase != EXPLORING or document.step is None:
        return None
    reached: Optional[str] = None
    for key in skipped(document.size, document.step, steps):
        test = _OUTPUT.get(key)
        if test is None or not test(payload):
            break
        reached = key
    return reached


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
    step = OLD_NAMES.get(step, step)
    if step not in (steps or BUILT_IN).order():
        raise JourneyError(
            f"unknown step {step!r}; this document's journey is "
            + ", ".join(journey(document.size, steps)),
            code="unknown_step",
        )
    move = {"from": document.step, "to": step}
    document.step = step
    await record_event(session, document, kind="journey", actor=actor, detail={"step": move})
    # Leaving the step that writes the criteria stages the pre-mortem (FR-11, D7); whether its job
    # is on and automatic is judged when it fires, after this move commits.
    from . import pre_mortem

    if pre_mortem.leaves_criteria(
        current_name(move["from"]), step, list((steps or BUILT_IN).order())
    ):
        pre_mortem.fire_after_commit(session, document)
    return move


#: The same work under another journey's name: the small journey joins requirements and acceptance
#: into one step, the large one splits it (F631).
_SAME_WORK: Dict[str, Tuple[str, ...]] = {
    REQUIREMENTS: (REQUIREMENTS_AND_ACCEPTANCE,),
    ACCEPTANCE: (REQUIREMENTS_AND_ACCEPTANCE,),
    REQUIREMENTS_AND_ACCEPTANCE: (REQUIREMENTS, ACCEPTANCE),
}


def step_for_size(
    size: Optional[str], step: Optional[str], steps: Optional[ProjectSteps] = None
) -> Optional[str]:
    """Where a document at `step` stands on this size's journey (F631).

    Its own step when the journey has it; the same work under the journey's name for it (the
    requirements and acceptance steps); otherwise the journey's first step after it in the
    project's order, as `next_step` moves, or the journey's last step when none comes after. A
    step the project no longer has, or no step, is left as it is.
    """
    steps = steps or BUILT_IN
    step = current_name(step)
    path = journey(size, steps)
    order = steps.order()
    if step is None or step in path or step not in order:
        return step
    for same in _SAME_WORK.get(step, ()):
        if same in path:
            return same
    place = order.index(step)
    return next((s for s in path if order.index(s) > place), path[-1] if path else step)


async def set_size(
    session: AsyncSession,
    document: SpecDocument,
    size: Optional[str],
    *,
    actor: Actor,
    reason: str = "",
    steps: Optional[ProjectSteps] = None,
) -> Dict[str, Optional[str]]:
    """Record the work's size and why, moving a step the new journey lacks to where it now stands.

    It used to leave the step where it was, so a document at `requirements` sized small sat at a
    step its journey does not have, and propose warned about a step it would never reach (F631).
    """
    _require_journey(document)
    if size is not None and size not in SIZES:
        raise JourneyError(
            f"unknown size {size!r}; a size is one of: {', '.join(SIZES)}", code="unknown_size"
        )
    move = {"from": document.size, "to": size}
    detail: Dict[str, Any] = {"size": move, "reason": reason}
    document.size = size
    placed = step_for_size(size, document.step, steps)
    if placed != document.step:
        detail["step"] = {"from": document.step, "to": placed}
        document.step = placed
    await record_event(session, document, kind="journey", actor=actor, detail=detail)
    return move


# ---------------------------------------------------------------------------------------------
# What each step asks of the agent (FR-3, FR-4, FR-7, FR-8). One duty per step, each opening with
# its marker (D4) so a test can prove a briefing holds one step and not another. Short on purpose:
# instruction adherence falls as instructions grow, and a turn is told only its own step.
# ---------------------------------------------------------------------------------------------


def marker(step: str) -> str:
    return f"[step: {step}]"


#: Appended to every step's duty but the build step's: the agent moves itself on once the step is
#: written and nothing is waiting on the operator (`agent-advances`, D3). It replaced the
#: ask-to-advance protocol (Continue here / fresh conversation / stop), whose question the operator
#: answered at every step without deciding anything; the step stays on the document, so they can
#: still move it back or open a fresh conversation from the phase bar.
ADVANCE_YOURSELF = (
    "- **When this step's output is written into the document and you have no question for the "
    "operator, call `advance_spec_step(path)` yourself**, in this turn: it records the move, tells "
    "you what this step left empty, and returns the next step's instructions. Follow them in the "
    "same turn, and say in your reply which step you moved to. Do not ask the operator whether to "
    "go on, or where. End your turn waiting for them only when you ask something only they can "
    "decide.\n"
    "- **A save can move the step for you.** When `submit_spec_document` answers with "
    "`step_moved`, the document already holds what the earlier steps produce and the save placed "
    "it at `step_moved.to`. Do not call `advance_spec_step` for that move, which would skip the "
    "step you were placed at: follow `step_moved.instructions` in the same turn, and say in your "
    "reply which step the document is at."
)

#: The one questioning rule every built-in step shares (D4, `few-deep-questions`,
#: `describe-first`, `grounded-questions`, `volunteered-ideas`). It replaced a rule that asked for
#: choices wherever possible, which the operator answered with "yes to all your recommendations".
QUESTIONING = (
    "- **How to ask.** Ask in your reply, then end your turn; the operator answers in the "
    "composer. Ask **at most three questions** per reply, the deepest first. Each question names "
    "the finding that makes it matter: code you read (`file:line`), behaviour you observed, or an "
    "earlier answer. Ask a question others depend on first, and hold back the ones that depend on "
    "its answer. Where you ask what the operator wants (what they are trying to achieve, how "
    "something should behave or feel), ask them to describe it in their own words before "
    "offering any options; offer options with a recommendation only for a fork between "
    "alternatives you have named. When an answer opens a new branch or contradicts something "
    "already written, follow it up before moving to a new topic.\n"
    "- **Ideas apart.** Where the code or the operator's answers suggest an idea beyond the "
    "request, offer it in a separate **Worth considering** list after your questions, not as one "
    "of them. Never write an idea into the requirements or scope until the operator picks it up.\n"
    "- Write only this step's part of the document; later steps write the rest."
)

#: What the operator is shown at the steps that write requirements and criteria (`contested-only`):
#: the document is open beside the conversation, and they read the rest there when they want to.
CONTESTED_ONLY = (
    "- **Show the operator only what is contested:** the requirements and criteria you are unsure "
    "of or that contradict something (the code, an earlier answer, another requirement), the "
    "assumptions behind them, and the acceptance drive. Do not list the rest in your reply; point "
    "at the document for it."
)

#: The plan steps (approach, tasks, build) are the agent's work, and the operator sees the whole plan
#: at approval (`agent-advances`): a question there is only for what the code cannot settle.
PLAN_ASKS = (
    "- **Ask the operator here only what only they can decide:** a hazard (a migration, live "
    "data, security) or a choice the code cannot settle. Decide the rest yourself and say what "
    "you decided."
)

#: The intake's first reply on a document, while its problem is unwritten (D1, `intent-playback`).
#: Gated on the document rather than a step of its own, so a fresh conversation on a document whose
#: problem is written does not play the intent back again.
PLAYBACK = (
    "- **The problem is not written yet, so your reply is the intent playback alone.** Say, in "
    "plainer and simpler words than the operator used, what you understood they are trying to "
    "achieve and why, without describing how it would be built, and ask whether you got that "
    "right. Then end your turn: no research findings, no other questions. Once the operator "
    "confirms it (or corrects it), write the confirmed intent as the document's `problem` with "
    "`submit_spec_document` before going on to the rest of this step."
)

#: What intake has covered before it ends (D5, `coverage-and-assumptions`).
COVERAGE = (
    "what the operator is trying to achieve and why",
    "who it affects and their workflow",
    "scope boundaries",
    "failure and boundary cases",
    "conflicts with existing behaviour",
    "what success looks like",
)

_REQUIREMENTS = (
    "- Write the requirements with `submit_spec_document`: each a single testable statement with "
    "its modal (MUST, SHOULD, MAY), and a rationale where the reason is not obvious. Ground each in "
    "what the code does today. A slice is about a dozen requirements or fewer.\n"
    "- A requirement may list, in `facts`, the vault facts you used for it, by id (`fct-` and 12 "
    "hex characters, read with `vault_map` or `vault_read`). A requirement nothing in the vault "
    "backs lists none; that is fine and draws no warning."
)

_ACCEPTANCE = (
    "- Agree with the operator, for **every MUST requirement**, at least one acceptance criterion: "
    "`given`, `when`, `then`, plus `how_to_check` (the command, test, drive step or manual action "
    "that shows it) and `checked_by`: `agent` when an agent can check it unaided, `operator` when "
    "only the operator can. Write them as `acceptance_criteria` with `submit_spec_document`.\n"
    "- Name the **acceptance drive**: the one end-to-end check that fails while the behaviour cannot "
    "fire for real, and passes only when it can. Record it as a criterion.\n"
    "- Check that each criterion's `given` can actually be reached under this document's own "
    "requirements.\n"
    "- Check **each criterion against the current code**. For one that already holds, either mark "
    "it a guard (`guard: true`) or rewrite it so that it fails until the change is built. Record "
    "the confirmation of every criterion with `confirm_acceptance_criteria`; approval waits for it."
)

STEP_DUTIES: Dict[str, str] = {
    INTAKE: (
        f"{marker(INTAKE)} **Intake: understand the request, show where it lands, and size the "
        "work.** Do not implement anything.\n"
        "- Read the code the request touches before asking anything you could look up.\n"
        "- **Write the picture before any requirement**, into the document's `design` with "
        "`submit_spec_document`, under two headings. `## Today`: how the part of the system the "
        "request touches works now, citing `file:line`. `## Proposed shape`: a before/after sketch "
        "of how the change fits on top of it, what it would touch and what it changes for existing "
        "behaviour, and, where there is a real choice, two or three approaches with your "
        "recommendation. This holds for every size, a fix included. Summarise it in your reply so "
        "the operator can correct it.\n"
        "- **Grill, curious first, then relentless.** Before this step ends, challenge the request's "
        "premise at least once (is this the right problem; would a smaller or different change "
        "serve it?), and ask about the failure modes, boundary cases and conflicts with existing "
        "behaviour that the code shows.\n"
        "- **Cover:** " + "; ".join(COVERAGE) + ". End every reply with the items still open and "
        "each **assumption** you are making in place of an answer, so nothing is silently assumed.\n"
        "- Settle the problem, who it affects, and what is out of scope. Write them as `problem` "
        "and `scope` (`in_scope`, `non_goals`) with `submit_spec_document`.\n"
        "- **Size the work yourself:** **fix** (a defect with a repro, or a change you can say in "
        "one sentence), **small** (one demonstrable outcome, a few requirements), or **large** "
        "(several outcomes, a migration, security, or a contract other parts rely on). Larger than "
        "one demonstrable outcome is a `roadmap` plus the first slice's change document instead. "
        "Record it with `set_spec_size(path, size, reason)` and tell the operator the size and "
        "your reason in your reply; do not ask them to confirm it. They can change it from the "
        "phase bar.\n"
        "- **Already built:** look for commits on the main branch that hold the work. Ask the "
        "operator whether it is built only when you found candidate commits, naming them. "
        'Otherwise record `{"built": false}` and say so. Record it as `already_built` with '
        '`submit_spec_document`: `{"built": true, "commits": ["<sha>"]}` when it is. '
        "Approving a document recorded as built offers to close its tasks as already built "
        "instead of building them.\n" + QUESTIONING
    ),
    REQUIREMENTS: (
        f"{marker(REQUIREMENTS)} **Requirements: say what must be true.** Do not implement "
        "anything.\n" + _REQUIREMENTS + "\n" + CONTESTED_ONLY + "\n" + QUESTIONING
    ),
    ACCEPTANCE: (
        f"{marker(ACCEPTANCE)} **Acceptance: agree how each requirement is shown to hold.** This is "
        "the step that most decides whether the work can be trusted; take care with it.\n"
        + _ACCEPTANCE
        + "\n"
        + CONTESTED_ONLY
        + "\n"
        + QUESTIONING
    ),
    REQUIREMENTS_AND_ACCEPTANCE: (
        f"{marker(REQUIREMENTS_AND_ACCEPTANCE)} **Requirements and acceptance: what must be true, "
        "and how each is shown.** Do not implement anything.\n"
        + _REQUIREMENTS
        + "\n"
        + _ACCEPTANCE
        + "\n"
        + CONTESTED_ONLY
        + "\n"
        + QUESTIONING
    ),
    APPROACH: (
        f"{marker(APPROACH)} **Approach: decide how it will be built.** Write short decision records "
        "into `design` under `## Decisions`, below the `## Today` and `## Proposed shape` that "
        "intake wrote: each decision, the alternative rejected, and why. Name any hazard (a "
        "migration, live data, security) and its rollback. Do not implement anything.\n"
        "- **Name the contract** that the tasks and the drive share: each new setting field, route "
        "and response field with its exact name and shape, and any status path a drive walks. Name "
        "any existing guard or test the change relaxes. A name a builder has to guess is a gap in "
        "this step.\n" + PLAN_ASKS + "\n" + QUESTIONING
    ),
    TASKS: (
        f"{marker(TASKS)} **Tasks: split the work.** Write `tasks` with `submit_spec_document`.\n"
        "- **One task per independently demonstrable piece**, built by one agent: a piece someone "
        "can see working on its own, not one task per layer (model, route, UI) or per file. Every "
        "task costs a turn, a review and a check run, so split only where the pieces can be shown "
        "working apart.\n"
        "- **Task 1 writes the acceptance drive** against the contract the approach names, **and "
        "records it failing** on today's code; the other tasks depend on it. A fix's one task "
        "carries its own failing check.\n"
        "- **A last task runs the acceptance drive against the built feature** and records its "
        "result as evidence. It depends on every task that builds behaviour, so no review defers "
        "that run to a step nobody owns.\n"
        "- A test and its fix are one task, so every task leaves the project's checks green.\n"
        "- For each task list in `files` the paths it will edit, and in `depends_on` the tasks it "
        "waits on; chain other tasks to each other only where they share a path or one needs what "
        "another builds; every chain makes a task wait. Put each acceptance criterion in the task "
        "that builds the behaviour it needs. Link each task to the requirements it serves.\n"
        "- **Name people on every task.** Give each task its own `builder` and `checker`, chosen "
        "from the open agents, with `builder_reason` and `checker_reason`: one sentence each. A "
        "reason states the pick in terms of that agent's model (its cost and performance) and the "
        "task's complexity, and nothing else. Give a hazardous task (a migration, live data, "
        "security) an agent whose model suits it and a routine one (a copy change) a cheaper "
        "model where the roster has one. A task's checker is never its builder; with one open "
        "agent, leave `checker` empty and let `checker_reason` say why. A task missing a pick or "
        "a reason draws a warning on the document, never a block. Still set `delivery.builder` "
        "and `delivery.checker` as the defaults.\n" + PLAN_ASKS + "\n" + QUESTIONING
    ),
    BUILD: (
        f"{marker(BUILD)} **Build: recommend how it will be built.** You recommend; the operator "
        "decides when they press Build, which opens with your recommendation filled in. Recommend "
        "a flow when the work splits into tasks: a flow starts every task whose prerequisites are "
        "met, has finished work reviewed when there is another agent, and can stop when its queue "
        "empties. Recommend which agent works it, who checks, when it stops and how often it "
        "fires (every 5 minutes unless the operator says otherwise). Each check also tests the "
        "running product; the checker both tests and records the verdict (`delivery.checker`). "
        "'No flow' is a valid recommendation. Record the recommendation as "
        "`delivery`, with `reasons`: one sentence for each choice, keyed `mode`, `agent`, "
        "`stop` and `cron`. Each task's builder and checker are recommended on the task, with "
        "their reasons, at the tasks step. Include `delivery` in every later submission. "
        "Each save returns a verdict: report the document to the operator as ready only when "
        "the latest save says `ready_to_approve` is true. Otherwise fix each open gap it lists, "
        "or acknowledge it with a reason (`acknowledge_spec_gap`) where you judge it acceptable.\n"
        + PLAN_ASKS
        + "\n"
        + QUESTIONING
    ),
}


#: A custom step's output is named in its own Markdown (D3); this line covers Markdown that does not.
WRITE_WHERE = (
    "- Write this step's result where the instructions above say. When they name no place, choose "
    "a section of the document or a file, and tell the operator where you wrote it."
)


#: An open agent and the model its runner is bound to ("" when it has none).
Roster = List[Tuple[str, str]]

#: An open agent's pool: `(runner id, model, effort or "", is default)` per entry, by agent name.
Pools = Dict[str, List[Tuple[str, str, str, bool]]]


def pool_brief(pools: Optional[Pools]) -> str:
    """Every entry of every open agent's pool, and how a task names one that is not the default
    (`the-spec-process-uses-what-the-hub-already-knows`, FR-1)."""
    if not pools:
        return ""
    lines = ["- **Each open agent's pool** (runner id, model, effort when set):"]
    for name in sorted(pools):
        entries = "; ".join(
            f"`{runner_id}` {model or 'no model set'}"
            + (f", effort {effort}" if effort else "")
            + (" (default)" if is_default else "")
            for runner_id, model, effort, is_default in pools[name]
        )
        lines.append(f"  - `{name}`: {entries}")
    lines.append(
        "- A task runs on its agent's default entry unless it names another: set `builder_entry` "
        'or `checker_entry` to `{"runner_id": "<runner id>", "effort": "<effort or null>"}` for an '
        "entry of that agent's pool. State the pick's reason (`builder_reason`, `checker_reason`) "
        "in terms of that entry's model, not the agent's default."
    )
    return "\n".join(lines)


def people_brief(
    size: Optional[str], roster: Optional[Roster], pools: Optional[Pools] = None
) -> str:
    """What the tasks step adds once the roster and size are known: each open agent's model, and
    for a document larger than a fix, the evidence the picks rest on (FR-2, FR-13). It no longer
    asks the operator which sources to judge by (`agent-settles-process`, D6): the agent judges
    from its own knowledge and the project's record, and the operator overturns a pick on the task.
    """
    lines: List[str] = []
    pool_lines = pool_brief(pools)
    if pool_lines:
        lines.append(pool_lines)
    if roster:
        lines.append(
            "- **Open agents and their models:** "
            + "; ".join(f"`{name}` ({model or 'no model set'})" for name, model in roster)
            + "."
        )
        if len(roster) == 1:
            lines.append(
                "- There is one open agent, so no task can have a checker other than its "
                "builder: leave every `checker` empty and say why in `checker_reason`."
            )
    if size != "fix":
        lines.append(
            "- **Judge these models yourself** (cost, performance, where each is strong) from what "
            "you already know and this project's record (`read_model_record`); do not ask the "
            "operator how to judge them. If the record is unavailable or too small to tell, say "
            "so rather than presenting a guess as the finding.\n"
            "- **Record what you found in the document's `evidence`, in the submission that names "
            'the people:** it is an object, `{"checked": [...], "limits": [...]}`, of strings. '
            "`checked` holds one line per source used, with any figures and their sample sizes "
            "(`project record: sample of 12 tasks built, 30 turns; ...`, an empty record too); "
            "`limits` holds what those sources cannot tell you. Stating it in your reply or the "
            "design does not record it. A submission replaces the whole document, so keep "
            "`evidence` in every later one."
        )
    return "\n".join(lines)


def duty(
    step: Optional[str],
    steps: Optional[ProjectSteps] = None,
    *,
    size: Optional[str] = None,
    roster: Optional[Roster] = None,
    problem_written: bool = False,
    pools: Optional[Pools] = None,
) -> str:
    """The step's instructions, the project's appended instruction for that step and no other
    (FR-4), and the instruction to advance itself; "" for a step the project does not have.

    At intake, while the document's `problem` is unwritten, the duty opens with the intent playback
    (`intent-playback`, D1). The rest of intake stays in the text, because the turn the operator
    confirms the playback in still starts with the problem unwritten.
    """
    entry = (steps or BUILT_IN).get(step)
    if entry is None:
        return ""
    if entry.custom:
        text = f"{marker(entry.key)} **{entry.title}.**\n{entry.instructions}\n{WRITE_WHERE}"
    else:
        text = STEP_DUTIES[entry.key]
        if entry.key == INTAKE and not problem_written:
            head, _, rest = text.partition("\n")
            text = head + "\n" + PLAYBACK + "\n" + rest
        if entry.key == TASKS:
            brief = people_brief(size, roster, pools)
            if brief:
                text += "\n" + brief
    if entry.append:
        text += "\n- **This project adds to this step:** " + entry.append
    return text if entry.key == BUILD else text + "\n" + ADVANCE_YOURSELF


def removed(step: str, size: Optional[str], steps: Optional[ProjectSteps] = None) -> str:
    """The briefing for a document whose step the project removed (FR-8)."""
    return (
        f"{marker(step)} **The step {step!r} was removed from this project's journey.** Do not "
        "continue it. Ask in your reply which step to resume at, offering this journey's steps "
        f"({', '.join(journey(size, steps))}), and end your turn. When the operator answers, call "
        "`advance_spec_step(path, to=<their choice>)` and follow the instructions it returns."
    )


def journey_line(
    size: Optional[str], step: Optional[str], steps: Optional[ProjectSteps] = None
) -> str:
    """One line naming the journey and the current step (FR-3)."""
    step = current_name(step)
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
    step = current_name(step)
    if step == INTAKE:
        if not payload.get("problem"):
            gaps.append("problem")
        if payload.get("already_built") is None:
            gaps.append("already_built")
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
    if step == BUILD:
        delivery = payload.get("delivery")
        if not delivery:
            gaps.append("delivery")
        elif isinstance(delivery, dict) and not delivery.get("reasons"):
            gaps.append("delivery.reasons")
    return gaps
