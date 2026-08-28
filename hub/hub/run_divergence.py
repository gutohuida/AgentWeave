"""What happens when a run ends holding work nobody moved.

`run_task_binding` answers *whether* a run advanced its task. This module is what the answer costs:
it records the divergence, and applies the policy the task carries — surface it, run the same agent
once more, or route the work to a stronger one.

Asked at the run boundary, which AgentWeave owns for every runner, rather than inside the agent.
That is the difference between enforcement and instruction, and it is why none of this needs a
hook: a runner without hooks is governed identically
(`openspec/specs/agent-capability-plane/spec.md`, "No capability may exist only in a hook").

Separate from `run_task_binding` because this half starts processes. Keeping the decision inert and
testable on one side of that line, and the spawning on the other, is what lets the rules be
exercised without a runner.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .checkpoints import loop_for_conversation
from .conversations import get_conversation_by_id, name_conversation, new_conversation
from .db.engine import async_session_factory
from .db.models import (
    Agent,
    InboundQueueEntry,
    Question,
    Run,
    RunDivergence,
    SpecDocument,
    SpecDocumentEvent,
    Task,
)
from .inbound_queue import new_entry
from .run_task_binding import (
    DEFAULT_POLICY,
    OUTCOME_ESCALATED,
    OUTCOME_RESTAFFED,
    OUTCOME_RETRIED,
    OUTCOME_SURFACED,
    POLICY_ESCALATE,
    POLICY_FLOW,
    POLICY_RETRY,
    POLICY_REVIEW,
    block_task_for_question,
    may_retry,
    review_task_for_run,
    run_advanced_its_task,
    unanswered_blocking_question,
)
from .sse import sse_manager
from .task_transitions import ACTOR_RUN, STATUS_BLOCKED, allowed_targets
from .utils import persist_event, short_id

logger = logging.getLogger(__name__)


async def resolve_divergences_for_task(session: AsyncSession, task_id: str) -> int:
    """Close every open divergence on `task_id`. Returns how many were closed.

    A divergence is an open condition, not a verdict. Long work spanning several turns opens one on
    each intermediate run, and each closes the moment the work reaches the ledger — which is what
    keeps the default policy from reading as an accusation against an agent that is simply not
    finished yet (design D6, and its Open Question 1).

    `resolved_at` is the one field ever written after the row is created. The record survives its
    own resolution: "this happened" stays true regardless of what happened next.

    Emits `run_divergence_resolved` naming the task and the count, and only when the count is
    non-zero — closing nothing is not news (design D6). `commit=False`: this is reached from
    `apply_transition`, before its own `TaskTransition` and status write are committed by the
    caller (`task_transition_service.py`'s own docstring: "the caller commits") — committing here
    would land that still-in-flight write early. `sse_manager.broadcast` needs no such care: its
    payload is exactly what is already in memory, not a re-read of the database.
    """
    result = await session.execute(
        select(RunDivergence)
        .where(RunDivergence.task_id == task_id)
        .where(RunDivergence.resolved_at.is_(None))
    )
    open_rows = list(result.scalars().all())
    now = datetime.now(timezone.utc)
    for row in open_rows:
        row.resolved_at = now
    if open_rows:
        payload = {"task_id": task_id, "count": len(open_rows)}
        await persist_event(
            session,
            open_rows[0].project_id,
            "run_divergence_resolved",
            payload,
            severity="info",
            commit=False,
        )
        await sse_manager.broadcast(open_rows[0].project_id, "run_divergence_resolved", payload)
    return len(open_rows)


async def is_live_flow_work_turn(session: AsyncSession, run: Run) -> bool:
    """Was `run` a live flow's own ordinary work turn?

    One owned answer, read by both the severity derivation (D6) and the `retry` suppression (D7)
    — writing this check inline at both sites is the exact defect `one-answer-to-what-is-happening`
    exists to end: one question, two answers, free to drift.

    Four things must all be true, and each is its own way to be False:

    - the run was bound to a task at all (`run.task_id`) — an unbound run has no work turn to ask
      about;
    - it was not a review (`review_task_for_run`) — a review's conversation belongs to the same
      live loop the flow's work turns do, so this cannot be answered by conversation lookup alone;
    - its conversation was actually fired by a flow (`loop_for_conversation` finds a `Loop`) — a
      delegated or operator-started run's conversation names no `JobRun` at all;
    - that flow is still live — `stopped_at` and `archived_at` are both checked explicitly rather
      than treating a non-None `Loop` as live (design D5, and the Risk this design names for
      exactly that trap).
    """
    if not run.task_id:
        return False
    if await review_task_for_run(session, run) is not None:
        return False
    if run.conversation_id is None:
        return False
    loop = await loop_for_conversation(session, run.conversation_id)
    if loop is None:
        return False
    return loop.stopped_at is None and loop.archived_at is None


async def _may_escalate(session: AsyncSession, run: Run) -> bool:
    """Whether a divergence of `run` may be answered by escalating.

    A run that is not itself a divergence response always may. A run that *is* one may escalate
    only if it was a **retry** — so `retry → escalate → surface` is a legal chain and
    `escalate → escalate` is not.

    Without this the escalation path loops. A task whose policy is `escalate` reassigns to agent C;
    if C's run also diverges, the same policy and the same escalation agent are still there, and it
    escalates to C again, forever. `may_retry` alone does not stop it, because escalation never
    consults it.

    Read from the divergence that caused this run rather than from a column, because the answer
    already exists: that row records what was decided.
    """
    if run.divergence_source_run_id is None:
        return True
    result = await session.execute(
        select(RunDivergence.outcome)
        .where(RunDivergence.run_id == run.divergence_source_run_id)
        .order_by(RunDivergence.sequence.desc())
        .limit(1)
    )
    row = result.first()
    return row is not None and row[0] == OUTCOME_RETRIED


async def _decide(session: AsyncSession, task: Task, run: Run) -> str:
    """Which outcome a divergence of `run` on `task` gets.

    Reads as the fall-through it is:

    - `retry`, and this run has not already spent the chain's retry → retry;
    - otherwise, anything that wanted to escalate, has somewhere to escalate to, and is not itself
      the product of an escalation → escalate;
    - otherwise → surface.

    So `escalate` never retries first, a spent `retry` escalates when the task names an agent
    (5.5), an `escalate` naming nobody surfaces rather than silently doing nothing (5.4), and every
    chain terminates: at most one retry and at most one escalation, then surface.
    """
    policy = task.divergence_policy or DEFAULT_POLICY
    if policy == POLICY_RETRY and may_retry(run):
        return OUTCOME_RETRIED
    if (
        policy in (POLICY_RETRY, POLICY_ESCALATE)
        and task.escalation_agent
        and await _may_escalate(session, run)
    ):
        return OUTCOME_ESCALATED
    return OUTCOME_SURFACED


def _response_prompt(task: Task, diverging_run: Run, escalating: bool) -> str:
    """What the responding run is told.

    Names the task, where it stands, and what it may legally do next — an agent told only "you
    forgot something" retries the same nothing. The reachable set comes from the same declaration
    the service enforces, so this cannot drift into promising a move that would be refused.
    """
    reachable = sorted(allowed_targets(task.status, ACTOR_RUN))
    moves = ", ".join(reachable) if reachable else "none — this task is not yours to move"
    lead = (
        f"Run {diverging_run.id} ({diverging_run.agent}) ended without recording any progress on "
        f"task {task.id}, so this work has been escalated to you."
        if escalating
        else f"Your previous run ended without recording any progress on task {task.id}."
    )
    return (
        f"{lead}\n\n"
        f"Task: {task.title}\n"
        f"Current status: {task.status}\n"
        f"Transitions available to you: {moves}\n\n"
        f"Either continue the work and record the transition when it is genuinely done, or say "
        f"plainly what is blocking it. Do not record a status the work has not reached."
    )


async def _agent_exists(session: AsyncSession, project_id: str, name: str) -> bool:
    result = await session.execute(
        select(Agent.id).where(Agent.project_id == project_id, Agent.name == name).limit(1)
    )
    return result.first() is not None


async def _queue_response(
    session: AsyncSession,
    *,
    project_id: str,
    agent: str,
    prompt: str,
    task_id: str,
    source_run_id: str,
    diverged_run: Run,
    review_task_id: Optional[str] = None,
) -> str:
    """Put the response in the agent's queue rather than spawning it here.

    Through the queue so hop budget, delivery caps and ordering all apply unchanged (task 5.7), and
    so a response arriving while the agent is busy waits instead of failing — a divergence answered
    with "that agent is already running" would answer nothing.

    `hop_depth=0`: the Hub is the origin, not a forwarding agent. The retry bound (D8) is what stops
    a chain here, not the hop budget.

    **`review_task_id` is set when the diverged run was itself a review** (design D5). Without it a
    responding reviewer is fired into its own worktree, where the author's unmerged work does not
    exist — finding F10, reproduced by the very mechanism meant to rescue a failed review. It had
    never fired only because reaching this path at all required `task.escalation_agent`, which is
    NULL on every task; D4 makes the path reachable, which is what turns this from a cleanup into a
    prerequisite.

    A response to a run that was *not* a review passes None and prepares no checkout. Left as an
    argument rather than derived here from `task_id`, because "which task this run works on" and
    "which task this run inspects" are the two meanings this change exists to keep apart — deriving
    one from the other inside this function would put the collision back one layer down.
    """
    conversation_id = await _conversation_for_response(
        session, project_id=project_id, agent=agent, diverged_run=diverged_run
    )
    entry = new_entry(
        project_id=project_id,
        agent=agent,
        origin_type="divergence",
        content=prompt,
        hop_depth=0,
        task_id=task_id,
        divergence_source_run_id=source_run_id,
        review_task_id=review_task_id,
        conversation_id=conversation_id,
    )
    session.add(entry)
    return entry.id


async def _conversation_for_response(
    session: AsyncSession,
    *,
    project_id: str,
    agent: str,
    diverged_run: Run,
) -> Optional[str]:
    """Which thread the response arrives in. **Finding F67.**

    Until 2026-08-26 this function did not exist and the entry carried no conversation at all —
    and `turn_scheduler.schedule_agent` refuses precisely that shape, returning *"queued entry has
    no conversation"*. So every response ever queued sat `queued` forever. Measured on the trial
    database before the fix: **25 divergence rows, zero carrying a `response_run_id`.** Not few;
    none, across the entire life of the capability.

    It stayed invisible because nothing reached here. `retry` needs a task nobody set to `retry`;
    `escalate` needs `task.escalation_agent`, NULL on every task ever recorded. All 24 historical
    divergences are `surfaced`, which queues nothing. `restaffed` (design D4) is the first outcome
    that reaches this on an ordinary task with nothing configured, and it walked straight into it on
    the first live drive.

    Two cases, and the agent is what separates them:

    - **Same agent** (`retry`) — continue in the thread the run diverged in. It is that agent's own
      thread and the work is the same work; a fresh conversation would hide the retry from the
      history that explains it, and would throw away a resumable provider session.
    - **A different agent** (`escalate`, `restaffed`) — a fresh thread, because a conversation
      belongs to one agent and `schedule_agent` checks exactly that. Origin `divergence`, its own
      value rather than a borrowed one: nobody asked for this thread, and reusing `operator` would
      put the operator's name on work they did not ask for (migration `0058`'s reasoning for the
      queue entry's own `origin_type`, and `0093`'s for this).

    Returns None only where the diverged run has no conversation to continue and none can be made,
    which leaves the old behaviour rather than raising — a divergence must never turn a finished run
    into a failed one.
    """
    if agent == diverged_run.agent and diverged_run.conversation_id:
        # `get_conversation_by_id`, never `session.get`: the primary key is `sequence`, an
        # autoincrement integer, so `session.get` would compare a `conv-…` string against an
        # integer column and never match. The helper exists because that trap has been fallen into
        # before — and it was fallen into again while writing this function, caught by the test.
        existing = await get_conversation_by_id(session, diverged_run.conversation_id)
        if existing is not None and existing.lifecycle == "open" and existing.agent == agent:
            return existing.id

    conversation = new_conversation(project_id=project_id, agent=agent, origin="divergence")
    name_conversation(conversation, f"Divergence on {diverged_run.id}")
    session.add(conversation)
    await session.flush()
    return conversation.id


# --------------------------------------------------------------------------------------
# A review that gave no verdict (`one-answer-to-what-is-happening`, D3–D6)
# --------------------------------------------------------------------------------------


async def _reviewers_that_gave_no_verdict(session: AsyncSession, task: Task) -> "set[str]":
    """Every agent holding an unresolved review divergence on *task*.

    This is what bounds re-resolution, and it is derived rather than counted. Excluding only the
    agent that just failed would let `A → B → A → B` run forever on a two-agent roster; excluding
    every agent that has already been silent on this task terminates against a finite roster, and
    reaches D4's own stated end state — *"a second failure with nobody left surfaces"* — by the
    general rule rather than by a hop counter nobody can see.

    Scoped to **unresolved** divergences deliberately. `resolve_divergences_for_task` closes these
    the moment an actor transition lands, so a task that went through a review cycle, got its
    verdict, was revised and came back is free to reach the same reviewer again. The bar is on the
    attempt in progress, not on the agent's history.
    """
    result = await session.execute(
        select(RunDivergence.agent)
        .where(RunDivergence.task_id == task.id)
        .where(RunDivergence.policy_applied == POLICY_REVIEW)
        .where(RunDivergence.resolved_at.is_(None))
    )
    return {agent for agent in result.scalars().all() if agent}


async def _review_was_declared(session: AsyncSession, run: Run, task: Task) -> bool:
    """Whether the reviewer that just gave no verdict was the one the task's document **named**.

    Derived by asking the declaration, not by storing which rung staffed the turn. The declaration
    is a fact about the document and the document is what the operator would fix — so reading it
    now answers with the operator's *current* statement. A document edited between staffing and
    failure therefore classifies by what it says today, which is the more useful of the two answers
    and self-correcting besides.

    A review run exists at all only where the declaration resolved to this agent, or where there
    was no declaration and availability picked one: rung 1b surfaces without firing anybody. So the
    two branches below are exhaustive.
    """
    from . import review_turn

    resolution = await review_turn.resolve_declared_reviewer(
        session, project_id=run.project_id, task=task
    )
    return bool(resolution.declared) and resolution.agent == run.agent


async def _answer_failed_review(
    session: AsyncSession, run: Run, task: Task
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """What a review that gave no verdict costs. Returns (outcome, response_agent, previous
    assignee, reason).

    Design D4's split, and it falls straight out of the requirement archived the same morning:
    *"by the same resolution the rest of the product already uses for a declared reviewer, never a
    second one."*

    ```
      reviewer was DECLARED   ──▶ surface. Never substitute.
      reviewer was AVAILABLE  ──▶ resolve again, excluding everyone already silent on this task
    ```

    Firing somebody else for a declared reviewer would tell the operator the named reviewer checked
    the work when it did not — the same reasoning rung 1b already applies to a declaration that
    fails to resolve, and it does not weaken because the named agent ran and then said nothing.

    `task.escalation_agent` is deliberately not consulted on either branch. It would be a *second*
    reviewer resolution, and D6's problem — an escalation target that authored the work is a
    guaranteed 403 from `agent_that_completed` — cannot arise here at all, because the resolver
    already excludes the author by construction.
    """
    # Local imports, matching `scheduler._task_is_claimable_by`'s own call of
    # `agent_that_completed`: this module is imported by the trigger path that `scheduler` also
    # reaches, and the module docstring's line about keeping the deciding half free of the spawning
    # half is what these keep true.
    from .scheduler import resolve_reviewer
    from .task_transition_service import agent_that_completed

    if await _review_was_declared(session, run, task):
        return (
            OUTCOME_SURFACED,
            None,
            None,
            f"{run.agent} is this task's declared reviewer and its review of {task.id} ended "
            f"without recording a verdict. Nobody has been substituted: naming a different "
            f"reviewer, reviewing it yourself, or asking this one again is the way forward.",
        )

    author = await agent_that_completed(session, task.id)
    barred = await _reviewers_that_gave_no_verdict(session, task)
    barred.add(run.agent)
    if author:
        barred.add(author)

    choice = await resolve_reviewer(session, task, project_id=run.project_id, exclude=barred)
    if choice.agent is None:
        # Rung 3, or a declaration that appeared since. Either way nobody is fired and the reason
        # comes from the resolver unchanged, so the operator reads why rather than that something
        # failed. The flow's job is untouched — it stays enabled and stays scheduled.
        return OUTCOME_SURFACED, None, None, choice.reason

    previous_assignee = task.assignee
    # Reassigned for the same reason escalation reassigns: leaving the assignee pointing at the
    # agent that gave no verdict would make the board disagree with reality. `enter_selected_task`
    # writes the reviewer into `assignee` on the flow path too, so this is the same statement that
    # path makes, not a new one. The previous assignee is on the record, so it is reversible.
    task.assignee = choice.agent
    await _queue_response(
        session,
        project_id=run.project_id,
        agent=choice.agent,
        prompt=_failed_review_prompt(task, run),
        task_id=task.id,
        # D5. The responding reviewer gets the same checkout of the work under review that the
        # original review turn was given.
        review_task_id=task.id,
        source_run_id=run.id,
        diverged_run=run,
    )
    return OUTCOME_RESTAFFED, choice.agent, previous_assignee, None


def _failed_review_prompt(task: Task, diverging_run: Run) -> str:
    """What a reviewer taking over from one that said nothing is told.

    Names the task, its status and the legal verdicts, from the same declaration the service
    enforces — so this cannot drift into promising a move that would be refused. It does **not**
    characterise the previous reviewer's judgement, because there was none to characterise: the
    only fact is that the turn ended without one.
    """
    reachable = sorted(allowed_targets(task.status, ACTOR_RUN))
    moves = ", ".join(reachable) if reachable else "none — this task is not yours to move"
    return (
        f"Run {diverging_run.id} ({diverging_run.agent}) was given task {task.id} to review and "
        f"ended without recording a verdict, so the review comes to you.\n\n"
        f"Task: {task.title}\n"
        f"Current status: {task.status}\n"
        f"Verdicts available to you: {moves}\n\n"
        f"Your workspace is the checkout of the work under review. Read it and record one of those "
        f"verdicts, or say plainly what stops you reaching one. Do not record a verdict the work "
        f"has not earned."
    )


async def _apply_policy(
    session: AsyncSession, run: Run, task: Task
) -> Tuple[str, Optional[str], Optional[str]]:
    """Do what the task's policy says. Returns (outcome, response_agent, previous_assignee)."""
    outcome = await _decide(session, task, run)

    if outcome == OUTCOME_RETRIED:
        await _queue_response(
            session,
            project_id=run.project_id,
            agent=run.agent,
            prompt=_response_prompt(task, run, escalating=False),
            task_id=task.id,
            source_run_id=run.id,
            diverged_run=run,
        )
        return outcome, run.agent, None

    if outcome == OUTCOME_ESCALATED:
        target = task.escalation_agent
        if not await _agent_exists(session, run.project_id, target):
            # A named agent that no longer exists is a surface, not a failure. Escalating into a
            # name nobody answers to would leave the work stalled with a record claiming it moved.
            logger.warning(
                "Task %s escalates to %r, which is not an agent in this project; surfacing instead",
                task.id,
                target,
            )
            return OUTCOME_SURFACED, None, None
        previous_assignee = task.assignee
        # Reassigned, not merely run: leaving the assignee pointing at the agent that just dropped
        # the work would make the board disagree with reality, and the next reader would re-delegate
        # to the wrong agent (design D9). The previous assignee is on the record, so it is
        # reversible.
        task.assignee = target
        await _queue_response(
            session,
            project_id=run.project_id,
            agent=target,
            prompt=_response_prompt(task, run, escalating=True),
            task_id=task.id,
            source_run_id=run.id,
            diverged_run=run,
        )
        return outcome, target, previous_assignee

    return OUTCOME_SURFACED, None, None


