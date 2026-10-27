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

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import blocking, requirement_evidence, traces, worktrees
from .db.models import Agent, Project, SpecDocument, Task
from .project_workspace import ProjectWorkspaceError, resolve_project_workspace
from .repo_hygiene import seed_repo_excludes
from .spec_documents import parse_stored, read_document
from .spec_manifest import SpecPathError
from .subprocess_windows import no_console_kwargs

logger = logging.getLogger(__name__)


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
    #: `git merge-base <commit_sha> <Project.main_branch>` (design D8) -- where the reviewed
    #: branch left the project's main branch, so a review-agents consult can be told a range
    #: rather than just a commit. `None` when there is nothing to name beyond the commit itself:
    #: no main branch is set, it does not exist, the command failed, or the merge base *is* the
    #: commit (the commit is already on the main branch, so the range would be empty).
    base_sha: Optional[str] = None

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
    roster: Optional[List[Agent]] = None,
) -> ReviewerResolution:
    """Resolve the `reviewer` a task's specification entry declared, per task 4.3.

    *roster* is every agent of the project, archived ones too, where the caller has already read
    it (the scheduler's `FiringFacts`); the declared name is then looked up in it instead of read.

    **Never silently substitutes a different agent.** A document is written by someone who has no
    way to know which agents exist on the machine that will eventually run it — the payload field
    says so itself — so an unresolvable name is a routine outcome, not a fault. What it must not do
    is quietly become somebody else: an operator reading "reviewed by critic" when `critic` does not
    exist and `auditor` reviewed it has been told something false about who checked the work.

    So the fallback is *the operator*, and the reason travels with it. A name that resolves to an
    archived agent is treated as unresolved for the same reason `trigger_agent_directly` refuses
    one: nothing runs an archived agent.
    """
    declared, named_by = await _declared_reviewer_name(session, task)
    if not declared:
        return ReviewerResolution()
    # The task's own field, or its document's `delivery.reviewer` standing in for it (F508). Both
    # are declarations and get the same never-substitute rule; only the sentence says which.
    whose = {
        "task": "this task's reviewer",
        "tester": "this document's tester",
    }.get(named_by or "", "this document's default reviewer")

    if roster is not None:
        row = next((agent for agent in roster if agent.name == declared), None)
    else:
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
                f"the specification names {declared!r} as {whose}, but no agent by "
                "that name is on this project's roster. Review falls back to you."
            ),
        )
    if row.lifecycle == "archived":
        return ReviewerResolution(
            declared=declared,
            unresolved=(
                f"the specification names {declared!r} as {whose}, but that agent is "
                "archived and nothing runs an archived agent. Review falls back to you."
            ),
        )
    return ReviewerResolution(declared=declared, agent=declared)


async def _document_payload(
    session: AsyncSession, project_id: str, document_id: str
) -> Optional[dict]:
    """The payload of the stored document *document_id*, or `None` when it cannot be read.

    A gone document, a moved project directory, a bad path and a file that is not a payload are all
    ordinary states, none of them worth an error.
    """
    document = await session.get(SpecDocument, document_id)
    if document is None:
        return None
    try:
        workspace = await resolve_project_workspace(session, project_id)
        content = read_document(workspace, document.path)
    except (ProjectWorkspaceError, SpecPathError, OSError):
        # Named rather than a blanket `except Exception`, which swallowed a `SpecPathError` during
        # development and turned "this document path is invalid" into "no reviewer was declared".
        # A declaration that cannot be read is reported as absent; a bug here should still surface.
        return None
    if content is None:
        return None
    payload = parse_stored(content)
    return payload if isinstance(payload, dict) else None


