"""F697 acceptance (Tier 1, operator decision 2026-10-18): a stopped Claude turn's interrupted
call is estimated, shown as an estimate, and never counted.

A turn stopped mid-call records `turn_usage` `unavailable`, and the CLI's session totals never
include the interrupted call, so it appeared nowhere (`run-02af114595bf`, sweep 2026-10-18). The
interrupted call's input is estimated from the turn's last context reading and recorded on the
unavailable row; the accounting snapshot reports it apart from every measured figure, and the
budget does not count it. Driven through the real trigger and the real stop route, in the order
the CLI emits its lines (`system/init`, then an `assistant` message with its usage).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import TurnUsage
from tests.test_agent_trigger import _await_background_run, _wait_for_active_pty, _wait_released

SESSION = "5f1c0d2e-0a4b-4c1e-9d7a-6b2f3e4a5c6d"

INIT = json.dumps(
    {
        "type": "system",
        "subtype": "init",
        "session_id": SESSION,
        "claude_code_version": "2.1.301",
        "tools": [],
        "mcp_servers": [],
    }
)


# The call that asked for a tool; the next call -- the one the stop interrupts -- would read at
# least this much context.
def _assistant(session=SESSION):
    return json.dumps(
        {
            "type": "assistant",
            "session_id": session,
            "message": {
                "model": "claude-haiku-5-5",
                "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {}}],
                "usage": {
                    "input_tokens": 2,
                    "cache_read_input_tokens": 333000,
                    "cache_creation_input_tokens": 100,
                    "output_tokens": 40,
                },
            },
        }
    )


ASSISTANT = _assistant()
ESTIMATE = 2 + 333000 + 100


def _streams_then_blocks(lines):
    """A fake PtySession that hands out `lines`, then blocks until `.terminate()`."""
    released = threading.Event()
    blocked = threading.Event()
    remaining = iter(lines)

    def _read(size=4096):
        line = next(remaining, None)
        if line is not None:
            return line
        blocked.set()
        _wait_released(released)
        return ""

    session = MagicMock()
    session.pid = 777
    session.read.side_effect = _read
    session.terminate.side_effect = lambda force=False: released.set()
    session.wait.return_value = 15
    return session, blocked


async def _agent(app, auth_headers, bind_runner, name):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner(name, cli="claude")


@pytest.mark.asyncio
async def test_a_stopped_claude_turn_records_an_estimate_that_is_not_counted(
    app, auth_headers, bind_runner
):
    await _agent(app, auth_headers, bind_runner, "stopped-claude")
    session, blocked = _streams_then_blocks([INIT + "\n", ASSISTANT + "\n"])
    with patch(  # noqa: SIM117
        "hub.api.v1.agent_trigger.PtySession.spawn", MagicMock(return_value=session)
    ):
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            trigger = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "stopped-claude", "message": "hi", "session_mode": "new"},
                headers=auth_headers,
            )
            assert trigger.status_code == 200, trigger.text
            run_id = trigger.json()["run_id"]
            await _wait_for_active_pty(run_id)
            deadline = time.monotonic() + 10
            while not blocked.is_set():
                assert time.monotonic() < deadline, "the fake PTY never reached its block"
                await asyncio.sleep(0.01)
            stop = await app.post(
                "/api/v1/projects/proj-test/agent/stopped-claude/stop", headers=auth_headers
            )
            assert stop.status_code == 200, stop.text
            await _await_background_run()

    async with async_session_factory() as db:
        row = (await db.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))).scalar_one()
    assert row.status == "unavailable"
    assert row.total_tokens is None and row.api_equivalent_usd_micros is None
    assert row.estimated_input_tokens == ESTIMATE

    snapshot = await app.get("/api/v1/projects/proj-test/accounting", headers=auth_headers)
    assert snapshot.status_code == 200, snapshot.text
    data = snapshot.json()
    turn = next(t for t in data["recent_turns"] if t["run_id"] == run_id)
    assert turn["status"] == "unavailable"
    assert turn["estimated_input_tokens"] == ESTIMATE
    assert data["project"]["estimated_input_tokens"] == ESTIMATE
    agent = next(a for a in data["agents"] if a["agent"] == "stopped-claude")
    assert agent["estimated_input_tokens"] == ESTIMATE
    # Never counted: not in a measured total, not in the budget.
    assert data["project"]["total_tokens"] is None
    assert data["project"]["input_tokens"] is None
    assert data["budget"]["used_tokens"] == 0


@pytest.mark.asyncio
async def test_a_completed_claude_turn_carries_no_estimate(app, auth_headers, bind_runner):
    from tests.test_a_claude_turn_records_its_own_cost import SESSION as COST_SESSION
    from tests.test_a_claude_turn_records_its_own_cost import TURNS, _init, _turn, _usage

    await _agent(app, auth_headers, bind_runner, "done-claude")
    lines = [_init("2.1.301"), _assistant(COST_SESSION), TURNS[0]]
    run_id = await _turn(app, auth_headers, "done-claude", lines)
    usage, _ = await _usage(run_id)
    assert usage.status == "measured"
    assert usage.estimated_input_tokens is None
