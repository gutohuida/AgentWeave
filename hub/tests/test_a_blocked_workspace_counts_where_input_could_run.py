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
from hub.task_workspace import AGENT_SCHEME, TASK_SCHEME
from hub.turn_scheduler import other_input_would_have_run_elsewhere, schedule_agent

from .review_evidence import record_review_evidence

TRIGGER = "hub.api.v1.agent_trigger.trigger_agent_directly"


def _blocked_agent_workspace(agent: str) -> TriggerAgentError:
    """The agent arm of `agent_trigger`'s workspace `except`: flagged, and flagged only this.

    Built per agent rather than shared, because the sentence names the agent and a reader comparing
    two tests should be able to see that the *only* difference between them is the queue.

    The sentence stops after the diagnosis. The real one is longer — phase 4 appended a remedy
    clause naming the directory to remove — and that is deliberate here rather than stale (checked
    by task 5.1): no assertion in this file reads the text, and each remedy is asserted against the
    obstruction it was written for in `test_a_blocked_workspace_refusal_states_its_remedy.py`. What
    the scheduler reads is the flag.
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
#: Truncated after the diagnosis for the same reason as the agent arm above.
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

    Each of the three takes one **optional** trailing element, and all three exist only for the
    helper-level half below: a conversation's `lifecycle`, a task's `workspace_scheme`, and a dict
    of further `new_entry` keywords for an entry (`review_task_id`, `hop_depth`). They default to
    the shapes a scheduler tick produces, so every scheduler-level test above reads unchanged.
    """
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 6
        for task in tasks:
            task_id, status = task[0], task[1]
            scheme = task[2] if len(task) > 2 else TASK_SCHEME
            db.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title=task_id,
                    status=status,
                    workspace_scheme=scheme,
                )
            )
        for conversation in conversations:
            conversation_id, task_id = conversation[0], conversation[1]
            db.add(
                Conversation(
                    id=conversation_id,
                    project_id="proj-test",
                    agent=agent,
                    lifecycle=conversation[2] if len(conversation) > 2 else "open",
                    task_id=task_id,
                )
            )
        for index, entry in enumerate(entries):
            conversation_id, task_id = entry[0], entry[1]
            extra = dict(entry[2]) if len(entry) > 2 else {}
            db.add(
                new_entry(
                    project_id="proj-test",
                    agent=agent,
                    origin_type="operator",
                    content=f"message {index}",
                    hop_depth=extra.pop("hop_depth", 0),
                    conversation_id=conversation_id,
                    task_id=task_id,
                    **extra,
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


# ---------------------------------------------------------------------------------------------
# The helper, asked directly.
#
# Everything above goes through `schedule_agent`, because it is about the *condition*: which
# refusals reach the counter, and what the operator's queue looks like after three schedules.
# Everything below calls `other_input_would_have_run_elsewhere` itself, because it is about the
# *scope rule*, and the shapes that rule turns on cannot be produced by a scheduler tick:
#
#   - a **grandfathered** task carries `workspace_scheme` `agent`, which migration `0095` stamped
#     once and no runtime path writes, so a drive against a fresh project cannot make one;
#   - a task id `validate_task_id` refuses cannot be minted by the product that would have to
#     create the row;
#   - an entry left out of its own conversation's batch needs `cap` or a kind split to arrange,
#     which is a fact about batching rather than about this rule.
#
# Building a whole tick around each of those would be testing the fixture. The helper is public
# (design D8) precisely so these can be one call and one `assert`.
# ---------------------------------------------------------------------------------------------


async def _would_have_run_elsewhere(agent, *, hop_budget=6):
    """Ask the helper about *agent*'s whole queue, with the head as the refused batch.

    `selected` is the head alone, which is the smallest honest stand-in for "the turn that was just
    refused": every other entry is therefore outside the batch and is the thing under test. The
    controlling conversation is the head's own, as it is in `schedule_agent`.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(InboundQueueEntry)
            .where(InboundQueueEntry.agent == agent)
            .order_by(InboundQueueEntry.sequence)
        )
        entries = list(result.scalars())
        head = entries[0]
        return await other_input_would_have_run_elsewhere(
            db,
            project_id="proj-test",
            agent=agent,
            entries=entries,
            selected=[head],
            controlling_conversation_id=head.conversation_id,
            hop_budget=hop_budget,
        )


@pytest.mark.asyncio
async def test_another_conversations_live_task_scheme_task_counts(app, auth_headers):
    """The positive control every negative below is a one-column edit away from.

    Another conversation, an entry naming a task that exists, is not decided, and takes its own
    checkout. That turn would have run in `.agentweave/tasks/<task>` while the agent's own
    directory stayed obstructed, so the head is genuinely in its way and the attempt counts.

    Without this, a helper that returned `False` unconditionally would pass every negative in this
    half — which is exactly what the `return False` mutation in iteration 5 measured at the
    scheduler level, and this is its helper-level twin.
    """
    agent = "f188-h-live"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hl-a", None), ("conv-f188-hl-b", None)],
        entries=[("conv-f188-hl-a", None), ("conv-f188-hl-b", "task-aabb10")],
        tasks=[("task-aabb10", "in_progress")],
    )

    assert await _would_have_run_elsewhere(agent) is True


@pytest.mark.asyncio
async def test_a_grandfathered_task_does_not_count(app, auth_headers):
    """3.7: a grandfathered task runs in the blocked directory, so nothing was starving.

    One column apart from the control above: the task's scheme is `AGENT_SCHEME`, set directly in
    the fixture because migration `0095` is the only writer and no runtime path would produce one.
    Such a task's turns take the shared per-agent checkout — the very directory the refusal is
    about — so counting on its behalf destroys the operator's message at the third schedule and
    releases a turn that will be refused identically (F188).

    **This test and `test_a_binding_inherited_from_the_thread_spends_the_heads_attempts` pin the
    rule from opposite sides, and neither one alone holds it.** The inherited-binding test rejects
    a rule too narrow (`entry.task_id` only, missing the thread's binding); this one rejects a rule
    too wide (any entry that names a task, R1's reduction, which counts here and is wrong). A rule
    that resolves the row but skips the scheme is wrong here alone: iteration 4 measured that
    deleting the scheme line from `task_workspace.takes_own_checkout` fails this test and nothing
    else in the suite.

    The grandfathered set is also not a corner: it is every task that had work on it when per-task
    isolation shipped, which is every project except the fresh ones a test or a drive creates.
    """
    agent = "f188-h-grand"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hg-a", None), ("conv-f188-hg-b", None)],
        entries=[("conv-f188-hg-a", None), ("conv-f188-hg-b", "task-aabb11")],
        tasks=[("task-aabb11", "in_progress", AGENT_SCHEME)],
    )

    assert await _would_have_run_elsewhere(agent) is False


@pytest.mark.asyncio
async def test_a_task_id_this_product_could_not_have_minted_does_not_count(app, auth_headers):
    """3.8, first shape: `validate_task_id` refuses the id, so `resolve_turn_workspace` would too.

    A row whose id is `../escape` arrived some other way, and `worktrees` will not provision a
    checkout for it — `task_workspace` returns `UNBOUND` and the turn runs in the per-agent
    directory. Same disposition as a grandfathered task, reached one layer further down: the entry
    is about a task, and is still about a turn that would have wanted the blocked workspace.

    The other conversation is bound to nothing, and that is load-bearing rather than tidy: give it
    a live task and the entry counts by inheritance no matter what its own id says, which is what
    `test_a_decided_task_in_a_thread_that_carries_a_live_one_counts` asserts on purpose.
    """
    agent = "f188-h-badid"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hb-a", None), ("conv-f188-hb-b", None)],
        entries=[("conv-f188-hb-a", None), ("conv-f188-hb-b", "../escape")],
        tasks=[("../escape", "in_progress")],
    )

    assert await _would_have_run_elsewhere(agent) is False


@pytest.mark.asyncio
async def test_a_task_id_with_no_row_does_not_count(app, auth_headers):
    """3.8, second shape: the named task has been deleted, so the binding drops.

    `run_task_binding.resolve_bound_task` cannot bind to a row that is not there. With nothing for
    the thread to fall through to, the entry's turn is unbound and runs in the blocked per-agent
    checkout, so it was never waiting on a workspace of its own.

    **Binding the other conversation to nothing is the whole point of this fixture**, not
    housekeeping: the fall-through is real, and an identical fixture whose conversation carries a
    live task counts (`test_a_decided_task_in_a_thread_that_carries_a_live_one_counts`). Filling
    that binding in would make this test pass for the wrong reason and stop distinguishing the two.
    """
    agent = "f188-h-norow"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hn-a", None), ("conv-f188-hn-b", None)],
        entries=[("conv-f188-hn-a", None), ("conv-f188-hn-b", "task-ffff98")],
    )

    assert await _would_have_run_elsewhere(agent) is False


@pytest.mark.asyncio
async def test_a_decided_task_does_not_count(app, auth_headers):
    """3.8, third shape: the task is in `TERMINAL_FOR_BINDING`, so it takes no new work.

    `decided_task_refusal` is the same band `release_bindings_to` releases at (design D7): work the
    operator has approved or rejected is finished being worked on, and `resolve_bound_task` drops
    the binding rather than attributing another turn to it. A dropped binding is an unbound turn,
    and an unbound turn wants the directory that is blocked.

    The other conversation is again bound to nothing, for the reason the previous docstring gives —
    and here the contrast is not hypothetical, because the next test is this fixture with the
    thread's binding filled in and the opposite expectation.
    """
    agent = "f188-h-decided"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hd-a", None), ("conv-f188-hd-b", None)],
        entries=[("conv-f188-hd-a", None), ("conv-f188-hd-b", "task-aabb12")],
        tasks=[("task-aabb12", "approved")],
    )

    assert await _would_have_run_elsewhere(agent) is False


@pytest.mark.asyncio
async def test_a_decided_task_in_a_thread_that_carries_a_live_one_counts(app, auth_headers):
    """3.8a: the inverse, and the reason the rule is an `or` rather than a list of exclusions.

    The entry names an approved task, exactly as the test above does. The difference is one column:
    its conversation is itself bound to a live task-scheme task. `resolve_bound_task` does not stop
    when it drops the named task — it falls through to `binding_for_conversation` — so this turn
    binds to the thread's task and takes that task's checkout. It really could have run.

    **This is R3's correction, stated as a measurement.** R2 listed deleted and decided tasks
    alongside grandfathering as unconditional non-counters; they are not. Grandfathering and an
    unmintable id are decided *after* the binding has been chosen and no fall-through can rescue
    them; a deleted or decided task is only a dropped binding, and the thread may supply another.
    A helper that excluded decided tasks outright would pass every other test in this half and fail
    here.
    """
    agent = "f188-h-inherit"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hi-a", None), ("conv-f188-hi-b", "task-aabb14")],
        entries=[("conv-f188-hi-a", None), ("conv-f188-hi-b", "task-aabb13")],
        tasks=[("task-aabb13", "approved"), ("task-aabb14", "in_progress")],
    )

    assert await _would_have_run_elsewhere(agent) is True


@pytest.mark.asyncio
async def test_a_review_whose_task_has_no_commit_does_not_count(app, auth_headers):
    """3.8b: design D3b — a review with nothing to check out was never going to start.

    A review turn's checkout is `.agentweave/reviews/<reviewer>`, a different directory from the
    one this refusal is about, so on scope alone it would count. But `prepare_review_turn` refuses
    a review whose task carries no evidence naming a commit, before any checkout is reached
    (`test_a_review_needs_something_to_review.py` is that refusal). Counting on its behalf would
    destroy the head of the queue to release a turn that is itself about to be refused — the same
    trade F188 is about, one feature over.

    The task exists and is `completed`; only the evidence is missing, which is precisely the state
    `commit_for_task_review` reports as unresolved.
    """
    agent = "f188-h-norev"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hr-a", None), ("conv-f188-hr-b", None)],
        entries=[
            ("conv-f188-hr-a", None),
            ("conv-f188-hr-b", None, {"review_task_id": "task-aabb15"}),
        ],
        tasks=[("task-aabb15", "completed")],
    )

    assert await _would_have_run_elsewhere(agent) is False


@pytest.mark.asyncio
async def test_a_review_whose_task_names_a_commit_counts(app, auth_headers):
    """3.8b's sibling: the same entry, with something to review, counts.

    One evidence row with a footprint naming a commit is the whole difference. Now
    `prepare_review_turn` would provision `.agentweave/reviews/<reviewer>` and the turn would have
    run, untouched by the obstruction on the agent's own worktree — so the head is in its way and
    the attempt counts, as it did before this change.

    The pair is what keeps the D3b check honest: without this one, a helper that never counted a
    review entry at all would pass its partner and hold input the requirement says to count.
    """
    agent = "f188-h-rev"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hv-a", None), ("conv-f188-hv-b", None)],
        entries=[
            ("conv-f188-hv-a", None),
            ("conv-f188-hv-b", None, {"review_task_id": "task-aabb16"}),
        ],
        tasks=[("task-aabb16", "completed")],
    )
    async with async_session_factory() as db:
        await record_review_evidence(db, "task-aabb16", suffix="f188")

    assert await _would_have_run_elsewhere(agent) is True


@pytest.mark.asyncio
async def test_an_entry_over_the_hop_budget_does_not_count(app, auth_headers):
    """3.9, first shape: an entry the scheduler would not admit is not evidence of starvation.

    `can_start` and `selected` both refuse an entry deeper than the project's hop budget (design
    D1, F5), so this one is not waiting on the head — it is waiting on a budget change that giving
    up on the head does not provide. Its task is live and task-scheme, so the scope rule alone
    would count it; the eligibility filter is what does not.
    """
    agent = "f188-h-deep"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hp-a", None), ("conv-f188-hp-b", None)],
        entries=[
            ("conv-f188-hp-a", None),
            ("conv-f188-hp-b", "task-aabb17", {"hop_depth": 7}),
        ],
        tasks=[("task-aabb17", "in_progress")],
    )

    assert await _would_have_run_elsewhere(agent, hop_budget=6) is False


@pytest.mark.asyncio
async def test_an_entry_in_a_conversation_that_is_not_open_does_not_count(app, auth_headers):
    """3.9, second shape: an archived thread's entry could not have run either.

    `schedule_agent` refuses a turn whose conversation is not `open`, so this entry is not blocked
    by the head; it is blocked by its own thread. The helper expresses that as a `WHERE` rather
    than as a filter over what came back, so the conversation simply does not appear and its entry
    falls out with it — which is also why the task below never needs to be looked at.
    """
    agent = "f188-h-closed"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hc-a", None), ("conv-f188-hc-b", None, "archived")],
        entries=[("conv-f188-hc-a", None), ("conv-f188-hc-b", "task-aabb18")],
        tasks=[("task-aabb18", "in_progress")],
    )

    assert await _would_have_run_elsewhere(agent) is False


@pytest.mark.asyncio
async def test_an_inherited_binding_in_the_controlling_conversation_is_not_consulted(
    app, auth_headers
):
    """The controlling conversation's own binding is already known not to have taken a checkout.

    Both entries are in the conversation that was just refused, and that conversation carries a
    live task-scheme task. Reaching an agent-workspace refusal proves the whole resolution for this
    batch came back unbound — including that inherited binding — so consulting it again for a
    sibling entry would count on the strength of a fact the refusal has already disproved, and
    destroy the head to release a turn in the same blocked directory.

    A scheduler tick reaches this shape only when the batch is truncated by `cap` or split by kind,
    which is why it is constructed here directly rather than driven. Iteration 4 measured that
    replacing the guard in `_tasks_this_entry_is_about` with `if True` fails this test and nothing
    else in the suite.
    """
    agent = "f188-h-ctrl"
    await _register(app, auth_headers, agent)
    await _seed(
        agent,
        conversations=[("conv-f188-hx-a", "task-aabb19")],
        entries=[("conv-f188-hx-a", None), ("conv-f188-hx-a", None)],
        tasks=[("task-aabb19", "in_progress")],
    )

    assert await _would_have_run_elsewhere(agent) is False
