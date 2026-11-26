"""A task reads "Preparing checkout" from its checkout's start until its run's row exists (TSBVD-10).

The checkout is written some way before the trigger writes the run, and in between the task had
neither: the build view drew Preparing checkout -> Not started -> Building, and the board, reading
at another instant, disagreed with it (task_stage_drive, 2026-11-26).
"""

from __future__ import annotations

import pytest

from hub import workspace_preparation
from hub.api.v1 import agent_trigger

P = "proj-prep-hold"
TASK = "task-00000000hold"


async def _prepare(ok: bool = True) -> None:
    try:
        async with workspace_preparation.preparing(
            P, agent="D", task_id=TASK, conversation_id="conv-hold"
        ):
            if not ok:
                raise RuntimeError("git failed")
    except RuntimeError:
        pass


@pytest.fixture
def events(monkeypatch):
    sent: list = []

    async def broadcast(project_id, event, data):
        sent.append((event, data["task_id"], data.get("ok")))

    monkeypatch.setattr(workspace_preparation.sse_manager, "broadcast", broadcast)
    yield sent
    workspace_preparation._live.clear()


@pytest.mark.asyncio
async def test_a_checkout_written_stays_preparing_until_the_trigger_ends(events):
    async with workspace_preparation.holding_until_started():
        await _prepare()
        # The checkout is written and the run not yet: still preparing, and not yet announced done.
        assert TASK in workspace_preparation.preparing_task_ids(P)
        assert events == [("workspace_preparing", TASK, None)]
    assert TASK not in workspace_preparation.preparing_task_ids(P)
    assert events[-1] == ("workspace_prepared", TASK, True)


@pytest.mark.asyncio
async def test_a_checkout_that_failed_ends_at_once(events):
    async with workspace_preparation.holding_until_started():
        await _prepare(ok=False)
        assert TASK not in workspace_preparation.preparing_task_ids(P)
        assert events[-1] == ("workspace_prepared", TASK, False)
    assert len(events) == 2


@pytest.mark.asyncio
async def test_outside_a_trigger_a_preparation_ends_with_its_block(events):
    await _prepare()
    assert TASK not in workspace_preparation.preparing_task_ids(P)
    assert events[-1] == ("workspace_prepared", TASK, True)


@pytest.mark.asyncio
async def test_the_trigger_holds_the_preparation_until_it_returns(events, monkeypatch):
    seen: dict = {}

    async def fake_trigger(**kwargs):
        await _prepare()
        # Where the real trigger renders the context, binds the task and writes the run.
        seen["after_checkout"] = TASK in workspace_preparation.preparing_task_ids(P)
        return "started"

    monkeypatch.setattr(agent_trigger, "_trigger_agent_directly", fake_trigger)
    assert await agent_trigger.trigger_agent_directly() == "started"
    assert seen["after_checkout"] is True
    assert TASK not in workspace_preparation.preparing_task_ids(P)


@pytest.mark.asyncio
async def test_a_refused_trigger_still_ends_the_preparation(events, monkeypatch):
    async def fake_trigger(**kwargs):
        await _prepare()
        raise agent_trigger.TriggerAgentError(409, "refused after the checkout")

    monkeypatch.setattr(agent_trigger, "_trigger_agent_directly", fake_trigger)
    with pytest.raises(agent_trigger.TriggerAgentError):
        await agent_trigger.trigger_agent_directly()
    assert TASK not in workspace_preparation.preparing_task_ids(P)
    assert events[-1] == ("workspace_prepared", TASK, True)
