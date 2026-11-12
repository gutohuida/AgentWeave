"""Closing a loose task without landing it here (`tasks-outside-a-flow-move-freely`, FR-7..FR-9).

Together with approve-and-land, these are the ways a task outside any flow ends:

* **Done elsewhere** -- another task's work, or a commit, is already on the main branch. The task is
  approved at that commit with a landing row already `landed`, so its stage reads "on main" at the
  commit; nothing is queued, checked or reviewed for it.
* **Cancelled** -- the task is rejected with an optional reason, its stage "closed without
  landing". Approved work that has not landed is sent back first, which withdraws what it queued.

Each task closes in its own savepoint: one that cannot close is named with its reason, and the
others still do. Everything is staged; the caller commits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from . import already_built, blocking, landing_queue, readable_ids, run_liveness, task_transitions
from .db.models import Project, Task, TaskLanding, TaskTransition
from .utils import short_id

DONE_ELSEWHERE = "done_elsewhere"
CANCELLED = "cancelled"
OUTCOMES = (DONE_ELSEWHERE, CANCELLED)

#: How a cancelled task is recognised afterwards: the stage shows what follows it as the reason.
CANCEL_NOTE = "Cancelled"
DONE_ELSEWHERE_NOTE = "Closed as done elsewhere at "


@dataclass
class Refused:
    task: str
    reason: str
    code: str


class CloseRefusedError(Exception):
    """The request as a whole cannot be answered (no main branch, an unknown named task or commit)."""

    def __init__(self, message: str, *, code: str, http_status: int = 409):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def cancel_note(reason: Optional[str]) -> str:
    text = " ".join((reason or "").split())
    return f"{CANCEL_NOTE}: {text}" if text else CANCEL_NOTE


def cancel_reason_of(note: Optional[str]) -> Optional[str]:
    """The reason a cancelling move's note carries, or None for a note that is not one."""
    if not note or not note.startswith(CANCEL_NOTE):
        return None
    rest = note[len(CANCEL_NOTE) :]
    return rest[2:] if rest.startswith(": ") else ""


async def _resolve_target(
    session: AsyncSession,
    project_id: str,
    *,
    by_task: Optional[str],
    commit: Optional[str],
    workspace,
) -> Dict[str, Any]:
    """The commit on main a done-elsewhere close points at, and what names it.

    Refused (`CloseRefusedError`) unless the named task's work landed on main, or the named commit
    is on it."""
    by_task = (by_task or "").strip() or None
    commit = (commit or "").strip() or None
    if bool(by_task) == bool(commit):
        raise CloseRefusedError(
            "name the task whose work is on main, or a commit on main -- one of the two",
            code="no_target",
            http_status=422,
        )
    project = await session.get(Project, project_id)
    main_branch = project.main_branch if project is not None else None
    if not main_branch:
        raise CloseRefusedError(
            "the project has no main branch set, so nothing says the work is on it; set it in "
            "the project's settings first",
            code="no_main_branch",
        )
    named_id: Optional[str] = None
    label: str
    if by_task:
        named_id = await readable_ids.resolve(session, project_id, by_task)
        other = await session.get(Task, named_id)
        if other is None or other.project_id != project_id:
            raise CloseRefusedError(f"{by_task} is not a task here", code="unknown_task")
        label = other.readable_id or other.id
        landing = await landing_queue.latest_landing(session, other.id)
        if (
            other.status != "approved"
            or landing is None
            or landing.state != landing_queue.LANDED
            or not landing.landed_sha
        ):
            where = (
                "approved but not landed yet"
                if other.status == "approved"
                else f"{other.status!r}, not approved"
            )
            raise CloseRefusedError(
                f"{label} is not on main: it is {where}", code="task_not_on_main"
            )
        ref = landing.landed_sha
    else:
        label = commit or ""
        ref = commit or ""
    found = await blocking.run(already_built._resolve_commits, workspace.root, [ref], main_branch)
    if found["unknown"]:
        raise CloseRefusedError(
            f"{label} is not in this repository", code="commit_not_on_main", http_status=422
        )
    if found["off_main"]:
        raise CloseRefusedError(
            f"{label} is not on {main_branch}", code="commit_not_on_main", http_status=422
        )
    return {"sha": found["resolved"][0], "label": label, "by_task": named_id}


