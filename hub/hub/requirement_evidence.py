"""Recording evidence, deciding it, and noticing when the ground moves under it.

An agent's assertion is not evidence. But that rule was originally aimed at the
wrong half: a stored test artifact is a **fact**, and it is the claim about what
it proves that needs judging. So producing evidence is open to anyone, and
**accepting** it is the controlled act.

Three rules follow, and each exists because of a specific way this goes wrong:

- **Agent-recorded evidence enters `awaiting`.** A run that reports "I verified
  it" produces a record awaiting review, never a verified requirement. A careful
  agent and a careless one report success in the same words with the same
  authority, and the record has to be able to tell them apart.
- **An agent may not accept evidence it produced.** Distinctness is on *agent*
  identity, not run identity — "a different run" is satisfied by an agent simply
  continuing its own work, which is how `task-lifecycle-governance` was first
  walked around in live use.
- **A project with no granted agent defers to the operator**, and that is a
  supported way to work rather than a degraded one. Someone may reasonably want
  to be the bottleneck.

Evidence is pinned to the requirement's digest at the moment it was produced.
That pin is the entire mechanism behind staleness: without it, a reworded
requirement keeps its old evidence looking current, and the difference is
unrecoverable after the fact.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import worktrees
from .db.models import (
    EVIDENCE_RETENTION_POLICIES,
    Agent,
    EvidenceFootprint,
    EvidenceReview,
    RequirementDrift,
    RequirementEvidence,
    SpecRequirement,
)
from .project_workspace import ProjectWorkspace
from .spec_lifecycle import Actor
from .utils import short_id

AWAITING = "awaiting"
ACCEPTED = "accepted"
REJECTED = "rejected"

# Where artifacts go, beneath the project directory. A tree an operator can open, diff, move and
# archive with ordinary tools — which is most of why the database does not hold the content.
EVIDENCE_ROOT = "evidence"


class EvidenceRefusedError(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """Something that may not be recorded or decided, with the reason stated."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class Footprint:
    kind: str
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    entries: Dict[str, str] = None  # type: ignore[assignment]
    reachable_from_main: Optional[bool] = None


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


async def record(
    session: AsyncSession,
    requirement: SpecRequirement,
    *,
    kind: str,
    actor: Actor,
    locator: str = "",
    summary: str = "",
    task_id: Optional[str] = None,
    workspace: Optional[ProjectWorkspace] = None,
) -> RequirementEvidence:
    """Store one piece of evidence against the requirement's *current* digest.

    An operator recording evidence is recording their own observation, so it is
    accepted on arrival — there is nobody else for it to await. An agent's lands
    `awaiting` regardless of how confidently it was described.
    """
    if requirement.state != "active":
        raise EvidenceRefusedError(
            f"{requirement.identifier} is retired; there is nothing left to demonstrate",
            code="requirement_retired",
        )

    evidence = RequirementEvidence(
        id=f"ev-{short_id()}",
        project_id=requirement.project_id,
        requirement_id=requirement.id,
        digest=requirement.digest,
        digest_version=requirement.digest_version,
        kind=kind,
        locator=locator,
        summary=summary,
        actor_kind=actor.kind,
        actor=actor.name or "",
        run_id=actor.run_id,
        task_id=task_id,
        review_state=ACCEPTED if actor.kind == "operator" else AWAITING,
    )
    session.add(evidence)
    await session.flush()

    if actor.kind == "operator":
        session.add(
            EvidenceReview(
                id=f"evr-{short_id()}",
                project_id=evidence.project_id,
                evidence_id=evidence.id,
                decision=ACCEPTED,
                actor_kind=actor.kind,
                actor=actor.name or "",
                run_id=actor.run_id,
                reason="recorded by the operator",
            )
        )

    if workspace is not None:
        await capture_footprint(session, evidence, workspace)

    return evidence


