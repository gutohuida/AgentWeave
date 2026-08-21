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


class IntegrationRetryRefusedError(TransitionRefusedError):
    """Integration was asked for on a task that is not in a state to receive it.

    409 rather than 403: any actor may ask, and it is the task's status that forbids it.
    """

    http_status = 409


class GateUnsatisfiedError(TransitionRefusedError):
    """The task serves a requirement an enforcing document has, and it is not verified.

    409 rather than 403: the request is well-formed and the asker is entitled to make it — the
    *state* of the work is what forbids it. Carries the structured refusal so a surface can render
    each blocking requirement rather than parse a sentence.
    """

    http_status = 409

    def __init__(self, refusal) -> None:
        super().__init__(refusal.detail())
        self.refusal = refusal


class DependencyUnmetError(TransitionRefusedError):
    """The task depends on work that is not `approved` yet (`task-dependencies` design D1/D2).

    409, same reasoning as `GateUnsatisfiedError`: the request is well-formed and the asker may make
    it — a *prerequisite's* state is what forbids it, not this task's own. Carries the structured
    refusal so a surface can render each unmet or permanently-rejected prerequisite rather than
    parse a sentence.
    """

    http_status = 409

    def __init__(self, refusal) -> None:
        super().__init__(refusal.detail())
        self.refusal = refusal


#: Reaching `approved`, `rejected` or `revision_needed` is a judgement on work someone else did.
#: These are the moves author/reviewer separation guards.
_REVIEW_OUTCOMES = frozenset({"approved", "rejected", "revision_needed"})


