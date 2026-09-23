"""What a review turn is, and what the reviewing agent is given.

A reviewer agent could not see the work it was reviewing (`scripts/drive/FINDINGS.md`, F10). The
gap was circular rather than incidental: isolation is per agent, and unreviewed work exists only on
the author's branch, so the only way to see it was to integrate it — which is what the review was
meant to decide.

Two halves are required, and this module owns both because they must not drift apart:

* **Where.** The reviewer's workspace for the turn is a detached checkout of the commit the
  evidence names, and its own working checkout is outside that boundary. This is enforced.
* **What.** The turn context states that this *is* a review, of which task, at which commit. This
  is stated.

Design D4 is explicit that the first without the second fails: *"a reviewer that is not told it is
reviewing will helpfully fix the bug itself and report the work as verified."* The boundary can
only enforce where the agent may act, never what it thinks it is doing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_evidence, worktrees
from .db.models import Agent, SpecDocument, Task
from .project_workspace import ProjectWorkspaceError, resolve_project_workspace
from .repo_hygiene import seed_repo_excludes
from .spec_documents import read_document
from .spec_manifest import SpecPathError
from .spec_payload import extract_payload


class ReviewTurnRefused(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """A review turn cannot be prepared, with the reason stated.

    Raised rather than returned, unlike `requirement_evidence.commit_for_task_review`'s refusal,
    because by this layer the caller is a route that already turns a refusal into a status and a
    message. The reason text is carried through unchanged so the operator reads why, not that.
    """


@dataclass
class ReviewContext:
    """One review turn: who is reviewing what, where, and at which commit."""

    task_id: str
    task_title: str
    reviewer: str
    commit_sha: str
    evidence_id: str
    workspace: Path
    branch: Optional[str] = None
    #: Commits named by *earlier* evidence for the same task, oldest first (design D5).
    earlier_commits: List[requirement_evidence.EarlierCommit] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.earlier_commits is None:
            self.earlier_commits = []

    @property
    def work_moved(self) -> bool:
        return bool(self.earlier_commits)


@dataclass
class ReviewerResolution:
    """Who a task's declaration says should review it, and whether that name resolves.

    Three outcomes, kept distinct because an operator acts differently on each: nobody was named,
    a named agent is on the roster, or a named agent is **not**. The third is the one that must
    never be papered over — see `unresolved`.
    """

    #: The name the specification declared, if any. Kept even when it does not resolve.
    declared: Optional[str] = None
    #: The roster agent to give the review turn to, or None for operator review.
    agent: Optional[str] = None
    #: Why the declared name could not be used. Non-empty only when `declared` is set and
    #: `agent` is not.
    unresolved: Optional[str] = None

    @property
    def falls_back_to_operator(self) -> bool:
        return self.agent is None


async def resolve_declared_reviewer(
    session: AsyncSession,
    *,
    project_id: str,
    task: Task,
) -> ReviewerResolution:
    """Resolve the `reviewer` a task's specification entry declared, per task 4.3.

    **Never silently substitutes a different agent.** A document is written by someone who has no
    way to know which agents exist on the machine that will eventually run it — the payload field
    says so itself — so an unresolvable name is a routine outcome, not a fault. What it must not do
    is quietly become somebody else: an operator reading "reviewed by critic" when `critic` does not
    exist and `auditor` reviewed it has been told something false about who checked the work.

    So the fallback is *the operator*, and the reason travels with it. A name that resolves to an
    archived agent is treated as unresolved for the same reason `trigger_agent_directly` refuses
    one: nothing runs an archived agent.
    """
    declared = await _declared_reviewer_name(session, task)
    if not declared:
        return ReviewerResolution()

    row = (
        (
            await session.execute(
                select(Agent).where(Agent.project_id == project_id, Agent.name == declared)
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        return ReviewerResolution(
            declared=declared,
            unresolved=(
                f"the specification names {declared!r} as this task's reviewer, but no agent by "
                "that name is on this project's roster. Review falls back to you."
            ),
        )
    if row.lifecycle == "archived":
        return ReviewerResolution(
            declared=declared,
            unresolved=(
                f"the specification names {declared!r} as this task's reviewer, but that agent is "
                "archived and nothing runs an archived agent. Review falls back to you."
            ),
        )
    return ReviewerResolution(declared=declared, agent=declared)


async def _declared_reviewer_name(session: AsyncSession, task: Task) -> Optional[str]:
    """The `reviewer` field of *task*'s entry in the document that declared it.

    Returns None for a hand-made task, a task whose document is gone, or a document whose payload
    no longer carries the entry — all ordinary states, none of them worth an error.
    """
    if not task.spec_document_id or not task.spec_task_key:
        return None
    document = await session.get(SpecDocument, task.spec_document_id)
    if document is None:
        return None

    try:
        workspace = await resolve_project_workspace(session, task.project_id)
        content = read_document(workspace, document.path)
    except (ProjectWorkspaceError, SpecPathError, OSError):
        # Named rather than a blanket `except Exception`, which swallowed a `SpecPathError` during
        # development and turned "this document path is invalid" into "no reviewer was declared".
        # A declaration that cannot be read is reported as absent; a bug here should still surface.
        return None
    if content is None:
        return None
    payload = extract_payload(content)
    if not isinstance(payload, dict):
        return None

    for entry in payload.get("tasks") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("key") != task.spec_task_key:
            continue
        reviewer = entry.get("reviewer")
        return reviewer.strip() if isinstance(reviewer, str) and reviewer.strip() else None
    return None


async def verdict_evidence_sentence(
    session: AsyncSession, task: Task, *, may_decide: bool
) -> Optional[str]:
    """What the evidence gate means for this review's verdict, or None when nothing is waiting (F357).

    Both review channels (the loop briefing and the turn context) tell a reviewer to end with
    `approved` or `revision_needed`, and that instruction predates `approval-refuses-unaccepted-
    evidence`. Measured on LoopEngine, 2026-09-14: seven approvals refused by the gate, and the
    reviewers told their peers the task was approved anyway -- the briefing had set up the refusal
    and said nothing about it. One sentence, built here, so the two channels cannot disagree.

    Keyed on what is waiting now, from the gate's own source (`awaiting_targets`), so a task with
    no requirements -- every documentless loop -- is told nothing. *may_decide* is the reviewer's
    `can_accept_evidence` grant; the reviewer is never the author, but a requirement can be served
    by more than one task, so "not your own" is still said.

    "Can be refused", not "is refused": the gate allows the mixed case where something else of
    this task's would merge (`requirement_gate._check_unaccepted`), and a reviewer cannot tell
    which case it is in.
    """
    from . import task_integration
    from .requirement_gate import _identifiers_for

    awaiting = await task_integration.awaiting_targets(session, task)
    if not awaiting:
        return None
    identifiers = await _identifiers_for(session, [row.requirement_id for row in awaiting])
    pieces = "; ".join(
        f"`{identifiers.get(row.requirement_id or '', '') or 'a requirement'}` at "
        f"`{(row.commit_sha or '')[:12] or 'an unnamed commit'}`"
        for row in awaiting
    )
    sentence = (
        f"**This task's evidence is still waiting for a decision** ({pieces}). Until it is "
        "accepted, `approved` can be refused: approving would merge none of it. "
        "`revision_needed` is not affected."
    )
    if may_decide:
        return sentence + (
            " You can decide evidence: if the work is right, accept what it demonstrates with "
            "`decide_evidence` first (not any you recorded yourself), then approve."
        )
    return sentence + (
        " Deciding evidence is the operator's, not yours. If `approved` is refused, your verdict "
        "was not recorded: leave the task where it is, send the verdict as a message saying the "
        "work is ready and waiting on the operator's evidence decision, and do not tell anyone "
        "the task is approved."
    )


async def prepare_review_turn(
    session: AsyncSession,
    *,
    project_id: str,
    reviewer: str,
    task_id: str,
    repo_root: Path,
) -> ReviewContext:
    """Provision *reviewer*'s checkout of the work on *task_id* and describe the turn.

    Deliberately does **not** gate on the task's status. Which statuses dispatch a reviewer is
    `loop-becomes-a-flow`'s question, and this change's scope is visibility only (design D7); the
    real gate here is evidence naming a commit, because without one there is nothing to check out
    and nothing to review.
    """
    task = await session.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise ReviewTurnRefused(f"task {task_id} is not a task in this project")

    target = await requirement_evidence.commit_for_task_review(session, task_id)
    if not target.resolved:
        raise ReviewTurnRefused(target.refusal or f"task {task_id} has no commit to review")

    if not worktrees.is_git_repo(repo_root):
        raise ReviewTurnRefused(
            "this project is not a git repository, so there is no commit to check out for "
            "review. Evidence recorded here names changed paths rather than a commit."
        )

    # `resolve_agent_workspace` seeds these on every ordinary turn, and a review turn deliberately
    # does not go through it — so this is now a second funnel into the project, and skipping it
    # would leave a project whose only turns are reviews with no ignore rules at all.
    seed_repo_excludes(repo_root)

    try:
        workspace = worktrees.ensure_review_checkout(repo_root, reviewer, target.commit_sha)
    except worktrees.ReviewCommitUnavailableError as exc:
        # The evidence names a commit the repository does not contain — an author's branch pruned,
        # or evidence carried over from a different checkout. Stated, never worked around: putting
        # the reviewer on some *nearby* commit would produce a verdict about code nobody wrote.
        raise ReviewTurnRefused(str(exc)) from exc
    except (worktrees.GitCommandError, worktrees.IsolationUnavailableError) as exc:
        raise ReviewTurnRefused(f"could not prepare {reviewer}'s review checkout: {exc}") from exc

    return ReviewContext(
        task_id=task_id,
        task_title=task.title,
        reviewer=reviewer,
        commit_sha=target.commit_sha,
        evidence_id=target.evidence_id or "",
        workspace=workspace,
        branch=target.branch,
        earlier_commits=target.earlier_commits,
    )
