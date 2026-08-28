"""F108: a request the Hub will never honour is answered as refused, not as queued.

`POST /agent/trigger` answered `200 {"success": true, "status": "queued"}` to a request that could
never succeed, with the refusal's own sentence delivered in a field named `waiting_reason`. These
tests pin the four halves of the fix and, as much as the rest, the **population it must not touch**:
a refusal about the *environment* — no runner bound, the CLI missing from PATH — still queues and
still states its reason, because performing the repair is what delivers it (F96).

The classification is asked directly on `TriggerAgentError` (`request_level`) rather than derived
from `transient`, and it defaults to `False`, so a raise site keeps today's behaviour until somebody
decides otherwise. `test_unbound_agent_accumulates_queue_with_visible_reason`,
`test_runner_binding_redrain.py` and `test_runtime_diagnostics.py` are the tests that say what
"today's behaviour" is for the unmarked population; they are expected to pass unchanged, and this
file adds `test_an_environment_level_refusal_leaves_the_entry_queued` beside them for the same
reason at the scheduler's own level.
"""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.api.v1.agent_trigger import TriggerAgentError
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Project
from hub.inbound_queue import new_entry
from hub.turn_scheduler import ScheduleResult, schedule_agent

TRIGGER = "hub.api.v1.agent_trigger.trigger_agent_directly"


async def _register(app, auth_headers, bind_runner, agent):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(agent, cli="claude")


async def _seed(agent, conversation_id, entries):
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 6
        db.add(
            Conversation(
                id=conversation_id,
                project_id="proj-test",
                agent=agent,
                lifecycle="open",
            )
        )
        db.add_all(entries)
        await db.commit()


def _entry(agent, conversation_id, content="hello"):
    return new_entry(
        project_id="proj-test",
        agent=agent,
        origin_type="operator",
        content=content,
        hop_depth=0,
        conversation_id=conversation_id,
    )


async def _row(entry_id):
    async with async_session_factory() as db:
        return (
            await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
        ).scalar_one()


# ---------------------------------------------------------------- group 2: the carrier


@pytest.mark.asyncio
async def test_an_empty_queue_carries_no_refusal(app, auth_headers, bind_runner):
    """2.3 — `"queue is empty"` returns with `terminal_failure` at its **defaulted** `True`, and a
    caller that read that flag would answer *failed* to a request another drain had just delivered.
    The refusal carrier is what a caller reads instead, and this is the return that proves the
    defaults cannot leak into it."""
    agent = "refusal-empty"
    await _register(app, auth_headers, bind_runner, agent)

    result = await schedule_agent("proj-test", agent)

    assert result.waiting_reason == "queue is empty"
    assert result.terminal_failure is True, "the dishonest default this design routes around"
    assert result.refusal is None


@pytest.mark.asyncio
async def test_a_hop_budget_early_return_carries_no_refusal(app, auth_headers, bind_runner):
    """2.3 — the same for the other defaulted-`True` early return that is easy to reach."""
    agent = "refusal-hops"
    await _register(app, auth_headers, bind_runner, agent)
    entry = _entry(agent, "conv-refusal-hops")
    await _seed(agent, "conv-refusal-hops", [entry])
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 0
        row = await db.get(InboundQueueEntry, entry.sequence)
        row.hop_depth = 5
        await db.commit()

    result = await schedule_agent("proj-test", agent)

    assert result.waiting_reason == "hop budget exhausted"
    assert result.terminal_failure is True
    assert result.refusal is None


@pytest.mark.asyncio
async def test_a_request_level_refusal_carries_its_status_and_its_own_entries(
    app, auth_headers, bind_runner
):
    """2.4 — the carrier holds the error's own status, its sentence, and the ids of exactly the
    entries the refused turn would have delivered."""
    agent = "refusal-carried"
    await _register(app, auth_headers, bind_runner, agent)
    first = _entry(agent, "conv-refusal-carried", "one")
    second = _entry(agent, "conv-refusal-carried", "two")
    await _seed(agent, "conv-refusal-carried", [first, second])

    with patch(
        TRIGGER,
        AsyncMock(
            side_effect=TriggerAgentError(403, "the reviewer is its own author", request_level=True)
        ),
    ):
        result = await schedule_agent("proj-test", agent)

    assert result.refusal is not None
    assert result.refusal.status_code == 403
    assert result.refusal.detail == "the reviewer is its own author"
    assert set(result.refusal.entry_ids) == {first.id, second.id}


