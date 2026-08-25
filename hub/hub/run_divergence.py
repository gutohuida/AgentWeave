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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.engine import async_session_factory
from .db.models import Agent, InboundQueueEntry, Question, Run, RunDivergence, SpecDocument, Task
from .inbound_queue import new_entry
from .run_task_binding import (
    DEFAULT_POLICY,
    OUTCOME_ESCALATED,
    OUTCOME_RETRIED,
    OUTCOME_SURFACED,
    POLICY_ESCALATE,
    POLICY_RETRY,
    block_task_for_question,
    may_retry,
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
    return len(open_rows)


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
) -> str:
    """Put the response in the agent's queue rather than spawning it here.

    Through the queue so hop budget, delivery caps and ordering all apply unchanged (task 5.7), and
    so a response arriving while the agent is busy waits instead of failing — a divergence answered
    with "that agent is already running" would answer nothing.

    `hop_depth=0`: the Hub is the origin, not a forwarding agent. The retry bound (D8) is what stops
    a chain here, not the hop budget.
    """
    entry = new_entry(
        project_id=project_id,
        agent=agent,
        origin_type="divergence",
        content=prompt,
        hop_depth=0,
        task_id=task_id,
        divergence_source_run_id=source_run_id,
    )
    session.add(entry)
    return entry.id


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
    three questions with recorded answers: was this turn given a document, does that document have
    content, and did this run write a question.

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
    # No row, or a row with content, both mean this is not the F38 shape. `content_digest` is the
    # digest of what was last submitted, so its absence is "nothing has ever been written here" —
    # the state the author's document was left in.
    if document is None or document.content_digest:
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
        severity="warning",
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

        policy = task.divergence_policy or DEFAULT_POLICY
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
        # `warn`, not `error`: the work is not lost and nothing is broken. It is the operator's
        # attention this needs, which is what `warn` means in the operator's view.
        await persist_event(
            session,
            run.project_id,
            "run_diverged",
            payload,
            agent=run.agent,
            severity="warn",
        )
        await sse_manager.broadcast(run.project_id, "run_diverged", payload)

        if response_agent is not None:
            from .turn_scheduler import schedule_agent

            await schedule_agent(run.project_id, response_agent)

        return divergence.id
