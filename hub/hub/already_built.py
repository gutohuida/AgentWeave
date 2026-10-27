"""Closing an approved document's open tasks as already built (`every-task-can-always-be-moved-on`).

On 2026-10-23 three specifications were approved after their work had shipped, and created thirteen
pending tasks for work already on master. A run takes one task, `pending` reaches only `assigned`
or `in_progress`, and no agent tool deletes a task, so closing them cost one paid run each or the
operator deleting them by hand (src-28d4bff83265). This is the one operator action that closes
them instead (FR-5), and keeps the closing checkable (FR-6):

1. **Close.** Every open task of the document is walked, as the operator, along edges the map
   already has to `under_review`, held by nobody, each move's history row naming this action and
   the commits. No run is started; the walk is the operator's own moves.
2. **Claim.** For each requirement each task serves, one piece of evidence pointing at the named
   commits, recorded on that task and left `awaiting` like any agent's: "already built" is checked
   like any other work (operator, 2026-10-26).
3. **Approve.** Once every piece on a closed task is decided and accepted, the task is approved as
   the operator's standing instruction, from whichever route decided the last piece
   (`approve_what_was_waiting_for_this_evidence`). A rejected piece leaves its task under review,
   where the approval gate already refuses it for the rejection.

Nothing here widens the transition map: the walk uses the operator's edges, and the one exemption,
`closing_with`, only stops the dependency gate holding a task back for a prerequisite closed by the
same action -- no work is starting, so there is nothing for the gate to protect.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import blocking, requirement_evidence, run_liveness, spec_lifecycle, task_transitions
from .db.models import Project, RequirementEvidence, SpecRequirement, Task, TaskRequirementLink

logger = logging.getLogger(__name__)

#: The `kind` of the evidence this action records, and how a closed task is recognised afterwards.
EVIDENCE_KIND = "already_built"

#: The operator's walk from each open status to `under_review`, along edges `TRANSITIONS` grants
#: the operator. `under_review` itself needs no move, only the evidence.
WALK: Dict[str, tuple] = {
    "pending": ("in_progress", "completed", "under_review"),
    "assigned": ("in_progress", "completed", "under_review"),
    "blocked": ("in_progress", "completed", "under_review"),
    "revision_needed": ("in_progress", "completed", "under_review"),
    "in_progress": ("completed", "under_review"),
    "completed": ("under_review",),
    "under_review": (),
}

#: Bounds the request, not the work: a document has a few tasks.
MAX_COMMITS = 20


class AlreadyBuiltRefused(Exception):  # noqa: N818 - "refused" is the outcome, not a fault
    def __init__(self, message: str, *, code: str, http_status: int = 409, **detail: Any):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.detail = detail


@dataclass
class ClosedTask:
    id: str
    title: str
    from_status: str
    status: str
    evidence: List[str]


def short(sha: str) -> str:
    return sha[:12]


def closing_note(commits: Sequence[str]) -> str:
    return "Closed as already built at " + ", ".join(short(sha) for sha in commits)


def _resolve_commits(root: Path, named: Sequence[str], main_branch: str) -> Dict[str, Any]:
    """Each named commit resolved, and whether it is on *main_branch*; off the loop (git)."""
    from . import task_integration

    resolved: List[str] = []
    unknown: List[str] = []
    off_main: List[str] = []
    for ref in named:
        sha = task_integration.resolve(root, ref)
        if sha is None:
            unknown.append(ref)
            continue
        if requirement_evidence.is_reachable_from(root, sha, main_branch) is not True:
            off_main.append(ref)
            continue
        if sha not in resolved:
            resolved.append(sha)
    # The piece's footprint names one commit: the named one that contains the most of the others,
    # so the tree it describes holds as much of the work as one commit can. Ties keep the order named.
    newest = max(
        resolved,
        key=lambda sha: sum(
            1
            for other in resolved
            if other != sha and requirement_evidence.is_reachable_from(root, other, sha) is True
        ),
        default=None,
    )
    return {"resolved": resolved, "unknown": unknown, "off_main": off_main, "newest": newest}


async def _open_tasks(session: AsyncSession, document_id: str) -> List[Task]:
    rows = await session.execute(
        select(Task)
        .where(Task.spec_document_id == document_id, Task.status.in_(tuple(WALK)))
        .order_by(Task.created_at, Task.id)
    )
    return list(rows.scalars().all())


async def _requirements_of(session: AsyncSession, task: Task) -> List[SpecRequirement]:
    rows = await session.execute(
        select(SpecRequirement)
        .join(TaskRequirementLink, TaskRequirementLink.requirement_id == SpecRequirement.id)
        .where(TaskRequirementLink.task_id == task.id, SpecRequirement.state == "active")
        .order_by(SpecRequirement.identifier, SpecRequirement.id)
    )
    found: List[SpecRequirement] = []
    for requirement in rows.scalars().all():
        if requirement not in found:
            found.append(requirement)
    return found


async def close(
    session: AsyncSession,
    document,
    commits: Sequence[str],
    *,
    workspace,
    level: Optional[str] = None,
) -> Dict[str, Any]:
    """Close *document*'s open tasks against *commits*; stages everything, the caller commits.

    *level* `fast` approves each task at once once its evidence is recorded, accepting that
    evidence in the approval (`a-build-has-a-driver-a-level-and-its-people`, D4: slice B's resolved
    question). At any other level, or none, each task waits under review for its evidence to be
    decided, as before. The approval still runs every gate; a refusal leaves the task under review.

    Refuses (`AlreadyBuiltRefused`) before changing anything: a document that is not an approved
    change, no commit named or one the repository lacks or that is not on the main branch, no open
    task, or a task with a turn still running on it -- closing work somebody is doing would record
    it as done under them.
    """
    from .task_transition_service import TransitionRefusedError, apply_transition

    if document.kind != "change-spec" or document.phase != spec_lifecycle.APPROVED:
        raise AlreadyBuiltRefused(
            "only an approved change's tasks are closed as already built", code="not_approved"
        )
    named = [ref.strip() for ref in commits if ref and ref.strip()]
    if not named:
        raise AlreadyBuiltRefused(
            "name the commit (or commits) on the main branch that hold the work",
            code="no_commits",
            http_status=422,
        )
    if len(named) > MAX_COMMITS:
        raise AlreadyBuiltRefused(
            f"name at most {MAX_COMMITS} commits", code="too_many_commits", http_status=422
        )
    project = await session.get(Project, document.project_id)
    main_branch = project.main_branch if project is not None else None
    if not main_branch:
        raise AlreadyBuiltRefused(
            "the project has no main branch set, so nothing says the work is on it; set it in "
            "the project's settings first",
            code="no_main_branch",
        )
    found = await blocking.run(_resolve_commits, workspace.root, named, main_branch)
    if found["unknown"] or found["off_main"]:
        parts = []
        if found["unknown"]:
            parts.append(f"not in this repository: {', '.join(found['unknown'])}")
        if found["off_main"]:
            parts.append(f"not on {main_branch}: {', '.join(found['off_main'])}")
        raise AlreadyBuiltRefused(
            "every commit named must be on the main branch; " + "; ".join(parts),
            code="commit_not_on_main",
            http_status=422,
            unknown=found["unknown"],
            off_main=found["off_main"],
        )
    resolved: List[str] = found["resolved"]

    tasks = await _open_tasks(session, document.id)
    if not tasks:
        raise AlreadyBuiltRefused(f"{document.path} has no open task to close", code="nothing_open")
    running = []
    for task in tasks:
        live = await run_liveness.live_turn_for_task(session, task)
        if live is not None:
            running.append({"task": task.id, "agent": live.agent, "run_id": live.run_id})
    if running:
        raise AlreadyBuiltRefused(
            "a turn is still running on "
            + ", ".join(f"{entry['task']} ({entry['agent']})" for entry in running)
            + "; stop it or let it end before closing its work as already built",
            code="turn_running",
            running=running,
        )

    operator = task_transitions.operator()
    note = closing_note(resolved)
    batch = frozenset(task.id for task in tasks)
    evidence_actor = spec_lifecycle.Actor(kind="operator", name="operator")
    closed: List[ClosedTask] = []
    for task in tasks:
        from_status = task.status
        for step in WALK[from_status]:
            if step == "under_review":
                # Held by nobody: no agent is reviewing it, the evidence is what gets judged, and
                # a holder that authored it would make the entry a lie the guard refuses (F70).
                task.assignee = None
            try:
                await apply_transition(session, task, step, operator, note=note, closing_with=batch)
            except TransitionRefusedError as exc:
                raise AlreadyBuiltRefused(
                    f"{task.id} ({task.title!r}) could not be moved from {task.status!r} to "
                    f"{step!r}: {exc}",
                    code="move_refused",
                    task=task.id,
                ) from exc
        recorded: List[str] = []
        for requirement in await _requirements_of(session, task):
            summary = (
                f"Closed as already built by the operator: the work for "
                f"{requirement.identifier} ({task.title}) is on {main_branch} at "
                f"{', '.join(short(sha) for sha in resolved)}."
            )
            try:
                evidence = await requirement_evidence.record(
                    session,
                    requirement,
                    kind=EVIDENCE_KIND,
                    actor=evidence_actor,
                    locator=" ".join(resolved),
                    summary=summary,
                    task_id=task.id,
                    workspace=workspace,
                    main_branch=main_branch,
                    commit=found["newest"],
                    covers="full",
                    awaiting=True,
                )
            except requirement_evidence.EvidenceRefusedError as exc:
                if exc.code == "duplicate_evidence":
                    # Closed against this commit before; that piece still stands for it.
                    continue
                raise AlreadyBuiltRefused(
                    f"evidence for {requirement.identifier} on {task.id} was refused: {exc}",
                    code=exc.code or "evidence_refused",
                ) from exc
            recorded.append(evidence.id)
        if level == "fast" and task.status == "under_review":
            approval = (
                f"Approved as already built at {', '.join(short(sha) for sha in resolved)}: "
                "closed at level fast, its evidence accepted with it"
            )
            try:
                async with session.begin_nested():
                    await apply_transition(
                        session, task, "approved", operator, note=approval, verdict_reason=approval
                    )
            except TransitionRefusedError as exc:
                logger.info("Task %s closed at fast was not approved: %s", task.id, exc)
        closed.append(
            ClosedTask(
                id=task.id,
                title=task.title,
                from_status=from_status,
                status=task.status,
                evidence=recorded,
            )
        )
    return {
        "document": document.path,
        "commits": resolved,
        "tasks": [vars(entry) for entry in closed],
    }


async def _waiting_to_be_approved(session: AsyncSession, task: Task) -> Optional[List[str]]:
    """The requirement identifiers whose accepted pieces approve *task*, or None while it waits.

    A task closed as already built is approved once it holds already-built pieces, every one of
    them accepted, and nothing else on it still awaits a decision -- approving accepts whatever
    awaits, and a piece somebody else recorded is not this action's to accept.
    """
    if task.status != "under_review":
        return None
    pieces = (
        (
            await session.execute(
                select(RequirementEvidence).where(RequirementEvidence.task_id == task.id)
            )
        )
        .scalars()
        .all()
    )
    built = [piece for piece in pieces if piece.kind == EVIDENCE_KIND]
    if not built:
        return None
    if any(piece.review_state != requirement_evidence.ACCEPTED for piece in built):
        return None
    if any(piece.review_state == requirement_evidence.AWAITING for piece in pieces):
        return None
    identifiers = []
    for piece in built:
        requirement = await session.get(SpecRequirement, piece.requirement_id)
        name = requirement.identifier if requirement is not None else piece.requirement_id
        if name not in identifiers:
            identifiers.append(name)
    return identifiers


async def approve_what_was_waiting_for_this_evidence(
    session: AsyncSession, evidence_id: str, decided_by: str
) -> Optional[str]:
    """Approve the task closed as already built whose last piece *evidence_id* was; its id, or None.

    Called after the decision has committed, from every route that decides evidence, and never
    able to undo it: a refusal (the approval gate, a conflict) leaves the task under review for
    somebody to land, and is logged. Approved as the operator, because closing as already built is
    the operator's instruction to approve once checked; the note names who accepted. Takes the id
    and reads the row afresh: the integration before it may have rolled back and expired it (F426).
    """
    from .task_transition_service import TransitionRefusedError, apply_transition

    try:
        evidence = await session.get(RequirementEvidence, evidence_id)
        if evidence is None or evidence.kind != EVIDENCE_KIND or not evidence.task_id:
            return None
        if evidence.review_state != requirement_evidence.ACCEPTED:
            return None
        task = await session.get(Task, evidence.task_id)
        if task is None:
            return None
        task_id = task.id
        identifiers = await _waiting_to_be_approved(session, task)
        if identifiers is None:
            return None
        commits = (evidence.locator or "").split()
        note = (
            f"Approved as already built at {', '.join(short(sha) for sha in commits)}: the "
            f"evidence for {', '.join(identifiers)} was accepted by {decided_by}"
        )
        try:
            await apply_transition(
                session,
                task,
                "approved",
                task_transitions.operator(),
                note=note,
                verdict_reason=note,
            )
        except TransitionRefusedError as exc:
            await session.rollback()
            logger.info("Task %s closed as already built was not approved: %s", task_id, exc)
            return None
        await session.commit()
        return task_id
    except Exception:  # noqa: BLE001 - never let an approval undo the decision that asked for it
        logger.warning(
            "Could not approve the task waiting on evidence %s", evidence_id, exc_info=True
        )
        await session.rollback()
        return None
