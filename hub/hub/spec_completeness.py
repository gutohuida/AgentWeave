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
from typing import List

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


def check(payload: SpecPayload) -> List[Finding]:
    """Everything wrong with this document, not just the first thing.

    Reporting one problem per attempt turns a five-problem document into five
    round trips.
    """
    findings: List[Finding] = []

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
        if requirement.key not in tasked:
            findings.append(
                Finding(
                    "requirement_without_task",
                    where,
                    f"{requirement.key!r} has no task, so nothing implements it",
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

    return findings