async def named_reviewers(session: AsyncSession, project_id: str, document_id: str) -> Set[str]:
    """Every agent a flow's document names to judge work: each task's `reviewer`, and the
    delivery's `reviewer` and `tester` (F767). The scheduler withholds these from fresh work, since
    the ladder will not substitute for a named reviewer and an agent that built a task is excluded
    from reviewing it."""
    payload = await _document_payload(session, project_id, document_id)
    if payload is None:
        return set()
    names = [
        entry.get("reviewer") for entry in payload.get("tasks") or [] if isinstance(entry, dict)
    ]
    delivery = payload.get("delivery")
    if isinstance(delivery, dict):
        names += [delivery.get("reviewer"), delivery.get("tester")]
    return {name for name in map(_name, names) if name}


async def _declared_reviewer_name(
    session: AsyncSession, task: Task
) -> Tuple[Optional[str], Optional[str]]:
    """The reviewer *task*'s document declares for it, and who declared it: `task` or `document`.

    The task entry's own `reviewer` first; failing that, the document's `delivery.reviewer`, its
    default for every task that names none (F508). `(None, None)` for a hand-made task, a task
    whose document is gone, or a document whose payload no longer carries the entry — all
    ordinary states, none of them worth an error.
    """
    nobody: Tuple[Optional[str], Optional[str]] = (None, None)
    if not task.spec_document_id or not task.spec_task_key:
        return nobody
    payload = await _document_payload(session, task.project_id, task.spec_document_id)
    if payload is None:
        return nobody

    for entry in payload.get("tasks") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("key") != task.spec_task_key:
            continue
        reviewer = _name(entry.get("reviewer"))
        if reviewer:
            return reviewer, "task"
        delivery = payload.get("delivery")
        # tester-amends D4: a named tester tests every task that names no reviewer of its own,
        # ahead of the document's default reviewer.
        tester = _name(delivery.get("tester")) if isinstance(delivery, dict) else None
        if tester:
            return tester, "tester"
        default = _name(delivery.get("reviewer")) if isinstance(delivery, dict) else None
        return (default, "document") if default else nobody
    return nobody


def findings_lines(task: Optional[Task]) -> List[str]:
    """Whose a problem a reviewer finds is: the task's, or a side finding (operator, 2026-10-24).

    Every review gets these, in both briefing channels. Measured on slice 2 of the red thread
    (`spdoc-75175af77f8f`): QA approved every task and filed what it found as side tasks, among them
    a `black` failure, three red project-delete tests and a Thread page that missed its own job's
    event -- all three caused by the work it approved. "Outside the criteria" had become a reason to
    approve. The criteria say what the work must do; they do not license what it breaks.
    """
    where = (
        "; name the requirement it bears on with `requirement_ids` and "
        "`spec_document`, so it stays visible beside this task's document"
        if task is not None and task.spec_document_id
        else ""
    )
    return [
        "**A defect this task's work introduces is this task's, whatever the criteria say.** A "
        "lint, format, type or test failure it causes, a regression in something it touched, or "
        "a feature it ships that does not work: end with `revision_needed` and notes naming it. "
        "Do not approve and file it for later.",
        "Only a problem that was there before this task, in code it did not touch, is a side "
        f"finding: put it in a task with `create_task`{where}. Say in your verdict notes which "
        "side findings you filed.",
    ]


async def test_duty_lines(session: AsyncSession, task: Task) -> List[str]:
    """The test duty a flow's review turn carries while its document's testing is on (tester-amends).

    Empty for a hand-made task, a document that is not delivered by a flow, or `delivery.tester:
    false` (D4). Both briefing channels render these same lines, so they cannot drift apart.
    """
    from .spec_amendments import testing_on

    if not task.spec_document_id:
        return []
    document = await session.get(SpecDocument, task.spec_document_id)
    if document is None:
        return []
    try:
        workspace = await resolve_project_workspace(session, task.project_id)
        payload = parse_stored(read_document(workspace, document.path))
    except (ProjectWorkspaceError, SpecPathError, OSError):
        return []
    delivery = payload.get("delivery") if isinstance(payload, dict) else None
    if not isinstance(delivery, dict) or delivery.get("mode") != "flow" or not testing_on(payload):
        return []
    path = document.path
    return [
        "**This review is also a test.** Drive the running product against the task's acceptance "
        "criteria (run it, call it, click it, as each criterion's `how_to_check` says) as well as "
        "reading the code and the evidence.",
        f"When the product does not meet a criterion, amend the document: "
        f'`amend_spec_document(path="{path}", op="add_task", task={{key, title, description, '
        "requirements}}, reason=..., how_to_check=...)`. The fix joins the flow at once and the "
        "implementer picks it up; say in `reason` what you ran and what it showed. Then give your "
        "verdict on the task under review.",
        "Amend only within the document's stated criteria. A defect the work under review "
        "introduces sends the task back (above), never into the spec. A criterion the work "
        "cannot meet as written is `report_cannot_satisfy`, never a weakened criterion.",
    ]