@pytest.mark.asyncio
async def test_a_transient_refusal_carries_none(app, auth_headers, bind_runner):
    """2.5 — a turn parked behind another agent's checkout (design D8) clears when that turn ends.
    Answering it as a failure would report the system working as broken."""
    agent = "refusal-transient"
    await _register(app, auth_headers, bind_runner, agent)
    entry = _entry(agent, "conv-refusal-transient")
    await _seed(agent, "conv-refusal-transient", [entry])

    with patch(
        TRIGGER,
        AsyncMock(
            side_effect=TriggerAgentError(
                409, "builder is already running a turn on that task", transient=True
            )
        ),
    ):
        result = await schedule_agent("proj-test", agent)

    assert result.waiting_reason == "builder is already running a turn on that task"
    assert result.terminal_failure is False
    assert result.refusal is None


@pytest.mark.asyncio
async def test_an_environment_level_refusal_leaves_the_entry_queued(app, auth_headers, bind_runner):
    """2.5 and 4.6, and the reason `request_level` is not the negation of `transient`.

    "No runner is bound" is non-transient — it will not clear on its own — and it must still queue.
    F96 exists because an operator who performs the repair the refusal names has to get their
    message delivered; withdrawing the entry here would delete that finding's fix.
    """
    agent = "refusal-environment"
    await _register(app, auth_headers, bind_runner, agent)
    entry = _entry(agent, "conv-refusal-environment")
    await _seed(agent, "conv-refusal-environment", [entry])

    with patch(
        TRIGGER,
        AsyncMock(
            side_effect=TriggerAgentError(
                409, "No runner is bound to this agent. Bind one in the Hub UI."
            )
        ),
    ):
        result = await schedule_agent("proj-test", agent)

    assert result.terminal_failure is True, "it does not clear on its own"
    assert result.refusal is None, "but it is not about what was asked"
    row = await _row(entry.id)
    assert row.state == "queued"
    assert row.waiting_reason == "No runner is bound to this agent. Bind one in the Hub UI."


# ---------------------------------------------------------------- group 3: the answer


@pytest.mark.asyncio
async def test_a_request_level_refusal_answers_with_its_own_status_and_sentence(
    app, auth_headers, bind_runner
):
    """3.1 and 3.4 — the F108 reproduction, in the shape round 2 showed is actually reachable.

    The route's pre-queue guards already refuse an archived agent, a missing task and an invalid
    `work_dir` before anything is queued. What they cannot see is time: a guard that passed when the
    request arrived can be false by the time the entry is dispatched, because the queue makes that
    gap arbitrarily long. Patching the dispatch to refuse is exactly that state — the request was
    admitted, and the turn it was admitted for can no longer happen.
    """
    agent = "refusal-answered"
    await _register(app, auth_headers, bind_runner, agent)

    sentence = (
        "Task task-x is already under review by 'critic'. Reassign the task if "
        "'refusal-answered' should take it over, or let the review in flight finish."
    )
    with patch(
        TRIGGER, AsyncMock(side_effect=TriggerAgentError(409, sentence, request_level=True))
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "review it", "session_mode": "new"},
            headers=auth_headers,
        )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == sentence


@pytest.mark.asyncio
async def test_a_refusal_naming_another_conversation_is_not_reported_as_this_ones(
    app, auth_headers, bind_runner
):
    """3.3 and 3.6 — `schedule_agent` builds its turn from the oldest eligible entry across the
    agent's whole queue, so the refusal it raises frequently belongs to a conversation this caller
    never mentioned. Reporting it here would hand the caller a sentence about somebody else's input.
    """
    agent = "refusal-foreign"
    await _register(app, auth_headers, bind_runner, agent)
    older = _entry(agent, "conv-refusal-foreign-older", "earlier work")
    await _seed(agent, "conv-refusal-foreign-older", [older])

    foreign = "Task task-secret is already under review by 'critic'."
    with patch(TRIGGER, AsyncMock(side_effect=TriggerAgentError(409, foreign, request_level=True))):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "mine", "session_mode": "new"},
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert foreign not in (body["waiting_reason"] or "")
    assert "other input" in body["waiting_reason"]


@pytest.mark.asyncio
async def test_a_concurrent_drain_is_still_answered_as_accepted(app, auth_headers, bind_runner):
    """3.7 — the race D2 refuses to gate on. `schedule_agent` reports an empty queue with
    `terminal_failure` at its defaulted `True`; the request nevertheless worked."""
    agent = "refusal-drained"
    await _register(app, auth_headers, bind_runner, agent)

    with patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=ScheduleResult(waiting_reason="queue is empty")),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"


