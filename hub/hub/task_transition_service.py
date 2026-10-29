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

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from . import blocking, flow_advance, traces
from .db.models import RequirementEvidence, Run, Task, TaskTransition
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


class GitUnavailableError(TransitionRefusedError):
    """The approval gate could not ask git whether the work would merge (F424).

    Refused rather than raised: the gate exists so that nothing is approved that might not merge,
    and a timeout or a missing git leaves that unanswered. The operator can retry once git answers.
    """

    http_status = 409


async def evaluate_approval(session: AsyncSession, task: Task, **kwargs):
    """`requirement_gate.evaluate` for a move to `approved`, with a git that cannot be asked turned
    into a stated refusal (F424). Every approving surface asks through this: the transition (operator
    PATCH, the agent plane, MCP) and the land route. Looked up at call time, as the transition always
    did, so a test patching `requirement_gate.evaluate` still reaches it."""
    from . import requirement_gate

    try:
        return await requirement_gate.evaluate(session, task, **kwargs)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise GitUnavailableError(
            "The Hub could not ask git whether this task's work would merge "
            f"({type(exc).__name__}: {exc}), so it was not approved. Check the project's "
            "repository and try again."
        ) from exc


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
    return (await completion_attributions(session, [task_id]))[task_id]


async def completion_attributions(
    session: AsyncSession, task_ids: Iterable[str]
) -> "dict[str, CompletionAttribution]":
    """`completion_attribution` for several tasks in one statement, keyed by every id asked."""
    ids = sorted(set(task_ids))
    found: "dict[str, CompletionAttribution]" = {}
    if ids:
        result = await session.execute(
            select(TaskTransition.task_id, TaskTransition.actor_kind, TaskTransition.actor_agent)
            .where(TaskTransition.task_id.in_(ids))
            .where(TaskTransition.to_status == "completed")
            # By `sequence`, not `created_at`: transitions staged in one flush share a timestamp,
            # and "most recent completion" must mean the last one that happened, not an arbitrary
            # pick among ties. This matters after a revision cycle, where an earlier completion by
            # another run is exactly what must not be chosen.
            .order_by(TaskTransition.task_id, TaskTransition.sequence.desc())
        )
        for task_id, actor_kind, actor_agent in result.all():
            found.setdefault(
                task_id,
                CompletionAttribution(recorded=True, actor_kind=actor_kind, agent=actor_agent),
            )
    nothing = CompletionAttribution(recorded=False, actor_kind=None, agent=None)
    return {task_id: found.get(task_id, nothing) for task_id in ids}


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

    So this is a **term** in the exclusion `agents_that_may_have_authored` builds, and outside it it
    is used in exactly one place: the wedged-review predicate in `scheduler.py`, which asks whether
    the *assignee* is one of the agents that produced the work and for which the wider set is wrong
    by construction (`task-lifecycle-governance`). There it is joined by
    `agents_that_recorded_evidence_for` (F167), because an all-operator history names nobody here.
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


async def agents_that_recorded_evidence_for(session: AsyncSession, task_id: str) -> "set[str]":
    """The agents that recorded **evidence** for this task — each one asserting it did the work.

    Found live 2026-09-09 (F306): an operator-completed task whose only agent-side trace was an
    evidence row naming the commit was reviewed and approved by the agent that wrote the row. The
    transitions named nobody (the operator made every move), the run that did the work was never
    bound, and the ladder resolved the author because nothing it read associated it with the task.

    Each filter is there for a reason a reader will be tempted to undo:

    * **`actor_kind == 'agent'`.** The same table holds the operator's own evidence (`POST
      /spec/evidence` records it as an operator actor). An operator's name in an exclusion of
      *agents* is a category error, and where an operator credential and an agent share a name it
      would silently un-staff a legitimate reviewer. It is also what keeps a truly untouched task
      reviewable: an operator may supply the evidence naming the commit and every agent stays
      eligible.
    * **A non-empty `actor`.** `requirement_evidence.record` writes `actor.name or ""`, and `''` in
      an exclusion set is a member that matches no agent but is not nothing. The other two terms
      drop falsy values for the same reason.
    * **`review_state` is deliberately NOT filtered** — do not add `review_state == 'accepted'`.
      Producing evidence is the agent's own claim and accepting it is somebody else's decision
      (`requirement-traceability`), so an exclusion keyed on the claim is keyed on the only part of
      the row the agent owns. Keyed on the decision, evidence still awaiting review — which is
      exactly the evidence a reviewer is being staffed to judge — would exclude nobody, and the
      exclusion would depend on the outcome of the review it is staffing.

    **Five consumers, and four of them use this term without the union.** The union
    `agents_that_may_have_authored` folds it in with the other three sources, for the *offer*. The
    transition guards (`_guard_author_is_not_reviewer`, `_guard_reviewer_is_not_the_author`) and
    the dispatch refusal (`api/v1/agent_trigger.review_dispatch_refusal`) fall back to it **alone**
    where no agent completed the task, for the *refusal* — because by the time a reviewer records
    its verdict it is the task's assignee and its run is bound to it, so the union names the
    reviewer itself and would refuse the flow's every staffed review of an operator-completed task.
    The fifth is the wedged-review predicate in `scheduler.py` (F167), which joins it to
    `agents_that_worked` -- the two records that name an author and never a staffed reviewer. Of
    the four sources, only an evidence row is an authorship claim that reviewing does not
    manufacture. That is why this is a function and not an expression inlined in the union: do not
    fold it back in.
    """
    return (await evidence_authors_by_task(session, [task_id]))[task_id]


async def evidence_authors_by_task(
    session: AsyncSession, task_ids: Iterable[str]
) -> "dict[str, set[str]]":
    """`agents_that_recorded_evidence_for` for several tasks in one statement, keyed by every id
    asked."""
    ids = sorted(set(task_ids))
    authors: "dict[str, set[str]]" = {task_id: set() for task_id in ids}
    if ids:
        rows = await session.execute(
            select(RequirementEvidence.task_id, RequirementEvidence.actor)
            .where(RequirementEvidence.task_id.in_(ids))
            .where(RequirementEvidence.actor_kind == "agent")
            .where(RequirementEvidence.actor != "")
            .distinct()
        )
        for task_id, agent in rows.all():
            if agent:
                authors[task_id].add(agent)
    return authors


