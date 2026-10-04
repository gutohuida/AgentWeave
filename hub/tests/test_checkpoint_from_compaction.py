"""Slice 5 group A, tasks 1.4 and 1.5: a compaction counts as the checkpoint threshold crossed.

`a-copilot-agent-uses-hooks-and-its-own-agents` design D4's table, one test per row, driving
`checkpoint_trigger.consider(..., compacted=True)` against real rows (the pattern of
`test_checkpoint_cutover.py`). Generation and cutover are patched, as the existing trigger tests
patch the spawn, so each row can say whether a checkpoint was generated, with which trigger, and
whether it was handed over. Then the funnel: `record_agent_output` dispatches the consideration
for a `compacted` status, and nothing it does changes what the output routes answer.

Each test failed before group A was built: `consider` took no `compacted`, and
`consider_from_compaction` did not exist.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from hub import checkpoint_trigger
from hub.checkpoint_trigger import consider, consider_from_compaction
from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, InboundQueueEntry, Run

from .test_checkpoint_cutover import (
    AGENT,
    PROJECT,
    _configured_project,
    _conversation,
    _handed_over_and_reopened,
    _ready_checkpoint,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def spend(monkeypatch):
    """What the consideration did: generation (with its trigger), cutover, and broadcasts."""
    generated = AsyncMock(
        return_value=SimpleNamespace(id="ckpt-c", status="ready", probe_status="passed")
    )
    handed_over = AsyncMock(return_value=(SimpleNamespace(id="conv-successor"), "entry-c"))
    broadcasts = []

    async def broadcast(project_id, event, payload):
        broadcasts.append((event, payload))

    monkeypatch.setattr(checkpoint_trigger, "generate_checkpoint", generated)
    monkeypatch.setattr(checkpoint_trigger, "cut_over", handed_over)
    monkeypatch.setattr(checkpoint_trigger.sse_manager, "broadcast", broadcast)
    return SimpleNamespace(generated=generated, handed_over=handed_over, broadcasts=broadcasts)


async def _compaction(percent=None):
    return await consider(
        PROJECT, AGENT, "conv-1", context_tokens=None, percent=percent, compacted=True
    )


async def _state(conversation_id="conv-1"):
    async with async_session_factory() as db:
        conversation = await get_conversation_by_id(db, conversation_id)
        checkpoint_entries = (
            (
                await db.execute(
                    select(InboundQueueEntry).where(
                        InboundQueueEntry.conversation_id == conversation_id,
                        InboundQueueEntry.origin_type == "checkpoint",
                    )
                )
            )
            .scalars()
            .all()
        )
    return conversation, checkpoint_entries


def _due(spend):
    return [payload for event, payload in spend.broadcasts if event == "checkpoint_due"]


# --------------------------------------------------------------------------- D4's table


async def test_checkpointing_off_ignores_a_compaction(app, spend):
    async with async_session_factory() as db:
        await _configured_project(db, checkpoint_mode="off")
        await _conversation(db)

    assert await _compaction(percent=99.0) is None
    conversation, entries = await _state()
    assert conversation.checkpoint_warning is None
    assert entries == []
    assert not spend.generated.called
    assert _due(spend) == []


async def test_a_conversation_that_is_not_open_ignores_a_compaction(app, spend):
    async with async_session_factory() as db:
        await _configured_project(db)
        await _conversation(db, lifecycle="archived")

    assert await _compaction() is None
    assert not spend.generated.called


async def test_a_dismissed_conversation_is_not_warned_again_even_at_96_percent(app, spend):
    """Without a compaction this is the final-warning backstop at >=92%. After the compaction
    the loss has happened; the run's `compacted` card is the notice."""
    async with async_session_factory() as db:
        await _configured_project(db, checkpoint_mode="offered")
        await _conversation(db, checkpoint_warning="dismissed")

    assert await _compaction(percent=96.0) is None
    conversation, _ = await _state()
    assert conversation.checkpoint_warning == "dismissed"
    assert _due(spend) == []
    assert not spend.generated.called


async def test_the_same_dismissed_conversation_does_get_its_final_warning_from_a_reading(
    app, spend
):
    """The control for the row above: the reading path still raises the backstop."""
    async with async_session_factory() as db:
        await _configured_project(db, checkpoint_mode="offered")
        await _conversation(db, checkpoint_warning="dismissed")

    await consider(PROJECT, AGENT, "conv-1", context_tokens=None, percent=96.0)
    conversation, _ = await _state()
    assert conversation.checkpoint_warning == "final"


