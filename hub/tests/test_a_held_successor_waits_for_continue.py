"""A held successor waits for Continue (F598, `spec/changes/a-held-successor-waits-for-continue`).

With checkpoint auto-continue off, a cutover queues the successor's checkpoint entry without
scheduling it -- and every run's end and every settings save then re-drained the whole project,
which started it anyway. Two agents fed each other through that redrain for 13 unattended turns in
the 2026-10-15 sweep. These tests pin the hold at the seam the finding names (the redrain and the
settings save) and the two ways the operator releases it (Continue, or their own message).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.checkpoint_cutover import cut_over
from hub.checkpoint_generation import CheckpointBody, render_body
from hub.checkpoints import compute_envelope, create_checkpoint
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Run
from hub.inbound_queue import new_entry
from hub.turn_scheduler import redrain_queued_agents, schedule_agent

from ._background_runs import await_background_runs as _drain
from .test_checkpoint_generation import GOOD_BODY

PROJECT = "proj-test"
AGENT = "heldy"


def _completed_session(pid, session_id):
    session = MagicMock()
    session.pid = pid
    session.read.side_effect = [
        '{"type":"result","subtype":"success","is_error":false,' f'"session_id":"{session_id}"}}\n',
        "",
    ]
    session.wait.return_value = 0
    return session


def _spawned(pid=7598):
    return MagicMock(return_value=_completed_session(pid, f"held-{pid}"))


async def _register(app, auth_headers, bind_runner):
    await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {AGENT: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    await bind_runner(AGENT, cli="claude")


async def _cut_over(auto_continue=False, conversation_id="conv-held-pre"):
    """A predecessor, a ready checkpoint, and the cutover. Returns (successor id, entry id)."""
    async with async_session_factory() as db:
        predecessor = Conversation(
            id=conversation_id,
            project_id=PROJECT,
            agent=AGENT,
            lifecycle="open",
            origin="operator",
            title="Wire up the worker",
            lineage_id=conversation_id,
        )
        db.add(predecessor)
        await db.commit()
        checkpoint = await create_checkpoint(
            db,
            predecessor,
            trigger="context_pressure",
            envelope=await compute_envelope(db, predecessor),
            body=render_body(CheckpointBody(**GOOD_BODY), notes_incorporated=False),
        )
        successor, entry_id = await cut_over(
            db, predecessor, checkpoint, auto_continue=auto_continue
        )
        return successor.id, entry_id


async def _queue(origin_type, content, conversation_id, origin_agent=None):
    async with async_session_factory() as db:
        entry = new_entry(
            project_id=PROJECT,
            agent=AGENT,
            origin_type=origin_type,
            origin_agent=origin_agent,
            content=content,
            hop_depth=1 if origin_type == "agent" else 0,
            conversation_id=conversation_id,
        )
        db.add(entry)
        await db.commit()
        return entry.id


async def _entry(entry_id):
    async with async_session_factory() as db:
        return (
            (await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.id == entry_id)))
            .scalars()
            .one()
        )


def _prompt(spawn):
    """Everything the spawned CLI was handed, untruncated (a call's repr elides the middle)."""
    return " ".join(str(part) for part in spawn.call_args.args[0])


def _launch(spawn):
    return (
        patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn),
        patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"),
    )


@pytest.mark.asyncio
async def test_a_redrain_does_not_start_a_held_successor(app, auth_headers, bind_runner):
    await _register(app, auth_headers, bind_runner)
    _successor, entry_id = await _cut_over()

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        await redrain_queued_agents(PROJECT)
        await _drain()

    spawn.assert_not_called()
    entry = await _entry(entry_id)
    assert entry.state == "queued"
    assert entry.awaits_continue is True


@pytest.mark.asyncio
async def test_a_settings_save_does_not_start_a_held_successor(app, auth_headers, bind_runner):
    """The exact door the sweep measured: its own `checkpoint_mode: off` write started a run."""
    await _register(app, auth_headers, bind_runner)
    _successor, entry_id = await _cut_over()
    settings = (await app.get(f"/api/v1/projects/{PROJECT}/settings", headers=auth_headers)).json()

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        saved = await app.put(
            f"/api/v1/projects/{PROJECT}/settings", json=settings, headers=auth_headers
        )
        await _drain()

    assert saved.status_code == 200
    spawn.assert_not_called()
    assert (await _entry(entry_id)).state == "queued"


@pytest.mark.asyncio
async def test_a_peer_message_into_the_successor_waits_with_it(app, auth_headers, bind_runner):
    """A peer binding follows the line of work into the successor. Running the peer's message
    there would start the successor without the checkpoint it was handed."""
    await _register(app, auth_headers, bind_runner)
    successor, entry_id = await _cut_over()
    peer_entry = await _queue("agent", "a peer's note", successor, origin_agent="peer")

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        await redrain_queued_agents(PROJECT)
        await _drain()

    spawn.assert_not_called()
    assert (await _entry(entry_id)).state == "queued"
    assert (await _entry(peer_entry)).state == "queued"


