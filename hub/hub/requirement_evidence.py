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
import re
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
    Run,
    SpecRequirement,
)
from .project_workspace import ProjectWorkspace
from .spec_lifecycle import Actor
from .subprocess_windows import no_console_kwargs
from .utils import short_id

AWAITING = "awaiting"
ACCEPTED = "accepted"
REJECTED = "rejected"

# Where artifacts go, beneath the project directory. A tree an operator can open, diff, move and
# archive with ordinary tools — which is most of why the database does not hold the content.
EVIDENCE_ROOT = "evidence"


class EvidenceRefusedError(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """Something that may not be recorded or decided, with the reason stated.

    `http_status` is how a refusal that is *not* about authority overrides a route's default. The
    decision routes answer 403, which is right for the two capability refusals — no grant, and an
    agent deciding about its own work — and wrong for a malformed enum. An agent reading the status
    code rather than the body concluded it lacked permission and stopped retrying, when all it had
    to do was spell the value correctly (`scripts/drive/FINDINGS.md`, F8). None means "whatever the
    route would have sent", so adding a refusal never silently changes an existing one.
    """

    def __init__(self, message: str, *, code: str, http_status: Optional[int] = None) -> None:
        self.code = code
        self.http_status = http_status
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

    The footprint is read *before* the row is created, because it is half of what says whether this
    piece has already been recorded — see `duplicate_of`.

    **An operator whose `locator` names a commit is footprinted at that commit** (finding F71), not
    at whatever their checkout is sitting on. See `_take_footprint`.
    """
    if requirement.state != "active":
        raise EvidenceRefusedError(
            f"{requirement.identifier} is retired; there is nothing left to demonstrate",
            code="requirement_retired",
        )

    if task_id is None:
        # The run already knows its task, so an agent that did not repeat it is not ambiguous --
        # only quiet. Without this the row lands with `task_id` NULL and `commit_for_task_review`,
        # which selects on that column, reports the task as having no evidence at all (F74).
        task_id = await task_bound_to_run(session, actor.run_id)

    taken: Optional[Footprint] = None
    if workspace is not None:
        # Design D7: the directory this actor's run was actually given, when there was a run.
        taken = _take_footprint(
            workspace, actor, locator, await recorded_workspace_dir(session, actor.run_id)
        )
        already = await duplicate_of(
            session,
            requirement,
            task_id=task_id,
            commit_sha=taken.commit_sha,
            actor=actor,
        )
        if already is not None:
            raise EvidenceRefusedError(
                f"{already.id} already records evidence for {requirement.identifier} on this task "
                f"at this commit, and is {already.review_state}. Recording the same demonstration "
                f"twice makes the reviewer decide once per copy and overstates "
                f"{requirement.identifier}'s evidence count. If the wording is wrong, say so on "
                f"that piece; if the work has moved on, commit it first so the new evidence names "
                f"the commit it demonstrates.",
                code="duplicate_evidence",
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
        await capture_footprint(session, evidence, workspace, taken=taken)

    return evidence


async def duplicate_of(
    session: AsyncSession,
    requirement: SpecRequirement,
    *,
    task_id: Optional[str],
    commit_sha: Optional[str],
    actor: Optional[Actor] = None,
) -> Optional[RequirementEvidence]:
    """The evidence a new piece would merely repeat, if there is one.

    Same requirement, same task, same commit, **same actor** is the narrowest key that means "this
    demonstrates nothing the record does not already hold": the requirement fixes what is being
    shown, the task fixes which piece of work is showing it, the commit fixes the state of the code
    it was shown against, and the actor fixes whose demonstration it is. Observed live — `builder`
    recorded FR-1 unprompted on its first turn and again when asked, near-identical prose, both
    stored, both `awaiting`, coverage reading `evidence_count: 2, accepted_count: 0`
    (`scripts/drive/FINDINGS.md`, F7).

    **Actor is in the key because a confirmation is not a copy** (F75). A review turn runs in a
    detached checkout of the very commit under review, so a reviewer that checks the work itself
    produces the same requirement, task and commit as the author it is checking — and without this
    the one actor whose evidence the record most needs is the one refused. That case was
    unreachable while agent evidence carried no task at all (F74) and appeared the moment it did.

    Note the existing `digest` column is *not* this check and never was. It pins the requirement's
    wording at production time, which is the mechanism behind staleness — a different and
    well-designed thing that happens to be equal across duplicates for the same reason it is equal
    across two genuinely distinct demonstrations.

    Silent — returns None — where any part of the key is unknown. A project with no repository has
    no commit, and evidence recorded against no task has nothing to be a second copy *of*; guessing
    in either case would refuse a first piece of evidence, which is far worse than accepting a
    second.

    A `rejected` piece never matches. It was judged inadequate, and a re-record at the same commit
    with a better summary is the honest response to that judgement rather than a duplicate of it.
    """
    if not task_id or not commit_sha or actor is None:
        return None
    result = await session.execute(
        select(RequirementEvidence)
        .join(EvidenceFootprint, EvidenceFootprint.evidence_id == RequirementEvidence.id)
        .where(RequirementEvidence.requirement_id == requirement.id)
        .where(RequirementEvidence.task_id == task_id)
        .where(EvidenceFootprint.commit_sha == commit_sha)
        .where(RequirementEvidence.actor_kind == actor.kind)
        .where(RequirementEvidence.actor == (actor.name or ""))
        .where(RequirementEvidence.review_state != REJECTED)
        .order_by(RequirementEvidence.produced_at, RequirementEvidence.id)
        .limit(1)
    )
    return result.scalars().first()


def _take_footprint(
    workspace: ProjectWorkspace,
    actor: Actor,
    locator: str,
    recorded_dir: Optional[str] = None,
) -> Footprint:
    """The footprint this evidence should carry, given who is recording it and what they named.

    **Finding F71, found live 2026-08-27.** An operator recorded evidence whose `locator` was the
    full sha of the commit carrying the fix, and the footprint captured their own checkout's `HEAD`
    instead — an unrelated earlier commit, still carrying the bug. Nothing refused and nothing
    warned: `commit_for_task_review` then returned that commit with `resolved: True`, so a review
    turn would have been checked out to the pre-fix tree with total, unearned confidence, and
    `reachable_from_main: 1` would have told `task_integration` the fix was already on `master`. The
    error runs the other way just as easily — a checkout *ahead* of the described work footprints a
    fix as demonstrated when it is not.

    So a named commit wins over the checkout, because it is the operator's own explicit statement of
    which tree the evidence is about, and the checkout was only ever a fallback for when nothing
    said otherwise. `footprint_root`'s docstring makes that fallback's reasoning explicit — *"if
    they are on a feature branch that is where they observed the thing"* — and a locator naming a
    commit is strictly better information than that inference.

    **Refuses rather than falling back** when the locator names a commit this repository does not
    have. Falling back to `HEAD` there would reproduce F71 exactly, in the one case where the
    operator has said most clearly what they meant; and a footprint that silently describes a
    different tree than the one named is worse than no evidence at all, because the review path
    trusts it.

    **Operators only.** An agent's footprint is deliberately its worktree's `HEAD`, uncommitted work
    and all, and `restamp_run_footprints` corrects it once the commit exists — a locator-named
    commit would fight that mechanism rather than improve it.
    """
    root = footprint_root(workspace, actor.kind, actor.name or "", recorded_dir)
    named = locator_commit(locator) if actor.kind == "operator" else None
    if named is None:
        return read_footprint(root)

    resolved = _git(root, "rev-parse", "--verify", f"{named}^{{commit}}")
    if resolved is None:
        raise EvidenceRefusedError(
            f"this evidence names commit {named} as its locator, and that commit is not in this "
            f"project's repository. Recording it would footprint the checkout's own HEAD instead, "
            f"which describes a different tree than the one named — and a review of this task "
            f"would then be handed that tree as though it were the work. Fetch or push the commit "
            f"first, or name something other than a commit in the locator.",
            code="locator_commit_unknown",
        )
    return read_footprint(root, at=resolved)


def footprint_root(
    workspace: ProjectWorkspace,
    actor_kind: str,
    actor: str,
    recorded_dir: Optional[str] = None,
) -> Path:
    """The directory whose HEAD is the work this evidence is about.

    An agent works in its own checkout, on its own branch. Reading the *project* directory instead
    names whatever the operator happens to be sitting on — which on a fresh project is the main
    branch, so the footprint claims the work is already in the product and integration then merges a
    commit into itself. That was observed live on 2026-08-13.

    The operator keeps the project directory, and that is right rather than merely convenient: it is
    their own checkout, and if they are on a feature branch that is where they observed the thing.
    It is also safe by construction — git refuses to check out a branch already checked out in a
    linked worktree, so the project checkout can never *be* an agent's branch.

    **`recorded_dir` is the directory the run actually executed in (`Run.workspace_dir`, design
    D7), and it wins when it still exists.** Passed in as a plain value rather than looked up here,
    for the same reason D1 passes the base and prerequisite commits into `worktrees`: the answer
    depends on database state and this function is synchronous and git-only.

    It replaces a derivation that has no correct form once work is isolated per task. Deriving from
    the agent's name gives the per-agent checkout, which is not where a task-bound turn ran; and
    **it is already wrong today for a reviewer**, whose evidence is footprinted at its own worktree
    rather than at the detached review checkout it actually inspected. A recorded fact answers the
    task workspace, the per-agent workspace, a grandfathered task, a review checkout and a project
    with no repository with one rule.

    The fallback is deliberate and load-bearing in two cases at once: a run predating the column
    (never recorded), and a task checkout that has since been **released**, whose directory is
    gone by design (D5). Both land on the behaviour this function already had rather than on a
    path that does not exist.
    """
    if recorded_dir:
        candidate = Path(recorded_dir)
        if candidate.is_dir():
            return candidate
    if actor_kind != "agent" or not actor:
        return workspace.root
    return worktrees.existing_worktree(workspace.root, actor) or workspace.root


async def recorded_workspace_dir(session: AsyncSession, run_id: Optional[str]) -> Optional[str]:
    """The directory a run executed in, or None when there is no run or it predates the column."""
    if not run_id:
        return None
    return await session.scalar(select(Run.workspace_dir).where(Run.id == run_id))


async def task_bound_to_run(session: AsyncSession, run_id: Optional[str]) -> Optional[str]:
    """The task a run was started for, or None when there is no run and for an operator.

    An operator has no run, so this is how the fallback stays a fallback: their evidence is still
    task-less unless they say otherwise, which is what `POST /spec/evidence` has always meant for
    them.
    """
    if not run_id:
        return None
    return await session.scalar(select(Run.task_id).where(Run.id == run_id))


def _apply_footprint(
    session: AsyncSession,
    evidence: RequirementEvidence,
    taken: Footprint,
    existing: Optional[EvidenceFootprint] = None,
) -> EvidenceFootprint:
    """Write *taken* onto *evidence*'s footprint, creating the row where there is none.

    One place maps a `Footprint` onto a row, so capture and re-capture cannot come to disagree about
    what a footprint means. `restamp_run_footprints` needs the create branch as well as the update
    one: where the workspace could not be resolved at record time the evidence exists with no
    footprint at all.
    """
    row = existing
    if row is None:
        row = EvidenceFootprint(
            id=f"efp-{short_id()}",
            project_id=evidence.project_id,
            evidence_id=evidence.id,
        )
        session.add(row)
    row.kind = taken.kind
    row.commit_sha = taken.commit_sha
    row.branch = taken.branch
    row.entries = taken.entries or {}
    row.reachable_from_main = taken.reachable_from_main
    return row


async def capture_footprint(
    session: AsyncSession,
    evidence: RequirementEvidence,
    workspace: ProjectWorkspace,
    *,
    taken: Optional[Footprint] = None,
) -> EvidenceFootprint:
    """What the implementation looked like when this evidence was produced.

    The root is derived from the evidence row rather than passed in, so the footprint and the
    evidence it hangs off cannot come to disagree about whose work is being described — and any
    later caller (a backfill, a re-capture) gets the right answer without knowing this rule exists.

    Mid-turn this necessarily names the commit the turn *started* from, because the agent's work is
    still uncommitted — see `restamp_run_footprints`, which corrects it once the commit exists.

    `taken` is for the one caller that has already read it: `record` needs the commit *before* the
    row exists, to answer the duplicate check, and re-reading here would spend a second set of git
    calls to learn the same answer. It is the same read, derived from the same root — `record`
    passes the actor it is about to write onto the row.
    """
    if taken is None:
        # Resolved from the evidence row, keeping this function's stated principle: a later caller
        # gets the right answer without knowing the rule exists (design D7).
        taken = read_footprint(
            footprint_root(
                workspace,
                evidence.actor_kind,
                evidence.actor,
                await recorded_workspace_dir(session, evidence.run_id),
            )
        )
    return _apply_footprint(session, evidence, taken)


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            **no_console_kwargs(),
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


def read_footprint(root: Path, *, at: Optional[str] = None) -> Footprint:
    """The footprint of a workspace, by whichever of the two shapes applies.

    A project without a repository is a supported first-class case
    (`2026-08-12-run-without-a-git-repository`), and a git-only implementation
    would leave every one of them permanently unverifiable — so both ship
    together rather than one now and one later.

    Note `entries` is the *whole* tree, not the changed paths the model documents. That mismatch is
    real and pre-existing: it means one unrelated commit on the compared ref drifts every requirement
    at once. Fixing it is a separate change, deliberately, so that it cannot mask this one.

    `at` describes a commit the caller *named* rather than the one the checkout happens to be
    sitting on (finding F71). It must already be resolved — `record` verifies it and refuses rather
    than falling back, because a silent fallback to `HEAD` is the whole defect.
    """
    commit = _git(root, "rev-parse", at or "HEAD")
    if commit:
        branch = (
            _branch_at(root, commit)
            if at
            else (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "")
        )
        return Footprint(
            kind="git",
            commit_sha=commit,
            branch=branch,
            entries=tree_entries(root, commit) or {},
            reachable_from_main=is_reachable_from_main(root, commit),
        )

    if at:
        # A named commit in a directory with no repository at all. Nothing can be said about it, and
        # a path-hash footprint of the working tree would describe something else entirely.
        return Footprint(kind="paths", entries={}, reachable_from_main=None)

    return Footprint(kind="paths", entries=hash_tree(root), reachable_from_main=None)


#: A locator that is a bare git object name, and nothing else. Deliberately narrow: `locator` is a
#: free-form field that usually holds a *path* (`evidence_locator_exists` resolves it as one), so
#: anything looser would start reading file names as revisions. A branch name is not accepted for
#: exactly that reason — `cart.py` and `feature/x` are both plausible paths, and guessing which is
#: meant is the kind of judgement this product does not make on the operator's behalf.
_COMMIT_ISH = re.compile(r"^[0-9a-f]{7,40}$")


def locator_commit(locator: str) -> Optional[str]:
    """The commit *locator* names, or `None` when it names something that is not a commit."""
    candidate = (locator or "").strip()
    return candidate if _COMMIT_ISH.match(candidate) else None


def _branch_at(root: Path, commit: str) -> str:
    """The local branch whose tip is exactly *commit*, or `""` when that is not one branch.

    Only an exact tip counts. A commit in the middle of a branch's history belongs to every branch
    that descends from it, and picking one would put a guess into the field
    `task_integration.integration_targets` groups by. `""` is already this module's word for "names
    no line of work" — `evidence_drift` skips such a footprint rather than treating it as drift —
    so the unknown case has an established, honest meaning rather than a new one.
    """
    listed = _git(root, "branch", "--format=%(refname:short)", "--points-at", commit)
    if not listed:
        return ""
    names = [line.strip() for line in listed.splitlines() if line.strip()]
    return names[0] if len(names) == 1 else ""


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
            **no_console_kwargs(),
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
        # Names what would work, the way `model_catalog.validate_overrides` names the permitted
        # `permission_mode` values. The product's own stated principle — "a refusal the author
        # cannot act on produces a retry loop, which is the failure mode the prose contract had"
        # (`spec_payload.py`) — was honoured there and not here.
        raise EvidenceRefusedError(
            f"{decision!r} is not a permitted evidence decision "
            f"(permitted: {', '.join(sorted((ACCEPTED, REJECTED)))})",
            code="unknown_decision",
            # A malformed enum is a validation error, not an authorisation one.
            http_status=422,
        )

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
        .order_by(EvidenceReview.sequence)
    )
    return list(result.scalars().all())


@dataclass
class EarlierCommit:
    """A commit an *earlier* piece of evidence for the same task named."""

    commit_sha: str
    evidence_id: str
    produced_at: datetime


@dataclass
class ReviewTarget:
    """Which commit a review turn is about, or why there is not one.

    A result rather than a raised exception, deliberately (task 2.2). "This task cannot be reviewed
    yet" is an ordinary answer that the caller renders to an operator, not a fault — and a refusal
    carrying its own reason cannot be caught and discarded by a generic handler on the way out.
    """

    commit_sha: Optional[str] = None
    evidence_id: Optional[str] = None
    branch: Optional[str] = None
    #: Distinct commits named by earlier evidence for the same task, oldest first. Design D5: the
    #: reviewer is *told* the work moved rather than silently handed the newest commit — one that
    #: knows can ask why, and one that does not cannot.
    earlier_commits: List[EarlierCommit] = None  # type: ignore[assignment]
    refusal: Optional[str] = None

    def __post_init__(self) -> None:
        if self.earlier_commits is None:
            self.earlier_commits = []

    @property
    def resolved(self) -> bool:
        return self.commit_sha is not None


async def commit_for_task_review(session: AsyncSession, task_id: str) -> ReviewTarget:
    """The commit to check out to review *task_id*, per design D5.

    **The most recent evidence wins.** A task can carry several evidence rows naming different
    commits — observed live, `ev-42cad5d2` and `ev-5d0273ad` on the same task — so this needs a rule
    rather than an assumption.

    Rejected while designing this: the task's latest run snapshot. It is the same commit in the
    ordinary case and a different one whenever a run ended without recording evidence, and in that
    case there is nothing to review anyway.
    """
    result = await session.execute(
        select(RequirementEvidence, EvidenceFootprint)
        .join(EvidenceFootprint, EvidenceFootprint.evidence_id == RequirementEvidence.id)
        .where(RequirementEvidence.task_id == task_id)
        .order_by(RequirementEvidence.produced_at, RequirementEvidence.id)
    )
    rows = list(result.all())

    naming_a_commit = [
        (evidence, footprint)
        for evidence, footprint in rows
        if footprint.commit_sha and footprint.commit_sha.strip()
    ]

    if not naming_a_commit:
        # Two different states, and an operator can act on only one of them, so they are not
        # collapsed into one message.
        if rows:
            reason = (
                f"task {task_id} has recorded evidence, but none of it names a commit — the "
                "project may not be a git repository, so there is no tree to check out for review"
            )
        else:
            reason = (
                f"task {task_id} has no recorded evidence, so there is no commit to review. "
                "Evidence naming a commit is what a review turn is given."
            )
        return ReviewTarget(refusal=reason)

    newest_evidence, newest_footprint = naming_a_commit[-1]
    newest_sha = newest_footprint.commit_sha.strip()

    earlier: List[EarlierCommit] = []
    seen = {newest_sha}
    for evidence, footprint in naming_a_commit[:-1]:
        sha = footprint.commit_sha.strip()
        if sha in seen:
            continue
        seen.add(sha)
        earlier.append(
            EarlierCommit(commit_sha=sha, evidence_id=evidence.id, produced_at=evidence.produced_at)
        )

    return ReviewTarget(
        commit_sha=newest_sha,
        evidence_id=newest_evidence.id,
        branch=newest_footprint.branch,
        earlier_commits=earlier,
    )


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


async def restamp_run_footprints(
    session: AsyncSession,
    *,
    project_id: str,
    run_id: str,
    root: Path,
    commit_sha: Optional[str] = None,
    main_branch: Optional[str] = None,
) -> int:
    """Re-point a finished run's footprints at the commit that actually contains its work.

    An agent records evidence *during* its turn, while its work is still uncommitted, so
    `read_footprint` can only ever name the commit the branch pointed at when the turn started. The
    commit containing the work is made by `worktrees.snapshot_worktree` after the process exits.
    The window is structural — there is no moment at which recording could observe the right sha —
    so the record is corrected once the commit exists.

    Left uncorrected this is worse than a wrong label. On a new project the pre-turn commit is
    usually already on the main line, so the row is written `reachable_from_main=True` and evidence
    for code that does not exist reads as already shipped. `task_integration.integration_targets`
    merges on exactly this field.

    Every row of the run is re-pointed, whatever has since been decided about it. The commit is a
    fact about where the work is, not a judgement about the work; sparing accepted rows would leave
    approval merging a commit that does not contain the work, and would make correctness depend on
    how quickly a reviewer clicked. `EvidenceReview` is append-only and is not touched.

    `commit_sha` of `None` is *not* a reason to skip. `snapshot_worktree` returns `None` when nothing
    was dirty, which happens both when the agent committed its own work mid-turn — where the
    record-time footprint is still stale, because it predates that commit — and when the agent
    changed nothing, where it is already right. So fall back to the checkout's current `HEAD` and let
    the second case fall out through the unchanged-commit guard.

    The footprint is read **once per run**, not once per row: a turn's evidence shares one checkout
    and one commit, and looping `capture_footprint` would spend three git calls per row.
    """
    target = commit_sha or _git(root, "rev-parse", "HEAD")
    if not target:
        return 0

    rows = (
        await session.execute(
            select(RequirementEvidence, EvidenceFootprint)
            .outerjoin(
                EvidenceFootprint,
                EvidenceFootprint.evidence_id == RequirementEvidence.id,
            )
            .where(
                RequirementEvidence.project_id == project_id,
                RequirementEvidence.run_id == run_id,
                RequirementEvidence.actor_kind == "agent",
            )
        )
    ).all()
    if not rows:
        return 0

    # Deliberately a *fresh* answer, and free to be `False`. `refresh_reachability` is upgrade-only
    # because for a fixed commit the answer only travels one way — but this is a different commit,
    # and carrying over its predecessor's `True` is precisely the poison being removed here.
    taken = Footprint(
        kind="git",
        commit_sha=target,
        branch=_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "",
        entries=tree_entries(root, target) or {},
        reachable_from_main=(
            is_reachable_from(root, target, main_branch)
            if main_branch
            else is_reachable_from_main(root, target)
        ),
    )

    updated = 0
    for evidence, footprint in rows:
        if footprint is not None and footprint.kind == "git" and footprint.commit_sha == target:
            continue
        _apply_footprint(session, evidence, taken, footprint)
        updated += 1
    return updated


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