async def test_a_handed_over_conversation_spends_nothing_on_a_compaction(app, spend):
    async with async_session_factory() as db:
        await _configured_project(db)
        await _handed_over_and_reopened(db)

    assert await _compaction() is None
    conversation, entries = await _state()
    assert entries == [], "no notes requested"
    assert _due(spend) == []
    assert not spend.generated.called


async def test_no_notes_are_requested_in_the_notes_band_and_automatic_still_generates(app, spend):
    """At 72% a reading asks for notes (`checkpoint_notes_value` 70). A compaction does not: notes
    written now would be written from the runner's summary."""
    async with async_session_factory() as db:
        await _configured_project(db)
        await _conversation(db)

    assert await _compaction(percent=72.0) == "ckpt-c"
    _conversation_row, entries = await _state()
    assert entries == []
    assert spend.generated.await_args.kwargs["trigger"] == "context_pressure"


async def test_automatic_generates_and_hands_over_below_its_threshold(app, spend):
    """The threshold (80%) is not consulted: it exists to act before the runner compacts."""
    async with async_session_factory() as db:
        await _configured_project(db)
        await _conversation(db)

    assert await _compaction(percent=10.0) == "ckpt-c"
    assert spend.generated.await_count == 1
    assert spend.generated.await_args.kwargs["trigger"] == "context_pressure"
    assert spend.handed_over.await_count == 1
    assert [event for event, _ in spend.broadcasts] == ["conversation_cut_over"]


async def test_the_reading_path_below_threshold_still_declines(app, spend):
    """The control for the row above."""
    async with async_session_factory() as db:
        await _configured_project(db)
        await _conversation(db)

    assert await consider(PROJECT, AGENT, "conv-1", context_tokens=None, percent=10.0) is None
    assert not spend.generated.called


async def test_nothing_new_since_the_last_checkpoint_declines_a_compaction(app, spend):
    async with async_session_factory() as db:
        await _configured_project(db)
        conversation = await _conversation(db)
        db.add(
            Run(
                id="run-c1",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-1",
                status="completed",
            )
        )
        await db.commit()
        checkpoint = await _ready_checkpoint(db, conversation)
        assert checkpoint.covers_through_run_id == "run-c1"

    assert await _compaction() is None
    assert not spend.generated.called


async def test_offered_warns_after_a_compaction_and_spends_nothing(app, spend):
    async with async_session_factory() as db:
        await _configured_project(db, checkpoint_mode="offered")
        await _conversation(db)

    assert await _compaction(percent=10.0) is None
    conversation, _ = await _state()
    assert conversation.checkpoint_warning == "due"
    assert len(_due(spend)) == 1
    assert "compacted" not in _due(spend)[0], "no UI reads such a flag (D4, R2)"
    assert not spend.generated.called


async def test_automatic_with_no_checkpoint_runner_generates_nothing(app, spend):
    async with async_session_factory() as db:
        await _configured_project(db, checkpoint_runner_id=None)
        await _conversation(db)

    assert await _compaction() is None
    assert not spend.generated.called


async def test_a_compaction_arriving_mid_consideration_waits_and_is_never_concurrent(
    app, monkeypatch
):
    """A reading's consideration is in flight; a compaction arrives. It is not dropped: once the
    running task ends, `consider` is called with `compacted=True` -- and never while the first is
    still running. A plain copy of `consider_from_reading`'s early return drops it."""
    release = asyncio.Event()
    calls = []
    running = []

    async def fake_consider(project_id, agent_name, conversation_id, **kwargs):
        running.append(conversation_id)
        assert len(running) == 1, "two considerations of one conversation ran at once"
        calls.append(kwargs)
        if not kwargs.get("compacted"):
            await release.wait()
        running.pop()

    monkeypatch.setattr(checkpoint_trigger, "consider", fake_consider)
    checkpoint_trigger.consider_from_reading(PROJECT, AGENT, "conv-mid", {"percent": 50.0})
    await asyncio.sleep(0)
    assert "conv-mid" in checkpoint_trigger._in_flight

    consider_from_compaction(PROJECT, AGENT, "conv-mid", {"phase": "compacted", "percent": 81.0})
    await asyncio.sleep(0.01)
    assert [c.get("compacted") for c in calls] == [False], "it waits for the reading"

    release.set()
    for _ in range(20):
        await asyncio.sleep(0.01)
        if len(calls) == 2:
            break

    assert [c.get("compacted") for c in calls] == [False, True]
    assert calls[1]["percent"] == 81.0
    await asyncio.sleep(0.01)
    assert "conv-mid" not in checkpoint_trigger._in_flight
    assert "conv-mid" not in checkpoint_trigger._compaction_pending


