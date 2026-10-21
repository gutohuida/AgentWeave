"""F819 -- a loop whose agent cannot run says so instead of briefing it again.

The Hub gives up on an entry after `DELIVERY_ATTEMPT_LIMIT` failed runs and withdraws it. The loop's
task stayed `in_progress` with that agent and nothing on the loop said why, so the card read
"Active" and every Run briefed the same broken agent for three more failures.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Run
from hub.scheduler import DECISION_STALLED

from .test_a_held_agent_is_busy import _fire
from .test_a_review_nobody_is_doing import _roster
from .test_flow_width import _decide, _flow, _task

pytestmark = pytest.mark.asyncio

ERROR = "The 'gpt-5.6-sol' model is not supported when using Codex with a ChatGPT account."
_SEQ = 20_000


async def _abandoned(agent, task_id, *, tag, run_error=ERROR, run_status="failed"):
    """An entry the Hub withdrew after its delivery failed three times, as `schedule_agent` leaves it."""
    global _SEQ
    _SEQ += 1
    async with async_session_factory() as db:
        db.add(
            Conversation(id=f"conv-ab-{tag}", project_id="proj-test", agent=agent, lifecycle="open")
        )
        await db.flush()
        db.add(
            Run(
                id=f"run-ab-{tag}",
                project_id="proj-test",
                agent=agent,
                status=run_status,
                exit_code=1,
                error=run_error,
                task_id=task_id,
                turn_depth=0,
            )
        )
        db.add(
            InboundQueueEntry(
                id=f"iq-ab-{tag}",
                project_id="proj-test",
                agent=agent,
                origin_type="job",
                conversation_id=f"conv-ab-{tag}",
                sequence=_SEQ,
                content="work",
                hop_depth=0,
                state="withdrawn",
                task_id=task_id,
                delivery_attempts=3,
                delivered_in_run_id=f"run-ab-{tag}",
                abandoned_reason="delivery failed 3 times; the Hub stopped retrying",
            )
        )
        await db.commit()


async def _job_entries(agent):
    async with async_session_factory() as db:
        rows = await db.execute(
            select(InboundQueueEntry).where(
                InboundQueueEntry.agent == agent, InboundQueueEntry.origin_type == "job"
            )
        )
        return list(rows.scalars().all())


async def test_a_loop_names_the_agent_whose_delivery_was_abandoned(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "broke")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="f819", agent="broke")
        task = await _task(db, loop, "f819", status="in_progress", assignee="broke")
    await _abandoned("broke", task.id, tag="f819")

    decision = await _decide(job.id, loop.id, agent="broke")

    assert decision.kind == DECISION_STALLED
    assert decision.stall_reason is not None
    assert "broke" in decision.stall_reason and task.id in decision.stall_reason
    assert "not supported when using Codex" in decision.stall_reason

    await _fire(job.id, times=2)
    assert len(await _job_entries("broke")) == 1  # only the abandoned one


async def test_a_newer_turn_on_the_task_ends_the_standing_abandonment(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "mends")
    async with async_session_factory() as db:
        job, loop = await _flow(db, suffix="f819b", agent="mends")
        task = await _task(db, loop, "f819b", status="in_progress", assignee="mends")
    await _abandoned("mends", task.id, tag="f819b")
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-ab-later",
                project_id="proj-test",
                agent="mends",
                status="completed",
                exit_code=0,
                task_id=task.id,
                turn_depth=0,
            )
        )
        await db.commit()

    decision = await _decide(job.id, loop.id, agent="mends")

    assert not (decision.stall_reason or "").count("stopped retrying")
    assert "could not start" not in (decision.stall_reason or "")
