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
from typing import AbstractSet, Dict, List, Mapping, Optional, Tuple

from .spec_payload import SpecPayload

# The marker the skills used for an unresolved question, kept because documents
# and habits already use it. Matched case-insensitively and tolerant of spacing.
CLARIFICATION_RE = re.compile(r"\[\s*needs[ _-]?clarification", re.IGNORECASE)


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


@dataclass(frozen=True)
class RoadmapState:
    """What a slice document's link needs to know about the roadmap it names (C1a D3).

    Resolved by the caller from the database and the roadmap's file, as `approved_document_paths`
    is, so this module stays a pure function of its inputs.
    """

    phase: str
    title: str
    slice_keys: Tuple[str, ...]


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
    roadmaps: Optional[Mapping[str, RoadmapState]] = None,
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

    `roadmaps` maps a roadmap path to its state, for the roadmap a slice document names. A path
    absent from it is a roadmap that does not exist.
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

    if payload.kind == "roadmap":
        # A roadmap asserts its slices, not requirements: those are written in each slice's change
        # document when that slice is next (C1a D3).
        if not payload.slices:
            findings.append(
                Finding(
                    "roadmap_without_slices",
                    "slices",
                    "a roadmap with no slices plans nothing; list the slices in the order they "
                    "are built",
                )
            )
    elif not payload.requirements:
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

    findings.extend(_unknown_field_findings(payload))

    if payload.kind == "roadmap":
        for index, item in enumerate(payload.slices):
            if len(item.done.split()) < _OUTCOME_WORDS:
                findings.append(
                    Finding(
                        "slice_done_empty",
                        f"slices[{index}].done",
                        f"slice {item.key!r} does not say how anyone can tell it is finished; "
                        "state the outcome that shows it is done",
                    )
                )

    if payload.roadmap is not None:
        findings.extend(_roadmap_link_findings(payload, roadmaps or {}))

    # D4: only a change-spec document declares delivery — no other kind is asked.
    if payload.kind == "change-spec":
        if payload.delivery is None:
            findings.append(
                Finding(
                    "delivery_unanswered",
                    "delivery",
                    "ask how this document's tasks will be worked once approved: a flow "
                    "(with a default agent and a stop condition) or no flow at all",
                )
            )
        elif payload.delivery.mode == "flow" and (
            not payload.delivery.agent
            or not (payload.delivery.stop_when_queue_empties or payload.delivery.stop_at)
        ):
            findings.append(
                Finding(
                    "delivery_flow_incomplete",
                    "delivery",
                    "a flow delivery needs a default agent and at least one stop condition "
                    "(stop_when_queue_empties or stop_at)",
                )
            )

    return findings


def _normalise_path(path: str) -> str:
    return path.strip().replace("\\", "/").strip("/")


def paths_overlap(a: str, b: str) -> Optional[str]:
    """The overlapping path of two declared paths, or None. A directory covers what is beneath it."""
    left, right = _normalise_path(a), _normalise_path(b)
    if left == right or right.startswith(left + "/"):
        return right
    if left.startswith(right + "/"):
        return left
    return None


def overlap_warnings(payload: SpecPayload) -> List[Finding]:
    """Pairs of tasks that declare overlapping `files` with no `depends_on` path between them.

    Advisory only: these never enter `check`, so `ready_to_propose` is unaffected. Imported entries
    and tasks declaring no `files` are never named.
    """
    declared = [t for t in payload.tasks if t.from_ is None and t.files]
    edges = {t.key: list(t.depends_on) for t in payload.tasks}

    def reaches(start: str, goal: str) -> bool:
        seen, todo = set(), [start]
        while todo:
            key = todo.pop()
            for nxt in edges.get(key, []):
                if nxt == goal:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        return False

    warnings: List[Finding] = []
    for i, first in enumerate(declared):
        for second in declared[i + 1 :]:
            shared = next(
                (
                    hit
                    for a in first.files
                    for b in second.files
                    if (hit := paths_overlap(a, b)) is not None
                ),
                None,
            )
            if shared is None or reaches(first.key, second.key) or reaches(second.key, first.key):
                continue
            warnings.append(
                Finding(
                    "unordered_file_overlap",
                    "tasks",
                    f"tasks {first.key!r} and {second.key!r} both declare {shared!r} and neither "
                    "depends_on the other, so they would be built in parallel; chain them with "
                    "depends_on",
                )
            )
    return warnings


def undeclared_files_warnings(payload: SpecPayload) -> List[Finding]:
    """One warning naming every local task that declares no `files`, when there are two or more.

    Advisory only, like `overlap_warnings`, and for the same reason: it never enters `check`. It
    covers the planner that skips `files` entirely, which `overlap_warnings` cannot see (F509).
    Imported entries neither count toward the two nor are named.
    """
    local = [t for t in payload.tasks if t.from_ is None]
    unfiled = [t.key for t in local if not t.files]
    if len(local) < 2 or not unfiled:
        return []
    names = ", ".join(repr(key) for key in unfiled)
    return [
        Finding(
            "undeclared_task_files",
            "tasks",
            f"tasks {names} declare no `files`, so the Hub cannot tell whether they edit the same "
            "path; list the paths each will edit in `files`, and chain tasks that share a path "
            "with depends_on, or they would be built in parallel",
        )
    ]