async def assignee_produced_the_work(
    session: AsyncSession,
    task: Task,
    *,
    completion: Optional[CompletionAttribution] = None,
    authors: Optional[set[str]] = None,
) -> bool:
    """*"Is the agent holding this task one of the agents that produced its work?"*

    The wedged-review predicate (F70, F142, F167, F505), stated once for its two readers
    (`a-flow-stages-its-review-in-the-dispatch`, D5): `decide_firing`, which routes such a row to
    the reviewer ladder, and the dispatch's holder check, which must then let the reviewer that
    ladder chose replace it. Two statements of "this holder is the author" would let the recovery
    and the dispatch it depends on disagree, and the dispatch would refuse every attempt.

    The recorded completer where one names an agent, plus the evidence authors (F505); else the
    agents that moved the task, plus the evidence authors (F142, F167). Not the entry guard's rule
    (`_guard_reviewer_is_not_the_author` reads the evidence authors **alone** where no agent
    completed the task): that guard asks whether *this* agent may be entered as holder, where
    refusing on `agents_that_worked` would refuse a staffed reviewer that was once assigned the
    work. This asks whether the one already holding it is an author, and F142's measured row -- the
    agent moved it through `in_progress`, the operator did the rest, nobody recorded evidence -- is
    an author by this rule and not by that one.
    """
    if not task.assignee:
        return False
    # *completion* and *authors* are `completion_attribution` and `agents_that_recorded_evidence_for`
    # for this task, where the caller has already read them (the scheduler's `FiringFacts`).
    if completion is None:
        completion = await completion_attribution(session, task.id)
    completer = completion.agent
    if authors is None:
        authors = await agents_that_recorded_evidence_for(session, task.id)
    if completer is not None:
        return completer == task.assignee or task.assignee in authors
    return task.assignee in (await agents_that_worked(session, task.id) | authors)


