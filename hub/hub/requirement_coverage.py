"""One definition of "is this verified", and one precedence.

The document badge, the project total and B4's gate all call this function.
**Two implementations would disagree eventually, and the disagreement would be
invisible until somebody compared two screens** — so there is exactly one, and a
test asserts there is exactly one.

The precedence, highest first:

1. `drifting` — an unresolved drift record exists
2. `stale` — evidence exists, none of it applies to the current digest
3. `evidence_awaiting_review` — current-digest evidence, review pending
4. `verified` — accepted current-digest evidence
5. `in_progress` — linked work active, or completed without evidence
6. `not_started` — linked work exists, not started
7. `unserved` — no work linked at all

**Coverage is a state *and* an integration answer, and no surface may show one
without the other.** Approved work in this product routinely sits on a per-agent
branch that nothing merges, so `verified` alone would be true of the branch and
false of the product. Integration is not an eighth precedence level: the
precedence ranks how good the evidence is, and integration is an independent fact
about the same evidence. Ranking them together would force a choice between
"stale but merged" and "verified but unmerged" that has no correct answer.

A requirement that is structurally invalid or carries no identifier is a
**diagnostic outside coverage**, not a coverage state. It is not unserved; it is
broken, and a gate must refuse on it separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import (
    EvidenceFootprint,
    RequirementEvidence,
    SpecRequirement,
    Task,
    TaskRequirementLink,
)
from .requirement_evidence import ACCEPTED, AWAITING, open_drift_for

DRIFTING = "drifting"
STALE = "stale"
AWAITING_REVIEW = "evidence_awaiting_review"
VERIFIED = "verified"
IN_PROGRESS = "in_progress"
NOT_STARTED = "not_started"
UNSERVED = "unserved"

# Highest first. The order is the specification; the function below reads it rather than restating
# it as a chain of conditionals whose order could drift from this list.
PRECEDENCE = (DRIFTING, STALE, AWAITING_REVIEW, VERIFIED, IN_PROGRESS, NOT_STARTED, UNSERVED)

# A task at one of these has not started. Anything else linked to a requirement counts as work under
# way, including terminal statuses — a completed task with no evidence is `in_progress` for the
# purposes of *coverage*, because coverage asks whether the requirement is demonstrated and it
# demonstrably is not.
NOT_STARTED_STATUSES = {"pending", "assigned"}

INTEGRATED = "integrated"
NOT_INTEGRATED = "not_integrated"
INTEGRATION_UNKNOWN = "unknown"
# No evidence, so nothing to be integrated. Distinct from "unknown", which means there is a
# footprint and no main branch to compare it against.
INTEGRATION_NOT_APPLICABLE = "not_applicable"


@dataclass
class Coverage:
    """One requirement's coverage state, and the integration answer that goes with it."""

    identifier: str
    requirement_id: str
    document_id: str
    state: str
    integration: str
    evidence_count: int = 0
    accepted_count: int = 0
    linked_task_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "identifier": self.identifier,
            "requirement_id": self.requirement_id,
            "document_id": self.document_id,
            "state": self.state,
            # Always present, never optional. `test_no_surface_reports_a_state_without_integration`
            # is what keeps it that way.
            "integration": self.integration,
            "evidence_count": self.evidence_count,
            "accepted_count": self.accepted_count,
            "linked_task_ids": list(self.linked_task_ids),
        }


@dataclass
class Diagnostic:
    """A requirement that cannot be given a coverage state, and why."""

    requirement_id: str
    identifier: str
    document_id: str
    problem: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "requirement_id": self.requirement_id,
            "identifier": self.identifier,
            "document_id": self.document_id,
            "problem": self.problem,
        }