def _name(value: object) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


async def verdict_evidence_sentence(
    session: AsyncSession, task: Task, *, may_decide: bool
) -> Optional[str]:
    """What the evidence gate means for this review's verdict, or None when it cannot refuse (F357).

    Both review channels (the loop briefing and the turn context) tell a reviewer to end with
    `approved` or `revision_needed`, and that instruction predates `approval-refuses-unaccepted-
    evidence`. Measured on LoopEngine, 2026-09-14: seven approvals refused by the gate, and the
    reviewers told their peers the task was approved anyway -- the briefing had set up the refusal
    and said nothing about it. One sentence, built here, so the two channels cannot disagree.

    **Said only where the gate can refuse.** Nothing is waiting (every documentless loop's task), or
    evidence does not govern the merge (`evidence_governs`: a loop declaring `work_needs_evidence`
    false merges the branch tip, and awaiting rows are only advisory there) -> None. Where it does
    govern, "can be refused" and not "is refused": the gate's mixed case lets approval through when
    something else of this task's would merge (`requirement_gate._check_unaccepted`), and a
    reviewer cannot tell which case it is in.

    Each waiting piece is named with its evidence id -- `decide_evidence` takes the id -- and, like
    the gate's own detail, with the task that recorded it where that is another task serving the
    same requirement.

    **The ungranted remedy is to end the turn**, not `ask_user` (F563). This sentence used to send
    the reviewer to `ask_user`; measured on a flow (tester-amends drive, 2026-10-09) the reviewer
    polled its question for about five minutes and the turn ended with no verdict, because nobody in
    a flow watches for it. A turn that ends while the gate refuses is already surfaced to the
    operator with the gate's own sentence and re-staffs nobody (`run_divergence`, `F374-fix`), so
    the reviewer's part is to stop and say what waits. Not claimed: that the review resumes once the
    evidence is decided -- the operator approves or sends it back from the surfaced reason.
    *may_decide* is the reviewer's `can_accept_evidence` grant.
    """
    from . import task_integration
    from .requirement_gate import _identifiers_for, rejected_identifiers

    rejected = " ".join(
        part
        for part in (
            await _dependencies_sentence(session, task),
            await _other_requirements_sentence(session, task),
            _rejected_sentence(await rejected_identifiers(session, task)),
            await _checks_sentence(session, task),
        )
        if part
    )
    rejected = rejected or None
    awaiting = await task_integration.awaiting_targets(session, task)
    if not awaiting or not await task_integration.evidence_governs(session, task):
        return rejected
    identifiers = await _identifiers_for(session, [row.requirement_id for row in awaiting])

    def named(row) -> str:
        identifier = identifiers.get(row.requirement_id or "", "") or "a requirement"
        commit = (row.commit_sha or "")[:12] or "an unnamed commit"
        return f"`{row.evidence_id}` for `{identifier}` at `{commit}`"

    # vis-D4: the verdict decides the evidence recorded for this task; only a piece another task
    # recorded waits for that task's own review.
    own = [row for row in awaiting if row.task_id == task.id]
    foreign = [row for row in awaiting if row.task_id != task.id]
    parts = [rejected] if rejected else []
    if own:
        parts.append(
            f"**Your verdict decides this task's evidence** ({'; '.join(named(r) for r in own)}). "
            "Approving accepts it and merges the work; sending the task back with "
            "`revision_needed` rejects it. Judge what each piece claims as part of the review, and "
            "say in `notes` what you checked: your notes are the reason recorded on each piece."
        )
    if foreign:
        recorded = "; ".join(
            (
                f"{named(r)}, recorded by task `{r.task_id}`"
                if r.task_id
                else f"{named(r)}, recorded " "outside any task"
            )
            for r in foreign
        )
        sentence = (
            f"Evidence your verdict does not decide is waiting for a decision ({recorded}): it was "
            "recorded by another task serving the same requirement, or by a run bound to no task. "
            "If nothing of this task's would merge without it, `approved` can be refused."
        )
        if may_decide:
            sentence += (
                " You can decide evidence: if that work is right, accept it with "
                "`decide_evidence` first (not any you recorded yourself), then approve."
            )
        else:
            sentence += (
                " If `approved` is refused for it, your verdict was not recorded: end your turn, "
                "saying which evidence is waiting. Do not tell anyone the task is approved until "
                "`update_task` has succeeded."
            )
        parts.append(sentence)
    return " ".join(parts) if parts else None