def footprint_root(workspace: ProjectWorkspace, actor_kind: str, actor: str) -> Path:
    """The directory whose HEAD is the work this evidence is about.

    An agent works in its own checkout, on its own branch. Reading the *project* directory instead
    names whatever the operator happens to be sitting on — which on a fresh project is the main
    branch, so the footprint claims the work is already in the product and integration then merges a
    commit into itself. That was observed live on 2026-08-13.

    The operator keeps the project directory, and that is right rather than merely convenient: it is
    their own checkout, and if they are on a feature branch that is where they observed the thing.
    It is also safe by construction — git refuses to check out a branch already checked out in a
    linked worktree, so the project checkout can never *be* an agent's branch.
    """
    if actor_kind != "agent" or not actor:
        return workspace.root
    return worktrees.existing_worktree(workspace.root, actor) or workspace.root


async def capture_footprint(
    session: AsyncSession, evidence: RequirementEvidence, workspace: ProjectWorkspace
) -> EvidenceFootprint:
    """What the implementation looked like when this evidence was produced.

    The root is derived from the evidence row rather than passed in, so the footprint and the
    evidence it hangs off cannot come to disagree about whose work is being described — and any
    later caller (a backfill, a re-capture) gets the right answer without knowing this rule exists.
    """
    taken = read_footprint(footprint_root(workspace, evidence.actor_kind, evidence.actor))
    row = EvidenceFootprint(
        id=f"efp-{short_id()}",
        project_id=evidence.project_id,
        evidence_id=evidence.id,
        kind=taken.kind,
        commit_sha=taken.commit_sha,
        branch=taken.branch,
        entries=taken.entries or {},
        reachable_from_main=taken.reachable_from_main,
    )
    session.add(row)
    return row


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def tree_entries(root: Path, ref: str) -> Optional[Dict[str, str]]:
    """`{path: blob id}` at *ref*, or `None` when *ref* does not resolve here.

    One parser, two callers: capture reads `HEAD`, drift reads the branch a stored footprint names.
    Two parses would eventually disagree about what a footprint means.
    """
    listing = _git(root, "ls-tree", "-r", ref)
    if listing is None:
        return None
    entries: Dict[str, str] = {}
    for line in listing.splitlines():
        # "<mode> blob <sha>\t<path>"
        head, _, path = line.partition("\t")
        parts = head.split()
        if len(parts) == 3 and path:
            entries[path] = parts[2]
    return entries


def read_footprint(root: Path) -> Footprint:
    """The footprint of a workspace, by whichever of the two shapes applies.

    A project without a repository is a supported first-class case
    (`2026-08-12-run-without-a-git-repository`), and a git-only implementation
    would leave every one of them permanently unverifiable — so both ship
    together rather than one now and one later.

    Note `entries` is the *whole* tree, not the changed paths the model documents. That mismatch is
    real and pre-existing: it means one unrelated commit on the compared ref drifts every requirement
    at once. Fixing it is a separate change, deliberately, so that it cannot mask this one.
    """
    commit = _git(root, "rev-parse", "HEAD")
    if commit:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or ""
        return Footprint(
            kind="git",
            commit_sha=commit,
            branch=branch,
            entries=tree_entries(root, "HEAD") or {},
            reachable_from_main=is_reachable_from_main(root, commit),
        )

    return Footprint(kind="paths", entries=hash_tree(root), reachable_from_main=None)


# The names a project's main line of work goes by, in the order they are tried. Nothing here guesses
# beyond this list: an answer of "no main branch found" is reported as unknown rather than as "not
# integrated", because those are different facts and only one of them is about the work.
MAIN_BRANCH_NAMES = ("main", "master")


def is_reachable_from(root: Path, commit: str, branch: str) -> Optional[bool]:
    """Whether `commit` is an ancestor of `branch`.

    `None` when `branch` does not resolve in this repository — unknown, which is
    not the same as `False`.

    Split out from `is_reachable_from_main` so that integration and reporting ask
    the same question of the same code. Integration targets a *configured*
    branch; reporting falls back to a guess. Two implementations of "is it
    already in there?" would eventually answer differently, and the one that
    mattered would be whichever the merge consulted.
    """
    if _git(root, "rev-parse", "--verify", branch) is None:
        return None
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, branch],
            cwd=str(root),
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.returncode == 0


def is_reachable_from_main(root: Path, commit: str) -> Optional[bool]:
    """Whether `commit` is an ancestor of the project's main branch.

    `None` when there is no main branch to compare against — unknown, which is
    not the same as `False`. Reporting "not integrated" for a project that simply
    does not use a main branch would be an accusation about a choice.
    """
    for name in MAIN_BRANCH_NAMES:
        answer = is_reachable_from(root, commit, name)
        if answer is not None:
            return answer
    return None


