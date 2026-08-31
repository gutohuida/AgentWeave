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

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Run, Task, TaskTransition
from .task_transitions import (
    STATUS_BLOCKED,
    Actor,
    allowed_targets,
    is_allowed,
    refusal_detail,
)
from .utils import short_id

logger = logging.getLogger(__name__)


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


class RunNotBoundError(TransitionRefusedError):
    """A run tried to claim or finish a task it does not hold.

    403 rather than 409, by this module's own rule: the task's state is fine and the move is a legal
    edge — the *asker* is wrong. Collapsing it into 409 would send an agent looking for a state
    problem that is not there.
    """

    http_status = 403


@dataclass(frozen=True)
class CompletionAttribution:
    """What the record says about the most recent move of a task into `completed`.

    Three fields because `agent_that_completed`'s `None` is **two worlds**, and until this existed
    no caller could tell them apart:

    1. the **operator** completed it — provenance exists and is a person;
    2. **nothing** completed it — the row was written straight into the status, or predates the
       transition table.

    They are separable at zero cost. `Actor.__post_init__` makes an actor of kind `run` *without* an
    agent unconstructible and an actor of kind `operator` *with* one equally so, so on a
    `-> completed` transition `actor_agent IS NULL` is exactly *the operator made the move*. One
    extra column on a query the callers already run tells the two apart: no migration, no new
    column, no second round trip.

    Measured live (F142, 2026-08-30): a flow whose only task the operator had marked finished was
    dropped by `decide_firing` in silence, on every firing, forever — because the walk read `None`
    and had no way to ask which world it was in.
    """

    #: Whether a `-> completed` transition is recorded for the task at all.
    recorded: bool
    #: `'run'` or `'operator'`, or `None` where nothing is recorded.
    actor_kind: Optional[str]
    #: The agent, where a run recorded it. `None` for an operator completion and for no completion.
    agent: Optional[str]