# ---------------------------------------------------------------- group 4: the queue agrees


@pytest.mark.asyncio
async def test_a_refused_request_leaves_nothing_queued(app, auth_headers, bind_runner):
    """4.1 and 4.3 — the answer and the queue say the same thing. Without this the operator reads
    an error while their input goes on being retried behind them."""
    agent = "refusal-withdrawn"
    await _register(app, auth_headers, bind_runner, agent)

    sentence = "Task task-y is 'approved', which is not a status a review starts from."
    with patch(
        TRIGGER, AsyncMock(side_effect=TriggerAgentError(409, sentence, request_level=True))
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "review it", "session_mode": "new"},
            headers=auth_headers,
        )
    assert resp.status_code == 409

    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .all()
        )
    assert [row.state for row in rows] == ["withdrawn"]
    assert rows[0].abandoned_reason == sentence


@pytest.mark.asyncio
async def test_the_withdrawal_is_announced_and_not_as_an_abandonment(
    app, auth_headers, bind_runner
):
    """4.4 and 4.4a — `queue_entry_queued` was already broadcast before the refusal was known, so a
    silent withdrawal leaves the operator holding an error *and* a queue card still counting the
    input. `queue_entry_withdrawn`, not `queue_entry_abandoned`: nothing was tried and nobody gave
    up, so the event that carries an attempt count and a run id would be a lie."""
    agent = "refusal-announced"
    await _register(app, auth_headers, bind_runner, agent)

    broadcasts = []

    async def _record(project_id, event_type, data):
        broadcasts.append(event_type)

    sentence = "Cannot review task task-z as its own author."
    with (
        patch(TRIGGER, AsyncMock(side_effect=TriggerAgentError(403, sentence, request_level=True))),
        patch.object(agent_trigger.sse_manager, "broadcast", AsyncMock(side_effect=_record)),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "review it", "session_mode": "new"},
            headers=auth_headers,
        )

    assert resp.status_code == 403
    assert "queue_entry_withdrawn" in broadcasts
    assert "queue_entry_abandoned" not in broadcasts


@pytest.mark.asyncio
async def test_the_route_sees_a_withdrawal_its_own_session_never_made(
    app, auth_headers, bind_runner
):
    """4.5, design D11 — the trap this change would otherwise have walked into.

    `async_session_factory` is built with `expire_on_commit=False` and `schedule_agent` runs in a
    session of its own, so the route's copy of its entry still reads `state="queued"` after the
    scheduler withdrew the row at the delivery-attempt limit. A tolerance check written against the
    stale object is correct, tested, and unable to fire. Here the scheduler withdraws through a
    genuinely separate session, exactly as the real one does, and the route must not announce a
    withdrawal it did not make.
    """
    agent = "refusal-stale"
    await _register(app, auth_headers, bind_runner, agent)

    sentence = "no such agent"
    real_schedule = schedule_agent

    async def withdraw_then_refuse(project_id, agent_name):
        # Let the real scheduler run first, so this stands where the real one stands.
        await real_schedule(project_id, agent_name)
        async with async_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(InboundQueueEntry).where(InboundQueueEntry.agent == agent_name)
                    )
                )
                .scalars()
                .all()
            )
            ids = [row.id for row in rows]
            for row in rows:
                row.state = "withdrawn"
                row.abandoned_reason = "withdrawn by the scheduler at the attempt limit"
            await db.commit()
        from hub.turn_scheduler import TurnRefusal

        return ScheduleResult(
            waiting_reason=sentence,
            refusal=TurnRefusal(status_code=409, detail=sentence, entry_ids=tuple(ids)),
        )

    broadcasts = []

    async def _record(project_id, event_type, data):
        broadcasts.append(event_type)

    with (
        patch("hub.turn_scheduler.schedule_agent", AsyncMock(side_effect=withdraw_then_refuse)),
        patch.object(agent_trigger.sse_manager, "broadcast", AsyncMock(side_effect=_record)),
    ):
        resp = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )

    assert resp.status_code == 409, resp.text
    assert broadcasts.count("queue_entry_withdrawn") == 0, (
        "the scheduler already withdrew it and announced its own; a second announcement would "
        "report one withdrawal twice"
    )
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)))
            .scalars()
            .all()
        )
    assert [row.abandoned_reason for row in rows] == [
        "withdrawn by the scheduler at the attempt limit"
    ], "the route must not overwrite the reason the scheduler recorded"