async def record_response_run(
    session: AsyncSession, source_run_id: str, response_run_id: str
) -> None:
    """Stamp the run that answered a divergence onto its record.

    Written here rather than when the divergence is recorded because the response run does not
    exist yet at that point: the answer is *queued*, and becomes a run in a later call, when the
    agent is free. This and `resolved_at` are the only fields ever written after creation, and both
    record something that was not knowable when the row was made.
    """
    result = await session.execute(
        select(RunDivergence)
        .where(RunDivergence.run_id == source_run_id)
        .where(RunDivergence.response_run_id.is_(None))
        .order_by(RunDivergence.sequence.desc())
        .limit(1)
    )
    divergence = result.scalars().first()
    if divergence is not None:
        divergence.response_run_id = response_run_id


async def _announce_block(
    session: AsyncSession,
    run: Run,
    task: Task,
    question: Question,
) -> None:
    """Tell the operator's board that a task is now waiting on them.

    `info`, not `warn`. A divergence is `warn` because it wants attention on something that went
    wrong; this is the mechanism working — the agent asked rather than guessed. Warning about it
    would train the operator to read the one signal that means "someone did the right thing" as a
    problem.
    """
    payload = {
        "run_id": run.id,
        "agent": run.agent,
        "task_id": task.id,
        "task_title": task.title,
        "question_id": question.id,
        "reason": task.blocked_reason,
    }
    await persist_event(
        session,
        run.project_id,
        "task_blocked",
        payload,
        agent=run.agent,
        severity="info",
    )
    await sse_manager.broadcast(run.project_id, "task_blocked", payload)


