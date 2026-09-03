"""Start queued agent turns when an agent is idle and within the hop budget."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import requirement_evidence
from .conversations import get_conversation_by_id
from .db.engine import async_session_factory
from .db.models import Conversation, InboundQueueEntry, Run, Task
from .inbound_queue import (
    DELIVERY_ATTEMPT_LIMIT,
    can_start,
    format_turn_prompt,
    project_limits,
    queued_entries,
)
from .run_task_binding import decided_task_refusal
from .sse import sse_manager
from .task_workspace import takes_own_checkout
from .usage_accounting import project_budget_state
from .utils import persist_event

_agent_locks: Dict[Tuple[str, str], asyncio.Lock] = {}


@dataclass(frozen=True)
class TurnRefusal:
    """A refusal about what a request asked for, carried out to the caller that asked it.

    Exists so a caller can answer *no* instead of *queued* (F108). Its **presence** is the
    classification, which is why it is a separate object rather than another boolean beside
    `terminal_failure`: that flag defaults to `True` and six early returns below take the default
    without meaning it, so a caller gating on it would report a working request as failed. Nothing
    but the refusal branch can construct one of these, so no early return can produce a false
    positive however its defaults are written.

    `entry_ids` is what makes it attributable. `schedule_agent` builds its turn from the oldest
    eligible entry across the agent's *whole* queue, so a refusal frequently belongs to a
    conversation the current caller never mentioned; without the ids, answering *no* to whoever
    happened to arrive would report a refusal about somebody else's input.
    """

    status_code: int
    detail: str
    entry_ids: Tuple[str, ...]


@dataclass
class ScheduleResult:
    response: Optional[object] = None
    waiting_reason: Optional[str] = None
    terminal_failure: bool = True
    refusal: Optional[TurnRefusal] = None


def _lock_for(project_id: str, agent: str) -> asyncio.Lock:
    return _agent_locks.setdefault((project_id, agent), asyncio.Lock())


def _entry_kind(entry: InboundQueueEntry) -> Optional[str]:
    """Returns "review" or "work", or `None` for an entry naming neither (design D3, F66).

    `review_task_id` wins when both are set — the divergence response that restaffs a failed
    review sets both to the same task (`run_divergence.py`), and that entry needs the review
    checkout, not the ordinary worktree, so it is a review turn regardless of the `task_id` beside
    it.
    """
    if entry.review_task_id is not None:
        return "review"
    if entry.task_id is not None:
        return "work"
    return None


async def other_input_would_have_run_elsewhere(
    db: AsyncSession,
    *,
    project_id: str,
    agent: str,
    entries: Sequence[InboundQueueEntry],
    selected: Sequence[InboundQueueEntry],
    controlling_conversation_id: str,
    hop_budget: int,
) -> bool:
    """Would any queued input for *agent* outside *selected* have run in a different workspace?

    Asked only when a turn was refused because the agent's **own** worktree could not be prepared
    (`agent_workspace_unavailable`). `agent-conversation-workspace` says such a refusal counts a
    delivery attempt only *"where other queued input could have run"*, and this is that test.
    `schedule_agent` is the only party that can answer it: `trigger_agent_directly` sees one turn,
    while this function already holds every queued entry for the agent, across conversations.

    **The test, stated against what actually decides the workspace.** An entry outside `selected`
    would have run elsewhere when it is *eligible* -- within the hop budget, in an open conversation
    belonging to this agent and project -- **and** either names a review that could itself have
    started (its checkout is `.agentweave/reviews/<reviewer>`, a different directory entirely), or
    is about a task that takes its own checkout: a row that exists here, is not decided, and
    `task_workspace.takes_own_checkout` accepts.

    **R1 reduced this to `entry.task_id is not None`, and that reduction is wrong.** Reaching this
    refusal does prove `is_writing_agent` and `is_git_repo`, and both are properties of the agent
    and the project rather than of an entry, so they drop out of the comparison. It does not follow
    that naming a task means taking a task workspace: `agent_trigger` hands `resolve_turn_workspace`
    the id `task_workspace` resolved, not the entry's, and that comes back `UNBOUND` for a
    **grandfathered** task (the stamp migration `0095` left on every task that had already been
    worked) and for a task id `validate_task_id` refuses. Either one is a turn *about a task* that
    runs in the blocked directory. Under R1's rule it counts as evidence that something else could
    have run, the attempt is counted, and the operator's message is destroyed at the limit having
    released nothing -- on precisely the projects that predate per-task isolation, which is every
    project that had work on it when isolation shipped and none of the fresh ones a test or a drive
    creates.

    **R2 extended that list to deleted and decided tasks, and R3 measured that those two are
    conditional.** `run_task_binding.resolve_bound_task` does not stop when it drops the named task;
    it falls through to `binding_for_conversation`, so an entry naming a deleted or decided task, in
    a thread that is itself about a live task, binds to the thread's task and takes that task's
    checkout. It really could have run. Grandfathering and an unmintable id are unconditional
    because they are decided one layer lower, *after* the binding has been chosen. That is why the
    test below is an **or** over the entry's own task and its conversation's, and why collapsing it
    to either half alone would be wrong -- the argument for the `or` is R3's, not R2's, even though
    both arrive at the same code.

    **Which way each approximation errs, because the two errors are not symmetric.** A false *no*
    holds input the requirement would have counted, and the operator's queue waits -- recoverable,
    and the next repair delivers it. A false *yes* counts an attempt and destroys the operator's
    message at the third schedule (F188). So every approximation here leans toward *no*: an entry
    with no conversation, one whose conversation is closed or over the hop budget, a review with no
    commit to check out, a task id that no longer resolves to a row -- none of them count, because
    none of them could have run either.

    **Entries inside `selected` are excluded, and the reason is not an enumeration of routes.**
    Reaching this refusal proves the *whole* resolution for this batch -- every entry's named task,
    the conversation's inherited task, the scheme, the id -- already produced `UNBOUND`. Nothing
    about the next schedule changes any of those inputs, so an entry inside `selected` reaches this
    same arm again. For the same reason no entry in the **controlling** conversation is given an
    inheritance lookup: that conversation's own binding is already known not to have taken a
    checkout of its own, so such an entry counts only by naming a task or a review itself.

    **Two queries, in this order, and the order is forced.** First the conversations the remaining
    entries belong to, for their lifecycle and the task each one carries; then one query over the
    union of the task ids the entries name and the task ids those conversations carry -- whose `IN`
    list does not exist until the first query has run. Never one query per entry. The exception is
    `commit_for_task_review`, one call per review entry considered (design D3b), and the ordinary
    count of review entries outside `selected` is zero.
    """
    chosen = {entry.id for entry in selected}
    remaining = [
        entry
        for entry in entries
        if entry.id not in chosen
        and entry.hop_depth <= hop_budget
        and entry.conversation_id is not None
    ]
    if not remaining:
        return False

    # Eligibility is expressed as `WHERE`, not as a filter over what came back: a conversation that
    # is closed, or belongs to another agent or project, simply does not appear and its entries
    # fall out with it. `schedule_agent` refuses on those same three above, so an entry riding on
    # one could not have run either.
    conversations: Dict[str, Conversation] = {
        conversation.id: conversation
        for conversation in (
            await db.execute(
                select(Conversation).where(
                    Conversation.project_id == project_id,
                    Conversation.agent == agent,
                    Conversation.lifecycle == "open",
                    Conversation.id.in_({entry.conversation_id for entry in remaining}),
                )
            )
        )
        .scalars()
        .all()
    }
    eligible = [entry for entry in remaining if entry.conversation_id in conversations]
    if not eligible:
        return False

    named: Set[str] = set()
    for entry in eligible:
        named.update(_tasks_this_entry_is_about(entry, conversations, controlling_conversation_id))
    if not named:
        return False

    tasks: Dict[str, Task] = {
        task.id: task
        for task in (
            await db.execute(select(Task).where(Task.project_id == project_id, Task.id.in_(named)))
        )
        .scalars()
        .all()
    }

    for entry in eligible:
        if _entry_kind(entry) == "review":
            review_task_id = entry.review_task_id
            if review_task_id is None or review_task_id not in tasks:
                continue
            # Design D3b: a review whose task carries no evidence naming a commit is refused by
            # `prepare_review_turn` before it reaches a checkout, so counting on its behalf would
            # destroy the head of the queue for a turn that was never going to happen.
            target = await requirement_evidence.commit_for_task_review(db, review_task_id)
            if target.resolved:
                return True
            continue
        for task_id in _tasks_this_entry_is_about(
            entry, conversations, controlling_conversation_id
        ):
            task = tasks.get(task_id)
            if task is None:
                continue
            if takes_own_checkout(task) and decided_task_refusal(task) is None:
                return True
    return False


def _tasks_this_entry_is_about(
    entry: InboundQueueEntry,
    conversations: Dict[str, Conversation],
    controlling_conversation_id: str,
) -> List[str]:
    """The task ids `other_input_would_have_run_elsewhere` has to resolve for *entry*.

    A review entry is about exactly one task and reaches it by a different route, so it names only
    that one -- `_entry_kind` already encodes that `review_task_id` wins where an entry carries
    both, because the divergence response that restaffs a failed review sets both to the same task
    and needs the review checkout. Everything else names its own task *and* the one its thread
    inherits, except in the controlling conversation, whose binding is already known not to have
    taken a checkout of its own.
    """
    if _entry_kind(entry) == "review":
        return [entry.review_task_id] if entry.review_task_id is not None else []
    named: List[str] = []
    if entry.task_id is not None:
        named.append(entry.task_id)
    if entry.conversation_id != controlling_conversation_id:
        conversation = conversations.get(entry.conversation_id or "")
        inherited = getattr(conversation, "task_id", None)
        if inherited is not None and inherited not in named:
            named.append(inherited)
    return named


async def schedule_agent(project_id: str, agent: str) -> ScheduleResult:
    """Start at most one turn for *agent*; leave work durable when it cannot start."""
    from .api.v1.agent_trigger import TriggerAgentError, trigger_agent_directly

    async with _lock_for(project_id, agent), async_session_factory() as db:
        running = await db.execute(
            select(Run.id)
            .where(Run.project_id == project_id, Run.agent == agent, Run.status == "running")
            .limit(1)
        )
        if running.scalar_one_or_none() is not None:
            return ScheduleResult(waiting_reason="agent is already running", terminal_failure=False)

        entries = await queued_entries(db, project_id, agent)
        if not entries:
            return ScheduleResult(waiting_reason="queue is empty")
        hop_budget, cap = await project_limits(db, project_id)
        if not can_start(entries, hop_budget):
            return ScheduleResult(waiting_reason="hop budget exhausted")

        controlling = next((entry for entry in entries if entry.hop_depth <= hop_budget), None)
        if controlling is None or controlling.conversation_id is None:
            return ScheduleResult(waiting_reason="queued entry has no conversation")
        conversation = await get_conversation_by_id(db, controlling.conversation_id)
        if (
            conversation is None
            or conversation.project_id != project_id
            or conversation.agent != agent
            or conversation.lifecycle != "open"
        ):
            return ScheduleResult(waiting_reason="conversation is unavailable")

        # Filter by depth and by kind, as well as by conversation. `can_start` asks whether the
        # turn may begin; nothing used to ask which entries may ride on it, so an over-budget
        # entry was bundled into a turn admitted by a shallower one and delivered anyway (design
        # D1, finding F5). F66 is the same defect one column over: a review entry and a work entry
        # batched together delivered a turn that was neither, so the controlling entry's kind
        # decides the turn and the other kind's entries are deferred to the next one (design D3).
        # An entry naming neither — a plain message riding beside a delegation — has no kind to
        # conflict with either and always rides along.
        controlling_kind = _entry_kind(controlling)
        selected = [
            entry
            for entry in entries
            if entry.conversation_id == conversation.id
            and entry.hop_depth <= hop_budget
            and (
                controlling_kind is None
                or _entry_kind(entry) is None
                or _entry_kind(entry) == controlling_kind
            )
        ][:cap]
        if not selected:
            return ScheduleResult(waiting_reason="hop budget exhausted")
        controlling_operator = next(
            (entry for entry in selected if entry.origin_type == "operator"), None
        )
        initiator = "operator" if controlling_operator is not None else "autonomous"
        budget = await project_budget_state(db, project_id)
        if initiator == "autonomous" and budget["exhausted"]:
            return ScheduleResult(waiting_reason="token budget exhausted")
        work_dir = controlling_operator.work_dir if controlling_operator is not None else None
        # Read from the same entry `work_dir` comes from, for the same reason: a turn can batch
        # several entries, and the operator's own is the one whose viewing position describes
        # what they asked. An agent's or a job's entry never carries one.
        spec_document = (
            controlling_operator.spec_document if controlling_operator is not None else None
        )

        try:
            response = await trigger_agent_directly(
                project_id=project_id,
                agent=agent,
                message=format_turn_prompt(selected),
                conversation_id=conversation.id,
                work_dir=work_dir,
                spec_document=spec_document,
                session=db,
                queue_entry_ids=[entry.id for entry in selected],
                # The admitting entry's depth, not `min()` across the batch. `min()` was never a
                # decision — it let a turn batching a hop-0 entry with a deeper one restart the
                # count from zero, so the chain ran backwards (design D2). With the filter above,
                # every delivered entry is within budget and `controlling` is the first of them.
                turn_depth=controlling.hop_depth,
                initiator=initiator,
            )
        except TriggerAgentError as exc:
            workspace_unavailable = getattr(exc, "workspace_unavailable", False)
            # Written down before the classification is even asked, because it matters in both
            # branches and for the same reason: this is the only place the refusal's own words
            # exist. `GET /queue/{agent}/status` re-derives what it can and reported
            # `waiting_reason: null` for everything it could not — a D8 checkout collision, an
            # unimplemented runner, a work_dir the project does not contain (F97). Recording it
            # here is what keeps the status route from having to restate each condition, and what
            # makes the *next* refusal visible without another edit.
            for entry in selected:
                entry.waiting_reason = exc.detail
            await db.commit()
            # Does this refusal clear on its own? `workspace_unavailable` was the first refusal
            # that did, and it still selects the operator event below, but it is no longer the only
            # one: a turn refused because another agent holds the task's checkout (design D8) waits
            # for that turn to end. Asking the classification rather than enumerating the causes is
            # what stops the next transient refusal from having to edit this branch again.
            transient = getattr(exc, "transient", workspace_unavailable)
            if workspace_unavailable:
                await persist_event(
                    db,
                    project_id,
                    "queue_agent_paused",
                    {
                        "agent": agent,
                        "reason": exc.detail,
                        "directory_state": exc.directory_state,
                    },
                    agent=agent,
                    severity="warn",
                )
                await sse_manager.broadcast(
                    project_id,
                    "queue_agent_paused",
                    {
                        "agent": agent,
                        "reason": exc.detail,
                        "directory_state": exc.directory_state,
                    },
                )
            elif (
                not transient
                and not getattr(exc, "agent_wide", False)
                # The third question, and it is asked **last** because it is the only one of the
                # three that costs queries: `not transient` and `not agent_wide` are attribute
                # reads, so a refusal that is either never reaches the helper at all.
                #
                # A refusal about the agent's **own** worktree is not `agent_wide` and by design
                # must not become it (design D2 of `a-blocked-agent-workspace-holds-its-input`):
                # the agent has a runner, its CLI is installed, and it would have run. But nothing
                # queued behind the head can run either while that one directory is obstructed
                # — unless some other queued entry would have taken a *different* workspace, in
                # which case the head really is in the way and F56's argument applies unchanged.
                # `agent-conversation-workspace` counts such a refusal exactly *"where other
                # queued input could have run"*, and this is where that is measured. Every other
                # refusal reaches this branch with the condition it already had (F188).
                and (
                    not getattr(exc, "agent_workspace_unavailable", False)
                    or await other_input_would_have_run_elsewhere(
                        db,
                        project_id=project_id,
                        agent=agent,
                        entries=entries,
                        selected=selected,
                        controlling_conversation_id=conversation.id,
                        hop_budget=hop_budget,
                    )
                )
            ):
                # No `Run` was ever created for this attempt, so `selected` never became
                # `delivered` and `return_run_entries`'s own abandonment bookkeeping never runs
                # for it (F56) — a refusal raised here (a review target with no evidence naming a
                # commit, an archived agent, a task that does not exist, ...) repeats identically
                # forever, and every entry queued behind it starves along with it. Count the
                # attempt the same way a spawned-and-failed run's does, and give up on the same
                # schedule, so a permanently wrong entry stops wedging the whole queue.
                #
                # **`and not agent_wide` is F114, and it is the same rule the `transient` half of
                # this condition already applies.** F56's reasoning holds wherever the refused
                # entry is *in the way of other input* — which is every example in the list above.
                # It does not hold where the refusal stops the agent running at all: no runner is
                # bound, its CLI is not installed, its runner row is gone. Nothing is starving
                # behind that entry, because nothing for that agent could run either way, so
                # dropping the head of the queue buys nobody a turn — and it costs the operator
                # the input the product promised to hold until they performed the repair (F96).
                #
                # Measured before this line existed: three messages to an unbound agent destroyed
                # the first in under two seconds, and two clicks of the Continue button — the
                # control the conversation view offers for exactly this situation — destroyed it
                # faster. Every schedule counted an attempt, so the operator's own attempts to
                # find out why nothing was happening were what consumed the allowance.
                #
                # Only refusals that are *certainly* agent-wide carry the flag, and a refusal
                # that blocks one entry keeps counting (design D3a of
                # `2026-08-28-a-delivery-attempt-means-a-delivery`).
                #
                # **This comment used to say the workspace refusal was one of those, flatly, and
                # for one of its two arms that was wrong** — which is F188, and which
                # `a-blocked-agent-workspace-holds-its-input` is the change that split them. The
                # two arms are now different sites raising different sentences, and the `or` above
                # is where the difference lands:
                #
                #   * a **task's** checkout that could not be prepared is the *task's* workspace,
                #     not the agent's. The agent is fine, its other input can run, and the head
                #     entry really is in the way — so that arm carries no flag at all and reaches
                #     this branch exactly as it did before either flag existed.
                #   * the agent's **own** workspace is the case that argument does not survive.
                #     Nothing of this agent's runs in a directory the Hub cannot provision, so
                #     there is usually nothing behind the head that dropping it would release, and
                #     dropping it costs the operator the message F96 promised to hold. That arm
                #     carries `agent_workspace_unavailable`, and the condition above asks
                #     `other_input_would_have_run_elsewhere` before believing the head is in
                #     anybody's way — because "usually" is not "always", and a task-bound entry
                #     waiting in another conversation would have run in the task's checkout, which
                #     this failure never touched.
                #
                # Two citations, kept apart on purpose. The rule *this* branch applies is D3a of
                # the change named above. The predicate the helper reaches for — whether some other
                # entry's task would have taken a checkout of its own — is design **D8** of
                # `a-blocked-agent-workspace-holds-its-input`, numbered away from D3a precisely so
                # that a reference in this file names exactly one of them; the split at the raise
                # site itself is that change's D1.
                abandoned: list[InboundQueueEntry] = []
                for entry in selected:
                    entry.delivery_attempts = (entry.delivery_attempts or 0) + 1
                    if entry.delivery_attempts >= DELIVERY_ATTEMPT_LIMIT:
                        entry.state = "withdrawn"
                        entry.withdrawn_at = datetime.now(timezone.utc)
                        entry.abandoned_reason = (
                            f"delivery failed {entry.delivery_attempts} times "
                            f"({exc.detail}); the Hub stopped retrying"
                        )
                        abandoned.append(entry)
                await db.commit()
                # Same shape `_report_abandoned_entries` broadcasts for a spawned-and-failed run,
                # `run_id: None` because none was ever created — the operator's signal that input
                # is being dropped should not depend on which of the two paths dropped it.
                for entry in abandoned:
                    payload = {
                        "entry_id": entry.id,
                        "agent": agent,
                        "run_id": None,
                        "attempts": entry.delivery_attempts,
                        "reason": entry.abandoned_reason,
                        "conversation_id": entry.conversation_id,
                    }
                    await persist_event(
                        db,
                        project_id,
                        "queue_entry_abandoned",
                        payload,
                        agent=agent,
                        severity="warn",
                    )
                    await sse_manager.broadcast(project_id, "queue_entry_abandoned", payload)
            # A transient refusal that is not the paused-workspace one records nothing at all,
            # which is the shape the sibling per-agent rule already has: `schedule_agent` returns
            # "agent is already running" above without an event, because a queue waiting its turn
            # is the system working. The entry keeps `delivery_attempts` at whatever it was, stays
            # `queued`, and the next tick tries again.
            # Carried out only when the refusal is about what was asked (design D10). A
            # non-transient refusal about the *environment* — no runner bound, the CLI missing
            # from PATH — is why the queue exists: the entry waits, the operator performs the
            # repair, and binding a runner delivers it (F96). Answering those as failures would
            # discard input the Hub promised to keep.
            refusal = (
                TurnRefusal(
                    status_code=exc.status_code,
                    detail=exc.detail,
                    entry_ids=tuple(entry.id for entry in selected),
                )
                if getattr(exc, "request_level", False) and not transient
                else None
            )
            return ScheduleResult(
                waiting_reason=exc.detail,
                terminal_failure=not transient,
                refusal=refusal,
            )
        return ScheduleResult(response=response, terminal_failure=False)


async def redrain_queued_agents(project_id: str) -> None:
    """Re-evaluate every queued agent after repair or settings change."""
    async with async_session_factory() as db:
        agents = (
            (
                await db.execute(
                    select(InboundQueueEntry.agent)
                    .where(
                        InboundQueueEntry.project_id == project_id,
                        InboundQueueEntry.state == "queued",
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        for agent in agents:
            await schedule_agent(project_id, agent)
