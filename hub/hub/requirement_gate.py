"""The gate: a task cannot be approved while a requirement it serves is unverified.

It lives inside the transition service rather than beside it. A second enforcement
point is a second thing to bypass, and the rule that no route assigns
`Task.status` directly is what makes one point sufficient.

**On `approved`, not `completed`.** `completed` is an agent reporting it finished
writing; `approved` records that the work is good, and is terminal. Evidence is
accepted after review and review follows completion, so refusing `completed`
would deadlock the ordinary path — the task could never reach the step that
produces the acceptance it is blocked for.

**Coverage comes from B3's single query.** If the gate computed its own answer, a
task could be refused while the document beside it showed everything green, and
nobody could say which was lying. One query, or two truths.

**A refusal has to be actionable.** This is the first thing in the product that
can stop the operator's own work, so the failure response is part of the feature:
each blocked requirement is named with its state and with what would change it.
An unactionable gate gets switched off, which is worse than never having built
one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_coverage, spec_rigor
from .db.models import SpecDocument, SpecRequirement, Task, TaskRequirementLink

# The state a `gate` requirement must be in. Deliberately one value: `verified` means the same at
# every rigor, because a word whose meaning shifts with context is worse than a strict one — and
# because promoting a document would otherwise silently un-verify requirements that were verified a
# moment before.
SATISFIED = requirement_coverage.VERIFIED

# What to do about each state that is not `verified`. The wording is the feature: "the gate refused"
# without it is unactionable.
REMEDY = {
    requirement_coverage.UNSERVED: "no task is linked to it — link the work that serves it",
    requirement_coverage.NOT_STARTED: "its linked work has not started",
    requirement_coverage.IN_PROGRESS: (
        "its linked work has produced no evidence — record what demonstrates it"
    ),
    requirement_coverage.AWAITING_REVIEW: (
        "its evidence is waiting for someone to accept it — accept or reject it"
    ),
    requirement_coverage.STALE: (
        "its evidence was produced against an earlier wording — record evidence for what it "
        "says now"
    ),
    requirement_coverage.DRIFTING: (
        "the implementation changed after it was verified — resolve the drift candidate"
    ),
}


@dataclass
class GateRefusal:
    """Why the gate refused, in a shape a surface can render without parsing prose."""

    blocking: List[Dict[str, str]] = field(default_factory=list)
    diagnostics: List[Dict[str, str]] = field(default_factory=list)
    # Work that cannot land where approval says it lands. Separate from `blocking` because it is a
    # different kind of claim: not "this is unproven" but "this cannot go in". An operator told the
    # requirement is unverified would go and record evidence, which would not help at all here.
    unmergeable: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def refuses(self) -> bool:
        return bool(self.blocking or self.diagnostics or self.unmergeable)

    def detail(self) -> str:
        if self.unmergeable and not (self.blocking or self.diagnostics):
            return self._merge_detail()
        parts: List[str] = []
        for entry in self.blocking:
            parts.append(f"{entry['identifier']} is {entry['state']}: {entry['remedy']}")
        for entry in self.diagnostics:
            parts.append(
                f"{entry['identifier'] or 'a requirement'} cannot be checked at all: "
                f"{entry['problem']}"
            )
        sentence = (
            "This task serves requirements a gate is enforcing, and they are not verified: "
            + "; ".join(parts)
            + ". Satisfy them, or lower the document's rigor — which is recorded."
        )
        if self.unmergeable:
            sentence += " " + self._merge_detail()
        return sentence

    def _merge_detail(self) -> str:
        paths: List[str] = []
        target = ""
        for entry in self.unmergeable:
            target = target or str(entry.get("target_branch") or "")
            paths.extend(str(path) for path in entry.get("paths", []))
        listed = ", ".join(sorted(set(paths))[:10])
        return (
            f"This task's work does not merge cleanly into {target or 'the main branch'}: "
            f"{listed}. Resolve the conflict on the branch, then approve — approving is what "
            "merges it."
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": "gate_unsatisfied",
            "blocking": list(self.blocking),
            "diagnostics": list(self.diagnostics),
            "unmergeable": list(self.unmergeable),
            "message": self.detail(),
        }


async def _gated_requirements(
    session: AsyncSession, task: Task
) -> tuple[List[SpecRequirement], Dict[str, str]]:
    """The task's linked requirements whose document is enforcing, and each one's document."""
    rows = (
        await session.execute(
            select(SpecRequirement, SpecDocument)
            .join(TaskRequirementLink, TaskRequirementLink.requirement_id == SpecRequirement.id)
            .join(SpecDocument, SpecDocument.id == SpecRequirement.document_id)
            .where(TaskRequirementLink.task_id == task.id)
        )
    ).all()
    gated = [
        requirement
        for requirement, document in rows
        if (document.rigor or spec_rigor.SKETCH) == spec_rigor.GATE
    ]
    rigors = {document.id: (document.rigor or spec_rigor.SKETCH) for _, document in rows}
    return gated, rigors


async def _check_mergeable(session: AsyncSession, task: Task, refusal: GateRefusal) -> None:
    """Add a refusal where the task's work would not merge into the project's main branch.

    Deliberately **not** conditional on rigor. Rigor is a claim about how well the work must be
    proven; this is a claim about whether it can go where approval puts it. A conflicting branch
    approved at `sketch` would record an approval that silently integrates nothing.

    Every "cannot check" path here is silent, not a refusal: no configured main branch, no
    repository, no accepted commit, an unavailable workspace. Approval must never be blocked by the
    *absence* of an integration, only by one that would fail.
    """
    from . import project_workspace, task_integration
    from .db.models import Project

    project = await session.get(Project, task.project_id)
    if project is None or not project.main_branch:
        return

    try:
        workspace = await project_workspace.resolve_project_workspace(session, task.project_id)
    except Exception:
        # An unreachable workspace is a reason to not know, never a reason to refuse.
        return

    root = workspace.root
    if not task_integration.is_repository(root):
        return
    if not task_integration.branch_exists(root, project.main_branch):
        return

    for target in await task_integration.integration_targets(session, task):
        paths = task_integration.would_conflict(root, target.commit_sha, project.main_branch)
        if paths:
            refusal.unmergeable.append(
                {
                    "commit_sha": target.commit_sha,
                    "source_branch": target.branch,
                    "target_branch": project.main_branch,
                    "paths": paths,
                }
            )


async def evaluate(session: AsyncSession, task: Task) -> tuple[GateRefusal, str]:
    """`(refusal, policy_digest)` for moving this task to `approved`.

    A task linked to nothing is unaffected, and so is one whose documents are all
    sketches — the default blocks nothing, and it has to, or the change would
    arrive as a barrier nobody asked for.
    """
    refusal = GateRefusal()
    await _check_mergeable(session, task, refusal)

    gated, rigors = await _gated_requirements(session, task)
    if not gated:
        return refusal, ""

    by_document: Dict[str, List[SpecRequirement]] = {}
    for requirement in gated:
        by_document.setdefault(requirement.document_id, []).append(requirement)

    wanted = {requirement.id for requirement in gated}
    policy: List[Dict[str, Any]] = []

    for document_id in by_document:
        report = await requirement_coverage.requirement_coverage(
            session, task.project_id, document_id=document_id, include_retired=True
        )
        for entry in report.requirements:
            if entry.requirement_id not in wanted:
                continue
            policy.append(
                {
                    "identifier": entry.identifier,
                    "state": entry.state,
                    "integration": entry.integration,
                    "rigor": rigors.get(document_id, spec_rigor.SKETCH),
                }
            )
            if entry.state != SATISFIED:
                refusal.blocking.append(
                    {
                        "identifier": entry.identifier,
                        "requirement_id": entry.requirement_id,
                        "state": entry.state,
                        "remedy": REMEDY.get(entry.state, "it is not verified"),
                    }
                )
        for entry in report.diagnostics:
            if entry.requirement_id not in wanted:
                continue
            # Broken, not unverified. A gate refuses on it separately, because "this requirement is
            # unverified" would send someone to record evidence for something that cannot hold any.
            refusal.diagnostics.append(
                {
                    "identifier": entry.identifier,
                    "requirement_id": entry.requirement_id,
                    "problem": entry.problem,
                }
            )
            policy.append(
                {
                    "identifier": entry.identifier,
                    "state": "invalid",
                    "integration": "not_applicable",
                    "rigor": rigors.get(document_id, spec_rigor.SKETCH),
                }
            )

    return refusal, spec_rigor.policy_digest(policy)
