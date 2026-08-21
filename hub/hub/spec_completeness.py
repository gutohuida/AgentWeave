"""The checks that decide whether a document may be proposed.

Every one of these was a bullet in `aw-spec-propose.md`'s step 7b, where the
model was asked to run them on itself and report the result:

    "Every requirement is referenced by at least one acceptance criterion **and**
    one task; every task references at least one requirement. Report both
    directions — an orphan in either direction is a real gap, not a formatting
    nit."

That is an algorithm, and asking its subject to run it is the `unverifiable_claim`
failure mode by construction — a model that reports success without checking is
indistinguishable, in a status column, from one that checked.

They are separate from `spec_payload.validate_payload` on purpose. That answers
"is this well formed?" and runs on every save, because a document being written
is incomplete and refusing to store it would make exploring impossible. This
answers "is this finished?" and runs at the transition, where being incomplete
is the whole point of asking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import AbstractSet, Dict, List, Optional

from .spec_payload import SpecPayload

# The marker the skills used for an unresolved question, kept because documents
# and habits already use it. Matched case-insensitively and tolerant of spacing.
CLARIFICATION_RE = re.compile(r"\[\s*needs[ _-]?clarification", re.IGNORECASE)

# A task naming more requirements than this is a decomposition failure, not a big task: the operator
# found one approved ticket carrying 6 of 9 requirements on 42 words, which hid a rejected requirement
# (FR-9) inside a task that read as done. `design.md` D6 derives 3 from the evidence — see there for
# why 3 and not 2 or 4. A module constant, not a magic number in the check, so a future ruling changes
# it in one place.
MAX_REQUIREMENTS_PER_TASK = 3


@dataclass(frozen=True)
class Finding:
    """One reason the document is not ready, and where to look.

    `where` is not decoration. A refusal the author cannot act on produces a
    retry loop, which is what a prose contract full of "should" produced.
    """

    code: str
    where: str
    message: str

    def to_dict(self) -> dict:
        return {"code": self.code, "where": self.where, "message": self.message}


def _text_fields(payload: SpecPayload) -> List[tuple]:
    fields = [
        ("summary", payload.summary),
        ("problem", payload.problem),
        ("design", payload.design),
        ("lifecycle", payload.lifecycle),
    ]
    for index, requirement in enumerate(payload.requirements):
        fields.append((f"requirements[{index}].statement", requirement.statement))
    return fields


def _first_cycle(local_edges: Dict[str, List[str]]) -> Optional[List[str]]:
    """The first cycle found among locally-declared tasks, as the sequence of keys walked.

    `local_edges` already excludes imported entries — they resolve to a task in another,
    already-approved document, so they are leaves by construction and cannot participate in a
    cycle within this one. Depth-first with a recursion-stack (grey/black) set: the graph is a
    handful of tasks per document, not a scale that needs anything cleverer.
    """
    unvisited, visiting, done = 0, 1, 2
    color = dict.fromkeys(local_edges, unvisited)
    stack: List[str] = []

    def visit(key: str) -> Optional[List[str]]:
        color[key] = visiting
        stack.append(key)
        for neighbour in local_edges.get(key, []):
            if neighbour not in local_edges:
                continue  # not a locally-declared task; cannot close a cycle
            if color[neighbour] == visiting:
                return stack[stack.index(neighbour) :] + [neighbour]
            if color[neighbour] == unvisited:
                found = visit(neighbour)
                if found:
                    return found
        stack.pop()
        color[key] = done
        return None

    for key in local_edges:
        if color[key] == unvisited:
            found = visit(key)
            if found:
                return found
    return None


def check(
    payload: SpecPayload,
    *,
    board_served: Optional[AbstractSet[str]] = None,
    approved_document_paths: Optional[AbstractSet[str]] = None,
) -> List[Finding]:
    """Everything wrong with this document, not just the first thing.

    Reporting one problem per attempt turns a five-problem document into five
    round trips.

    `board_served` is the set of requirement keys a real task-board task already links to,
    independent of what the document's own `tasks[]` declares. Without it, an operator or agent who
    hand-creates board tasks before proposing gets `requirement_without_task` anyway, and then
    `materialise()` mints a second, overlapping set of tasks on approval — two decompositions with
    nothing reconciling them. The document's own `tasks[]` and the real board converge here instead.

    `approved_document_paths` is the set of this project's currently-approved document paths,
    supplied the same way `board_served` is — this module stays a pure function of its inputs,
    never touching the database itself. Used to check an import (`Task.from_`) names a document
    that has actually materialised the task it claims to reference.
    """
    findings: List[Finding] = []
    served = board_served or frozenset()
    approved = approved_document_paths or frozenset()

    all_task_keys = {task.key for task in payload.tasks}
    for index, task in enumerate(payload.tasks):
        for position, dep in enumerate(task.depends_on):
            if dep not in all_task_keys:
                findings.append(
                    Finding(
                        "depends_on_unresolved",
                        f"tasks[{index}].depends_on[{position}]",
                        f"{dep!r} names neither a task declared in this document nor an "
                        "imported entry's key, so nothing satisfies it",
                    )
                )
        if task.from_ is not None and task.from_.document not in approved:
            findings.append(
                Finding(
                    "import_not_approved",
                    f"tasks[{index}]",
                    f"{task.key!r} imports {task.from_.key!r} from "
                    f"{task.from_.document!r}, which is not approved — an import can only name "
                    "a document whose task has already materialised",
                )
            )

    local_edges = {task.key: list(task.depends_on) for task in payload.tasks if task.from_ is None}
    cycle = _first_cycle(local_edges)
    if cycle:
        findings.append(
            Finding(
                "dependency_cycle",
                "tasks",
                "a cycle among locally-declared tasks: "
                + " -> ".join(cycle)
                + " — cycles are detected within this document only, not across documents",
            )
        )

    if not payload.requirements:
        findings.append(
            Finding(
                "no_requirements",
                "requirements",
                "a document with no requirements asserts nothing that can be satisfied or violated",
            )
        )

    if not payload.scope.non_goals:
        findings.append(
            Finding(
                "non_goals_empty",
                "scope.non_goals",
                "state what is out of scope; omission is silence, not a non-goal",
            )
        )

    covered = {criterion.requirement for criterion in payload.acceptance_criteria}
    tasked = {key for task in payload.tasks for key in task.requirements}

    for index, requirement in enumerate(payload.requirements):
        where = f"requirements[{index}]"
        if requirement.key not in covered:
            findings.append(
                Finding(
                    "requirement_without_criterion",
                    where,
                    f"{requirement.key!r} has no acceptance criterion, so nothing demonstrates it",
                )
            )
        if requirement.key not in tasked and requirement.key not in served:
            findings.append(
                Finding(
                    "requirement_without_task",
                    where,
                    f"{requirement.key!r} is in neither the document's own tasks[] nor a task "
                    "already on the board, so nothing implements it",
                )
            )

    # The other direction, reported separately. An orphan either way is a real
    # gap, and only reporting one of them lets the other class hide.
    for index, task in enumerate(payload.tasks):
        if not task.requirements:
            findings.append(
                Finding(
                    "task_without_requirement",
                    f"tasks[{index}]",
                    f"{task.key!r} traces to no requirement, so it is work nobody asked for",
                )
            )
        elif len(task.requirements) > MAX_REQUIREMENTS_PER_TASK:
            findings.append(
                Finding(
                    "task_too_coarse",
                    f"tasks[{index}]",
                    f"{task.key!r} names {len(task.requirements)} requirements, over the ceiling of "
                    f"{MAX_REQUIREMENTS_PER_TASK} — split it so each piece of work is demonstrable on "
                    "its own",
                )
            )

    for index, question in enumerate(payload.open_questions):
        if not question.resolved:
            findings.append(
                Finding(
                    "unresolved_question",
                    f"open_questions[{index}]",
                    "resolve it or drop it; a guess written as a requirement is built on as a decision",
                )
            )

    for where, text in _text_fields(payload):
        if text and CLARIFICATION_RE.search(text):
            findings.append(
                Finding(
                    "clarification_marker",
                    where,
                    "an unresolved clarification marker is still in the text",
                )
            )

    return findings