# A tree walk is bounded so a project directory that happens to contain a large build output cannot
# turn recording one screenshot into a minutes-long stat storm.
MAX_HASHED_FILES = 2000
SKIP_DIRECTORIES = {".git", ".agentweave", "node_modules", "__pycache__", ".venv", "dist", "build"}


def hash_tree(root: Path) -> Dict[str, str]:
    """A content hash per file, for a project that is not a repository."""
    hashes: Dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if len(hashes) >= MAX_HASHED_FILES:
            break
        if not path.is_file():
            continue
        if any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts):
            continue
        try:
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        except OSError:
            continue
    return hashes


# ---------------------------------------------------------------------------
# Deciding
# ---------------------------------------------------------------------------


async def may_accept(session: AsyncSession, project_id: str, actor: Actor) -> bool:
    """Whether this actor may accept evidence at all."""
    if actor.kind == "operator":
        return True
    if actor.kind != "agent" or not actor.name:
        return False
    agent = (
        (
            await session.execute(
                select(Agent).where(Agent.project_id == project_id, Agent.name == actor.name)
            )
        )
        .scalars()
        .first()
    )
    return bool(agent and agent.can_accept_evidence)


async def decide(
    session: AsyncSession,
    evidence: RequirementEvidence,
    *,
    decision: str,
    actor: Actor,
    reason: str = "",
) -> EvidenceReview:
    """Accept or reject one piece of evidence, and record who decided.

    The two refusals here are the whole capability model: an actor without the
    grant cannot decide, and an agent cannot decide about its own work. Both are
    checked on agent *identity*, because every turn an agent takes is a new run
    and a run-based check is satisfied by an agent simply continuing.
    """
    if decision not in (ACCEPTED, REJECTED):
        raise EvidenceRefusedError(f"unknown decision {decision!r}", code="unknown_decision")

    if not await may_accept(session, evidence.project_id, actor):
        raise EvidenceRefusedError(
            "accepting evidence is the operator's, or an agent the operator has granted it. "
            "A project that has granted no agent still has the operator.",
            code="acceptance_not_granted",
        )

    if (
        actor.kind == "agent"
        and evidence.actor_kind == "agent"
        and actor.name
        and actor.name == evidence.actor
    ):
        raise EvidenceRefusedError(
            "an agent cannot accept evidence it produced; another agent or the operator decides",
            code="self_acceptance",
        )

    review = EvidenceReview(
        id=f"evr-{short_id()}",
        project_id=evidence.project_id,
        evidence_id=evidence.id,
        decision=decision,
        actor_kind=actor.kind,
        actor=actor.name or "",
        run_id=actor.run_id,
        reason=reason,
    )
    session.add(review)
    # Materialised from the append-only reviews so coverage is a join rather than a correlated
    # subquery. `evidence_reviews` is what governs; this follows it.
    evidence.review_state = decision
    return review


async def reviews_for(session: AsyncSession, evidence_id: str) -> List[EvidenceReview]:
    result = await session.execute(
        select(EvidenceReview)
        .where(EvidenceReview.evidence_id == evidence_id)
        .order_by(EvidenceReview.created_at, EvidenceReview.id)
    )
    return list(result.scalars().all())


