"""Streamed output lines are on screen at once, written in batches, and all stored before the run
is reported finished.

`turn-starts-approvals-and-evidence-never-freeze-the-hub`: FR-4 (line-cost) and FR-5
(line-visible-and-durable). Measured before this change: about 5 ms of event-loop time per line,
from a session, two reads, an insert, a whole rewrite of the run's chat span and a commit for every
line (and, on Claude, a re-binding of the provider session on every line as well).

The cost half is asserted as database statements per line rather than milliseconds: each
statement is a round trip the loop pays for, and a count does not depend on how fast the machine
running the suite is. The drive (`scripts/drive/perf_loop_lag.py`) measures the milliseconds.
"""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest
from sqlalchemy import event, select

from hub.db.engine import async_session_factory, engine
from hub.db.models import AgentOutput, Run
from hub.sse import sse_manager

from ._background_runs import await_background_runs
from .test_agent_trigger import _fake_pty

SESSION = "sess-batched"


def _lines(count: int) -> list:
    lines = [json.dumps({"type": "system", "subtype": "init", "session_id": SESSION})]
    for i in range(count):
        block = {"type": "text", "text": f"line {i}"}
        lines.append(
            json.dumps(
                {"type": "assistant", "session_id": SESSION, "message": {"content": [block]}}
            )
        )
    lines.append(json.dumps({"type": "result", "subtype": "success", "session_id": SESSION}))
    return [line + "\n" for line in lines]


async def _run(app, auth_headers, bind_runner, agent, spawn):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(agent, cli="claude")
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": agent, "message": "work", "session_mode": "new"},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await await_background_runs()
    return response.json()["run_id"]


@pytest.mark.asyncio
async def test_two_hundred_lines_are_all_stored_before_the_run_is_reported_finished(
    app, auth_headers, bind_runner
):
    stored_at_finish = {}
    publish = sse_manager.publish

    async def _count(run_id):
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(AgentOutput.sequence, AgentOutput.content)
                    .where(AgentOutput.run_id == run_id)
                    .order_by(AgentOutput.sequence)
                )
            ).all()
        stored_at_finish[run_id] = rows

    pending = []

    def _watch(project_id, event_type, data):
        if event_type == "run_completed":
            import asyncio

            pending.append(asyncio.ensure_future(_count(data["run_id"])))
        return publish(project_id, event_type, data)

    with patch.object(sse_manager, "publish", _watch):
        run_id = await _run(app, auth_headers, bind_runner, "batched-200", _fake_pty(_lines(200)))
        for task in pending:
            await task
    rows = stored_at_finish[run_id]
    texts = [content for _, content in rows if content.startswith("line ")]
    assert texts == [f"line {i}" for i in range(200)]
    sequences = [sequence for sequence, _ in rows]
    assert sequences == sorted(sequences)
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_a_line_reaches_open_streams_within_250_ms_of_the_hub_receiving_it(
    app, auth_headers, bind_runner
):
    received = {}
    shown = {}
    lines = _lines(5)

    def _spawn(*args, **kwargs):
        session = _fake_pty([])(*args, **kwargs)
        remaining = iter(enumerate([*lines, ""]))

        def _read(*_a, **_k):
            index, line = next(remaining, (None, ""))
            if line:
                time.sleep(0.05)
                received[index] = time.perf_counter()
            return line

        session.read.side_effect = _read
        return session

    publish = sse_manager.publish

    def _watch(project_id, event_type, data):
        if event_type == "agent_output" and str(data.get("content", "")).startswith("line "):
            shown[int(data["content"].split()[1])] = time.perf_counter()
        return publish(project_id, event_type, data)

    with patch.object(sse_manager, "publish", _watch):
        await _run(app, auth_headers, bind_runner, "batched-seen", _spawn)
    # Stream line i + 1 carries "line i" (the first line is the session's `init`).
    lags = [shown[i] - received[i + 1] for i in range(5)]
    assert max(lags) < 0.250, lags


@pytest.mark.asyncio
async def test_streamed_lines_cost_few_statements_each(app, auth_headers, bind_runner):
    """FR-4's proxy: at most one statement per line on average across the whole stream, against
    about six per line before (a session per line, the session re-binding, the new-session read,
    the chat span read and rewrite, the insert and the commit)."""
    statements = []

    def _count(conn, cursor, statement, params, context, executemany):  # noqa: ANN001
        statements.append(statement.split(None, 2)[:2])

    lines = _lines(60)
    counting = {"on": False}

    def _spawn(*args, **kwargs):
        session = _fake_pty([])(*args, **kwargs)
        remaining = iter([*lines, ""])

        def _read(*_a, **_k):
            line = next(remaining, "")
            # Count from the first line read to the run's end, its final write included.
            counting["on"] = counting["on"] or bool(line)
            return line

        session.read.side_effect = _read
        return session

    def _maybe_count(*args):  # noqa: ANN002
        if counting["on"]:
            _count(*args)

    event.listen(engine.sync_engine, "before_cursor_execute", _maybe_count)
    try:
        run_id = await _run(app, auth_headers, bind_runner, "batched-cost", _spawn)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _maybe_count)
    async with async_session_factory() as session:
        stored = (
            await session.execute(select(AgentOutput.id).where(AgentOutput.run_id == run_id))
        ).all()
    assert len(stored) >= 60
    assert len(statements) <= 60, (len(statements), statements[:20])
