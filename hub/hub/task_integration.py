"""Putting approved work into the product.

Approval is the moment the system records that work is good. Until this module existed, that was all
it recorded: the work stayed on the agent's branch, `master` kept whatever it had, and "approved" and
"shipped" were unrelated facts. B3 made the gap reportable (`verified, not integrated`); this closes
it.

Three rules shape everything here, and each exists because the naive version damages a repository:

**Merge a commit, never a branch.** `worktrees.branch_name` is per *agent*, so one builder's branch
carries every task it ever worked on. Merging the branch when one task is approved would ship the
others. The accepted evidence already names the commit the work was demonstrated at; that is what
goes in, and anything committed after it stays out.

**Never merge into a branch nobody named.** `requirement_evidence.MAIN_BRANCH_NAMES` guesses, and is
right to — a wrong guess in a read-only report costs an `unknown`. A wrong guess here writes commits
into a branch the operator did not choose, so the target is explicit configuration or there is no
merge.

**Never push.** No remote is contacted by anything in this file. That is what keeps the whole
feature unable to damage anything shared, and it is asserted by test as well as by intent.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_evidence, worktrees
from .db.models import (
    EvidenceFootprint,
    RequirementEvidence,
    Task,
    TaskIntegration,
    TaskRequirementLink,
)
from .subprocess_windows import no_console_kwargs
from .utils import short_id

logger = logging.getLogger(__name__)

MERGED = "merged"
SKIPPED = "skipped"
FAILED = "failed"

# Why nothing was merged, in words that name the thing the operator would change. Each is a state of
# the world rather than an error: none of them means anything went wrong, and approval succeeds
# through all of them.
NO_MAIN_BRANCH = "this project has no main branch set — choose one in the project's settings"
NOT_A_REPOSITORY = "this project is not a git repository, so there is nothing to merge"
NOTHING_TO_MERGE = "no accepted evidence names a commit, so there is nothing to merge"
# Both of these used to end "and the next approval will merge". By the time the operator reads one
# the task is already `approved`, and restating a status is deliberately a no-op — so following the
# instruction provably did nothing: the request succeeded, no attempt was recorded, and the main
# branch did not move. Measured on 2026-08-14. They name the retry instead, which is on screen
# already: `TaskIntegrationNote.tsx` renders "Try again" for both.
CHECKOUT_DIRTY = (
    "the project's checkout has uncommitted changes to tracked files — commit or stash them, "
    "then retry the integration"
)
CHECKOUT_ELSEWHERE = (
    "the project's checkout is on {current}, not {target} — switch to {target}, then retry the "
    "integration"
)
# Not a failure, and emphatically not a merge. `git merge <ancestor>` prints "Already up to date",
# exits 0 and creates nothing, so without this guard a no-op was recorded as work reaching the
# product — which is the one thing this record exists to distinguish.
ALREADY_INTEGRATED = "{commit} is already in {target}; there was nothing to merge"
# The evidence-free route's own empty answer. Distinct from `NOTHING_TO_MERGE`, which is a statement
# about *evidence* and would be a lie for a task whose merge evidence does not govern: it covers a
# grandfathered task (one migration `0095` stamped onto the per-agent scheme), a task whose turn
# never provisioned a checkout,
# and a branch deleted by hand. Deliberately does not fall back to the agent branch — that branch
# carries every task the agent ever worked on, which is the one thing this module refuses to merge.
NO_TASK_BRANCH = "this task has no branch of its own, so there is nothing to merge"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        **no_console_kwargs(),
    )


def is_repository(root: Path) -> bool:
    result = _git(root, "rev-parse", "--is-inside-work-tree")
    return result.returncode == 0 and result.stdout.strip() == "true"


def detect_main_branch(root: Path) -> Optional[str]:
    """A *suggestion* for the project's main branch, never an assignment.

    Reuses the same names, in the same order, that reporting already tries. The difference between
    this and `requirement_evidence.is_reachable_from_main` is not the guess — it is that nothing
    here acts on the answer until an operator has accepted it.
    """
    if not is_repository(root):
        return None
    for name in requirement_evidence.MAIN_BRANCH_NAMES:
        if _git(root, "rev-parse", "--verify", name).returncode == 0:
            return name
    return None


def branch_exists(root: Path, branch: str) -> bool:
    return _git(root, "rev-parse", "--verify", branch).returncode == 0


def current_branch(root: Path) -> Optional[str]:
    result = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def has_uncommitted_changes(root: Path) -> bool:
    """Whether *tracked* files have uncommitted modifications.

    Untracked files are deliberately not counted. The Hub writes specification documents into the
    project directory, so a project that has ever had a document has untracked content essentially
    permanently — counting it would skip almost every merge, and the reason given would name a
    condition the operator cannot clear without committing files the Hub put there.

    Untracked files are also not a hazard: `git merge` only refuses over one it would overwrite, and
    that refusal is caught and recorded as a failure rather than corrupting anything.
    """
    result = _git(root, "status", "--porcelain", "--untracked-files=no")
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


@dataclass
class Target:
    """One commit to integrate, and the branch it was produced on.

    The three optional fields are for saying *whose* commit this is, and are populated on both
    paths because the accepted path carries them harmlessly. They exist because a refusal has to
    name each piece of evidence it is waiting on, with a route back to its cause: the evidence row,
    the requirement it demonstrates, and the task that recorded it — which is not always the task
    being approved, since a requirement may be served by more than one task.

    `requirement_id` is the `spec_requirements.id` foreign key, not the human identifier. The
    identifier lives on `SpecRequirement`, which this module deliberately does not import: reaching
    it would add a join to the *merge* query for a field only a sentence uses. `requirement_gate`
    already imports `SpecRequirement` and resolves it where the sentence is composed.
    """

    commit_sha: str
    branch: Optional[str] = None
    evidence_id: Optional[str] = None
    requirement_id: Optional[str] = None
    task_id: Optional[str] = None


async def _targets(session: AsyncSession, task: Task, review_state: str) -> List[Target]:
    """Every footprint for *task* in *review_state* that names a commit, oldest first, undeduplicated.

    The **filter**, shared by the two callers below so that the refusal and the merge cannot come to
    disagree about what counts. That shared property is exact: the refusal fires precisely when
    acceptance would produce a target that does not exist now. Two independently-written queries
    would drift, and a filter added to one and not the other produces either a refusal nothing can
    clear or a silent non-merge — which is the defect this whole capability exists to end.

    Evidence is reached through `TaskRequirementLink`, so evidence recorded by *another* task against
    a *shared* requirement is in scope here. That is not an accident of the join: if that evidence
    were accepted, it is this task's integration that would merge its commit.

    The empty-`commit_sha` guard belongs to the filter and lives here, although it sat inside
    `integration_targets`' reduction loop until this function existed. Left there, a `git` footprint
    whose `commit_sha` is `""` would refuse an approval that the merge would then silently ignore.
    """
    rows = (
        await session.execute(
            select(EvidenceFootprint, RequirementEvidence)
            .join(
                RequirementEvidence,
                RequirementEvidence.id == EvidenceFootprint.evidence_id,
            )
            .join(
                TaskRequirementLink,
                TaskRequirementLink.requirement_id == RequirementEvidence.requirement_id,
            )
            .where(
                TaskRequirementLink.task_id == task.id,
                RequirementEvidence.project_id == task.project_id,
                RequirementEvidence.review_state == review_state,
                EvidenceFootprint.kind == "git",
                EvidenceFootprint.commit_sha.is_not(None),
            )
            .order_by(EvidenceFootprint.observed_at.asc())
        )
    ).all()
    return [
        Target(
            commit_sha=footprint.commit_sha,
            branch=footprint.branch,
            evidence_id=evidence.id,
            requirement_id=evidence.requirement_id,
            task_id=evidence.task_id,
        )
        for footprint, evidence in rows
        if footprint.commit_sha
    ]


async def integration_targets(session: AsyncSession, task: Task) -> List[Target]:
    """The commits to integrate for *task*: the newest accepted footprint per distinct branch.

    Only `accepted` evidence contributes. Evidence still awaiting review has not been judged, and
    rejected evidence has been judged the other way — merging on the strength of either would make
    the review that gates the merge decorative.

    A `paths` footprint contributes nothing: there is no commit, so there is nothing that could be
    merged. That is a supported project shape, not a degraded one.
    """
    # Ordered oldest-first, so the last write per branch leaves the newest commit standing. One
    # target per branch: work produced on two branches has to be merged twice, and silently
    # dropping one of them would integrate half of what was approved.
    newest: Dict[Optional[str], Target] = {}
    for target in await _targets(session, task, requirement_evidence.ACCEPTED):
        newest[target.branch] = target
    return list(newest.values())


async def awaiting_targets(session: AsyncSession, task: Task) -> List[Target]:
    """Every piece of *task*'s evidence that names a commit and is still waiting to be judged.

    Shares `integration_targets`' filter and deliberately **not** its per-branch reduction. Keying by
    branch answers *what do I merge* — one merge per branch, because merging two commits from the
    same branch twice is pointless. This function is not deciding anything about merging; it is
    enumerating what has not been judged, and a refusal built on it must name each waiting piece
    rather than only how many there are. Two awaiting rows on one branch — one agent, one task, two
    sittings — would collapse to one under the reduction, and the refusal would name one of the two.

    The property the shared filter buys survives the split whole, because that property is about
    **non-emptiness**: a per-branch dedup of a non-empty list is non-empty, so both reductions are
    empty on exactly the same row sets. Sharing the filter buys all of it; the reduction was never
    carrying any.
    """
    return await _targets(session, task, requirement_evidence.AWAITING)


def task_branch_tip(root: Path, task_id: str) -> Optional[str]:
    """The commit at the head of *task_id*'s own branch, or None if it has none (design D6).

    `worktrees.task_branch_name` validates the id and raises for one the product did not mint. That
    is caught rather than propagated, for the reason `task_workspace` already gives about foreign
    ids: an id this module cannot name a branch for simply has no branch, and the caller's answer
    is `NO_TASK_BRANCH` either way — not a 500 in the middle of an approval that has already
    happened.
    """
    try:
        branch = worktrees.task_branch_name(task_id)
    except ValueError:
        return None
    result = _git(root, "rev-parse", "--verify", f"refs/heads/{branch}")
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


async def task_has_requirement_links(session: AsyncSession, task: Task) -> bool:
    """Is this task wired into the evidence chain at all (design D11, task 4.3c)?

    An existence check on `TaskRequirementLink`, not a count of evidence. The question is whether
    the task *can* be demonstrated, which is a fact about how it was created and does not change
    when the first piece of evidence is recorded. Answering it from evidence instead would make the
    merge source depend on when you asked — D10's rejected timing-dependent alternative — so a task
    would merge its branch tip in the morning and its evidence in the afternoon.

    Reached only from the last arm of `evidence_governs`, so an ordinary task, a flow task and a
    loop that declared for itself never pay for the query.
    """
    return (
        await session.execute(
            select(TaskRequirementLink.task_id)
            .where(TaskRequirementLink.task_id == task.id)
            .limit(1)
        )
    ).first() is not None


async def evidence_governs(session: AsyncSession, task: Task) -> bool:
    """Does accepted evidence decide what *task*'s approval merges (design D5, D10, D11)?

    Five answers, in this order, and the order is the design:

    1. **No loop** → yes. An ordinary task is untouched by any of this.
    2. **The loop id does not resolve** → yes. A dangling id decides nothing.
    3. **The loop declared** → the operator said, in either direction, and the operator wins over
       both defaults below.
    4. **The loop has a document** → yes. It is a *flow*, and `Loop` is a flow's row too (D10). A
       document's requirements are the evidence chain, so a flat "a loop merges its branch tip"
       default here would switch every flow onto a commit no reviewer accepted and degrade
       `approval-refuses-unaccepted-evidence` to an advisory product-wide.
    5. **Otherwise** → whether the task carries a requirement link (D11). A documentless loop's task
       created with `requirement_ids` gets real links, and `record_evidence` resolves against the
       *project's* index rather than a document's, so that task merges its evidence **today**.
       Stopping at step 4 would silently switch it to its branch tip — and since `_targets`
       deliberately includes evidence another task recorded against a shared requirement, a per-task
       branch tip could not carry that commit at all.

    `session.get` rather than a `select`, deliberately: `_merge_situation` and `integrate_task` both
    ask this within one approval and one session, so the PK get is answered from the identity map
    the second time and a `select` would not be.
    """
    if task.loop_id is None:
        return True
    from .db.models import Loop

    loop = await session.get(Loop, task.loop_id)
    if loop is None:
        return True
    if loop.work_needs_evidence is not None:
        return loop.work_needs_evidence
    if loop.spec_document_id is not None:
        return True
    return await task_has_requirement_links(session, task)


async def merge_targets(session: AsyncSession, task: Task, root: Path) -> List[Target]:
    """What approving *task* would actually merge — the commits, whatever their source (design D5).

    `integration_targets` where evidence governs, and at most one branch-tip `Target` where it does
    not. `integration_targets` itself is **not** modified and stays a pure database query; the
    branch-tip answer needs a `rev-parse`, which is why this one takes a repository root and that
    one does not.

    The branch tip is the answer for exactly one population: a task on a documentless loop with no
    requirement link of any kind — the set for which `integration_targets` is structurally empty
    forever, because there is no requirement any evidence could ever be recorded against.

    An empty list means different things on the two routes, and the callers say so rather than
    collapsing them: `NOTHING_TO_MERGE` where evidence governs, `NO_TASK_BRANCH` where it does not.
    """
    if await evidence_governs(session, task):
        return await integration_targets(session, task)
    tip = task_branch_tip(root, task.id)
    if tip is None:
        return []
    # The three evidence fields stay None: there is no evidence row to point at, and `Target`'s
    # docstring says they exist so a refusal can name what it is waiting on. A refusal about
    # unaccepted evidence cannot arise for a target that came from a branch.
    return [Target(commit_sha=tip, branch=worktrees.task_branch_name(task.id), task_id=task.id)]


def commits_riding_along(root: Path, main_branch: str, commit_sha: str) -> List[str]:
    """Every commit `merge --no-ff <commit_sha>` would bring into *main_branch* besides the commit
    itself (F58).

    `git rev-list <main_branch>..<commit_sha>` walks history and touches nothing — same cost class
    as `would_conflict`, and must run *before* the merge: once `commit_sha` is reachable from
    `main_branch`, the same command reports nothing, because it now is. Oldest first, so a caller
    reads the ancestry in the order it was actually built.
    """
    result = _git(root, "rev-list", "--reverse", f"{main_branch}..{commit_sha}")
    if result.returncode != 0:
        return []
    shas = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [sha for sha in shas if sha != commit_sha]


def would_conflict(root: Path, commit: str, main_branch: str) -> List[str]:
    """The paths that would conflict, or an empty list for a clean merge.

    `git merge-tree --write-tree` is plumbing: it touches neither the working tree nor the index of
    any checkout, so asking this question costs nothing and changes nothing. That is what makes it
    safe to ask *before* approving rather than discovering the answer mid-merge, with a transition
    already recorded and a repository half-changed.
    """
    result = _git(root, "merge-tree", "--write-tree", "--name-only", main_branch, commit)
    if result.returncode == 0:
        return []
    paths: List[str] = []
    # First stdout line is the (conflicted) tree OID; conflicted paths follow, one per line, until
    # the blank line before git's human-readable messages.
    for line in result.stdout.splitlines()[1:]:
        if not line.strip():
            break
        paths.append(line.strip())
    # A non-zero exit with no parsed paths still means "would not merge cleanly"; saying so without
    # naming a file is worse than saying nothing, so the caller gets a marker it can render.
    return paths or ["(unknown path)"]


@dataclass
class IntegrationResult:
    outcome: str
    reason: str = ""
    commit_sha: Optional[str] = None
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    merged: List[str] = field(default_factory=list)
    # Commits that landed alongside `commit_sha` because `merge --no-ff` merges a commit's whole
    # ancestry (F58). Populated only when `outcome` is `merged`; empty means nothing rode along.
    rode_along: List[str] = field(default_factory=list)


def integrate(root: Path, target: Target, main_branch: str) -> IntegrationResult:
    """Merge one commit into *main_branch*, locally.

    Preconditions are checked here rather than assumed, and each failure returns a `skipped` with a
    reason naming what to change. Approval is never rolled back by anything this returns: the merge
    is what did or did not happen, not the judgement that the work was good.
    """
    base = IntegrationResult(
        outcome=SKIPPED,
        commit_sha=target.commit_sha,
        source_branch=target.branch,
        target_branch=main_branch,
    )

    if not branch_exists(root, main_branch):
        base.reason = NO_MAIN_BRANCH
        return base

    # Before any question about the working tree. Whether a commit is already in the target is a
    # fact about the commit and the target alone, so an operator mid-edit deserves the true reason
    # rather than "commit or stash and the next approval will merge" — which would be false.
    #
    # `is True` only: `None` means the ref did not resolve and `False` means it is genuinely not
    # there. An unknown commit makes `merge-base` exit non-zero, falls through, and lets git fail
    # with its own message, which is the honest outcome.
    if requirement_evidence.is_reachable_from(root, target.commit_sha, main_branch) is True:
        base.reason = ALREADY_INTEGRATED.format(commit=target.commit_sha[:12], target=main_branch)
        return base

    if has_uncommitted_changes(root):
        base.reason = CHECKOUT_DIRTY
        return base

    on = current_branch(root)
    if on != main_branch:
        base.reason = CHECKOUT_ELSEWHERE.format(current=on or "a detached HEAD", target=main_branch)
        return base

    # Computed before the merge runs: once it succeeds, `target.commit_sha` is reachable from
    # `main_branch` and the same query would report nothing rode along, because it now looks
    # identical to what was always there.
    rode_along = commits_riding_along(root, main_branch, target.commit_sha)

    # The identity is supplied, never assumed. A project whose repository has no configured
    # `user.email` is an ordinary project — git simply refuses to commit there — and the Hub
    # already supplies its own for worktree snapshots. Without the same here, the Hub could create
    # an agent's commits and then fail to merge them, which is what the first real run of this path
    # did: "Committer identity unknown … unable to auto-detect email address".
    result = _git(
        root,
        "-c",
        f"user.name={worktrees.COMMIT_IDENTITY[0]}",
        "-c",
        f"user.email={worktrees.COMMIT_IDENTITY[1]}",
        "merge",
        "--no-ff",
        "-m",
        f"Integrate approved work {target.commit_sha[:12]}",
        target.commit_sha,
    )
    if result.returncode != 0:
        # The merge was tested clean before approval, so reaching here means the world moved
        # underneath it. The transition stands and coverage reports `verified, not integrated`,
        # which is a true account of what happened.
        _git(root, "merge", "--abort")
        base.outcome = FAILED
        base.reason = (result.stderr or result.stdout).strip()[:2000] or "the merge failed"
        return base

    base.outcome = MERGED
    base.reason = ""
    base.rode_along = rode_along
    return base


def record(
    session: AsyncSession,
    task: Task,
    result: IntegrationResult,
    *,
    actor_kind: str,
    actor: str,
) -> TaskIntegration:
    """Append what happened. There is no update path and no delete path, by design."""
    row = TaskIntegration(
        id=f"tint-{short_id()}",
        project_id=task.project_id,
        task_id=task.id,
        commit_sha=result.commit_sha,
        source_branch=result.source_branch,
        target_branch=result.target_branch,
        outcome=result.outcome,
        reason=result.reason,
        rode_along_commits=",".join(result.rode_along),
        mechanism="local",
        actor_kind=actor_kind,
        actor=actor,
    )
    session.add(row)
    return row


async def tasks_skipped_for_want_of_a_main_branch(
    session: AsyncSession, project_id: str, *, limit: int = 50
) -> List[Task]:
    """Approved tasks whose most recent integration attempt skipped for want of a main branch.

    `NO_MAIN_BRANCH` reads "choose one in the project's settings". Discharging that instruction at
    the moment the operator follows it is what makes the sentence true — otherwise the system asked
    for something and then ignored it being done, which is what the loop-7 run hit.

    Deliberately only this reason. Naming a branch says nothing about a checkout with uncommitted
    changes or one parked elsewhere, and a merge that failed outright wants a person rather than a
    repetition.

    "Most recent" matters: a task that skipped and was later merged by an explicit retry must not be
    picked up again on the next settings save.
    """
    newest = (
        select(
            TaskIntegration.task_id.label("task_id"),
            func.max(TaskIntegration.created_at).label("at"),
        )
        .where(TaskIntegration.project_id == project_id)
        .group_by(TaskIntegration.task_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Task)
            .join(TaskIntegration, TaskIntegration.task_id == Task.id)
            .join(
                newest,
                (newest.c.task_id == TaskIntegration.task_id)
                & (newest.c.at == TaskIntegration.created_at),
            )
            .where(
                Task.project_id == project_id,
                Task.status == "approved",
                TaskIntegration.outcome == SKIPPED,
                TaskIntegration.reason == NO_MAIN_BRANCH,
            )
            .order_by(TaskIntegration.created_at.asc())
            .limit(limit)
        )
    ).scalars()
    # `.unique()` is not available on a plain scalars() result here, and a task with two integration
    # rows sharing the newest timestamp would otherwise appear twice and be retried twice.
    seen: List[Task] = []
    for task in rows:
        if task not in seen:
            seen.append(task)
    return seen


async def tasks_awaiting_this_commit(session: AsyncSession, evidence) -> List[Task]:
    """Approved tasks that would merge *evidence*'s commit and have no record of having done so.

    **The condition is a commit that is not in the product, not the reason the previous attempt
    gave.** The sibling above filters on the most recent skip because naming a main branch changes
    the world in exactly one way, so its proxy is exact. Accepting evidence is not like that: it adds
    a *target*, and a task can acquire one whatever its last attempt did. In the mixed case — some
    evidence accepted at approval, some still awaiting — the most recent row is a `merged`, so no
    reason filter can reach it, and the awaiting commit would stay outside the product permanently
    while the task sat terminal at `approved`.

    Only the commit *this task has already merged* is excluded, and only because repeating it could
    append nothing but a row saying nothing happened. A commit that reached the main branch some
    other way is deliberately *not* excluded: `integrate` asks the repository and records
    `ALREADY_INTEGRATED`, which is a fact about the repository the reader does not otherwise have.

    Correctness does not rest on this predicate being exact; only noise does. `integrate` self-guards
    by asking git whether the commit is reachable, before it asks anything about the working tree.
    """
    footprint = (
        await session.execute(
            select(EvidenceFootprint).where(EvidenceFootprint.evidence_id == evidence.id)
        )
    ).scalar_one_or_none()
    if footprint is None or footprint.kind != "git" or not footprint.commit_sha:
        return []

    already = select(TaskIntegration.task_id).where(
        TaskIntegration.project_id == evidence.project_id,
        TaskIntegration.outcome == MERGED,
        TaskIntegration.commit_sha == footprint.commit_sha,
    )
    rows = (
        await session.execute(
            select(Task)
            .join(TaskRequirementLink, TaskRequirementLink.task_id == Task.id)
            .where(
                TaskRequirementLink.requirement_id == evidence.requirement_id,
                Task.project_id == evidence.project_id,
                Task.status == "approved",
                Task.id.not_in(already),
            )
            .order_by(Task.id.asc())
        )
    ).scalars()
    # One task can hold several integration rows and several links, so the join can repeat it; a
    # duplicate here would attempt the same merge twice and record two rows for one acceptance.
    waiting: List[Task] = []
    for task in rows:
        if task not in waiting:
            waiting.append(task)
    return waiting


async def integrate_what_was_waiting_for_this_evidence(
    session: AsyncSession, evidence, actor
) -> None:
    """Merge the approved work that was waiting for *evidence* to be judged.

    Approval is refused while evidence that would merge sits unaccepted, and that refusal tells the
    reader to accept it. Discharging the instruction at the moment they follow it is what makes the
    sentence true — without this, an approved task whose evidence is accepted afterwards stays
    unmerged, and approving again cannot merge it, because restating a status is a no-op.

    Wrapped, and called *after* the route's commit, exactly as the main-branch sibling is: the
    decision is the operator's or the granted agent's, and it must stand or fall on its own terms. A
    repository failure is recorded as a skip like any other, never as a failure to accept.

    `actor` is whoever *accepted*, not `operator()` — the integration happened because of that
    decision, and a record naming the operator for an agent's decision is a false account of who
    caused it.
    """
    from .task_transition_service import retry_integration

    try:
        if evidence.review_state != requirement_evidence.ACCEPTED:
            # A rejection changes nothing that could merge.
            return
        waiting = await tasks_awaiting_this_commit(session, evidence)
        for task in waiting:
            await retry_integration(session, task, actor)
        if waiting:
            await session.commit()
    except Exception:  # noqa: BLE001 - never let a merge undo the decision that asked for it
        logger.warning(
            "Could not integrate the work waiting on evidence %s",
            getattr(evidence, "id", "?"),
            exc_info=True,
        )
        await session.rollback()


async def history_for(session: AsyncSession, task_id: str) -> List[TaskIntegration]:
    return list(
        (
            await session.execute(
                select(TaskIntegration)
                .where(TaskIntegration.task_id == task_id)
                .order_by(TaskIntegration.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
