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
from .db.models import Agent, Question, Run, RunDivergence, Task
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
        if run is None or not run.task_id:
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