async def completion_attribution(session: AsyncSession, task_id: str) -> CompletionAttribution:
    """Who is recorded as making the most recent move of this task into `completed`.

    Agent, not run. The first version of `agent_that_completed` compared `run_id`, and live use on
    2026-08-10 walked straight through it: an agent completed a task on one run and approved it on
    its next, which are different runs by construction. Every turn is a new run, so a run-based
    check is satisfied by an agent merely continuing its own work — it forbade nothing.

    Read from the history and never from `Task.updated_by_run_id`: that column is a single mutable
    field which the approving write overwrites, and it being unable to answer this question is the
    whole reason this table exists.
    """
    result = await session.execute(
        select(TaskTransition.actor_kind, TaskTransition.actor_agent)
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
    if row is None:
        return CompletionAttribution(recorded=False, actor_kind=None, agent=None)
    return CompletionAttribution(recorded=True, actor_kind=row[0], agent=row[1])


async def agent_that_completed(session: AsyncSession, task_id: str) -> Optional[str]:
    """The **agent** responsible for the most recent move of this task into `completed`.

    A wrapper over `completion_attribution`, with its signature and semantics unchanged. `None`
    still means *no agent is recorded as completing this* — which is true of an operator completion
    and of no completion at all, the two worlds that function exists to separate. Seven callers read
    this `None` in three different ways and four of them are correct as written; a caller that needs
    to know *which* world reaches for `completion_attribution` rather than reinterpreting this
    return value.

    The argument for reading the history, and for ordering by `sequence`, lives on
    `completion_attribution`.
    """
    return (await completion_attribution(session, task_id)).agent


async def agents_that_worked(session: AsyncSession, task_id: str) -> "set[str]":
    """The agents recorded on this task's **transitions**. *"Which agents moved this task?"*

    Not `{task.assignee}`, and the reason is that `assignee` is one mutable column overwritten by
    every restaff: a task returned for revision and picked up by a second agent has two authors and
    only the history names both.

    **And it is not every agent that worked the task either** — the converse matters just as much,
    because round 1 of this change asserted the opposite. An agent takes a transition only when it
    *changes* a task's status, so an agent whose run binds to a task already `in_progress` travels
    no edge and leaves no row here (`TRANSITIONS` has no `in_progress -> in_progress`). A task the
    operator started by hand, let an agent work, and then marked finished carries a full history
    that names no agent at all.

    So this is a **term** in the exclusion `agents_that_may_have_authored` builds, and it is used
    alone in exactly one place: the wedged-review predicate in `scheduler.py`, which asks whether
    the *assignee* is one of the agents that moved the task and for which the wider set is wrong by
    construction (`task-lifecycle-governance`).
    """
    rows = await session.execute(
        select(TaskTransition.actor_agent)
        .where(TaskTransition.task_id == task_id)
        .where(TaskTransition.actor_agent.isnot(None))
        .distinct()
    )
    return {agent for agent in rows.scalars().all() if agent}


async def agents_of_runs_bound_to(session: AsyncSession, task_id: str) -> "set[str]":
    """The agents whose runs were recorded as **about** this task.

    `bind_run_to_task`'s first statement is `run.task_id = task.id`, above the `blocked` guard and
    above the legality check, so a run that binds and takes no transition still records that it was
    about the task. That is the one record in the product naming the *second* agent to work a task
    already in progress: it is absent from the transitions (no edge was legal) and absent from
    `assignee` (the column was already filled by the first).

    **Why this reaches for a column `checkpoint_handover.py:87-92` forbids in the strongest terms.**
    That module rules out `run.task_id` on measurement — *"of the ten runs that had recorded a
    `completed` transition, six carried `run.task_id = NULL`"* — and a function reaching for it
    right afterwards has to say why it is not the same mistake. The failure directions are
    opposite. `_task_this_run_completed` asks *which task did this run finish?*, and a NULL there
    produces a **wrong answer**: a handover that should have happened does not. This asks *might
    this agent be the author?*, and a NULL produces a **missing candidate** in a set whose only job
    is to grow. A source that under-reports cannot make an exclusion unsafe; it can only fail to
    make it safer.

    Which is exactly why this is a **term and never the set**. Dropping the transition set in favour
    of this one would reproduce `checkpoint_handover`'s bug with this docstring's blessing.
    """
    rows = await session.execute(select(Run.agent).where(Run.task_id == task_id).distinct())
    return {agent for agent in rows.scalars().all() if agent}


async def agents_that_may_have_authored(session: AsyncSession, task: Task) -> "set[str]":
    """*"Might this agent be the author of this task's work?"* — the exclusion a reviewer ladder gets.

    Every agent **any** record associates with the task: the transitions that moved it, the agent it
    is assigned to, and the runs recorded as bound to it. Three sources for one question is not
    elegant, and the reason it is nonetheless right is that each names a different fact and each is
    individually incomplete:

    | source | names | misses |
    |---|---|---|
    | transitions | every agent that **moved** it | one that worked it without moving it |
    | `assignee` | the agent that **holds** it now | every previous holder, and everyone after the first |
    | bound runs | every agent whose run was **about** it | runs predating the column, and runs never bound |

    Used where no completion names an agent, which is the case where *the author is not provable
    from anything* — so the narrowest set that provably contains the author does not exist, and this
    is its honest replacement. The determination is therefore **over-inclusive by construction**: a
    record associating an agent with a task is sufficient to exclude it, and a source's silence is
    not evidence that the agent did not work it. The cost of excluding an agent that did nothing is
    a review the flow reports it could not staff, which the operator sees and resolves; the cost of
    including an agent that wrote the work is a self-approval nobody sees.

    **Not `agents_that_worked`, and the distinction is load-bearing.** That function answers *which
    agents moved this task?* and is what the wedged-review predicate needs; this one answers *might
    this agent be the author?* and is what an exclusion needs. Using this one there makes
    `assignee in <the set>` true of every assigned task, so every review genuinely in progress
    reports as one nobody is doing.
    """
    worked = await agents_that_worked(session, task.id)
    bound = await agents_of_runs_bound_to(session, task.id)
    return worked | bound | ({task.assignee} if task.assignee else set())


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
    completing_agent = await agent_that_completed(session, task.id)
    if completing_agent is not None and completing_agent == actor.agent:
        raise ActorNotPermittedError(
            f"Cannot move task {task.id} to {to_status!r}: agent {actor.agent!r} recorded the "
            f"task's move to 'completed', and approving, rejecting or requesting revision of work "
            f"requires a different actor. Another agent or the operator must review it. Starting a "
            f"new run does not make you a different actor."
        )


async def _guard_reviewer_is_not_the_author(
    session: AsyncSession, task: Task, to_status: str, actor: Actor
) -> None:
    """A task entering `under_review` may not still name its author as the one holding it.

    Found live 2026-08-27 (F70), driving a fresh project. A task was moved straight from
    `completed` to `under_review` without reassigning it away from the agent that completed it.
    Nothing refused, nothing logged, and the row was wedged permanently: `scheduler`'s
    `WITH_REVIEWER_LOOP_TASK_STATUSES` branch reads `under_review` as *a reviewer already holds
    this*, so the task is claimable by nobody and its exits are never offered; and because
    `_agents_that_are_free` counts that assignee as holding active work, the agent became
    unrecruitable as a reviewer for every **other** task in the project too. One bad edge, and the
    project's whole review capacity quietly drops by one.

    **This binds the operator, and that is the difference from `_guard_author_is_not_reviewer`.**
    That guard is about *authority* — who is entitled to sign off work — and the operator is
    exempt because a single-operator project must be able to approve anything. This one is about
    the *state the move produces*, which is a lie about the world no matter who writes it: it says
    a reviewer holds the task while naming the author. An operator reviewing the work themselves is
    still free to; they clear or reassign `assignee` first, which is what the refusal asks for.

    Two permissive cases, both deliberate:

    * **No assignee.** Nobody is claimed to hold it, so nothing is false and nothing wedges — the
      scheduler's branch records an in-flight holder only `if task.assignee`. This is the operator
      taking a task off the agents' board to look at themselves.
    * **No recorded completer.** The same asymmetry `_guard_author_is_not_reviewer` documents and
      `task_is_claimable_by` explains at length: refuse to *offer*, permit to *act*. A guard that
      blocked every move it could not attribute would stop legitimate work over a missing history
      row, and a task completed before the transition table existed has no completer to compare.

    The flow's own path satisfies this by construction — `enter_selected_task` writes the
    reviewer into `assignee` before it transitions, which it must, or the flow would refuse itself
    here on every review it staffs.

    **`actor` is deliberately unread**, and keeping it in the signature is the point rather than an
    oversight: this is one of the three actor-entitlement guards `apply_transition` calls in a row,
    so it takes their shape — and the fact that the parameter goes unused is exactly the paragraph
    above, in code. Nobody is exempt because the rule is not about who is asking.
    """
    if to_status != "under_review" or not task.assignee:
        return
    completing_agent = await agent_that_completed(session, task.id)
    if completing_agent is not None and completing_agent == task.assignee:
        raise ActorNotPermittedError(
            f"Cannot move task {task.id} to 'under_review': it is still assigned to "
            f"{task.assignee!r}, the agent recorded as completing it, so the move would claim its "
            f"own author is reviewing it. Assign a different reviewer, or clear the assignee to "
            f"review it yourself. Left as is, the task is claimable by nobody and "
            f"{task.assignee!r} counts as busy for every other review in this project."
        )


async def _guard_run_holds_the_task(
    session: AsyncSession, task: Task, to_status: str, actor: Actor
) -> None:
    """A run may claim work it does not hold, but may only finish work it does.

    Found live 2026-08-25 (F27): a run whose entire prompt was *"concurrency probe 1: reply CONC-1
    only"*, carrying `task_id = NULL`, moved four unrelated tasks straight to `completed`; a second
    unbound run took two more. Six tasks recorded as finished and no work done on any of them.

    Nothing was individually wrong, which is why no test caught it. The Developer charter tells
    agents to go and find waiting work. `TRANSITIONS` legally grants a `run` actor both edges.
    `completed` deliberately requires no evidence, because evidence is accepted after review and
    review follows completion — refusing there would deadlock the ordinary path, as
    `requirement_gate`'s docstring explains. The gap was that nothing asked whether the run closing
    a task was the run that took it, though `run_task_binding` already records exactly that.

    It does not stop at bookkeeping. `completed` is in `BAND_AWAITING_HANDOFF`, so a flow offers
    each falsely-finished task to *another* agent as reviewable work; that reviewer finds the code
    correct — it is, because a different agent really did it — approves, and `task_integration`
    merges. No human on that path, and no single false statement along it.

    So the rule is in two halves, and the second is only enforceable because of the first:

    * `-> in_progress` — **claiming binds.** A run holding nothing takes the task. This is what
      keeps the charter's "call `list_tasks` to see what is waiting" a real behaviour rather than a
      dead end. A run already holding a *different* task is refused, which is the existing
      `run-task-binding` invariant that a run carries at most one binding.
    * `-> completed` — **only the holder finishes.** `TRANSITIONS` makes `completed` reachable only
      from `in_progress`, so every legitimate completion has already passed through the claim above
      and is therefore bound. That is what makes this check safe to apply unconditionally rather
      than a trap for some path nobody remembered.

    The operator is untouched in both halves: `is_operator` returns immediately. An operator marking
    a card done is a statement by a person, and has never needed a binding.

    `bind_run_to_task` sets `run.task_id` *before* calling `apply_transition(..., origin=runtime)`,
    so the runtime path arrives already bound and takes the no-op branch.

    A run id with no `Run` row cannot be produced by any surface — the agent plane binds identity
    from a per-run credential (`agent_auth.py`) and never accepts it from a request — so rather than
    inventing a policy for an unreachable state, this leaves such a caller alone. There is no
    binding to check and none to record.
    """
    if actor.is_operator or to_status not in ("in_progress", "completed"):
        return
    run = await session.get(Run, actor.run_id)
    if run is None:
        return

    if run.task_id == task.id:
        return

    if to_status == "in_progress" and run.task_id is None:
        run.task_id = task.id
        return

    held = (
        f"it is already working task {run.task_id}" if run.task_id else "it is not working any task"
    )
    verb = "claim" if to_status == "in_progress" else "complete"
    raise RunNotBoundError(
        f"This run cannot {verb} task {task.id}: {held}. A run finishes the task it took, and "
        f"takes at most one. To work this task, start a run bound to it — or, if you meant to "
        f"report on work you did not do, say so rather than moving its status."
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

    # Beside the author/reviewer guard for the same reason `_guard_run_holds_the_task` is: it asks
    # whether this actor may make this move, not whether the work is ready. It runs on the other
    # end of the review — the entry rather than the verdict — and F70 is what the missing half
    # cost.
    await _guard_reviewer_is_not_the_author(session, task, to_status, actor)

    # Who is doing the work, before anything about whether the work may proceed (F27). Beside the
    # author/reviewer guard because it answers the same kind of question — is this actor entitled to
    # this move — rather than the gates below, which ask about the state of the work.
    await _guard_run_holds_the_task(session, task, to_status, actor)

    # The dependency gate, on the edges that *begin* work: `pending -> in_progress` and
    # `assigned -> in_progress`. Not `-> assigned` and not `-> rejected`: a whole wave can be routed
    # ahead of time and each task starts only once its own prerequisites clear. Same placement
    # reasoning as the requirement gate below — inside the service and before the history row, so
    # every caller (operator route, agent HTTP, the tool surface, jobs and the run-binding runtime
    # move) is covered without knowing this exists.
    #
    # **`blocked -> in_progress` is exempt** (`a-task-waits-while-its-run-waits`, design D5), which
    # reverses a shipped rule that used to be stated right here. Three facts carry it:
    #
    # 1. the gate asks whether work may *start*, and `blocked` is reachable only from
    #    `in_progress` — so this work started, and this edge resumes it;
    # 2. every refusal at this edge is necessarily a change that happened *after* the task started,
    #    which the shipped `task-dependencies` requirement *A dependency that regresses after a
    #    dependent has started does not halt it* already governs. Gating here breached that; the
    #    exemption restores it rather than trading it away;
    # 3. `scheduler.candidate_is_startable` already exempts `blocked` from this same call, in these
    #    words: *"nothing is about to transition it either — it is waiting on a person. Gating it
    #    would be asking whether work that is not about to start is allowed to start."* The board
    #    and the gate contradicted each other at exactly one edge; this is what makes them agree.
    #
    # The cost, stated rather than left to be found: a dependency *declared* while a task waits no
    # longer stops it resuming. Small, because the work is already under way, so the gate could not
    # have prevented it — only the record of it. It surfaces as `running_on_regressed` on the task
    # once the release lands, which is where a dependency problem on started work belongs.
    #
    # Derived from `from_status`, which `apply_transition` already captured, rather than from a flag
    # the caller passes: a flag is one more thing a caller can forget and one more thing a caller
    # can abuse, and the status at the transition already carries the whole fact. All three releases
    # — the operator's answer, their decline, and the run's expired wait — get it that way, which is
    # right: the reasoning does not distinguish them.
    if to_status == "in_progress" and from_status != STATUS_BLOCKED:
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

        # The acting run, excluded from the gate's liveness check: a turn is never blocked by
        # itself (design D10). `None` for the operator, which excludes nothing.
        refusal, policy = await evaluate(session, task, acting_run_id=actor.run_id)
        if refusal.refuses:
            raise GateUnsatisfiedError(refusal)
        # `contract` never refuses, so its unmet and rejected requirements have nowhere to surface
        # unless this call carries them out. Not persisted — a transient attribute on the returned
        # row rather than a column, because this is a report at the moment of approval, not an
        # audit trail; the audit trail is `requirement_coverage` and evidence review, unchanged.
        #
        # Two kinds travel on this one list: `contract`-rigor requirements that are unverified, and
        # evidence still awaiting review on a task that had accepted evidence to merge as well. Each
        # entry carries a `kind`, so a consumer cannot mistake one for the other — they call for
        # different things, and the second is not a statement about rigor at all.
        reported = list(refusal.reported) + list(refusal.advisory)

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

    # **After** integration (design D5). Release snapshots any uncommitted change onto the task
    # branch, so releasing first would advance the branch past the evidence commit before the merge
    # reads it.
    #
    # Honest about what that costs today: `integration_targets` resolves the commit from the
    # accepted evidence *footprint*, a database row, so the merged sha is the same under either
    # order and nothing observable changes. The order is defence against the change that would make
    # it matter — resolving the target from the branch tip instead — which is the exact shape of
    # F58. `test_release_happens_after_integration` observes the order directly for that reason,
    # rather than through the merged sha, which cannot discriminate it.
    if to_status in TERMINAL_STATUSES:
        await release_task_workspace(session, task)

    return transition


#: The statuses at which a task stops being worked, and so stops needing a checkout on disk. Neither
#: is a dead end — `approved -> revision_needed` and `rejected -> pending` are both legal
#: operator-only edges (`task_transitions.py`) — which is exactly why release keeps the branch: a
#: reopened task's next writing turn re-provisions from it with its prior work intact.
TERMINAL_STATUSES = frozenset({"approved", "rejected"})


async def release_task_workspace(session: AsyncSession, task: Task) -> None:
    """Remove a finished task's checkout and keep its branch (design D5).

    What bounds the disk is the *checkout*; the branch is the record of what the task did, and
    deleting it would destroy both the history an operator reads after the fact and the work a
    reopened task resumes from.

    **It must never fail the transition** — the same rule integration already lives by, and for the
    same reason: approval is a judgement that the work is good, and a git failure is not grounds to
    reverse a judgement. So every failure is swallowed, logged, and written to the event log where
    an operator can see that a directory was left behind.

    A grandfathered task (`workspace_scheme == 'agent'`) has no checkout of its own — its turns ran
    in the shared per-agent one, which belongs to the agent and outlives every task on it. Returning
    early is not merely an optimisation: calling through would ask `release_task_worktree` for a
    path that was never provisioned, and the honest answer for such a task is that there is nothing
    here to release.
    """
    from . import project_workspace, task_workspace, worktrees
    from .utils import persist_event

    if task.workspace_scheme != task_workspace.TASK_SCHEME:
        return

    try:
        workspace = await project_workspace.resolve_project_workspace(session, task.project_id)
        result = worktrees.release_task_worktree(workspace.root, task.id)
    except Exception as exc:  # noqa: BLE001 - any release failure is recorded, never a rollback
        logger.warning("Could not release task %s's checkout", task.id, exc_info=True)
        # `commit=False`: this runs inside `apply_transition`, whose caller commits. Committing
        # here would land the transition row early, ahead of the contract this module states.
        await persist_event(
            session,
            task.project_id,
            "task_worktree_release_failed",
            {"task_id": task.id, "reason": str(exc)},
            severity="warn",
            commit=False,
        )
        return

    if not result.released:
        return

    await persist_event(
        session,
        task.project_id,
        "task_worktree_released",
        {
            "task_id": task.id,
            "branch": result.branch,
            "had_uncommitted_changes": result.had_uncommitted_changes,
            "snapshot_commit": result.snapshot_commit,
            "unmerged_commits": result.unmerged_commits,
        },
        # An unmerged commit on a released branch is not a failure — a rejected task's work is
        # supposed to stay unmerged — but it is the one thing here an operator may want to act on.
        severity="warn" if result.has_unmerged_work else "info",
        commit=False,
    )


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
                reason=task_integration.WORKSPACE_UNAVAILABLE.format(error=exc),
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

    targets = await task_integration.merge_targets(session, task, root)
    if not targets:
        # Two reasons, not one. `NOTHING_TO_MERGE` is a statement about evidence and is only true
        # where evidence governs this task's merge; for a task whose merge comes from its own
        # branch, the honest answer is that it has no branch. Collapsing them would tell the
        # operator to accept evidence that could never exist.
        return _record(
            task_integration.IntegrationResult(
                outcome=task_integration.SKIPPED,
                reason=(
                    task_integration.NOTHING_TO_MERGE
                    if await task_integration.evidence_governs(session, task)
                    else task_integration.NO_TASK_BRANCH
                ),
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