async def _refusal_for(session: AsyncSession, task: Task, outcome: str) -> Optional[Refused]:
    name = task.readable_id or task.id
    if task.loop_id is not None:
        return Refused(
            name,
            "it is in a flow or loop, and a flow's tasks keep the moves they have",
            "in_flow",
        )
    landing = await landing_queue.latest_landing(session, task.id)
    if task.status == "rejected":
        return Refused(name, "it is already closed", "already_closed")
    if task.status == "approved":
        if landing is not None and landing.state == landing_queue.LANDED:
            return Refused(name, "it is already on main", "already_closed")
        if outcome == DONE_ELSEWHERE:
            return Refused(
                name,
                "it is approved and waiting to land; send it back or cancel it instead",
                "approved_waiting",
            )
    live = await run_liveness.live_turn_for_task(session, task)
    if live is not None:
        return Refused(
            name,
            f"a turn is still running on it ({live.agent}); stop it or let it end first",
            "turn_running",
        )
    return None


async def close_tasks(
    session: AsyncSession,
    project_id: str,
    task_refs: Sequence[str],
    outcome: str,
    *,
    by_task: Optional[str] = None,
    commit: Optional[str] = None,
    reason: Optional[str] = None,
    workspace=None,
) -> Dict[str, Any]:
    """Close each task in *task_refs* as *outcome*; `{closed: [...], refused: [...], ...}`."""
    from .task_transition_service import TransitionRefusedError, apply_transition

    operator = task_transitions.operator()
    target: Optional[Dict[str, Any]] = None
    if outcome == DONE_ELSEWHERE:
        target = await _resolve_target(
            session, project_id, by_task=by_task, commit=commit, workspace=workspace
        )
    closed: List[Dict[str, Any]] = []
    refused: List[Dict[str, str]] = []
    for ref in task_refs:
        task_id = await readable_ids.resolve(session, project_id, ref)
        task = await session.get(Task, task_id)
        if task is None or task.project_id != project_id:
            refused.append({"task": ref, "reason": "it is not a task here", "code": "unknown_task"})
            continue
        name = task.readable_id or task.id
        refusal = await _refusal_for(session, task, outcome)
        if refusal is None and target is not None and target["by_task"] == task.id:
            refusal = Refused(name, "it cannot be closed as done by itself", "self")
        if refusal is not None:
            refused.append({"task": refusal.task, "reason": refusal.reason, "code": refusal.code})
            continue
        try:
            async with session.begin_nested():
                if target is not None:
                    _close_done_elsewhere(session, task, target)
                else:
                    await _cancel(session, task, reason, apply_transition, operator)
        except TransitionRefusedError as exc:
            refused.append({"task": name, "reason": str(exc), "code": "move_refused"})
            continue
        from .run_task_binding import release_bindings_to, release_reason

        release_reason(task)
        await release_bindings_to(session, task)
        closed.append({"id": task.id, "readable_id": task.readable_id, "status": task.status})
    return {
        "outcome": outcome,
        "commit": target["sha"] if target else None,
        "closed": closed,
        "refused": refused,
    }


def _close_done_elsewhere(session: AsyncSession, task: Task, target: Dict[str, Any]) -> None:
    """Approve *task* at the commit already on main, without the landing queue: its landing row is
    written `landed`, so no check, batch or review is ever started for it."""
    sha: str = target["sha"]
    note = f"{DONE_ELSEWHERE_NOTE}{already_built.short(sha)}" + (
        f" (by {target['label']})" if target["by_task"] else ""
    )
    previous = task.status
    task.status = "approved"
    task.assignee = None
    session.add(
        TaskTransition(
            id=f"ttr-{short_id()}",
            project_id=task.project_id,
            task_id=task.id,
            from_status=previous,
            to_status="approved",
            actor_kind="operator",
            origin="actor",
            note=note,
            level=task.level if task.build_id else None,
        )
    )
    session.add(
        TaskLanding(
            id=f"land-{short_id()}",
            project_id=task.project_id,
            task_id=task.id,
            state=landing_queue.LANDED,
            kind="closed",
            order_key=0.0,
            actor_kind="operator",
            actor="operator",
            reason=note,
            landed_sha=sha,
            ended_at=landing_queue._now(),
        )
    )


async def _cancel(session, task: Task, reason: Optional[str], apply_transition, operator) -> None:
    if task.status == "approved":
        # Not on main yet: sending it back withdraws what it queued, so nothing of it lands.
        await apply_transition(session, task, "revision_needed", operator, note=cancel_note(reason))
    await apply_transition(session, task, "rejected", operator, note=cancel_note(reason))