@pytest.mark.asyncio
async def test_input_in_another_conversation_still_runs(app, auth_headers, bind_runner):
    """The hold is the successor conversation's, not the agent's."""
    await _register(app, auth_headers, bind_runner)
    _successor, entry_id = await _cut_over()
    async with async_session_factory() as db:
        db.add(
            Conversation(
                id="conv-held-other",
                project_id=PROJECT,
                agent=AGENT,
                lifecycle="open",
                lineage_id="conv-held-other",
            )
        )
        await db.commit()
    other = await _queue("agent", "unrelated work", "conv-held-other", origin_agent="peer")

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        result = await schedule_agent(PROJECT, AGENT)
        await _drain()

    assert result.response is not None
    assert (await _entry(other)).state == "delivered"
    assert (await _entry(entry_id)).state == "queued"


@pytest.mark.asyncio
async def test_continue_releases_the_successor_and_starts_it(app, auth_headers, bind_runner):
    await _register(app, auth_headers, bind_runner)
    successor, entry_id = await _cut_over()

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        pressed = await app.post(
            f"/api/v1/projects/{PROJECT}/conversations/{successor}/continue",
            headers=auth_headers,
        )
        await _drain()

    assert pressed.status_code == 200
    assert pressed.json()["started"] is True
    entry = await _entry(entry_id)
    assert entry.state == "delivered"
    # The checkpoint is what the successor's first turn is about.
    assert "generated by the Hub from that conversation's record" in _prompt(spawn)


@pytest.mark.asyncio
async def test_continue_pressed_while_running_is_kept_for_the_run_end(
    app, auth_headers, bind_runner
):
    """The release is written down: a Continue that meets a running agent is not lost."""
    await _register(app, auth_headers, bind_runner)
    successor, entry_id = await _cut_over()
    async with async_session_factory() as db:
        db.add(Run(id="run-held-busy", project_id=PROJECT, agent=AGENT, status="running"))
        await db.commit()

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        pressed = await app.post(
            f"/api/v1/projects/{PROJECT}/conversations/{successor}/continue",
            headers=auth_headers,
        )
        assert pressed.json()["started"] is False
        spawn.assert_not_called()
        assert (await _entry(entry_id)).awaits_continue is False

        async with async_session_factory() as db:
            run = await db.get(Run, "run-held-busy")
            run.status = "completed"
            await db.commit()
        await redrain_queued_agents(PROJECT)
        await _drain()

    assert (await _entry(entry_id)).state == "delivered"


@pytest.mark.asyncio
async def test_the_operators_own_message_releases_it(app, auth_headers, bind_runner):
    """Writing into the successor is the operator saying go; the checkpoint rides along."""
    await _register(app, auth_headers, bind_runner)
    successor, entry_id = await _cut_over()
    operator_entry = await _queue("operator", "carry on, and add a test", successor)

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        result = await schedule_agent(PROJECT, AGENT)
        await _drain()

    assert result.response is not None
    assert (await _entry(entry_id)).state == "delivered"
    assert (await _entry(operator_entry)).state == "delivered"
    prompt = _prompt(spawn)
    assert "carry on, and add a test" in prompt
    assert "generated by the Hub from that conversation's record" in prompt


@pytest.mark.asyncio
async def test_the_queue_status_says_it_waits_for_continue(app, auth_headers, bind_runner):
    await _register(app, auth_headers, bind_runner)
    successor, _entry_id = await _cut_over()

    status = await app.get(f"/api/v1/projects/{PROJECT}/queue/{AGENT}/status", headers=auth_headers)

    assert status.status_code == 200
    reason = status.json()["waiting_reason"]
    assert "Continue" in reason
    assert successor in reason


@pytest.mark.asyncio
async def test_the_scheduler_answers_waiting_for_continue_not_a_failure(
    app, auth_headers, bind_runner
):
    await _register(app, auth_headers, bind_runner)
    successor, _entry_id = await _cut_over()

    result = await schedule_agent(PROJECT, AGENT)

    assert result.response is None
    assert "Continue" in result.waiting_reason and successor in result.waiting_reason
    assert result.terminal_failure is False


@pytest.mark.asyncio
async def test_with_auto_continue_on_the_successor_is_not_held(app, auth_headers, bind_runner):
    await _register(app, auth_headers, bind_runner)

    spawn = _spawned()
    first, second = _launch(spawn)
    with first, second:
        _successor, entry_id = await _cut_over(auto_continue=True)
        await _drain()

    entry = await _entry(entry_id)
    assert entry.awaits_continue is False
    assert entry.state == "delivered"