async def agents_that_may_have_authored(session: AsyncSession, task: Task) -> "set[str]":
    """*"Might this agent be the author of this task's work?"* — the exclusion a reviewer ladder gets.

    Every agent **any** record associates with the task: the transitions that moved it, the agent it
    is assigned to, the runs recorded as bound to it, and the agents that recorded evidence for it.
    Four sources for one question is not elegant, and the reason it is nonetheless right is that
    each names a different fact and each is individually incomplete:

    | source | names | misses |
    |---|---|---|
    | transitions | every agent that **moved** it | one that worked it without moving it |
    | `assignee` | the agent that **holds** it now | every previous holder, and everyone after the first |
    | bound runs | every agent whose run was **about** it | runs predating the column, and runs never bound |
    | evidence | every agent that **asserted authorship** of it | work nobody recorded evidence for |

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
    evidenced = await agents_that_recorded_evidence_for(session, task.id)
    return worked | bound | evidenced | ({task.assignee} if task.assignee else set())


async def authorship_reason(
    session: AsyncSession, task: Task, agent: Optional[str]
) -> Optional[str]:
    """Why *agent* may not review *task*, as one clause, or `None` where it may.

    The one statement of the author rule every path that moves a task quotes: the transition
    guards, the review dispatch the flow and the mender's hand-off share, and `decide_move`. The
    agent recorded as completing it is its author; so is any agent that recorded evidence for it,
    including a mender that re-recorded some (F505). Read alone, never the union
    `agents_that_may_have_authored`, for the reason `agents_that_recorded_evidence_for` gives.
    """
    if not agent:
        return None
    if await agent_that_completed(session, task.id) == agent:
        return f"{agent!r} is the agent recorded as completing it"
    if agent in await agents_that_recorded_evidence_for(session, task.id):
        return f"{agent!r} recorded evidence for this task, which claims the work as its own"
    return None


@dataclass(frozen=True)
class MoveVerdict:
    """The answer to "may this actor make this move?": allowed, or refused with the error to raise."""

    allowed: bool
    refusal: Optional[TransitionRefusedError] = None
    #: Who holds the task afterwards, where the move changes that (a reviewer taking completed work).
    holder: Optional[str] = None

    @property
    def reason(self) -> Optional[str]:
        return str(self.refusal) if self.refusal is not None else None


async def decide_move(
    session: AsyncSession, task: Task, to_status: str, actor: Actor
) -> MoveVerdict:
    """The one decision of who may move a task where, consulted by every path that moves one.

    The map's edge, then author/reviewer separation. An agent other than the author may take a `completed` task into review and becomes its holder; the
    author, and a mender that re-recorded its evidence, may not (`every-task-can-always-be-moved-on`).
    This does not check for a flow: inside one, an agent other than the author may take completed
    work the same way, which the spec's FR-3 does not forbid.
    Reads only; `apply_transition` makes the move this allows, and adds the checks that ask about
    the state of the work rather than who is asking.
    """
    if to_status == task.status:
        return MoveVerdict(allowed=True)
    if task.status == "completed" and to_status == "approved" and task.build_id:
        # The one edge a level adds (`a-build-has-a-driver-a-level-and-its-people`, D4): at Fast,
        # the task's builder, its build's lead and the operator approve completed work without a
        # review. Not a map edge -- the map is the same for every task -- and so no author ever
        # holds its own task under review at any level. Refused elsewhere naming the level.
        from .builds import fast_approval_refusal

        refused = await fast_approval_refusal(session, task, actor)
        if refused is None:
            return MoveVerdict(allowed=True)
        error = ActorNotPermittedError if task.level == "fast" else IllegalTransitionError
        return MoveVerdict(allowed=False, refusal=error(refused))
    if not is_allowed(task.status, to_status, actor.kind):
        return MoveVerdict(
            allowed=False,
            refusal=IllegalTransitionError(refusal_detail(task.status, to_status, actor.kind)),
        )
    holder: Optional[str] = None
    if (
        not actor.is_operator
        and task.status == "completed"
        and to_status == "under_review"
        and actor.agent != task.assignee
    ):
        holder = actor.agent
    try:
        await _guard_author_is_not_reviewer(session, task, to_status, actor)
        await _guard_reviewer_is_not_the_author(
            session, task, to_status, actor, holder=holder or task.assignee
        )
    except TransitionRefusedError as refusal:
        return MoveVerdict(allowed=False, refusal=refusal)
    return MoveVerdict(allowed=True, holder=holder)


async def _guard_author_is_not_reviewer(
    session: AsyncSession, task: Task, to_status: str, actor: Actor
) -> None:
    """An agent run may not sign off work it produced.

    Binds agent runs only. The operator may approve their own work — refusing that would make a
    single-operator project unable to approve anything — and the history records that an operator
    did it (design D9).

    The comparison is on **agent**, so it holds across turns. An earlier version compared runs and
    was found in live use to forbid nothing, because a new turn is a new run.

    **Where no agent is recorded as completing the task, the agent that recorded evidence for it is
    its author** (F306). An operator completion writes no agent, so a completer comparison alone
    permits every agent's verdict — including the one whose evidence row names the commit under
    review. The fallback reads `agents_that_recorded_evidence_for` **alone and never the union**:
    by the time a reviewer records its verdict it is the task's assignee and its run is bound to the
    task, so `agents_that_may_have_authored` names the reviewer itself and would refuse the flow's
    every staffed review of an operator-completed task. It fires in both worlds `None` stands for —
    an operator completion and no completion at all — because it does not block over a *missing*
    record, which is what the permissive default protects; it blocks over a *present* one.

    What it still does not claim: two *different* agents belonging to the same operator can review
    each other freely, which is the intended shape rather than a gap. Nor does it reason about
    whether the review was diligent — that is B4's evidence gates. And where an agent **is**
    recorded as completing the task, that agent alone is compared: another agent's evidence row on
    the same task does not widen a decided answer to who the author is.
    """
    if actor.is_operator or to_status not in _REVIEW_OUTCOMES:
        return
    reason = await authorship_reason(session, task, actor.agent)
    if reason is not None:
        completing_agent = await agent_that_completed(session, task.id)
        whose = (
            ""
            if completing_agent == actor.agent
            else (
                "No agent is recorded as completing it, so the evidence is the record of who "
                "wrote it. "
                if completing_agent is None
                else f"{completing_agent!r} completed it, and an agent that recorded evidence for "
                f"it wrote part of what is being judged. "
            )
        )
        raise ActorNotPermittedError(
            f"Cannot move task {task.id} to {to_status!r}: {reason}, and approving, rejecting "
            f"or requesting revision of work requires a different actor. {whose}Another agent or "
            f"the operator must review it. Starting a new run does not make you a different actor."
        )


async def _guard_reviewer_is_not_the_author(
    session: AsyncSession,
    task: Task,
    to_status: str,
    actor: Actor,
    holder: Optional[str] = None,
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
    still free to; the refusal's own remedy (design D4, below) names how.

    Two permissive cases, both deliberate:

    * **No assignee.** Nobody is claimed to hold it, so nothing is false and nothing wedges — the
      scheduler's branch records an in-flight holder only `if task.assignee`. This is the operator
      taking a task off the agents' board to look at themselves.
    * **No recorded completer, and an assignee that recorded no evidence for the task.** The same
      asymmetry `_guard_author_is_not_reviewer` documents and `task_is_claimable_by` explains at
      length: refuse to *offer*, permit to *act*. A guard that blocked every move it could not
      attribute would stop legitimate work over a missing history row, and a task completed before
      the transition table existed has no completer to compare.

    **That second case used to be unconditional, and it is not any more** (F306, design D14). The
    asymmetry is sound only while *acting* remains possible, and for an agent that recorded
    evidence for an operator-completed task `_guard_author_is_not_reviewer` now refuses every
    verdict. Permitting the entry would then strand the task rather than free it: `under_review`,
    held by an agent that may not approve, reject or return it, which no transition names — so the
    flow reports a review genuinely in progress and never restaffs it. Unmovable by any actor and
    invisible as a problem. So where no agent completed the task and the assignee recorded evidence
    for it, the entry is refused here, before a turn is spent. The fallback is
    `agents_that_recorded_evidence_for` **alone**, for the reason that guard gives: the union
    names whoever is assigned, which here is the reviewer being entered, and would refuse the flow's
    every review of operator-completed work. Every other unattributable case keeps the old
    permission, including the historical tasks it was written for, which carry no evidence rows.

    The flow's own path satisfies this by construction — `enter_selected_task` writes the
    reviewer into `assignee` before it transitions, which it must, or the flow would refuse itself
    here on every review it staffs. And where no agent is recorded as completing the task — the
    only case the evidence fallback reads — the reviewer it writes is never an evidence author,
    because the ladder's exclusion on that arm (`agents_that_may_have_authored`) contains every one.

    **`actor` decides the remedy, not the refusal** (design D4): the edge is false no matter who
    asks, so nobody is exempt — this guard still takes the shape of the three actor-entitlement
    guards `apply_transition` calls in a row, and reads `actor` only to phrase what happens next.
    An operator can act directly (land the work themselves, or dispatch another agent's review
    turn); an agent holds no tool that reassigns a task, so its remedy names the operator instead
    of a PATCH it cannot make.
    """
    holder = holder or task.assignee
    if to_status != "under_review" or not holder:
        return
    remedy = (
        "Land it, on the task, to review it yourself, or dispatch a different agent's "
        "review turn (POST /agent/trigger with review_task_id)."
        if actor.is_operator
        else "None of the task tools you are offered reassigns a task; the operator can move "
        "it on."
    )
    reason = await authorship_reason(session, task, holder)
    if reason is not None:
        raise ActorNotPermittedError(
            f"Cannot move task {task.id} to 'under_review' with {holder!r} as its holder: "
            f"{reason}, so the move would claim its own author is reviewing it; an author may "
            f"not review its own work. {remedy}"
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

      It claims only work that is its agent's or nobody's (F450, found live 2026-10-07: Haiku
      beta, holding nothing, claimed alpha's assigned task and took it to `completed`). A task
      assigned to another agent is refused with the remedy — leave it, or have the operator
      reassign it. An unassigned task claimed this way gets the claimer as its assignee, so the
      board says who is working it. A recorded takeover is the operator's to make, not a run's.
      A read-only agent's run claims nothing (F425): it would work in the operator's checkout.
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
        # Bound, but a reviewer's run is bound to the task it inspects (F606): in one turn the
        # tester sent dev1's task back, then moved it to in_progress and completed itself, became
        # its recorded completer, and the flow refused to review it. A run that gave the task a
        # verdict, or took it for review while not its assignee, does not then work it.
        if await _run_reviewed_the_task(session, run, task):
            raise RunNotBoundError(
                f"This run cannot move task {task.id} to {to_status}: it reviewed this task, and "
                f"only its assignee ({task.assignee or 'nobody yet'}) works it. Leave your verdict "
                f"as it stands; the author picks the task up from here."
            )
        return

    if to_status == "in_progress" and run.task_id is None:
        # A read-only agent holds no task's work (F425), its own or anybody's. Imported here: the
        # launch module reaches back into this one, also lazily.
        from .launchability import is_read_only_agent, read_only_work_sentence

        if await is_read_only_agent(task.project_id, run.agent, session):
            raise RunNotBoundError(read_only_work_sentence(run.agent, task.id))
        if task.assignee and task.assignee != run.agent:
            raise RunNotBoundError(
                f"This run cannot claim task {task.id}: it is assigned to {task.assignee!r}, and an "
                f"agent claims only the tasks assigned to it or to nobody. Leave it to "
                f"{task.assignee!r}; the operator can reassign it if it should be yours."
            )
        run.task_id = task.id
        if not task.assignee:
            task.assignee = run.agent
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


async def _run_reviewed_the_task(session: AsyncSession, run: Run, task: Task) -> bool:
    """Whether *run* gave *task* a verdict (`revision_needed`), or took it to `under_review` while
    another agent is its assignee (F606). Read from the task's own history, by run id."""
    moves = (
        (
            await session.execute(
                select(TaskTransition.to_status).where(
                    TaskTransition.task_id == task.id,
                    TaskTransition.run_id == run.id,
                    TaskTransition.to_status.in_(("revision_needed", "under_review")),
                )
            )
        )
        .scalars()
        .all()
    )
    if "revision_needed" in moves:
        return True
    return "under_review" in moves and bool(task.assignee) and task.assignee != run.agent


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
#: A scheduled job made the move: the operator's authority (the actor stays the operator), a job's
#: cause, recorded with the job's id (`a-flows-own-moves-are-recorded-as-the-flows`). The operator
#: created the job, so it acts as them, as `runtime` acts as the run.
ORIGIN_JOB = "job"
#: The project's checks made the move: a completed task whose check run failed with its own failure
#: went back to its builder (`checks-run-before-anyone-reviews`, D7). The operator's authority, as
#: a job's is -- the operator configured the checks -- so the actor stays the operator.
ORIGIN_CHECKS = "checks"
ORIGINS = frozenset({ORIGIN_ACTOR, ORIGIN_RUNTIME, ORIGIN_JOB, ORIGIN_CHECKS})

#: Who overrode failing checks on an approval (`task_transitions.override_by`): the operator with a
#: typed reason, or the Hub over failures that were not the task's (`a-red-main-does-not-hold-the-
#: night`, D3).
OVERRIDE_BY_OPERATOR = "operator"
OVERRIDE_BY_HUB = "hub"


class _ChecksRefusal:
    """The structured body of a refusal over the project's checks (main.py's handler sends
    `to_dict()`; the MCP adapter returns its `message`)."""

    def __init__(self, code: str, message: str, **fields) -> None:
        self.code, self.message, self.fields = code, message, fields

    def detail(self) -> str:
        return self.message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, **self.fields}


class ChecksFailedError(TransitionRefusedError):
    """An agent's completion whose fast checks failed with the task's own failure (FR-3, D4).

    409: the asker may complete the task, the *work* is what forbids it. Carries each failing
    check's output, the merged commit and the run, so the agent fixes it in the same turn.
    """

    http_status = 409

    def __init__(self, task: Task, outcome) -> None:
        from .project_checks import failure_report

        report = failure_report(
            outcome.failing, run_id=outcome.run_id, merged_sha=outcome.merged_sha
        )
        message = (
            f"Task {task.id} was not completed. {report}\n\nFix what the check reports and move "
            f"the task to completed again; the fast checks run again on the new work."
        )
        if getattr(outcome, "unchanged_checkout", None):
            message = (
                f"Task {task.id} was not completed. Its work is unchanged since check run "
                f"{outcome.run_id} (commit {outcome.unchanged_commit}), so that run's verdict "
                f"stands and nothing ran again; this is not a stale cache. {report}\n\n"
                f"The checks run on the task's checkout at {outcome.unchanged_checkout} (relative "
                f"to the project root), not on your own agent worktree. Make the fix there and "
                f"commit it in that checkout, then move the task to completed again; the fast "
                f"checks run again on the new commit."
            )
        self.refusal = _ChecksRefusal(
            "checks_failed",
            message,
            task_id=task.id,
            run_id=outcome.run_id,
            merged_sha=outcome.merged_sha,
            checks=[
                {
                    key: result.get(key)
                    for key in (
                        "name",
                        "exit_code",
                        "timed_out",
                        "output_tail",
                        "failure_excerpt",
                    )
                }
                for result in outcome.failing
            ],
        )
        super().__init__(message)


class ChecksPendingError(TransitionRefusedError):
    """An agent taking completed work into review while its checks are undecided or have failed
    with the task's own failure (FR-9, D8). 409: the work's state forbids it, not the asker."""

    http_status = 409

    def __init__(self, task: Task, wait) -> None:
        message = (
            f"Task {task.id} cannot be taken into review yet: {wait.reason}. The review waits for "
            f"the project's checks."
        )
        self.refusal = _ChecksRefusal(
            "checks_pending", message, task_id=task.id, run_id=wait.run_id, state=wait.state
        )
        super().__init__(message)


async def completion_refusal(
    session: AsyncSession, task: Task, actor: Actor
) -> Optional[TransitionRefusedError]:
    """What `apply_transition` would refuse *actor* completing *task* for, before anything about the
    work: the map, author/reviewer separation, and that the run holds the task. Reads only."""
    verdict = await decide_move(session, task, "completed", actor)
    if verdict.refusal is not None:
        return verdict.refusal
    try:
        await _guard_run_holds_the_task(session, task, "completed", actor)
    except TransitionRefusedError as refusal:
        return refusal
    return None


async def run_fast_checks_before_completion(session: AsyncSession, task: Task, actor: Actor):
    """An agent's move to `completed` waits for the project's fast checks on the work its review
    would be given, and is refused with their output when one fails (FR-2..FR-4, D4).

    Called by the route before `apply_transition`, with nothing staged, so the wait never holds the
    database's write lock. Not inside `apply_transition`, which stages and runs inside other
    transactions; not in `decide_move`, which answers only who may move. A move this actor may not
    make is left for `apply_transition` to refuse, so nothing runs for it. Returns what the wait
    found (`None` where no fast check applies), for the caller to act on once it commits."""
    if actor.is_operator or task.status == "completed":
        return None
    if await completion_refusal(session, task, actor) is not None:
        return None
    from . import project_checks

    outcome = await project_checks.fast_checks_at_completion(session, task, actor.agent)
    if outcome is None:
        return None
    if outcome.failing:
        raise ChecksFailedError(task, outcome)
    # The wait may have been long: what is applied is the task as it stands now.
    await session.refresh(task)
    return outcome


async def apply_transition(
    session: AsyncSession,
    task: Task,
    to_status: str,
    actor: Actor,
    origin: str = ORIGIN_ACTOR,
    job_id: Optional[str] = None,
    override_checks_reason: Optional[str] = None,
    verdict_reason: Optional[str] = None,
    holder_named: bool = False,
    note: Optional[str] = None,
    closing_with: frozenset = frozenset(),
    failing_pieces: Optional[Dict[str, str]] = None,
    git_answers: Optional[traces.GitAnswers] = None,
    accepted_on_main: frozenset = frozenset(),
) -> Optional[TaskTransition]:
    """Move `task` to `to_status` as `actor`, recording it. Returns None when nothing changed.

    A move to `approved` asks its git before its first write and its gate reads those answers
    (`approved-work-merges-in-batches`, D3), queues the task's work for landing with its merge
    targets frozen, and leaves the merge and the checkout release to run once the caller commits
    (`landing_queue`). *git_answers* are answers a caller already asked before it wrote anything
    (`ask_approval_git_first`; the land route, which moves the task through `under_review` first).

    *note* is written on the history row: which operator action made this move, and against what
    (`already_built`). *closing_with* names the tasks one operator action is closing together as
    already built; a prerequisite among them does not hold this task back from `in_progress`, because
    no work is starting -- it is already on the main branch, and so is the prerequisite's.

    *holder_named* says the caller has just written `task.assignee` on the operator's instruction
    (the same PATCH that sends the work back, F743), so the send-back does not return it to its
    author over the top of that.

    A verdict decides the task's evidence (`the-reviewers-verdict-decides-the-tasks-evidence`),
    piece by piece (`each-piece-of-evidence-is-judged-on-its-own`): `approved` accepts the pieces
    recorded for it with *verdict_reason* (the verdict's notes); `revision_needed` and `rejected`
    reject only *failing_pieces* (evidence id to its own reason, `failing_pieces_of`) and hold every
    other piece with *verdict_reason*. What it decided is written on the history row's note.
    A send-back whose origin is `checks` also holds the task's own accepted evidence
    (`a-checks-send-back-returns-the-task-s-accepted-evidence`, D1), less the pieces whose commits
    are all in *accepted_on_main* (`requirement_evidence.own_accepted_commits_on_main`, read by the
    caller before its write lock).

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
    if (origin == ORIGIN_JOB) != (job_id is not None):
        raise ValueError("job_id is required with origin 'job' and forbidden with any other origin")
    if origin == ORIGIN_JOB and not actor.is_operator:
        raise ValueError("origin 'job' acts as the operator; a run actor cannot carry it")

    from_status = task.status

    # D7: restating the current status is a no-op that records nothing. An agent plane retry would
    # otherwise manufacture a `completed -> completed` transition, and "who completed this" would
    # start returning the retrying run.
    if to_status == from_status:
        return None

    verdict = await decide_move(session, task, to_status, actor)
    if verdict.refusal is not None:
        raise verdict.refusal
    if verdict.holder is not None:
        # A reviewer taking completed work becomes its holder, in this same move.
        task.assignee = verdict.holder

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
        if closing_with:
            dependency_refusal.unmet = [
                entry for entry in dependency_refusal.unmet if entry["id"] not in closing_with
            ]
        if dependency_refusal.refuses:
            raise DependencyUnmetError(dependency_refusal)

    # The work-state gate on taking finished work into review (`checks-run-before-anyone-reviews`,
    # D8): an agent waits for the project's checks, as the flow does, and a failure of the task's
    # own sends it back to its builder rather than to a reviewer. Beside the dependency gate, for
    # the same reason: it asks about the state of the work, not who is asking. The operator's own
    # dispatch is not gated (warn, don't gate); its reviewer is briefed as today.
    if from_status == "completed" and to_status == "under_review" and not actor.is_operator:
        from . import project_checks

        wait = await project_checks.review_wait(session, task)
        if wait is not None:
            if wait.needs_a_run:
                project_checks.schedule(task.project_id, task.id)
            elif wait.state == "failed":
                project_checks.schedule_return(task.id)
            raise ChecksPendingError(task, wait)

    # The gate, on this one edge. Inside the service and before the history row, so it cannot be
    # bypassed by a caller reaching the row a different way — which is also why every surface
    # (operator route, agent HTTP, the tool surface, jobs) gets it without knowing it exists.
    #
    # Imported locally: `requirement_gate` reads coverage, which reads the models, and this module
    # is the one every status write already passes through.
    policy = ""
    reported: list = []
    approval_gate = None
    overridden: Optional[str] = None
    decided: Optional[str] = None
    override_by: Optional[str] = None
    if to_status == "approved":
        # The acting run, excluded from the gate's liveness check: a turn is never blocked by
        # itself (design D10). `None` for the operator, which excludes nothing.
        # Only the operator may approve over failing checks, and only with a reason
        # (`approval-runs-the-projects-checks` D7). Approving may start a check run (D5).
        reason = (override_checks_reason or "").strip() or None
        if reason is not None and not actor.is_operator:
            raise ActorNotPermittedError(
                "Only the operator can approve over failing checks; send the task back to its "
                "author with revision_needed instead."
            )
        # Git is asked before the first write, with the evidence the verdict is about to accept
        # read as accepted; the gate below reads those answers, so no git runs while this
        # transaction holds the write lock (`approved-work-merges-in-batches`, D3).
        if git_answers is None:
            git_answers, _ = await ask_approval_git_first(
                session, task, actor, override_checks_reason=reason
            )
        # The approval accepts the task's evidence in the same savepoint the gate reads it in
        # (design D1): the gate judges the state it will merge from, and a refusal for any other
        # reason -- a conflict, failing checks -- rolls the acceptances back with it, so nothing is
        # recorded as accepted by an approval that did not happen.
        async with session.begin_nested():
            decided = await _decide_evidence_with_verdict(
                session, task, actor, "approved", verdict_reason
            )
            with traces.answering_from(git_answers):
                refusal, policy = await evaluate_approval(
                    session,
                    task,
                    acting_run_id=actor.run_id,
                    override_checks_reason=reason,
                )
            if refusal.refuses:
                refusal.for_operator = actor.is_operator
                raise GateUnsatisfiedError(refusal)
        approval_gate = refusal
        overridden = reason if refusal.checks_overridden else None
        if overridden is not None:
            override_by = OVERRIDE_BY_OPERATOR
        elif refusal.automatic_override is not None:
            # Failures that are not the task's -- main's, or flakes -- land with the Hub's override
            # (`a-red-main-does-not-hold-the-night`, D3). Who overrode is a column of its own: the
            # actor stays the approver, and there is no third actor kind.
            from .requirement_gate import override_reason_for

            overridden = override_reason_for(refusal.automatic_override)
            override_by = OVERRIDE_BY_HUB
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

    # Work sent back goes back to its author (F495). A flow writes its reviewer into `assignee`
    # before entering the review (`scheduler.enter_selected_task`, F70's ordering), and the firing
    # resumes a staffed task with whoever `assignee` names — so without this the reviewer reworked
    # what it had reviewed, became the completer, and the author was staffed to review the
    # reviewer's fix. Read before the status write, so the lookup's autoflush cannot matter. An
    # operator completion names no agent; `_holder_of_sent_back_work` then asks the other records
    # of authorship before it leaves the assignee alone (F708).
    if to_status == "revision_needed" and not (holder_named and actor.is_operator):
        task.assignee = await _holder_of_sent_back_work(session, task, actor)
    if to_status in ("revision_needed", "rejected"):
        decided = await _decide_evidence_with_verdict(
            session, task, actor, to_status, verdict_reason, failing_pieces
        )
        if origin == ORIGIN_CHECKS and to_status == "revision_needed":
            returned = await _return_accepted_evidence(
                session, task, actor, verdict_reason, accepted_on_main
            )
            decided = " ".join(part for part in (returned, decided) if part) or None
    if decided:
        # Its own sentence after the caller's note, which may not end in one (L's check return).
        lead = (note or "").rstrip()
        if lead and not lead.endswith((".", "!", "?")):
            lead += "."
        note = f"{lead} {decided}" if lead else decided

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
        job_id=job_id,
        # What governed this move. Null where no policy did — a fact about the transition rather
        # than a gap in it.
        policy_digest=policy or None,
        override_reason=overridden,
        override_by=override_by,
        note=note,
        # The build level that governed this move; none outside a build (slice D, FR-2).
        level=task.level if task.build_id else None,
    )
    # Not a column — see the comment where `reported` is built. `TaskResponse` reads this off the
    # object this same call returns; nothing else looks for it, and nothing persists it.
    transition.reported_advisories = reported
    session.add(transition)

    # A flow's work handed on: its firing is asked for once this commits, not at its next tick
    # (`flow_advance`). Never for the job's own moves -- a firing does not re-fire itself.
    if task.loop_id and to_status in flow_advance.HANDOFF_STATUSES and origin != ORIGIN_JOB:
        flow_advance.advance_after_commit(session, task.loop_id)
    # A task moved to `assigned` outside any flow is started for its assignee once this commits
    # (`a-red-main-does-not-hold-the-night`, FR-9): nothing else starts it.
    if to_status == "assigned" and not task.loop_id:
        from . import assigned_task_start

        assigned_task_start.start_after_commit(session, task.id, actor.run_id)

    if origin != ORIGIN_RUNTIME:
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
        # The work joins the landing queue with what the gate resolved, frozen; it lands once this
        # commits (`landing_queue`). An operator's reason over the task's own failed check lands
        # it alone, ahead of the queue, unchecked (D2).
        from . import landing_queue

        unchecked = bool(approval_gate is not None and approval_gate.overrode_own_failure)
        landing_queue.stage(
            session,
            task,
            actor_kind=actor.kind,
            actor=actor.agent or ("operator" if actor.is_operator else ""),
            kind="approval",
            targets=approval_gate.will_merge if approval_gate is not None else None,
            unchecked=unchecked,
            override_reason=overridden if unchecked else None,
            override_by=override_by if unchecked else None,
        )
        # The last open task of a document approved is a major event of the project's story: the
        # chapters job fires once this commits, if it is on with automatic firing.
        from . import chapters_job

        if await chapters_job.is_last_open_task(session, task):
            chapters_job.fire_after_commit(
                session,
                task.project_id,
                chapters_job.LAST_TASK_APPROVED,
                {"task": task.id, "document": task.spec_document_id},
            )

    # Work that leaves `approved` before it landed (the operator sends it back) leaves the queue, in
    # this same transaction: no batch lands it.
    if from_status == "approved" and to_status != "approved":
        from . import landing_queue

        await landing_queue.withdraw(session, task)

    # A task completed outside a turn has its work committed already, so its checks can start now
    # (approval-runs-the-projects-checks D4). One completed by a run is checked at that run's end,
    # after the snapshot that commits its work (`project_checks.after_run`). Never raises.
    if to_status == "completed" and actor.run_id is None:
        from . import project_checks

        if await project_checks.configured_for(session, task.project_id):
            project_checks.schedule(task.project_id, task.id)

    # The checkout is released once this commits, its git outside any transaction
    # (`approved-work-merges-in-batches`, D3). Release snapshots uncommitted changes onto the task
    # branch, which used to be why it had to follow the merge (F58's shape: a target read from the
    # branch tip after the snapshot). The landing's targets are frozen above, so the order no longer
    # matters; `test_release_does_not_move_the_frozen_target` holds that.
    if to_status in TERMINAL_STATUSES:
        from . import landing_queue

        landing_queue.release_after_commit(session, task)
        # The last open task of a slice whose approval asked for the next slice queues its drafting
        # (C1a D4a, F496). In a savepoint, and it never raises. Imported locally: it reads the spec
        # lifecycle, which is built on the models this module already holds.
        from .slice_drafting import on_task_closed

        await on_task_closed(session, task)
        # A build whose every task is closed has finished (slice D).
        from .builds import finish_if_done

        await finish_if_done(session, task)

    return transition


async def _holder_of_sent_back_work(
    session: AsyncSession, task: Task, actor: Actor
) -> Optional[str]:
    """Who holds *task* once it is sent back for revision: its author, never its reviewer.

    The agent that completed it, when one did (F495). When the operator completed it (F708, found
    2026-10-18: the tester sent back an operator-completed task and ended up holding the rework),
    the other records of authorship are asked — evidence recorded for the task, and the agents that
    took it to `in_progress` or `completed` — less the agent sending it back. The current assignee
    stays if it is one of them; otherwise a single named author takes it. With nobody named, the
    agent sending the work back does not keep it — the task is left unassigned for the operator to
    give — and any other holder is left as it is, not guessed at.
    """
    completer = await agent_that_completed(session, task.id)
    if completer is not None:
        return completer
    edges = await session.execute(
        select(TaskTransition.actor_agent)
        .where(TaskTransition.task_id == task.id)
        .where(TaskTransition.to_status.in_(("in_progress", "completed")))
        .where(TaskTransition.actor_agent.isnot(None))
        .distinct()
    )
    authors = {agent for agent in edges.scalars().all() if agent}
    authors |= await agents_that_recorded_evidence_for(session, task.id)
    authors.discard(actor.agent or "")
    if task.assignee in authors:
        return task.assignee
    if len(authors) == 1:
        return next(iter(authors))
    if actor.agent and task.assignee == actor.agent:
        return None
    return task.assignee


async def _decide_evidence_with_verdict(
    session: AsyncSession,
    task: Task,
    actor: Actor,
    to_status: str,
    verdict_reason: Optional[str],
    failing_pieces: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """The verdict on *task* decides the evidence recorded for it (vis-D4), piece by piece: a
    send-back rejects only *failing_pieces* and holds the rest. Returns the history's account of
    what it decided, or None when it decided nothing."""
    from . import requirement_evidence

    reviews = await requirement_evidence.decide_with_verdict(
        session,
        task,
        actor=evidence_actor(actor),
        decision=(
            requirement_evidence.ACCEPTED
            if to_status == "approved"
            else requirement_evidence.REJECTED
        ),
        reason=verdict_reason or "",
        failing=failing_pieces,
        # A Fast build has no reviewer (slice D, D4): its builder, lead or flow approving completed
        # work accepts the builder's own evidence, which a reviewer-less approval would otherwise
        # leave awaiting and refuse as "nobody has judged it".
        own_work=bool(
            to_status == "approved"
            and task.build_id
            and task.level == "fast"
            and task.status == "completed"
        ),
    )
    return await requirement_evidence.verdict_note(session, reviews)


async def _return_accepted_evidence(
    session: AsyncSession,
    task: Task,
    actor: Actor,
    verdict_reason: Optional[str],
    on_main: frozenset,
) -> Optional[str]:
    """A checks send-back holds the task's own accepted evidence, so the next completion is checked
    on the fix rather than on the commit that failed (F1081). Returns the history's account."""
    from . import requirement_evidence

    returned = await requirement_evidence.return_accepted(
        session,
        task,
        actor=evidence_actor(actor),
        reason=(verdict_reason or "").strip()
        or f"Held with the checks' sending back of {task.id}: the accepted work fails them",
        on_main=on_main,
    )
    return requirement_evidence.returned_note(returned)


def evidence_actor(actor: Actor):
    """*actor* as the evidence record names a decider (`spec_lifecycle.Actor`)."""
    from .spec_lifecycle import Actor as EvidenceActor

    if actor.is_operator:
        return EvidenceActor(kind="operator", name="operator")
    return EvidenceActor(kind="agent", name=actor.agent or "", run_id=actor.run_id)


#: The statuses at which a task stops being worked, and so stops needing a checkout on disk. Neither
#: is a dead end — `approved -> revision_needed` and `rejected -> pending` are both legal
#: operator-only edges (`task_transitions.py`) — which is exactly why release keeps the branch: a
#: reopened task's next writing turn re-provisions from it with its prior work intact.
TERMINAL_STATUSES = frozenset({"approved", "rejected"})


async def release_task_workspace(session: AsyncSession, task: Task) -> None:
    async with traces.work("worktree_release", task.project_id, **{"aw.task.id": task.id}):
        await _release_task_workspace(session, task)


async def _release_task_workspace(session: AsyncSession, task: Task) -> None:
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
        # Off the loop, one at a time with every other worktree change (`blocking`, D1/D5).
        result = await blocking.run_serialized(
            worktrees.release_task_worktree, workspace.root, task.id
        )
    except Exception as exc:  # noqa: BLE001 - any release failure is recorded, never a rollback
        logger.warning("Could not release task %s's checkout", task.id, exc_info=True)
        # `commit=False`: the caller (`landing_queue`'s release, after the move committed) commits.
        await persist_event(
            session,
            task.project_id,
            "task_worktree_release_failed",
            {"task_id": task.id, "reason": str(exc)},
            severity="warn",
            commit=False,
        )
        return

    if result.kept_reason:
        await persist_event(
            session,
            task.project_id,
            "task_worktree_release_skipped",
            {"task_id": task.id, "branch": result.branch, "reason": result.kept_reason},
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


async def retry_integration(
    session: AsyncSession, task: Task, actor: Actor, *, kind: str = "retry"
):
    """Queue integration again for a task that is already approved; returns the `TaskLanding`.

    Integration runs on the transition *into* `approved`, and restating a status is deliberately a
    no-op (D7 of the previous change) — so a merge that was skipped can never be attempted again by
    approving harder. Most skips name something the operator then puts right: a main branch that was
    never chosen, a checkout with uncommitted changes, a checkout parked elsewhere. Without a second
    entry point the remediation the system asked for accomplishes nothing, which was observed live.

    Through the landing queue, as every merge into main is (`approved-work-merges-in-batches`,
    FR every-hub-merge-goes-through-the-queue): the targets are resolved now, asking git before
    anything is staged, and frozen on the landing; the caller commits, then `landing_queue.settle`
    lands it (at once without checks, in the next batch with them).

    No refusal when the work is already merged: the landing asks the repository and records
    `ALREADY_INTEGRATED`, a fact, rather than reading the attempt log.
    """
    if task.status != "approved":
        raise IntegrationRetryRefusedError(
            f"Cannot retry integration for a task in {task.status!r}: "
            "only an approved task has work to integrate."
        )
    from . import landing_queue

    # One open landing per task: a second would be a second claim on the same work, and the first
    # to land would leave the other's record behind it.
    open_landing = await landing_queue.open_landing(session, task.id)
    if open_landing is not None:
        raise IntegrationRetryRefusedError(
            f"Task {task.id} already has an open landing ({open_landing.id}, "
            f"{open_landing.state}): it lands without being asked again."
        )
    targets = await landing_queue.resolve_targets(session, task)
    return landing_queue.stage(
        session,
        task,
        actor_kind=actor.kind,
        actor=actor.agent or ("operator" if actor.is_operator else ""),
        kind=kind,
        targets=targets,
    )


async def hub_written_documents(session: AsyncSession, workspace, project_id: str) -> set:
    """The project's documents whose file is exactly what the Hub last wrote (F515).

    `content_digest` is stamped by every Hub write of a document, so a file that still hashes to it
    holds no one's work but the Hub's. An operator's edit to the same file changes the hash and
    counts as theirs, as it should.
    """
    from . import spec_documents, spec_lifecycle
    from .db.models import SpecDocument

    rows = (
        (await session.execute(select(SpecDocument).where(SpecDocument.project_id == project_id)))
        .scalars()
        .all()
    )
    recorded = [(document.path, document.content_digest) for document in rows]

    def _still_written() -> set:
        written = set()
        for path, content_digest in recorded:
            try:
                content = spec_documents.read_document(workspace, path)
            except Exception:  # noqa: BLE001 - an unreadable file is simply not exempt
                continue
            if content is not None and spec_lifecycle.digest(content) == content_digest:
                written.add(path)
        return written

    # The files are read off the loop (`blocking`, D1); the rows were read on it, above.
    return await blocking.run(_still_written)


def _is_ancestor(root, ancestor: Optional[str], descendant: str) -> Optional[bool]:
    """`True` when *ancestor* is in *descendant*'s history (the same question `integrate` asks)."""
    from . import requirement_evidence

    if not ancestor:
        return True
    return requirement_evidence.is_reachable_from(root, ancestor, descendant)


class ResolutionRefusedError(Exception):
    """A resolution commit that does not carry the work approval would merge."""


async def land_resolution(session: AsyncSession, task: Task, actor: Actor, commit: str):
    """Queue *commit* to land in place of the approved task's own targets: the mender's resolution
    of a conflict (`stalls.py`). *commit* must contain every commit approval would merge, so nothing
    accepted is dropped; asked of git before anything is staged. Returns the `TaskLanding`; the
    caller commits and settles. Raises `ResolutionRefusedError`."""
    from . import landing_queue, task_integration

    open_landing = await landing_queue.open_landing(session, task.id)
    if open_landing is not None:
        raise ResolutionRefusedError(
            f"Task {task.id} already has an open landing ({open_landing.id}, "
            f"{open_landing.state}); a resolution lands once it has ended."
        )
    targets = await landing_queue.resolve_targets(session, task)
    if targets:
        from . import project_workspace

        root = (await project_workspace.resolve_project_workspace(session, task.project_id)).root
        missing = await blocking.run(
            lambda: [
                target.commit_sha
                for target in targets
                if _is_ancestor(root, target.commit_sha, commit) is not True
            ]
        )
        if missing:
            raise ResolutionRefusedError(
                f"{commit[:12]} does not contain {', '.join(sha[:12] for sha in missing)}, "
                "which approving this task merges: branch from that work, then merge the main "
                "branch into it."
            )
    return landing_queue.stage(
        session,
        task,
        actor_kind=actor.kind,
        actor=actor.agent or ("operator" if actor.is_operator else ""),
        kind="resolution",
        targets=[
            task_integration.Target(commit_sha=commit, branch=f"mend/{task.id}", task_id=task.id)
        ],
    )


async def ask_approval_git_first(
    session: AsyncSession,
    task: Task,
    actor: Actor,
    *,
    override_checks_reason: Optional[str] = None,
):
    """`(answers, refusal)`: approval's gate asked before anything is written, with the evidence the
    verdict would accept read as accepted, every git answer kept for the transaction to read
    (`approved-work-merges-in-batches`, D3). *refusal* is what the gate would say; a git that could
    not be asked raises `GitUnavailableError` here, before anything is staged."""
    from . import requirement_evidence, task_integration

    answers = traces.GitAnswers()
    pieces = await requirement_evidence.verdict_pieces(
        session,
        task,
        actor=evidence_actor(actor),
        decision=requirement_evidence.ACCEPTED,
    )
    token = task_integration.ASSUMED_ACCEPTED.set(frozenset(evidence.id for evidence, _ in pieces))
    try:
        with traces.asking_git_first(answers):
            refusal, _ = await evaluate_approval(
                session,
                task,
                acting_run_id=actor.run_id,
                override_checks_reason=override_checks_reason,
            )
    finally:
        task_integration.ASSUMED_ACCEPTED.reset(token)
    return answers, refusal


_REDRAIN_KEY = "integration_redrain_projects"
#: Strong references to the tasks the `after_commit` listener starts, so none is collected early.
_redrains_in_flight: set = set()


def _redrain_after_commit(session: AsyncSession, project_id: str) -> None:
    """Re-drain the project's queue once the session's root transaction commits, never if it
    does not (an approval that rolls back did not put the work on the main line)."""
    session.sync_session.info.setdefault(_REDRAIN_KEY, set()).add(project_id)


@event.listens_for(Session, "after_commit")
def _redrain_pending(session: Session) -> None:
    if session.in_nested_transaction():
        return
    pending = session.info.pop(_REDRAIN_KEY, set())
    if not pending:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # the next project open, run end or settings save drains it
    from . import project_checks

    for project_id in pending:
        # Main moved: the results waiting for review are stale now, so they re-run now rather
        # than when someone approves (`checks-wait-less`, FR-1). Never raises.
        project_checks.schedule_refresh(project_id)
        redrain = loop.create_task(_redrain(project_id))
        _redrains_in_flight.add(redrain)
        redrain.add_done_callback(_redrains_in_flight.discard)


@event.listens_for(Session, "after_transaction_end")
def _drop_pending_redrain(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_REDRAIN_KEY, None)


async def _redrain(project_id: str) -> None:
    from . import turn_scheduler

    try:
        await turn_scheduler.redrain_queued_agents(project_id)
    except Exception:  # noqa: BLE001 -- entries are durable; the next drain delivers them
        logger.warning("could not re-drain %s after a merge", project_id, exc_info=True)


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