async def for_requirement(session: AsyncSession, requirement_id: str) -> List[RequirementEvidence]:
    result = await session.execute(
        select(RequirementEvidence)
        .where(RequirementEvidence.requirement_id == requirement_id)
        .order_by(RequirementEvidence.produced_at, RequirementEvidence.id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def retention_is_valid(policy: str) -> bool:
    return policy in EVIDENCE_RETENTION_POLICIES


async def mark_artifact_removed(
    session: AsyncSession, evidence: RequirementEvidence
) -> RequirementEvidence:
    """Note that the artifact is gone. The record stays, and says so.

    Removing an artifact never removes its evidence record: that something was
    verified, by whom, and against which digest is the record; the artifact is
    its attachment.
    """
    del session
    evidence.artifact_removed_at = datetime.now(timezone.utc)
    return evidence


def artifact_exists(workspace: ProjectWorkspace, evidence: RequirementEvidence) -> bool:
    if not evidence.locator:
        return True
    try:
        return workspace.resolve_relative(evidence.locator).exists()
    except Exception:
        return False


# A bound, so that a project with a long evidence history cannot turn one approval into a minutes
# long run of git calls. Distinct commits, not rows — a branch's worth of evidence usually names a
# handful of commits between them.
MAX_REACHABILITY_CHECKS = 200


async def refresh_reachability(
    session: AsyncSession,
    project_id: str,
    root: Path,
    *,
    main_branch: Optional[str] = None,
) -> int:
    """Re-answer "has this reached the main line?" for footprints that did not already say yes.

    `reachable_from_main` is written once, when evidence is recorded — and evidence is recorded
    *before* the work is integrated, so for agent evidence the answer at that moment is always "not
    yet". Without this, a requirement would report as unintegrated permanently, including the
    instant after its work was merged, and the integration fix would read as a regression.

    Only upgrades are interesting, so rows already answering `True` are skipped: work does not leave
    the main line, and re-asking would spend git calls to confirm what cannot have changed.

    Prefers the *configured* branch over the guessed one. They can disagree — a project integrating
    into `develop` has a `main` that `MAIN_BRANCH_NAMES` would find first — and the configured one
    is what integration actually targets.
    """
    rows = (
        (
            await session.execute(
                select(EvidenceFootprint).where(
                    EvidenceFootprint.project_id == project_id,
                    EvidenceFootprint.kind == "git",
                    EvidenceFootprint.commit_sha.is_not(None),
                    EvidenceFootprint.reachable_from_main.is_not(True),
                )
            )
        )
        .scalars()
        .all()
    )

    answers: Dict[str, Optional[bool]] = {}
    updated = 0
    for row in rows:
        commit = row.commit_sha or ""
        if not commit:
            continue
        if commit not in answers:
            if len(answers) >= MAX_REACHABILITY_CHECKS:
                break
            answers[commit] = (
                is_reachable_from(root, commit, main_branch)
                if main_branch
                else is_reachable_from_main(root, commit)
            )
        answer = answers[commit]
        if answer is not None and answer != row.reachable_from_main:
            row.reachable_from_main = answer
            updated += 1
    return updated


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def _changed(baseline: Dict[str, str], observed: Dict[str, str]) -> Dict[str, Any]:
    """Which of the footprinted paths no longer look the way they did."""
    moved = {
        path: {"was": fingerprint, "now": observed.get(path)}
        for path, fingerprint in (baseline or {}).items()
        if observed.get(path) != fingerprint
    }
    return moved


async def detect_drift(
    session: AsyncSession,
    project_id: str,
    workspace: ProjectWorkspace,
) -> List[RequirementDrift]:
    """Raise a candidate wherever a footprint's files moved and the requirement did not.

    Nothing here writes to a specification document, and there is no code path
    from this function to one. Overlap between a footprint and a later change is
    a signal, not proof — which is why the outcome is a question for a person
    rather than a state the requirement acquires by itself.

    **Each footprint is compared against the line of work it names**, not against one fixed
    location. Comparing an agent's footprint against the project's main line would report every file
    that agent added as a change, making every demonstrated requirement a candidate at once. That
    the work is not on the main line is already reported as an integration answer, and raising it
    again here would ask the operator the same question in two vocabularies — the thing this
    function already refuses to do for rewordings.

    Accepted consequence: once the work merges, this keeps watching the agent's branch, so a later
    change to the same files *on* the main branch is not noticed. Answering that needs the changed
    paths rather than the whole tree (see `read_footprint`), so it is deferred rather than papered
    over by switching the basis once the work is reachable — that would make the basis depend on a
    column `refresh_reachability` mutates, and drift would flip bases underneath an open candidate.
    """
    # One read per distinct ref, and `hash_tree` at most once. Also fixes a latent bug: a single
    # observation used to be applied to both footprint kinds, so a `paths` footprint in a project
    # that later became a repository was compared against git blob ids.
    trees: Dict[str, Optional[Dict[str, str]]] = {}
    paths_tree: Optional[Dict[str, str]] = None

    rows = (
        await session.execute(
            select(RequirementEvidence, EvidenceFootprint, SpecRequirement)
            .join(EvidenceFootprint, EvidenceFootprint.evidence_id == RequirementEvidence.id)
            .join(SpecRequirement, SpecRequirement.id == RequirementEvidence.requirement_id)
            .where(
                RequirementEvidence.project_id == project_id,
                RequirementEvidence.review_state == ACCEPTED,
            )
        )
    ).all()

    open_candidates = {
        row.evidence_id
        for row in (
            await session.execute(
                select(RequirementDrift).where(
                    RequirementDrift.project_id == project_id,
                    RequirementDrift.state == "candidate",
                )
            )
        )
        .scalars()
        .all()
    }

    raised: List[RequirementDrift] = []
    for evidence, footprint, requirement in rows:
        if evidence.id in open_candidates:
            continue
        # A reworded requirement is not drift: the specification moved, which is
        # already reported as stale evidence, and calling it drift as well would
        # ask the operator the same question twice in two vocabularies.
        if evidence.digest != requirement.digest:
            continue

        if footprint.kind == "git":
            ref = footprint.branch or ""
            # A footprint taken on a detached HEAD names no line of work to re-read. Unknown is not
            # drift, so it raises nothing rather than guessing at a branch.
            if not ref or ref == "HEAD":
                continue
            if ref not in trees:
                trees[ref] = tree_entries(workspace.root, ref)
            observed = trees[ref]
            # The branch is gone — released, deleted, or never pushed anywhere this checkout can
            # see. Being unable to tell is not evidence that anything moved.
            if observed is None:
                continue
        else:
            if paths_tree is None:
                paths_tree = hash_tree(workspace.root)
            observed = paths_tree

        moved = _changed(footprint.entries or {}, observed)
        if not moved:
            continue

        already = await _resolved_for(session, evidence.id)
        if already is not None and already.resolved_fingerprint == moved:
            continue

        candidate = RequirementDrift(
            id=f"drift-{short_id()}",
            project_id=project_id,
            requirement_id=requirement.id,
            evidence_id=evidence.id,
            state="candidate",
            baseline=footprint.entries or {},
            observed=moved,
            digest=requirement.digest,
        )
        session.add(candidate)
        raised.append(candidate)

    return raised


async def _resolved_for(session: AsyncSession, evidence_id: str) -> Optional[RequirementDrift]:
    result = await session.execute(
        select(RequirementDrift)
        .where(RequirementDrift.evidence_id == evidence_id, RequirementDrift.state == "resolved")
        .order_by(RequirementDrift.resolved_at.desc())
    )
    return result.scalars().first()


async def resolve_drift(
    session: AsyncSession,
    candidate: RequirementDrift,
    *,
    resolution: str,
    actor: Actor,
) -> RequirementDrift:
    """The operator's answer, recorded with what was current when they gave it.

    Recording the digest and fingerprint at resolution is what stops the same
    change being reported twice — and a resolution that did not would make the
    feature a nuisance within a day.
    """
    if actor.kind != "operator":
        raise EvidenceRefusedError(
            "whether a specification or an implementation was wrong is the operator's judgement",
            code="resolution_is_the_operators",
        )
    if resolution not in (
        "specification_updated",
        "implementation_corrected",
        "no_change_required",
    ):
        raise EvidenceRefusedError(f"unknown resolution {resolution!r}", code="unknown_resolution")

    requirement = await session.get(SpecRequirement, candidate.requirement_id)
    candidate.state = "resolved"
    candidate.resolution = resolution
    candidate.resolved_by = actor.name or "operator"
    candidate.resolved_at = datetime.now(timezone.utc)
    candidate.resolved_digest = requirement.digest if requirement else candidate.digest
    candidate.resolved_fingerprint = candidate.observed
    return candidate


async def open_drift_for(session: AsyncSession, requirement_ids: Sequence[str]) -> set:
    if not requirement_ids:
        return set()
    result = await session.execute(
        select(RequirementDrift.requirement_id).where(
            RequirementDrift.requirement_id.in_(list(requirement_ids)),
            RequirementDrift.state == "candidate",
        )
    )
    return set(result.scalars().all())