async def note_turn_that_produced_nothing(session: AsyncSession, run: Run) -> bool:
    """Record a turn that was given a document to write, wrote none, and asked nothing (F38).

    Measured 2026-08-25: the spec author read the code, diagnosed the bug correctly and unprompted,
    and closed with four well-judged questions — as chat text, in a turn that then completed. No
    `Question` row, no blocking, no parked task. The run was over and the specification was never
    written. Its charter names `ask_user` six times; told plainly on the next turn, it used the tool
    immediately and well. The mechanism works — what was missing was anything noticing that a turn
    had produced nothing.

    **Every fact used here is structured state, and the agent's prose is never read.** That is the
    whole design, not an implementation detail. A backstop that inspected a run's final text for
    something question-shaped existed until 2026-08-20 and was retired deliberately, because
    guessing whether trailing prose is a question is a judgement the product should not make on the
    operator's behalf; migration `0082` dropped its table. This reintroduces none of that. It asks
    three questions with recorded answers: was this turn given a document, was anything ever written
    into it, and did this run write a question.

    The task case is not handled here — a bound run that ends without moving its task is a
    divergence, which is the rest of this module. This is the same shape for the deliverable that
    has no task: `InboundQueueEntry.spec_document` exists precisely because the operator had a
    document open when they sent the input.

    A turn with no document named is not a candidate at all. Most turns are conversation, and a
    reply that produces no row is the correct outcome for one — recording a non-outcome for every
    chat turn would be noise the operator learns to ignore, which is worse than silence.

    Returns whether anything was recorded.
    """
    document_path = await session.scalar(
        select(InboundQueueEntry.spec_document)
        .where(InboundQueueEntry.delivered_in_run_id == run.id)
        .where(InboundQueueEntry.spec_document.isnot(None))
        .limit(1)
    )
    if not document_path:
        return False

    document = await session.scalar(
        select(SpecDocument)
        .where(SpecDocument.project_id == run.project_id)
        .where(SpecDocument.path == document_path)
        .limit(1)
    )
    if document is None:
        return False

    # "Has anything ever been written here" is a count of `content` events after the first, not the
    # presence of `content_digest` (F41). Both creation paths — `api/v1/spec.py` `create_document`
    # and the agent's own `create_spec_document` in `api/v1/agent_actions.py` — call
    # `spec_service.save_document` with a scaffold payload immediately after the row exists, and
    # that scaffold write sets the digest. So `content_digest` is populated from the document's
    # first microsecond and never absent: measured on the live database, 50 documents, 0 without
    # one. Gating on it made this whole check unreachable.
    #
    # The original subject proves it. `spec/changes/teal-manticore/spec.html` — the document the
    # author was given and never wrote — records `created` and `content` at the same timestamp,
    # `2026-08-25 08:15:40.650773`, with `{"requirements": []}`. The check written to catch that
    # turn would have returned False on that turn.
    #
    # The scaffold contributes exactly one `content` event, so a second one is the first time
    # anybody wrote anything. That is still structured state and still never reads the agent's
    # prose, which is the property that matters here.
    writes = await session.scalar(
        select(func.count())
        .select_from(SpecDocumentEvent)
        .where(SpecDocumentEvent.document_id == document.id)
        .where(SpecDocumentEvent.kind == "content")
    )
    if (writes or 0) > 1:
        return False

    # Any question, not only a blocking one. `ask_user(blocking=False)` is the agent leaving a note
    # and carrying on, which is still the agent having said something the operator will see — and
    # this check is about silence, not about whether the run waited.
    asked = await session.scalar(
        select(Question.id).where(Question.created_by_run_id == run.id).limit(1)
    )
    if asked:
        return False

    await persist_event(
        session,
        run.project_id,
        "turn_produced_nothing",
        {
            "run_id": run.id,
            "agent": run.agent,
            "spec_document": document_path,
            "document_phase": document.phase,
            "run_exit_status": run.status,
        },
        agent=run.agent,
        severity="warn",
    )
    await session.commit()
    logger.info(
        "run %s ended without writing %s and without asking anything", run.id, document_path
    )
    return True