async def _dependencies_sentence(session: AsyncSession, task: Task) -> Optional[str]:
    """F519: what this task builds on, and where that work is. A reviewer judging the diff alone
    sent a correct fix back for having no tests: they were its prerequisite's, already merged."""
    from .db.models import TaskDependency, TaskIntegration

    prerequisites = (
        (
            await session.execute(
                select(Task)
                .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
                .where(TaskDependency.task_id == task.id)
                .order_by(Task.id)
            )
        )
        .scalars()
        .all()
    )
    if not prerequisites:
        return None
    pieces = []
    for prerequisite in prerequisites:
        merged = (
            await session.execute(
                select(TaskIntegration.commit_sha)
                .where(
                    TaskIntegration.task_id == prerequisite.id,
                    TaskIntegration.outcome == "merged",
                )
                .order_by(TaskIntegration.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        where = (
            f"merged as `{merged[:12]}`" if merged else f"`{prerequisite.status}`, not merged yet"
        )
        pieces.append(f"task `{prerequisite.id}` ({prerequisite.title}: {where})")
    return (
        f"**This task builds on** {'; '.join(pieces)}. Merged work is on the main branch and "
        "not in this task's diff: judge the change together with it, including tests it wrote "
        "for this task to satisfy."
    )


async def _other_requirements_sentence(session: AsyncSession, task: Task) -> Optional[str]:
    """F771: which of the document's requirements belong to other tasks. A reviewer that read the
    whole document sent correct work back twice for the sibling task's requirement. A requirement
    this task also serves is not another's; None for a task with no document entry or no sibling."""
    if not task.spec_document_id or not task.spec_task_key:
        return None
    payload = await _document_payload(session, task.project_id, task.spec_document_id)
    if payload is None:
        return None
    entries = [e for e in payload.get("tasks") or [] if isinstance(e, dict)]
    own = next((e for e in entries if e.get("key") == task.spec_task_key), None)
    if own is None:
        return None
    served = {r for r in own.get("requirements") or [] if isinstance(r, str)}
    siblings = {
        t.spec_task_key: t
        for t in (
            await session.execute(
                select(Task).where(
                    Task.project_id == task.project_id,
                    Task.spec_document_id == task.spec_document_id,
                    Task.id != task.id,
                )
            )
        )
        .scalars()
        .all()
    }
    others: dict = {}
    for entry in entries:
        key = entry.get("key")
        if key == task.spec_task_key:
            continue
        sibling = siblings.get(key)
        who = (
            f"`{sibling.id}` ({sibling.title})"
            if sibling is not None
            else f"`{key}` ({entry.get('title') or 'no title'})"
        )
        for requirement in entry.get("requirements") or []:
            if isinstance(requirement, str) and requirement not in served:
                others.setdefault(requirement, []).append(who)
    if not served or not others:
        return None
    belongs = "; ".join(f"`{r}`: {', '.join(w)}" for r, w in sorted(others.items()))
    return (
        f"**This task serves {', '.join(f'`{r}`' for r in sorted(served))}.** The document's other "
        f"requirements belong to other tasks ({belongs}): do not send this task back for them."
    )


def _rejected_sentence(identifiers: List[str]) -> Optional[str]:
    """F497: a served requirement whose evidence is all rejected refuses `approved` at every rigor
    (`requirement_gate.evaluate`, D2), whatever else is waiting. Its remedy is the author's, so the
    reviewer is told the verdict that returns the task to them."""
    if not identifiers:
        return None
    named = ", ".join(f"`{identifier}`" for identifier in identifiers)
    return (
        f"**{named} has only rejected evidence**, so `approved` will be refused until its author "
        "records evidence that satisfies it. Replacing it is not your work: if that is still true "
        "when you decide, end with `revision_needed` and notes naming what was rejected and why "
        "-- that returns the task to its author."
    )


async def _checks_sentence(session: AsyncSession, task: Task) -> Optional[str]:
    """The task's check result, for a reviewer (`approval-runs-the-projects-checks`, agent-flows).

    Reads what is recorded and starts nothing. `None` where no check applies. A failure is quoted,
    because the reviewer's notes are what the author reworks from."""
    from . import project_checks
    from .requirement_gate import merge_situation

    try:
        situation = await merge_situation(session, task)
        if situation is None:
            return None
        view = await project_checks.view(
            session,
            task,
            situation.root,
            situation.main_branch,
            [target.commit_sha for target in situation.will_merge],
        )
    except Exception:  # noqa: BLE001 -- a briefing never fails over a diagnostic
        logger.warning("could not read the checks of task %s", task.id, exc_info=True)
        return None
    if view is None:
        return None
    if view.state == "passed":
        passed = "**This task's checks passed** on the work approval would merge."
        results = view.reused
        if results is None:
            results = list(view.run.results or []) if view.run is not None else []
        flaky = [r for r in results if isinstance(r, dict) and r.get("flaky")]
        if flaky:
            # A flake is recorded, never swallowed: the reviewer is told which check flaked.
            names = ", ".join(f"`{r.get('name')}`" for r in flaky)
            tests = ", ".join(
                t for r in flaky for t in (r["flaky"].get("first") or {}).get("failed_tests") or []
            )
            passed += (
                f" {names} failed once and passed when run again on the same tree (a flaky "
                f"result{': ' + tests if tests else ''}), which does not hold approval."
            )
        return passed
    returns_it = (
        "Fixing it is not your work: end with `revision_needed` and notes quoting the failing "
        "output -- that returns the task to its author."
    )
    if view.state == "failed" and view.run is not None:
        failing = [r for r in view.run.results or [] if project_checks.failed(r)]
        names = ", ".join(f"`{r.get('name')}`" for r in failing)
        tail = str((failing[-1].get("output_tail") if failing else "") or "")[-600:].strip()
        # The gate's own decision, so the briefing and the approval cannot disagree
        # (`a-red-main-does-not-hold-the-night`, FR-8): failures that are main's or flakes are not
        # the task's work, and the reviewer is not told to send it back for them.
        from .requirement_gate import automatic_override

        try:
            decided = await automatic_override(session, task, view)
        except Exception:  # noqa: BLE001 -- a briefing never fails over a diagnostic
            logger.warning("could not decide the override for task %s", task.id, exc_info=True)
            decided = None
        if decided is not None:
            main = str(decided.get("main_sha") or "")[:12]
            tests = "; ".join(
                f"`{e['test']}` ({e['check']}) "
                + (
                    f"fails on main at {main} too"
                    if e["kind"] == project_checks.FAILS_ON_MAIN
                    else "passed when rerun on its own"
                )
                for e in decided["failures"]
            )
            fixes = sorted(set((decided.get("fix_tasks") or {}).values()))
            fix = (
                f" Fix task {', '.join(f'`{t}`' for t in fixes)} covers them."
                if fixes
                else " The Hub files a fix task for them."
            )
            return (
                f"**This task's checks fail ({names}), and the failure is not this task's work:** "
                f"{tests} (check run {decided.get('run_id')}). Approving lands it with an override "
                f"the Hub records.{fix} Judge the work itself; do not send it back for these."
            )
        if failing and all(project_checks.preexisting(r) for r in failing):
            # F605: the whole check fails on main too, and the Hub cannot tell the failures apart
            # by test (or may not override them): the approval waits on the operator.
            return (
                f"**This task's checks fail ({names}), and they fail on main too**, so the failure "
                f"is not this task's work. Last output: {tail!r}. `approved` waits on the "
                "operator, who lands it with an override reason or fixes main first; do not send "
                "it back for this."
            )
        return (
            f"**This task's checks failed** ({names}) on the work approval would merge, so "
            f"`approved` will be refused until they pass. Last output: {tail!r}. {returns_it}"
        )
    if view.state == "error" and view.run is not None:
        return (
            f"**This task's checks could not run** ({view.run.error}). Approving runs them "
            "again, and `approved` is refused until they pass."
        )
    return (
        "**This task's checks have not finished** on the work approval would merge, so "
        "`approved` will be refused until they pass. If they fail, " + returns_it
    )


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """`task_integration._git`'s pattern, not its instance: this module's own git spawns are one
    call deep and never share that module's `GIT_TIMEOUT_SECONDS` contextvar."""
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        **no_console_kwargs(),
    )


async def _merge_base_sha(
    session: AsyncSession, *, project_id: str, repo_root: Path, commit_sha: str
) -> Optional[str]:
    """`<base>` for design D8's review-agents bullet, or `None` when there is nothing to add to
    naming the commit alone. **Never raises**: a missing base narrows one bullet, not whether the
    review can happen at all (design D8, R3)."""
    project = await session.get(Project, project_id)
    main_branch = project.main_branch if project else None
    if not main_branch:
        return None
    try:
        result = await blocking.run(_git, repo_root, "merge-base", commit_sha, main_branch)
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    base = result.stdout.strip()
    if not base or base == commit_sha:
        return None
    return base


@traces.traced_work("review_staffing", attributes={"aw.agent": "reviewer", "aw.task.id": "task_id"})
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

    from . import task_integration

    target = await task_integration.review_target(session, task, repo_root)
    if not target.resolved:
        raise ReviewTurnRefused(target.refusal or f"task {task_id} has no commit to review")

    # Every git and file step of staffing runs off the loop (`blocking`, D1).
    if not await blocking.run(worktrees.is_git_repo, repo_root):
        raise ReviewTurnRefused(
            "this project is not a git repository, so there is no commit to check out for "
            "review. Evidence recorded here names changed paths rather than a commit."
        )

    # `resolve_agent_workspace` seeds these on every ordinary turn, and a review turn deliberately
    # does not go through it — so this is now a second funnel into the project, and skipping it
    # would leave a project whose only turns are reviews with no ignore rules at all.
    await blocking.run(seed_repo_excludes, repo_root)

    # Computed before the checkout is provisioned (design D8, R3): the alternative order would let
    # an escaping `TimeoutExpired` leak a provisioned-but-unclaimed checkout, the F326 class. This
    # call cannot raise -- see `_merge_base_sha` -- but the order matters whether or not it does.
    base_sha = await _merge_base_sha(
        session, project_id=project_id, repo_root=repo_root, commit_sha=target.commit_sha
    )

    try:
        # Serialized with every other worktree change, as it was on the loop (D5).
        workspace = await blocking.run_serialized(
            worktrees.ensure_review_checkout, repo_root, reviewer, target.commit_sha
        )
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
        base_sha=base_sha,
    )