@dataclass
class CoverageReport:
    requirements: List[Coverage] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)

    @property
    def totals(self) -> Dict[str, int]:
        counts = dict.fromkeys(PRECEDENCE, 0)
        for entry in self.requirements:
            counts[entry.state] = counts.get(entry.state, 0) + 1
        return counts

    @property
    def integration_totals(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self.requirements:
            counts[entry.integration] = counts.get(entry.integration, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, object]:
        return {
            "requirements": [entry.to_dict() for entry in self.requirements],
            "diagnostics": [entry.to_dict() for entry in self.diagnostics],
            "totals": self.totals,
            "integration": self.integration_totals,
        }


def _integration(footprints: List[EvidenceFootprint]) -> str:
    """The integration answer for one requirement's accepted evidence.

    Any footprint reachable from the main line means the work is in the product.
    None reachable, with at least one that could be checked, means it is not.
    Where nothing could be checked — no main branch, or a project with no
    repository — the answer is `unknown`, which is not the same as "not
    integrated": that would be an accusation about a choice.
    """
    if not footprints:
        return INTEGRATION_NOT_APPLICABLE
    answers = [footprint.reachable_from_main for footprint in footprints]
    if any(answer is True for answer in answers):
        return INTEGRATED
    if any(answer is False for answer in answers):
        return NOT_INTEGRATED
    return INTEGRATION_UNKNOWN


def _state(
    *,
    drifting: bool,
    evidence: List[RequirementEvidence],
    digest: str,
    linked: List[Task],
) -> str:
    current = [item for item in evidence if item.digest == digest]
    accepted = [item for item in current if item.review_state == ACCEPTED]
    awaiting = [item for item in current if item.review_state == AWAITING]

    if drifting:
        return DRIFTING
    if evidence and not current:
        # Evidence exists and none of it applies to what the requirement now says. This is the
        # state `requirement_digests` was recorded to expose and that nothing ever read.
        return STALE
    if awaiting:
        return AWAITING_REVIEW
    if accepted:
        return VERIFIED
    if not linked:
        return UNSERVED
    if all(task.status in NOT_STARTED_STATUSES for task in linked):
        return NOT_STARTED
    return IN_PROGRESS


async def requirement_coverage(
    session: AsyncSession,
    project_id: str,
    *,
    document_id: Optional[str] = None,
    include_retired: bool = False,
) -> CoverageReport:
    """The single definition. Every surface reporting coverage calls this."""
    query = select(SpecRequirement).where(SpecRequirement.project_id == project_id)
    if document_id is not None:
        query = query.where(SpecRequirement.document_id == document_id)
    if not include_retired:
        query = query.where(SpecRequirement.state == "active")
    requirements = list(
        (await session.execute(query.order_by(SpecRequirement.identifier))).scalars().all()
    )

    report = CoverageReport()
    if not requirements:
        return report

    ids = [requirement.id for requirement in requirements]

    evidence_rows = list(
        (
            await session.execute(
                select(RequirementEvidence).where(RequirementEvidence.requirement_id.in_(ids))
            )
        )
        .scalars()
        .all()
    )
    evidence_by_requirement: Dict[str, List[RequirementEvidence]] = {}
    for row in evidence_rows:
        evidence_by_requirement.setdefault(row.requirement_id, []).append(row)

    footprints = {
        row.evidence_id: row
        for row in (
            await session.execute(
                select(EvidenceFootprint).where(
                    EvidenceFootprint.evidence_id.in_([row.id for row in evidence_rows] or [""])
                )
            )
        )
        .scalars()
        .all()
    }

    tasks_by_requirement: Dict[str, List[Task]] = {}
    for requirement_id, task in (
        await session.execute(
            select(TaskRequirementLink.requirement_id, Task)
            .join(Task, Task.id == TaskRequirementLink.task_id)
            .where(TaskRequirementLink.requirement_id.in_(ids))
        )
    ).all():
        tasks_by_requirement.setdefault(requirement_id, []).append(task)

    drifting = await open_drift_for(session, ids)

    for requirement in requirements:
        if not requirement.identifier or not requirement.digest:
            # Outside coverage rather than inside it with a bad state: it is not unserved, it is
            # broken, and a gate has to be able to refuse on that separately.
            report.diagnostics.append(
                Diagnostic(
                    requirement_id=requirement.id,
                    identifier=requirement.identifier or "",
                    document_id=requirement.document_id,
                    problem=(
                        "carries no identifier"
                        if not requirement.identifier
                        else "carries no semantic digest"
                    ),
                )
            )
            continue

        evidence = evidence_by_requirement.get(requirement.id, [])
        linked = tasks_by_requirement.get(requirement.id, [])
        state = _state(
            drifting=requirement.id in drifting,
            evidence=evidence,
            digest=requirement.digest,
            linked=linked,
        )
        accepted = [
            item
            for item in evidence
            if item.review_state == ACCEPTED and item.digest == requirement.digest
        ]
        report.requirements.append(
            Coverage(
                identifier=requirement.identifier,
                requirement_id=requirement.id,
                document_id=requirement.document_id,
                state=state,
                integration=_integration(
                    [footprints[item.id] for item in accepted if item.id in footprints]
                ),
                evidence_count=len(evidence),
                accepted_count=len(accepted),
                linked_task_ids=[task.id for task in linked],
            )
        )

    return report


async def document_coverage(
    session: AsyncSession, project_id: str, document_id: str
) -> CoverageReport:
    """A document's rollup. Calls `requirement_coverage`; computes nothing itself."""
    return await requirement_coverage(session, project_id, document_id=document_id)


async def project_coverage(session: AsyncSession, project_id: str) -> CoverageReport:
    """A project's rollup. Calls `requirement_coverage`; computes nothing itself."""
    return await requirement_coverage(session, project_id)