async def evaluate_run_end(run_id: str, *, input_returned: bool = False) -> Optional[str]:
    """The run boundary check. Returns the divergence id when one was recorded.

    Exit status is not a condition: a run that crashed, failed or was killed is still a run that
    ended holding a task nobody moved, and the record names the exit status so a crash reads
    differently from a completed run that forgot.

    `input_returned` is a condition, and it is the one qualification the naive rule needs.
    `return_run_entries` puts a dead run's delivered input back on the queue, so the work is about
    to be handed to a new run that will bind to the same task. Nothing has been dropped, and
    treating it as divergence would both misdescribe it and, under `retry`, spawn a second run
    racing the redelivery. A directly-triggered run has no queued input to return, so it is checked
    normally.

    Opens its own session: this runs after the run row is already committed, and must not be able
    to strand a finished run.
    """
    if input_returned:
        return None
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return None
        if not run.task_id:
            # No task to have neglected — but a turn can be given a deliverable that is not a task,
            # and end having produced nothing (F38). Same boundary, same state-only reasoning, and
            # it returns None either way: this is a note for the operator, not a divergence, so
            # none of the policy machinery below applies to it.
            await note_turn_that_produced_nothing(session, run)
            return None
        if await run_advanced_its_task(session, run):
            return None

        task = await session.get(Task, run.task_id)
        if task is None:
            # The task was deleted while the run held it. There is nothing to have neglected and
            # nothing to route the work to.
            return None

        # An agent that stopped to ask is not an agent that dropped the work. Park the task on the
        # question instead, and say so on the board — this is the case that made the whole
        # `blocked` status necessary: before it, the run ended, the task had not moved, a
        # divergence was recorded, and under `retry` the agent was started again while still
        # waiting on the same unanswered question.
        question = await unanswered_blocking_question(session, run)
        if question is not None and await block_task_for_question(session, run, task, question):
            await session.commit()
            await _announce_block(session, run, task, question)
            return None

        # Already parked, by this run's earlier turn or by the operator. Excluded on the task's
        # *status at the boundary*, not on which run parked it (design D5) — which is what makes a
        # multi-turn blocked task safe now that every turn of a bound conversation is checked.
        if task.status == STATUS_BLOCKED:
            return None

        # One owned answer to "was this a live flow's own work turn" (design D4), read below by
        # both the `retry` suppression (D7) and the severity derivation (D6) — never re-derived at
        # either site, which is the exact defect `one-answer-to-what-is-happening` exists to end.
        flow_work_turn = await is_live_flow_work_turn(session, run)

        # Which régime governs (design D3). A review answers to the reviewer resolution; everything
        # else answers to the task's `divergence_policy`. Split here, at the one place both arrive,
        # rather than inside `_apply_policy` — a review must not *enter* the policy at all, or the
        # column recording which policy applied would name one that did not.
        #
        # Reviews reached this boundary for the first time in this change. Before D1 every one of
        # them was unbound and returned above on `if not run.task_id`.
        reason: Optional[str] = None
        if await review_task_for_run(session, run) is not None:
            policy = POLICY_REVIEW
            outcome, response_agent, previous_assignee, reason = await _answer_failed_review(
                session, run, task
            )
        else:
            policy = task.divergence_policy or DEFAULT_POLICY
            if policy == POLICY_RETRY and flow_work_turn:
                # Design D7: the flow is going to fire this task again on its own next tick, so
                # `retry` starting a second run here would race it. Recorded as its own régime
                # rather than as `policy_applied='retry'` beside an outcome nothing retried — the
                # one-word-two-meanings defect `POLICY_REVIEW` was kept out of `POLICIES` to avoid,
                # now hit a second way.
                policy = POLICY_FLOW
                outcome, response_agent, previous_assignee = OUTCOME_SURFACED, None, None
            else:
                outcome, response_agent, previous_assignee = await _apply_policy(session, run, task)

        divergence = RunDivergence(
            id=f"div-{short_id()}",
            project_id=run.project_id,
            run_id=run.id,
            agent=run.agent,
            task_id=task.id,
            task_status_at_end=task.status,
            run_exit_status=run.status,
            policy_applied=policy,
            outcome=outcome,
            previous_assignee=previous_assignee,
        )
        session.add(divergence)
        await session.commit()

        payload = {
            "divergence_id": divergence.id,
            "run_id": run.id,
            "agent": run.agent,
            "task_id": task.id,
            "task_status": task.status,
            "run_exit_status": run.status,
            "policy": policy,
            "outcome": outcome,
            "response_agent": response_agent,
        }
        if policy == POLICY_REVIEW:
            # What the operator needs in order to act, and what they cannot work out from the rest
            # of the payload. `was_review` because "agent X did not move task Y" reads as neglected
            # work when it was a verdict that never came, and `reason` because a surfaced review is
            # the branch where nothing else happens — a declared reviewer they must re-point, or a
            # roster with nobody left. Absent on the restaffed branch: `response_agent` says it.
            payload["was_review"] = True
            if reason:
                payload["reason"] = reason
        # Derived, not hardcoded (design D6). `warn` is still right for everything this comment
        # used to describe in full — the work is not lost and nothing is broken, but it is the
        # operator's attention this needs. `info` is for the one case that comment predates: a
        # live flow's own work turn that ended cleanly, on a task still held by the same agent —
        # long work spanning several turns, not a drop. Checked against the *post-policy* state of
        # the task deliberately: an escalation just moved `task.assignee` off `run.agent`, and a
        # divergence that reassigned the work is not the quiet case even when a flow started it.
        severity = (
            "info"
            if flow_work_turn and task.assignee == run.agent and run.status == "completed"
            else "warn"
        )
        await persist_event(
            session,
            run.project_id,
            "run_diverged",
            payload,
            agent=run.agent,
            severity=severity,
        )
        await sse_manager.broadcast(run.project_id, "run_diverged", payload)

        if response_agent is not None:
            from .turn_scheduler import schedule_agent

            await schedule_agent(run.project_id, response_agent)

        return divergence.id
