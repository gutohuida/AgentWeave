"""Input queued into a closed conversation holds nothing else (F1046).

On the operator's Hub, 2026-10-27, the roadmap's next-slice turn was queued into the Architect's
archived conversation. It sat at the head of the Architect's queue, the scheduler returned
"conversation is unavailable" for it on every pass, recording nothing and counting nothing, and the
checkpoint successor and the operator's own message queued behind it never started. These tests
pin the scheduler at that head, and the unarchive route that is the held input's repair.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry
from hub.inbound_queue import new_entry
from hub.turn_scheduler import schedule_agent

from ._background_runs import await_background_runs as _drain

PROJECT = "proj-test"
AGENT = "archy"


def _spawned(pid=1046):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,' f'"session_id":"s-{pid}"}}\n',
        "",
    ]
    session.wait.return_value = 0
    return MagicMock(return_value=session)


def _launch(spawn):
    return (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    )


async def _register(app, auth_headers, bind_runner):
    await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {AGENT: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(AGENT, cli="claude")


async def _conversation(conversation_id, lifecycle):
    async with async_session_factory() as db:
        db.add(
            Conversation(
                id=conversation_id,
                project_id=PROJECT,
                agent=AGENT,
                lifecycle=lifecycle,
                origin="operator",
                lineage_id=conversation_id,
            )
        )
        await db.commit()


async def _queue(content, conversation_id):
    async with async_session_factory() as db:
        entry = new_entry(
            project_id=PROJECT,
            agent=AGENT,
            origin_type="operator",
            content=content,
            hop_depth=0,
            conversation_id=conversation_id,
        )
        db.add(entry)
        await db.commit()
        return entry.id


async def _entry(entry_id):
    async with async_session_factory() as db:
        return (
            await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id))
        ).scalar_one()


@pytest.mark.asyncio
async def test_input_behind_an_archived_head_still_runs(app, auth_headers, bind_runner):
    await _register(app, auth_headers, bind_runner)
    await _conversation("conv-archived", "archived")
    await _conversation("conv-open", "open")
    stranded = await _queue("draft the next slice", "conv-archived")
    behind = await _queue("the operator's message", "conv-open")

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        result = await schedule_agent(PROJECT, AGENT)
        await _drain()

    assert result.response is not None, result.waiting_reason
    spawn.assert_called_once()
    assert (await _entry(behind)).state == "delivered"
    held = await _entry(stranded)
    assert held.state == "queued"
    assert held.delivery_attempts == 0
    assert "conv-archived" in held.waiting_reason and "archived" in held.waiting_reason
    assert "Unarchive" in held.waiting_reason


@pytest.mark.asyncio
async def test_input_only_in_an_archived_conversation_says_why_it_waits(
    app, auth_headers, bind_runner
):
    await _register(app, auth_headers, bind_runner)
    await _conversation("conv-archived", "archived")
    stranded = await _queue("draft the next slice", "conv-archived")

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        result = await schedule_agent(PROJECT, AGENT)

    spawn.assert_not_called()
    assert "conv-archived" in result.waiting_reason and "archived" in result.waiting_reason
    held = await _entry(stranded)
    assert held.state == "queued"
    assert held.waiting_reason == result.waiting_reason


@pytest.mark.asyncio
async def test_unarchiving_delivers_the_input_it_held(app, auth_headers, bind_runner):
    """The waiting reason names Unarchive as the repair, so Unarchive has to deliver."""
    await _register(app, auth_headers, bind_runner)
    await _conversation("conv-archived", "archived")
    stranded = await _queue("draft the next slice", "conv-archived")

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        reopened = await app.post(
            f"/api/v1/projects/{PROJECT}/agent/{AGENT}/conversations/conv-archived/unarchive",
            headers=auth_headers,
        )
        await _drain()

    assert reopened.status_code == 200, reopened.text
    spawn.assert_called_once()
    assert (await _entry(stranded)).state == "delivered"
