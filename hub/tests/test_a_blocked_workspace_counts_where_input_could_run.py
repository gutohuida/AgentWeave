"""A blocked *agent* workspace counts a delivery attempt only where something else could have run.

`agent-conversation-workspace` is deliberately narrower than "hold it always": a refusal about the
agent's own worktree counts *"where other queued input could have run"*. The whole change turns on
that clause, because the two halves protect different things. Holding the head releases the
operator's message from a three-schedule death sentence for a fault they have not been told how to
repair (F188, F96). Counting it is what keeps a permanently-refused head from wedging every other
entry behind it (F56) — and after this change one entry can still be permanently refused while the
next one over would run perfectly well, in a checkout the obstruction does not touch.

So these are the scheduler-level tests for `schedule_agent`'s counting condition: the same loop of
`DELIVERY_ATTEMPT_LIMIT` schedules that `test_a_blocked_agent_workspace_holds_its_input.py` runs,
against queues that differ only in what is waiting elsewhere.

**These tests go through `schedule_agent`, not through the helper.** They are about the *condition*
— which refusals reach the counter at all, and what the operator's queue looks like afterwards.
`other_input_would_have_run_elsewhere`'s own answers on shapes a scheduler tick cannot produce (a
grandfathered task, an id `validate_task_id` refuses, a review with no commit) are asserted against
the helper directly, because building a whole tick around each of them would test the fixture.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub.api.v1.agent_trigger import TriggerAgentError
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Project, Task
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT, new_entry
from hub.turn_scheduler import schedule_agent

TRIGGER = "hub.api.v1.agent_trigger.trigger_agent_directly"


def _blocked_agent_workspace(agent: str) -> TriggerAgentError:
    """The agent arm of `agent_trigger`'s workspace `except`: flagged, and flagged only this.

    Built per agent rather than shared, because the sentence names the agent and a reader comparing
    two tests should be able to see that the *only* difference between them is the queue.
    """
    return TriggerAgentError(
        409,
        f"Could not prepare {agent}'s own workspace: refusing existing path "
        f"/repo/.agentweave/worktrees/{agent}: it is not the registered git worktree",
        agent_workspace_unavailable=True,
    )


#: The **task** arm of the same `except`, which carries no flags at all — phase 2 split them for
#: exactly this reason. A task's checkout is not the agent's, so other input really can run and the
#: head really is in the way (design D3a). Held as the control for the third test below.
BLOCKED_TASK_CHECKOUT = TriggerAgentError(
    409,
    "Could not prepare the checkout for task task-aabb01: refusing existing path "
    "/repo/.agentweave/tasks/task-aabb01: it is not the registered git worktree",
)


async def _register(app, auth_headers, agent):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {}}}},
        headers=auth_headers,
    )


async def _seed(agent, *, conversations, entries, tasks=()):
    """Build one agent's whole queue in a single commit.

    *conversations* is `(id, task_id)` — the second is the thread's own binding, the half of "about
    a task" that an entry does not carry. *entries* is `(conversation_id, task_id)` in the order
    they should be scheduled; the first is the head. *tasks* is `(id, status)`.
    """
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 6
        for task_id, status in tasks:
            db.add(Task(id=task_id, project_id="proj-test", title=task_id, status=status))
        for conversation_id, task_id in conversations:
            db.add(
                Conversation(
                    id=conversation_id,
                    project_id="proj-test",
                    agent=agent,
                    lifecycle="open",
                    task_id=task_id,
                )
            )
        for index, (conversation_id, task_id) in enumerate(entries):
            db.add(
                new_entry(
                    project_id="proj-test",
                    agent=agent,
                    origin_type="operator",
                    content=f"message {index}",
                    hop_depth=0,
                    conversation_id=conversation_id,
                    task_id=task_id,
                )
            )
        await db.commit()


async def _rows(agent):
    async with async_session_factory() as db:
        result = await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent)
            .order_by(InboundQueueEntry.sequence)
        )
        return [(row.state, row.delivery_attempts or 0) for row in result.scalars()]


async def _schedule_to_the_limit(agent, refusal):
    with patch(TRIGGER, AsyncMock(side_effect=refusal)):
        for _ in range(DELIVERY_ATTEMPT_LIMIT):
            await schedule_agent("proj-test", agent)


@pytest.mark.asyncio
async def test_a_second_unbound_conversation_does_not_make_the_head_expendable(app, auth_headers):
    """3.4, first scenario: every other entry is unbound, so nothing is released by giving up.

    Two conversations, two messages, neither about a task. Both turns would have run in
    `.agentweave/worktrees/<agent>` — the one directory that is obstructed — so destroying the head
    at the limit buys the second one nothing, and costs the operator the first.

    The second entry is what makes this test more than a restatement of the single-entry
    reproduction: a condition written as "hold whenever this agent has one queued entry" would pass
    that one and fail this.
    """
    agent = "f188-two-unbound"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-2u-a", None), ("conv-f188-2u-b", None)],
        entries=[("conv-f188-2u-a", None), ("conv-f188-2u-b", None)],
    )

    await _schedule_to_the_limit(agent, _blocked_agent_workspace(agent))

    assert await _rows(agent) == [("queued", 0), ("queued", 0)]


@pytest.mark.asyncio
async def test_a_task_bound_entry_waiting_elsewhere_spends_the_heads_attempts(app, auth_headers):
    """3.4, second scenario, **and it is the one that keeps this change inside its requirement.**

    `agent-conversation-workspace` says a blocked agent workspace counts an attempt *"where other
    queued input could have run"*. Here it could: the second conversation's entry names a live
    task-scheme task, so its turn takes `.agentweave/tasks/<task>` and is untouched by the
    obstruction on the agent's own directory. The head is genuinely in the way of it, F56's
    argument applies unchanged, and the head is given up on at the limit exactly as it was before
    this change.

    Without this test the change would read as "an agent-workspace refusal is held", which is a
    breach of the requirement rather than an implementation of it — and every other test in this
    file would still pass.
    """
    agent = "f188-task-elsewhere"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-te-a", None), ("conv-f188-te-b", None)],
        entries=[("conv-f188-te-a", None), ("conv-f188-te-b", "task-aabb01")],
        tasks=[("task-aabb01", "in_progress")],
    )

    await _schedule_to_the_limit(agent, _blocked_agent_workspace(agent))

    assert await _rows(agent) == [("withdrawn", DELIVERY_ATTEMPT_LIMIT), ("queued", 0)]


@pytest.mark.asyncio
async def test_a_blocked_task_checkout_still_counts_with_nothing_waiting(app, auth_headers):
    """3.4, third scenario: the new term is reached by the flag, not by the words.

    Identical queue to the first test — two unbound entries, nothing that could have run elsewhere
    — and the opposite outcome, because the refusal is the **task** arm of the same `except`. That
    arm carries no flag, so the condition's first two terms decide it and the third is never
    evaluated: a task's checkout is not the agent's, the agent's own worktree is fine, and other
    input really is being starved by this head (design D3a).

    The two refusals are one line apart in `agent_trigger.py` and were one sentence before phase 2
    split them. This is the test that fails if a later edit re-merges them.
    """
    agent = "f188-task-arm"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-ta-a", None), ("conv-f188-ta-b", None)],
        entries=[("conv-f188-ta-a", None), ("conv-f188-ta-b", None)],
    )

    await _schedule_to_the_limit(agent, BLOCKED_TASK_CHECKOUT)

    assert await _rows(agent) == [("withdrawn", DELIVERY_ATTEMPT_LIMIT), ("queued", 0)]


@pytest.mark.asyncio
async def test_a_binding_inherited_from_the_thread_spends_the_heads_attempts(app, auth_headers):
    """3.5: the other entry names no task, but the thread it is in does. It must count.

    `run_task_binding.resolve_bound_task` falls through to `binding_for_conversation` when the
    entry names nothing, so a plain follow-up message typed into a task-bound thread runs in that
    task's checkout. It could have run; the head is in its way.

    **This is the half a scope test built only on `entry.task_id` gets wrong, and nothing else in
    the suite would notice.** Such a test passes the three above and fails only here — which is why
    the helper's rule is an `or` over the entry's own task and its conversation's (design D3).
    """
    agent = "f188-inherited"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-in-a", None), ("conv-f188-in-b", "task-aabb02")],
        entries=[("conv-f188-in-a", None), ("conv-f188-in-b", None)],
        tasks=[("task-aabb02", "in_progress")],
    )

    await _schedule_to_the_limit(agent, _blocked_agent_workspace(agent))

    assert await _rows(agent) == [("withdrawn", DELIVERY_ATTEMPT_LIMIT), ("queued", 0)]


@pytest.mark.asyncio
async def test_an_entry_in_the_refused_batch_naming_a_vanished_task_does_not_count(
    app, auth_headers
):
    """3.6: an entry riding on the refused turn is not evidence that anything else could have run.

    Both entries are in the controlling conversation, so both were batched into the turn that was
    just refused, and the second one names a task that has no row. Reaching this refusal proves the
    *whole* resolution for that batch came back unbound — the named task, the thread's binding, the
    scheme, the id — and nothing about the next schedule changes any of those inputs, so the next
    tick reaches the same arm. Counting on the batch's own behalf would destroy the head to release
    a turn that is the head (design D3).

    The vanished task is the sharp case: an implementation that asked only "does some entry name a
    task" without resolving it would count here, and would pass every other test in this file.
    """
    agent = "f188-in-batch"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-ib", None)],
        entries=[("conv-f188-ib", None), ("conv-f188-ib", "task-ffff99")],
    )

    await _schedule_to_the_limit(agent, _blocked_agent_workspace(agent))

    assert await _rows(agent) == [("queued", 0), ("queued", 0)]
