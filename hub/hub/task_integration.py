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
from .utils import short_id

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


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
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
    """One commit to integrate, and the branch it was produced on."""

    commit_sha: str
    branch: Optional[str] = None


async def integration_targets(session: AsyncSession, task: Task) -> List[Target]:
    """The commits to integrate for *task*: the newest accepted footprint per distinct branch.

    Only `accepted` evidence contributes. Evidence still awaiting review has not been judged, and
    rejected evidence has been judged the other way — merging on the strength of either would make
    the review that gates the merge decorative.

    A `paths` footprint contributes nothing: there is no commit, so there is nothing that could be
    merged. That is a supported project shape, not a degraded one.
    """
    rows = (
        (
            await session.execute(
                select(EvidenceFootprint)
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
                    RequirementEvidence.review_state == requirement_evidence.ACCEPTED,
                    EvidenceFootprint.kind == "git",
                    EvidenceFootprint.commit_sha.is_not(None),
                )
                .order_by(EvidenceFootprint.observed_at.asc())
            )
        )
        .scalars()
        .all()
    )

    # Ordered oldest-first, so the last write per branch leaves the newest commit standing. One
    # target per branch: work produced on two branches has to be merged twice, and silently
    # dropping one of them would integrate half of what was approved.
    newest: Dict[Optional[str], Target] = {}
    for row in rows:
        if not row.commit_sha:
            continue
        newest[row.branch] = Target(commit_sha=row.commit_sha, branch=row.branch)
    return list(newest.values())


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