async def _agent_that_completed(session: AsyncSession, task_id: str) -> Optional[str]:
    """The **agent** responsible for the most recent move of this task into `completed`.

    Agent, not run. The first version of this compared `run_id`, and live use on 2026-08-10 walked
    straight through it: an agent completed a task on one run and approved it on its next, which
    are different runs by construction. Every turn is a new run, so a run-based check is satisfied
    by an agent merely continuing its own work — it forbade nothing.

    Read from the history and never from `Task.updated_by_run_id`: that column is a single mutable
    field which the approving write overwrites, and it being unable to answer this question is the
    whole reason this table exists.
    """
    result = await session.execute(
        select(TaskTransition.actor_agent)
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

    The comparison is on **agent**, so it holds across turns. An earlier version compared runs and
    was found in live use to forbid nothing, because a new turn is a new run.

    What it still does not claim: two *different* agents belonging to the same operator can review
    each other freely, which is the intended shape rather than a gap. Nor does it reason about
    whether the review was diligent — that is B4's evidence gates.
    """
    if actor.is_operator or to_status not in _REVIEW_OUTCOMES:
        return
    completing_agent = await _agent_that_completed(session, task.id)
    if completing_agent is not None and completing_agent == actor.agent:
        raise ActorNotPermittedError(
            f"Cannot move task {task.id} to {to_status!r}: agent {actor.agent!r} recorded the "
            f"task's move to 'completed', and approving, rejecting or requesting revision of work "
            f"requires a different actor. Another agent or the operator must review it. Starting a "
            f"new run does not make you a different actor."
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


#: What caused a transition to be *requested*. `runtime` means the Hub made the move on the run's
#: behalf at a moment the run did not choose — today, moving a task to `in_progress` because a run
#: bound to it. The run and agent are still recorded, because the system acts *as* the run rather
#: than instead of it, which is why there is no third actor kind
#: (`2026-08-10-run-task-binding`, design D5).
ORIGIN_ACTOR = "actor"
ORIGIN_RUNTIME = "runtime"
ORIGINS = frozenset({ORIGIN_ACTOR, ORIGIN_RUNTIME})


async def apply_transition(
    session: AsyncSession,
    task: Task,
    to_status: str,
    actor: Actor,
    origin: str = ORIGIN_ACTOR,
) -> Optional[TaskTransition]:
    """Move `task` to `to_status` as `actor`, recording it. Returns None when nothing changed.

    Raises `TransitionRefusedError` (or a subclass) instead of mutating when the move is not permitted.
    The caller commits; this function stages the change and the history row together so a refusal
    after a partial write is not possible.

    `origin` defaults to `actor` because that is what almost every caller is, and because a default
    of `runtime` would let a forgotten argument quietly exempt a real transition from the divergence
    check. Only the run→task binding passes `runtime`, and a source scan in
    `hub/tests/test_task_transitions.py` holds that true.

    A `runtime` transition is subject to every legality and actor rule a requested one is: it is the
    *same* call, with the same `Actor`. The runtime cannot make a move the run could not.
    """
    if origin not in ORIGINS:
        raise ValueError(f"origin must be one of {sorted(ORIGINS)}, got {origin!r}")

    from_status = task.status

    # D7: restating the current status is a no-op that records nothing. An agent plane retry would
    # otherwise manufacture a `completed -> completed` transition, and "who completed this" would
    # start returning the retrying run.
    if to_status == from_status:
        return None

    if not is_allowed(from_status, to_status, actor.kind):
        raise IllegalTransitionError(refusal_detail(from_status, to_status, actor.kind))

    await _guard_author_is_not_reviewer(session, task, to_status, actor)

    # The dependency gate, on the `-> in_progress` edge only (`task-dependencies` design D1) — this
    # covers `pending -> in_progress`, `assigned -> in_progress` and the `blocked -> in_progress`
    # resume edge alike, since all three share this one `to_status`. Not `-> assigned` and not
    # `-> rejected`: a whole wave can be routed ahead of time and each task starts only once its own
    # prerequisites clear. Same placement reasoning as the requirement gate below — inside the
    # service and before the history row, so every caller (operator route, agent HTTP, the tool
    # surface, jobs and the run-binding runtime move) is covered without knowing this exists.
    if to_status == "in_progress":
        from .dependency_gate import evaluate as evaluate_dependencies

        dependency_refusal = await evaluate_dependencies(session, task)
        if dependency_refusal.refuses:
            raise DependencyUnmetError(dependency_refusal)

    # The gate, on this one edge. Inside the service and before the history row, so it cannot be
    # bypassed by a caller reaching the row a different way — which is also why every surface
    # (operator route, agent HTTP, the tool surface, jobs) gets it without knowing it exists.
    #
    # Imported locally: `requirement_gate` reads coverage, which reads the models, and this module
    # is the one every status write already passes through.
    policy = ""
    reported: list = []
    if to_status == "approved":
        from .requirement_gate import evaluate

        refusal, policy = await evaluate(session, task)
        if refusal.refuses:
            raise GateUnsatisfiedError(refusal)
        # `contract` never refuses, so its unmet and rejected requirements have nowhere to surface
        # unless this call carries them out. Not persisted — a transient attribute on the returned
        # row rather than a column, because this is a report at the moment of approval, not an
        # audit trail; the audit trail is `requirement_coverage` and evidence review, unchanged.
        reported = list(refusal.reported)

    task.status = to_status
    transition = TaskTransition(
        id=f"ttr-{short_id()}",
        project_id=task.project_id,
        task_id=task.id,
        from_status=from_status,
        to_status=to_status,
        actor_kind=actor.kind,
        run_id=actor.run_id,
        actor_agent=actor.agent,
        origin=origin,
        # What governed this move. Null where no policy did — a fact about the transition rather
        # than a gap in it.
        policy_digest=policy or None,
    )
    # Not a column — see the comment where `reported` is built. `TaskResponse` reads this off the
    # object this same call returns; nothing else looks for it, and nothing persists it.
    transition.reported_advisories = reported
    session.add(transition)

    if origin == ORIGIN_ACTOR:
        # A divergence is an open condition, not a verdict: work reaching the ledger closes it,
        # whoever brought it there. Resolved here, inside the one function every accepted
        # transition passes through, so no caller can move a task by a route that leaves a stale
        # divergence showing against it.
        #
        # Imported locally: `run_divergence` reads the transition history through the binding
        # module, which is built on this one.
        from .run_divergence import resolve_divergences_for_task

        await resolve_divergences_for_task(session, task.id)

    if to_status == "approved":
        await integrate_task(session, task, actor)

    return transition


async def retry_integration(session: AsyncSession, task: Task, actor: Actor) -> list:
    """Attempt integration again for a task that is already approved.

    Integration runs on the transition *into* `approved`, and restating a status is deliberately a
    no-op (D7 of the previous change) — so a merge that was skipped can never be attempted again by
    approving harder. Most skips name something the operator then puts right: a main branch that was
    never chosen, a checkout with uncommitted changes, a checkout parked elsewhere. Without a second
    entry point the remediation the system asked for accomplishes nothing, which was observed live.

    A second entry point to the same coroutine, rather than a second path through the transition:
    the early return that makes restating a no-op is correct and stays, because manufacturing an
    `approved -> approved` row would make "who approved this" start returning the retrying run.

    No refusal when the work is already merged. `task_integration.integrate` self-guards with
    `ALREADY_INTEGRATED`, which asks the repository whether the commit is reachable — a fact — rather
    than reading the attempt log, which records only what was tried. So a retry after a merge
    honestly records one skip and merges nothing.
    """
    if task.status != "approved":
        raise IntegrationRetryRefusedError(
            f"Cannot retry integration for a task in {task.status!r}: "
            "only an approved task has work to integrate."
        )
    return await integrate_task(session, task, actor)


async def integrate_task(session: AsyncSession, task: Task, actor: Actor) -> list:
    """Put the approved work in the product, and record what happened either way.

    **After** the transition row, and never able to undo it. Approval is a judgement that the work
    is good; a git failure is not a reason to reverse a judgement. Where the merge does not happen,
    coverage already has the words for it — `verified, not integrated` — so the product's account
    stays true without anything new being invented.

    Mergeability was tested before the transition (`requirement_gate`), so a failure here means the
    world moved in between. That is rare, recorded, and not fatal.
    """
    from . import project_workspace, task_integration
    from .db.models import Project

    project = await session.get(Project, task.project_id)
    if project is None:
        return []

    def _record(result: task_integration.IntegrationResult) -> list:
        task_integration.record(
            session,
            task,
            result,
            actor_kind=actor.kind,
            actor=actor.agent or "",
        )
        return [result]

    if not project.main_branch:
        return _record(
            task_integration.IntegrationResult(
                outcome=task_integration.SKIPPED, reason=task_integration.NO_MAIN_BRANCH
            )
        )

    try:
        workspace = await project_workspace.resolve_project_workspace(session, task.project_id)
    except Exception as exc:  # noqa: BLE001 - any workspace failure is a skip, never a rollback
        return _record(
            task_integration.IntegrationResult(
                outcome=task_integration.SKIPPED,
                reason=f"the project's workspace is unavailable: {exc}",
                target_branch=project.main_branch,
            )
        )

    root = workspace.root
    if not task_integration.is_repository(root):
        return _record(
            task_integration.IntegrationResult(
                outcome=task_integration.SKIPPED,
                reason=task_integration.NOT_A_REPOSITORY,
                target_branch=project.main_branch,
            )
        )

    targets = await task_integration.integration_targets(session, task)
    if not targets:
        return _record(
            task_integration.IntegrationResult(
                outcome=task_integration.SKIPPED,
                reason=task_integration.NOTHING_TO_MERGE,
                target_branch=project.main_branch,
            )
        )

    results = [task_integration.integrate(root, target, project.main_branch) for target in targets]
    for result in results:
        _record(result)

    # Re-answer "has this reached the main line?" across the project, not only for what just merged.
    # Bringing in one requirement's commit genuinely brings in every earlier commit on the same
    # branch, and coverage should say so rather than reporting work as unintegrated because its own
    # evidence predates the merge that carried it.
    if any(result.outcome == task_integration.MERGED for result in results):
        from . import requirement_evidence

        await requirement_evidence.refresh_reachability(
            session, task.project_id, root, main_branch=project.main_branch
        )

    return results


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
