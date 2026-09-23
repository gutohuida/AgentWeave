"""F328 — the operator's withdrawal and the Hub's give-up race for one queued entry, and both won.

Every writer that took an entry out of `queued` read the row, checked its state, and then wrote it
by primary key. So an operator's `DELETE` that waited on a refused review dispatch's write lock was
answered `200`, while the row carried *"delivery failed 3 times …; the Hub stopped retrying"* and a
`queue_entry_abandoned` event announced it (kept reproduction:
`testbed/scratch/opusf319/test_zz_opusf319.py::test_o2…`, delay 0.3). The repair is a single rule:
the check is the `UPDATE`'s own condition, on both sides, so whoever writes first wins and the other
matches no row.

Each side has a deterministic test, and the third drives the real interleaving through the route.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from hub.api.v1.agent_trigger import TriggerAgentError
from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run, Task
from hub.inbound_queue import DELIVERY_ATTEMPT_LIMIT, deliver_entries_with_run, withdraw_entry
from hub.turn_scheduler import schedule_agent

from .test_a_refused_review_leaves_nothing_behind import (
    TRIGGER,
    _conversation,
    _entry,
    _events,
    _refused,
    _register,
    _row,
    _runs,
)

pytestmark = pytest.mark.asyncio

HELPER = "hub.turn_scheduler.other_input_would_have_run_elsewhere"


async def test_input_withdrawn_after_the_reread_is_neither_counted_nor_announced(app, auth_headers):
    """The scheduler's side. The withdrawal commits after the refusal branch has re-read the entry
    as queued and before it counts it — the window a withdrawal waiting on the dispatch's write lock
    lands in. `other_input_would_have_run_elsewhere` is the seam: it is awaited exactly there, for a
    refusal about the agent's own workspace, and returning `True` sends the branch on to count.

    Mutation: the counting `UPDATE`'s `state == "queued"` condition dropped. This must fail, with
    the entry at `DELIVERY_ATTEMPT_LIMIT`, the Hub's reason and one `queue_entry_abandoned`.
    """
    agent = "wg-scheduler"
    await _register(app, auth_headers, agent)
    entry_id = await _entry(
        agent, await _conversation(agent), attempts=DELIVERY_ATTEMPT_LIMIT - 1, content="e"
    )
    withdrew: list = []

    async def withdraw_in_the_window(*args, **kwargs):
        async with async_session_factory() as other:
            withdrew.append(await withdraw_entry(other, "proj-test", entry_id) is not None)
        return True

    refusal = TriggerAgentError(409, "workspace obstructed", agent_workspace_unavailable=True)
    with (
        patch(TRIGGER, AsyncMock(side_effect=refusal)),
        patch(HELPER, AsyncMock(side_effect=withdraw_in_the_window)),
    ):
        await schedule_agent("proj-test", agent)

    assert withdrew == [True], "the seam was not reached, so this test measured nothing"
    row = await _row(entry_id)
    assert (row.state, row.delivery_attempts) == ("withdrawn", DELIVERY_ATTEMPT_LIMIT - 1)
    assert not row.abandoned_reason
    assert await _events("queue_entry_abandoned", agent=agent) == 0


async def test_a_withdrawal_that_loses_to_a_give_up_is_refused(app, auth_headers):
    """The withdrawal's side. The session holding the operator's copy read the entry as queued
    before the Hub gave up on it — which is what a `DELETE` waiting on the write lock has done. The
    identity-mapped copy is never expired (`expire_on_commit=False`), so a check made of it passes.

    Mutation: `_withdraw_if_queued`'s `state == "queued"` condition dropped. This must fail: the
    withdrawal reports success over the Hub's give-up and restamps `withdrawn_at`.
    """
    agent = "wg-withdrawal"
    await _register(app, auth_headers, agent)
    entry_id = await _entry(
        agent, await _conversation(agent), attempts=DELIVERY_ATTEMPT_LIMIT - 1, content="e"
    )
    async with async_session_factory() as operators_session:
        copy = await operators_session.scalar(
            select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id)
        )
        assert copy.state == "queued"
        with patch(TRIGGER, AsyncMock(side_effect=_refused((entry_id,)))):
            await schedule_agent("proj-test", agent)
        given_up = await _row(entry_id)
        assert given_up.abandoned_reason.startswith("delivery failed")
        withdrawn = await withdraw_entry(operators_session, "proj-test", entry_id)

    assert withdrawn is None
    row = await _row(entry_id)
    assert row.abandoned_reason == given_up.abandoned_reason
    assert row.withdrawn_at == given_up.withdrawn_at
    assert await _events("queue_entry_abandoned", agent=agent) == 1


async def test_a_delete_that_waits_on_a_refused_dispatch_agrees_with_the_record(app, auth_headers):
    """The interleaving F328 was measured in, through the real route. The dispatch flushes a write
    before it is refused — as a review dispatch does when it stages the reviewer — so it holds the
    database's write lock, and the operator's `DELETE`, issued meanwhile, waits on it. Which of the
    two then writes first is the database's business, and either order is correct. What must hold
    is that the answer and the record name the same winner:

    - `200`: the operator withdrew it — not counted, no Hub reason, nothing announced as abandoned;
    - `409`: the Hub gave up first — counted to the limit, its reason, one `queue_entry_abandoned`.

    Before the repair the `DELETE` was answered `200` and the record said the Hub gave up.
    """
    agent = "wg-route"
    await _register(app, auth_headers, agent)
    entry_id = await _entry(
        agent, await _conversation(agent), attempts=DELIVERY_ATTEMPT_LIMIT - 1, content="e"
    )
    seen: dict = {}

    async def hold_the_lock_then_refuse(**kw):
        session = kw["session"]
        session.add(
            Task(id="task-wg-staged", project_id="proj-test", title="staged", status="pending")
        )
        await session.flush()
        seen["delete"] = asyncio.create_task(
            app.delete(f"/api/v1/projects/proj-test/queue/entries/{entry_id}", headers=auth_headers)
        )
        await asyncio.sleep(0.3)
        # Recorded, not asserted: an `AssertionError` inside the product's call path is caught
        # nowhere useful and would read as the product's failure.
        seen["waited"] = not seen["delete"].done()
        raise _refused(tuple(kw["queue_entry_ids"]))

    with patch(TRIGGER, AsyncMock(side_effect=hold_the_lock_then_refuse)):
        await schedule_agent("proj-test", agent)
    response = await seen["delete"]

    assert seen["waited"], "the DELETE did not wait on the dispatch, so the race was not run"
    row = await _row(entry_id)
    abandoned = await _events("queue_entry_abandoned", agent=agent)
    withdrawn = await _events("queue_entry_withdrawn", agent=agent)
    assert row.state == "withdrawn"
    if response.status_code == 200:
        assert row.delivery_attempts == DELIVERY_ATTEMPT_LIMIT - 1
        assert not row.abandoned_reason
        assert (abandoned, withdrawn) == (0, 1)
    else:
        assert response.status_code == 409, response.text
        assert row.delivery_attempts == DELIVERY_ATTEMPT_LIMIT
        assert row.abandoned_reason.startswith("delivery failed")
        assert (abandoned, withdrawn) == (1, 0)


# --- F338: delivery is the third writer, and it follows the same rule -------------------------


async def test_a_withdrawal_that_lands_between_delivery_read_and_write_is_not_overwritten(app):
    """Delivery read the entry as queued, then wrote it `delivered` by primary key. A withdrawal
    committing in between -- the window a plain turn leaves open, since nothing ahead of the read
    writes -- was answered as a success and then overwritten, and the run started with input the
    operator was told they withdrew. The withdrawal is committed from inside that window here.

    Mutation: the claiming `UPDATE`'s `state == "queued"` condition dropped. This must fail, with
    the entry `delivered` and the run committed.
    """
    agent = "wg-deliver"
    conversation_id = await _conversation(agent)
    entry_id = await _entry(agent, conversation_id, content="withdraw me")
    withdrew: list = []

    async with async_session_factory() as delivering:
        real_execute = delivering.execute

        async def execute_then_withdraw(*args, **kwargs):
            result = await real_execute(*args, **kwargs)
            if not withdrew:  # right after delivery's read, before its write
                async with async_session_factory() as operator:
                    withdrew.append(
                        await withdraw_entry(operator, "proj-test", entry_id) is not None
                    )
            return result

        with patch.object(delivering, "execute", execute_then_withdraw):
            with pytest.raises(RuntimeError, match="queue changed before atomic delivery"):
                await deliver_entries_with_run(
                    delivering,
                    project_id="proj-test",
                    agent=agent,
                    entry_ids=[entry_id],
                    run=Run(
                        id="run-wg-deliver",
                        project_id="proj-test",
                        agent=agent,
                        conversation_id=conversation_id,
                        status="running",
                        turn_depth=0,
                    ),
                )

    assert withdrew == [True], "the operator's withdrawal was refused, so the window was missed"
    row = await _row(entry_id)
    assert (row.state, row.delivered_in_run_id) == ("withdrawn", None)
    assert "run-wg-deliver" not in await _runs()