async def test_a_compaction_with_no_running_loop_is_dropped_cleanly():
    """No route reaches this (an ASGI app always runs in a loop), so it is a direct synchronous
    call: nothing is left marked in flight or pending."""

    def call():
        return consider_from_compaction(PROJECT, AGENT, "conv-sync", {"phase": "compacted"})

    assert await asyncio.to_thread(call) is None
    assert "conv-sync" not in checkpoint_trigger._in_flight
    assert "conv-sync" not in checkpoint_trigger._compaction_pending


# --------------------------------------------------------------------------- 1.5 the funnel


@pytest.fixture
def seen(monkeypatch):
    calls = []

    async def fake_consider(project_id, agent_name, conversation_id, **kwargs):
        calls.append({"conversation_id": conversation_id, **kwargs})

    monkeypatch.setattr(checkpoint_trigger, "consider", fake_consider)
    return calls


async def _settle():
    for _ in range(5):
        await asyncio.sleep(0)


async def test_a_recorded_compaction_dispatches_with_the_runs_conversation(app, seen):
    from hub.output_recording import record_agent_output

    async with async_session_factory() as db:
        await _conversation(db, "conv-run")
        db.add(
            Run(
                id="run-cmp",
                project_id=PROJECT,
                agent=AGENT,
                conversation_id="conv-run",
                status="running",
            )
        )
        await db.commit()
        await record_agent_output(
            db,
            PROJECT,
            AGENT,
            content="Copilot compacted this conversation automatically.",
            session_id=None,
            kind="status",
            payload={"version": 1, "phase": "compacted", "percent": 83.5},
            run_id="run-cmp",
        )
        await _settle()

    assert seen == [
        {"conversation_id": "conv-run", "context_tokens": None, "percent": 83.5, "compacted": True}
    ]


async def test_a_status_with_another_phase_dispatches_nothing(app, seen):
    from hub.output_recording import record_agent_output

    async with async_session_factory() as db:
        await _conversation(db, "conv-other")
        await record_agent_output(
            db,
            PROJECT,
            AGENT,
            content="Plan",
            session_id=None,
            conversation_id="conv-other",
            kind="status",
            payload={"version": 1, "phase": "plan"},
        )
        await _settle()

    assert seen == []


async def test_a_consideration_that_raises_does_not_change_what_the_route_answers(
    app, auth_headers, monkeypatch
):
    async def boom(*_a, **_k):
        raise RuntimeError("consideration failed")

    monkeypatch.setattr(checkpoint_trigger, "consider", boom)
    response = await app.post(
        f"/api/v1/projects/{PROJECT}/agents/cmp-route/output",
        json={"content": "compacted", "kind": "status", "payload": {"phase": "compacted"}},
        headers=auth_headers,
    )
    await _settle()

    assert response.status_code == 201
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(AgentOutput).where(AgentOutput.agent == "cmp-route")))
            .scalars()
            .all()
        )
    assert len(rows) == 1


async def test_a_dispatch_that_raises_does_not_change_what_the_route_answers(
    app, auth_headers, monkeypatch
):
    """Raising in the dispatch itself, not inside the dispatched task: the row is committed
    first, so a raise would answer 500 for a stored row and a retry would store it twice."""

    def boom(*_a, **_k):
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr(checkpoint_trigger, "consider_from_compaction", boom)
    response = await app.post(
        f"/api/v1/projects/{PROJECT}/agents/cmp-route2/output",
        json={"content": "compacted", "kind": "status", "payload": {"phase": "compacted"}},
        headers=auth_headers,
    )
    assert response.status_code == 201


async def test_a_status_with_no_payload_is_stored_once(app, auth_headers, seen):
    response = await app.post(
        f"/api/v1/projects/{PROJECT}/agents/cmp-null/output",
        json={"content": "status", "kind": "status", "payload": None},
        headers=auth_headers,
    )
    await _settle()

    assert response.status_code == 201
    assert seen == []
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(AgentOutput).where(AgentOutput.agent == "cmp-null")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
