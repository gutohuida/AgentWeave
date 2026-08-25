"""The hop budget bounds delivery, not just admission (2026-08-23-the-hop-budget-is-a-real-bound).

Finding F5, measured live on 2026-08-23: with ``hop_budget = 1``, a chain held correctly at depth 2
for as long as the entry sat alone — and was delivered the moment the operator said anything into
the same conversation. Two defects, both in ``turn_scheduler.schedule_agent``:

- ``can_start`` returns true when *any* entry is within budget, and the batch that followed applied
  no depth filter, so the blocked entry rode along on a turn admitted by a shallower one.
- the turn took ``min(hop_depth)`` across that batch, so a hop-0 entry bundled with a hop-2 entry
  produced a turn at depth 0 and the chain restarted its count from zero.

These tests pin both halves, and the last one reproduces F5's exact shape.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, EventLog, InboundQueueEntry, Project, Run
from hub.inbound_queue import new_entry
from hub.turn_scheduler import redrain_queued_agents, schedule_agent


def _completed_session(pid, session_id):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,' f'"session_id":"{session_id}"}}\n',
        "",
    ]
    session.wait.return_value = 0
    return session


async def _register(app, auth_headers, bind_runner, *agents):
    # One sync call for every agent the test needs: `sync_session` treats `agents` as the whole
    # roster and deletes anything absent, so a second call would remove the first agent.
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"} for agent in agents}}},
        headers=auth_headers,
    )
    for agent in agents:
        await bind_runner(agent, cli="claude")


async def _seed(agent, conversation_id, budget, entries):
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = budget
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


async def _drain():
    while agent_trigger._background_runs:
        for task in list(agent_trigger._background_runs):
            await task


async def _entries(agent):
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.agent == agent)
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )
        return [(row.content, row.hop_depth, row.state) for row in rows]


@pytest.mark.asyncio
async def test_an_over_budget_entry_is_not_delivered_beside_an_admitted_one(
    app, auth_headers, bind_runner
):
    """The batch carries only what the budget allows, whatever else is queued beside it."""
    await _register(app, auth_headers, bind_runner, "bound-target")
    await _seed(
        "bound-target",
        "conv-bound-target",
        1,
        [
            new_entry(
                project_id="proj-test",
                agent="bound-target",
                origin_type="agent",
                origin_agent="peer",
                content="within budget",
                hop_depth=1,
                conversation_id="conv-bound-target",
            ),
            new_entry(
                project_id="proj-test",
                agent="bound-target",
                origin_type="agent",
                origin_agent="peer",
                content="over budget",
                hop_depth=2,
                conversation_id="conv-bound-target",
            ),
        ],
    )

    spawn = MagicMock(return_value=_completed_session(7101, "bound-1"))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", "bound-target")
            assert result.response is not None
            await _drain()

    assert await _entries("bound-target") == [
        ("within budget", 1, "delivered"),
        ("over budget", 2, "queued"),
    ]
    # And the prompt the agent actually saw carried only the admitted entry — a filter that left
    # the queue state right while still handing the text over would not have fixed anything.
    assert "over budget" not in str(spawn.call_args)


@pytest.mark.asyncio
async def test_the_turn_depth_is_the_admitting_entrys_not_the_batch_minimum(
    app, auth_headers, bind_runner
):
    await _register(app, auth_headers, bind_runner, "depth-target")
    await _seed(
        "depth-target",
        "conv-depth-target",
        3,
        [
            new_entry(
                project_id="proj-test",
                agent="depth-target",
                origin_type="agent",
                origin_agent="peer",
                content="admits the turn",
                hop_depth=2,
                conversation_id="conv-depth-target",
            ),
            new_entry(
                project_id="proj-test",
                agent="depth-target",
                origin_type="agent",
                origin_agent="peer",
                content="shallower, arrived later",
                hop_depth=1,
                conversation_id="conv-depth-target",
            ),
        ],
    )

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(return_value=_completed_session(7102, "depth-1")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", "depth-target")
            assert result.response is not None
            run_id = result.response.run_id
            await _drain()

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        # Both entries are within budget and both ride this turn, so `min()` and the admitting
        # entry disagree here — which is the whole point of the assertion.
        assert run.turn_depth == 2


@pytest.mark.asyncio
async def test_an_outbound_message_is_deeper_than_the_entry_that_admitted_the_turn(
    app, auth_headers, bind_runner
):
    await _register(app, auth_headers, bind_runner, "outbound-target", "outbound-peer")
    # Budget 2 admits the depth-2 entry and holds what the turn sends onward at depth 3 — so the
    # same test shows both that the count advanced and that the bound catches it one hop later.
    await _seed(
        "outbound-target",
        "conv-outbound-target",
        2,
        [
            new_entry(
                project_id="proj-test",
                agent="outbound-target",
                origin_type="agent",
                origin_agent="outbound-peer",
                content="admits the turn",
                hop_depth=2,
                conversation_id="conv-outbound-target",
            )
        ],
    )

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(return_value=_completed_session(7103, "outbound-1")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", "outbound-target")
            run_id = result.response.run_id
            await _drain()

    # The run has finished under the mocked spawn; the arithmetic under test is what the messages
    # route reads off a live run, so put it back into the state it sends from.
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.turn_depth == 2
        run.status = "running"
        await db.commit()

    with patch("hub.api.v1.agent_trigger.PtySession.spawn") as peer_spawn:
        sent = await app.post(
            "/api/v1/projects/proj-test/messages",
            json={
                "from": "outbound-target",
                "to": "outbound-peer",
                "content": "reply outward",
                "run_id": run_id,
            },
            headers=auth_headers,
        )
    assert sent.status_code == 201
    assert await _entries("outbound-peer") == [("reply outward", 3, "queued")]
    peer_spawn.assert_not_called()


@pytest.mark.asyncio
async def test_an_operator_message_does_not_release_a_held_chain_in_its_own_conversation(
    app, auth_headers, bind_runner
):
    """F5, reproduced exactly: budget 1, a chain held at depth 2, one operator message.

    The operator entry is the shallower one and arrives second, so before the fix `min()` gave the
    turn depth 0 while the unfiltered batch delivered the depth-2 entry alongside it — the guard
    reset for that conversation by ordinary supervision.
    """
    await _register(app, auth_headers, bind_runner, "f5-target")
    await _seed(
        "f5-target",
        "conv-f5-target",
        1,
        [
            new_entry(
                project_id="proj-test",
                agent="f5-target",
                origin_type="agent",
                origin_agent="relay",
                content="hop two, over budget",
                hop_depth=2,
                conversation_id="conv-f5-target",
            ),
            new_entry(
                project_id="proj-test",
                agent="f5-target",
                origin_type="operator",
                content="an ordinary operator message",
                hop_depth=0,
                conversation_id="conv-f5-target",
            ),
        ],
    )

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(return_value=_completed_session(7104, "f5-1")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            result = await schedule_agent("proj-test", "f5-target")
            assert result.response is not None
            run_id = result.response.run_id
            await _drain()

    assert await _entries("f5-target") == [
        ("hop two, over budget", 2, "queued"),
        ("an ordinary operator message", 0, "delivered"),
    ]
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        assert run.turn_depth == 0


async def _held_entry(app, auth_headers, bind_runner, agent, *, budget=1, depth=2):
    """One agent with one entry held over the budget, and its id."""
    await _register(app, auth_headers, bind_runner, agent)
    entry = new_entry(
        project_id="proj-test",
        agent=agent,
        origin_type="agent",
        origin_agent="relay",
        content="held over the budget",
        hop_depth=depth,
        conversation_id=f"conv-{agent}",
    )
    await _seed(agent, f"conv-{agent}", budget, [entry])
    return entry.id


async def _events(kind):
    async with async_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(EventLog)
                    .where(EventLog.project_id == "proj-test", EventLog.event_type == kind)
                    .order_by(EventLog.id)
                )
            )
            .scalars()
            .all()
        )
        return [row.data for row in rows]


@pytest.mark.asyncio
async def test_releasing_a_held_entry_delivers_it_on_the_next_turn(app, auth_headers, bind_runner):
    entry_id = await _held_entry(app, auth_headers, bind_runner, "release-target")

    spawn = MagicMock(return_value=_completed_session(7201, "release-1"))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            released = await app.post(
                f"/api/v1/projects/proj-test/queue/entries/{entry_id}/release",
                headers=auth_headers,
            )
            await _drain()

    assert released.status_code == 200
    # Re-based to 0, not granted `+N`: the depth left behind says the operator restarted the
    # chain here, rather than carrying an offset whose meaning depends on history nobody kept.
    assert released.json()["hop_depth"] == 0
    assert await _entries("release-target") == [("held over the budget", 0, "delivered")]
    assert spawn.call_count == 1


@pytest.mark.asyncio
async def test_releasing_a_held_entry_records_what_it_was_released_from(
    app, auth_headers, bind_runner
):
    entry_id = await _held_entry(app, auth_headers, bind_runner, "record-target", depth=4)

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(return_value=_completed_session(7202, "record-1")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await app.post(
                f"/api/v1/projects/proj-test/queue/entries/{entry_id}/release",
                headers=auth_headers,
            )
            await _drain()

    # After the re-base the row itself reads 0, so the depth it came from survives only here.
    assert await _events("queue_entry_released") == [
        {"entry_id": entry_id, "agent": "record-target", "released_from_depth": 4}
    ]


@pytest.mark.asyncio
async def test_releasing_an_entry_the_budget_is_not_holding_is_refused_with_the_reason(
    app, auth_headers, bind_runner
):
    entry_id = await _held_entry(app, auth_headers, bind_runner, "within-target", budget=6, depth=2)

    with patch("hub.api.v1.agent_trigger.PtySession.spawn"):
        refused = await app.post(
            f"/api/v1/projects/proj-test/queue/entries/{entry_id}/release",
            headers=auth_headers,
        )

    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert "hop 2" in detail and "hop budget of 6" in detail
    # And it says where to look instead, because the entry really is waiting for something.
    assert "queue status" in detail
    assert await _events("queue_entry_released") == []


@pytest.mark.asyncio
async def test_releasing_an_absent_entry_is_refused(app, auth_headers):
    refused = await app.post(
        "/api/v1/projects/proj-test/queue/entries/entry-nonexistent/release",
        headers=auth_headers,
    )
    assert refused.status_code == 409
    assert "absent" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_held_entry_can_be_discarded_instead(app, auth_headers, bind_runner):
    entry_id = await _held_entry(app, auth_headers, bind_runner, "discard-target")

    with patch("hub.api.v1.agent_trigger.PtySession.spawn") as spawn:
        discarded = await app.delete(
            f"/api/v1/projects/proj-test/queue/entries/{entry_id}",
            headers=auth_headers,
        )

    assert discarded.status_code == 200
    assert await _entries("discard-target") == [("held over the budget", 2, "withdrawn")]
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_raising_the_budget_releases_a_held_entry_without_an_explicit_action(
    app, auth_headers, bind_runner
):
    await _held_entry(app, auth_headers, bind_runner, "raise-target")

    spawn = MagicMock(return_value=_completed_session(7203, "raise-1"))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            saved = await app.patch(
                "/api/v1/projects/proj-test/queue/settings",
                json={"hop_budget": 4, "turn_delivery_cap": 10},
                headers=auth_headers,
            )
            await _drain()

    assert saved.status_code == 200
    # Delivered at the depth it always had — raising the bound is not the operator restarting
    # the chain, so nothing is re-based and no release is recorded.
    assert await _entries("raise-target") == [("held over the budget", 2, "delivered")]
    assert await _events("queue_entry_released") == []


@pytest.mark.asyncio
async def test_redrain_delivers_a_held_entry_once_the_budget_admits_it(
    app, auth_headers, bind_runner
):
    """Pins behaviour that already existed and was never asserted (task 2.3).

    `redrain_queued_agents` is what project open and workspace repair call, so it is a second,
    independent path to the same release — and the delivery filter added in this change is
    exactly the kind of edit that could have broken it silently.
    """
    await _held_entry(app, auth_headers, bind_runner, "redrain-target")
    async with async_session_factory() as db:
        project = await db.get(Project, "proj-test")
        project.hop_budget = 5
        await db.commit()

    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn",
        MagicMock(return_value=_completed_session(7204, "redrain-1")),
    ):
        with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
            await redrain_queued_agents("proj-test")
            await _drain()

    assert await _entries("redrain-target") == [("held over the budget", 2, "delivered")]