_TEST_DIRS = {"tests", "test", "__tests__"}


def is_test_path(path: str) -> bool:
    """Whether a repo-relative path is a test by the common conventions: a `tests`/`test`/
    `__tests__` directory, or a `test_*`, `*_test.*`, `*.test.*` or `*.spec.*` file."""
    parts = path.replace(chr(92), "/").strip("/").split("/")
    name = parts[-1]
    stem = name.split(".")[0]
    return (
        any(part in _TEST_DIRS for part in parts[:-1])
        or stem.startswith("test_")
        or stem.endswith("_test")
        or ".test." in name
        or ".spec." in name
    )


def test_only_task_warnings(payload: SpecPayload) -> List[Finding]:
    """Tasks that edit only tests while another local task depends on them (F512).

    That shape is a test written red for a later task to turn green. Approval runs the project's
    checks on the work it would merge, so the first task can never pass them, and lands only by an
    operator override. Advisory, like `overlap_warnings`; a test task nothing depends on (covering
    code that already works) is not this shape and is not named.
    """
    local = [t for t in payload.tasks if t.from_ is None]
    warnings: List[Finding] = []
    for task in local:
        if not task.files or not all(is_test_path(path) for path in task.files):
            continue
        dependents = [t.key for t in local if task.key in t.depends_on]
        if not dependents:
            continue
        names = ", ".join(repr(key) for key in dependents)
        warnings.append(
            Finding(
                "test_only_task",
                "tasks",
                f"task {task.key!r} edits only tests and {names} depends on it, so it is red until "
                "they land and fails the project's checks at approval; put the failing test and "
                "the fix that turns it green in one task",
            )
        )
    return warnings


def reviewer_undeclared_warnings(payload: SpecPayload) -> List[Finding]:
    """A flow-delivered document none of whose tasks names a `reviewer` (F508).

    A flow staffs a review from the task's declared reviewer, and failing that from whichever agent
    is free (`scheduler.resolve_reviewer`). A planner on the trial Hub promised a reviewer in the
    design prose and left the field empty, and a leftover stub agent got the review. The Hub cannot
    read the prose, so it says what the fields will do. Advisory, like `overlap_warnings`.
    """
    if payload.delivery is None or payload.delivery.mode != "flow":
        return []
    local = [t for t in payload.tasks if t.from_ is None]
    if not local or any(t.reviewer for t in local):
        return []
    return [
        Finding(
            "reviewer_undeclared",
            "tasks",
            "no task names a `reviewer`, so the flow will give each review to any free agent; "
            "if a particular agent should review, set `reviewer` on the tasks it reviews",
        )
    ]


#: The fewest words a slice's `done` can state an outcome in. Real agents read the field as a status
#: and wrote "false", then "no" (F502); a list of such words is never complete, a sentence is the test.
_OUTCOME_WORDS = 3

#: Where a field written in the wrong place belongs, for the misplacements authors actually make.
_BELONGS = {
    ("requirement", "acceptance_criteria"): (
        "acceptance criteria go in the top-level acceptance_criteria[], each naming this "
        "requirement's key in `requirement`"
    ),
}


def _unknown_field_findings(payload: SpecPayload) -> List[Finding]:
    """Fields a part does not define (F502).

    The schema keeps unknown fields so a rewrite loses nothing, so a field written in the wrong
    place is stored and never read: a real agent nested its criteria under each requirement and was
    then told there were none. A later schema version is refused at validation, so anything unknown
    here was written for this one.
    """
    findings: List[Finding] = []
    parts = (
        ("requirements", "requirement", payload.requirements),
        ("acceptance_criteria", "acceptance criterion", payload.acceptance_criteria),
        ("tasks", "task", payload.tasks),
        ("slices", "slice", payload.slices),
    )
    for collection, singular, items in parts:
        for index, item in enumerate(items):
            for name in sorted(item.model_extra or {}):
                belongs = _BELONGS.get((singular, name))
                findings.append(
                    Finding(
                        "unknown_field",
                        f"{collection}[{index}].{name}",
                        f"{name!r} is not a field of a {singular}, so nothing reads it"
                        + (f"; {belongs}" if belongs else ""),
                    )
                )
    return findings


def _roadmap_link_findings(
    payload: SpecPayload, roadmaps: Mapping[str, RoadmapState]
) -> List[Finding]:
    """A slice document is proposable only once its roadmap is approved and holds its slice.

    Both block at proposed **and** at approved, unlike `import_not_approved`: a slice of a roadmap
    that has been reopened waits for it to be approved again.
    """
    assert payload.roadmap is not None
    path, key = payload.roadmap.document, payload.roadmap.slice
    state = roadmaps.get(path)
    if state is None or state.phase != "approved":
        where_it_is = "is not a roadmap of this project" if state is None else f"is {state.phase}"
        return [
            Finding(
                "roadmap_not_approved",
                "roadmap",
                f"names roadmap {path!r}, which {where_it_is}; a slice is proposed only once "
                "its roadmap is approved",
            )
        ]
    if key not in state.slice_keys:
        return [
            Finding(
                "roadmap_slice_unknown",
                "roadmap.slice",
                f"names slice {key!r}, which roadmap {path!r} does not hold (its slices: "
                f"{', '.join(state.slice_keys) or 'none'})",
            )
        ]
    return []
