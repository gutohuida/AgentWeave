"""Applying a task status change, or refusing it with a reason the caller can act on.

`task_transitions.py` declares the machine and answers questions about it without touching a
database. This module is where the machine meets a row: it reads the history to decide whether the
requesting actor is entitled to the move, writes the history when the move is accepted, and raises
a typed refusal when it is not.

The two refusals are deliberately distinct (design D6). An illegal move is a **409** — the request
is well-formed, the *state* is wrong. An actor who may not make an otherwise-legal move is a
**403** — the state is fine, the *asker* is wrong. Collapsing them into one code would send an
agent looking for a payload mistake it did not make.

This is also the seam B3's evidence checks and B4's completion gates plug into: they belong inside
`apply_transition`, before the history row is written, so a gate cannot be bypassed by a caller who
reaches the row a different way.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Task, TaskTransition
from .task_transitions import (
    Actor,
    allowed_targets,
    is_allowed,
    refusal_detail,
)
from .utils import short_id


class TransitionRefusedError(Exception):
    """A status change the machine will not make. Carries the HTTP status the route should send."""

    http_status = 409

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class IllegalTransitionError(TransitionRefusedError):
    """The move is not an edge of the map for this actor — the task's state forbids it."""

    http_status = 409


class ActorNotPermittedError(TransitionRefusedError):
    """The move is a legal edge, but not for this actor — author/reviewer separation."""

    http_status = 403


class InvalidEntryStatusError(TransitionRefusedError):
    """A task was created in a status that is not an entry point."""

    http_status = 409


#: Reaching `approved`, `rejected` or `revision_needed` is a judgement on work someone else did.
#: These are the moves author/reviewer separation guards.
_REVIEW_OUTCOMES = frozenset({"approved", "rejected", "revision_needed"})


async def _run_that_completed(session: AsyncSession, task_id: str) -> Optional[str]:
    """The run responsible for the most recent move of this task into `completed`.

    Read from the history and never from `Task.updated_by_run_id`: that column is a single mutable
    field which the approving write overwrites, and it being unable to answer this question is the
    whole reason this table exists.
    """
    result = await session.execute(
        select(TaskTransition.run_id)
        .where(TaskTransition.task_id == task_id)
        .where(TaskTransition.to_status == "completed")
        # By `sequence`, not `created_at`: transitions staged in one flush share a timestamp, and
        # "most recent completion" must mean the last one that happened, not an arbitrary pick
        # among ties. This matters after a revision cycle, where an earlier completion by another
        # run is exactly what must not be chosen.
        .order_by(TaskTransition.sequence.desc())
        .limit(1)
    )
    row = result.first()
    return row[0] if row else None


async def _guard_author_is_not_reviewer(
    session: AsyncSession, task: Task, to_status: str, actor: Actor
) -> None:
    """An agent run may not sign off work it produced.

    Binds agent runs only. The operator may approve their own work — refusing that would make a
    single-operator project unable to approve anything — and the history records that an operator
    did it (design D9).

    Note what this does *not* claim: an agent completing on one run and approving on its next run
    satisfies the letter of the rule. B1 closes self-approval *within a run*, not collusion across
    runs; separating agent identity from run identity is a B3/B4 concern.
    """
    if actor.is_operator or to_status not in _REVIEW_OUTCOMES:
        return
    completing_run = await _run_that_completed(session, task.id)
    if completing_run is not None and completing_run == actor.run_id:
        raise ActorNotPermittedError(
            f"Cannot move task {task.id} to {to_status!r}: this run recorded the task's move to "
            f"'completed', and approving, rejecting or requesting revision of work requires a "
            f"different actor. Another agent or the operator must review it."
        )


def guard_entry_status(status: str) -> None:
    """Refuse a task created anywhere but an entry point (design D10).

    Without this the machine is walkable around: a caller creates a task already `approved` and
    never makes a transition at all, so no rule about transitions can reach it.
    """
    from .task_transitions import ENTRY_STATUSES, is_entry_status

    if not is_entry_status(status):
        allowed = ", ".join(sorted(ENTRY_STATUSES))
        raise InvalidEntryStatusError(
            f"A task cannot be created with status {status!r}. A new task may only start at: "
            f"{allowed}. Every other status is reached by transitioning."
        )


async def apply_transition(
    session: AsyncSession,
    task: Task,
    to_status: str,
    actor: Actor,
) -> Optional[TaskTransition]:
    """Move `task` to `to_status` as `actor`, recording it. Returns None when nothing changed.

    Raises `TransitionRefusedError` (or a subclass) instead of mutating when the move is not permitted.
    The caller commits; this function stages the change and the history row together so a refusal
    after a partial write is not possible.
    """
    from_status = task.status

    # D7: restating the current status is a no-op that records nothing. An agent plane retry would
    # otherwise manufacture a `completed -> completed` transition, and "who completed this" would
    # start returning the retrying run.
    if to_status == from_status:
        return None

    if not is_allowed(from_status, to_status, actor.kind):
        raise IllegalTransitionError(refusal_detail(from_status, to_status, actor.kind))

    await _guard_author_is_not_reviewer(session, task, to_status, actor)

    task.status = to_status
    transition = TaskTransition(
        id=f"ttr-{short_id()}",
        project_id=task.project_id,
        task_id=task.id,
        from_status=from_status,
        to_status=to_status,
        actor_kind=actor.kind,
        run_id=actor.run_id,
    )
    session.add(transition)
    return transition


async def history_for(session: AsyncSession, task_id: str) -> list[TaskTransition]:
    """Every recorded transition for a task, oldest first."""
    result = await session.execute(
        select(TaskTransition)
        .where(TaskTransition.task_id == task_id)
        .order_by(TaskTransition.sequence.asc())
    )
    return list(result.scalars().all())


def reachable_from(status: str, actor: Actor) -> frozenset:
    """What `actor` may move a task in `status` to. Thin pass-through, kept so callers depend on
    the service rather than reaching around it into the declaration."""
    return allowed_targets(status, actor.kind)
