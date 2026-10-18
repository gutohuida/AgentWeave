"""F678 acceptance (spdoc-7f874f103d5b): a Claude turn records its own cost and tokens, not its
session's running total, and its tokens include its subagents'.

The two first result lines are real, measured 2026-10-18 on Claude Code 2.1.301 with Haiku 5.5
(`claude -p`, then `claude -p --resume` on the same session): `total_cost_usd` and `modelUsage`
are the session's running totals, `usage` is the turn's own main-thread calls. The third continues
the same session by the same arithmetic. Driven through the real trigger, one run per turn, in the
order the CLI emits its lines (`system/init` first, `result` last).
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Run, TurnUsage
from tests.test_agent_trigger import _await_background_run, _fake_pty

SESSION = "a9b7362d-380e-4256-883f-caaff3ec26b7"


def _init(version, session=SESSION):
    return json.dumps(
        {
            "type": "system",
            "subtype": "init",
            "session_id": session,
            "claude_code_version": version,
            "tools": [],
            "mcp_servers": [],
        }
    )


def _result(cost, usage, model_usage, session=SESSION):
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "session_id": session,
            "num_turns": 1,
            "total_cost_usd": cost,
            "usage": usage,
            "modelUsage": {
                "claude-haiku-5-5": {**model_usage, "contextWindow": 1000000, "costUSD": cost}
            },
        }
    )


TURNS = [
    _result(
        0.00272106,
        {
            "input_tokens": 2,
            "cache_creation_input_tokens": 12700,
            "cache_read_input_tokens": 16536,
            "output_tokens": 31,
        },
        {
            "inputTokens": 2,
            "outputTokens": 31,
            "cacheReadInputTokens": 16536,
            "cacheCreationInputTokens": 12700,
        },
    ),
    _result(
        0.00302972,
        {
            "input_tokens": 2,
            "cache_creation_input_tokens": 68,
            "cache_read_input_tokens": 29236,
            "output_tokens": 5,
        },
        {
            "inputTokens": 4,
            "outputTokens": 36,
            "cacheReadInputTokens": 45772,
            "cacheCreationInputTokens": 12768,
        },
    ),
    _result(
        0.00333386,
        {
            "input_tokens": 2,
            "cache_creation_input_tokens": 42,
            "cache_read_input_tokens": 29328,
            "output_tokens": 5,
        },
        {
            "inputTokens": 6,
            "outputTokens": 41,
            "cacheReadInputTokens": 75100,
            "cacheCreationInputTokens": 12810,
        },
    ),
]


async def _turn(app, auth_headers, agent, lines):
    """One run; a later turn continues the agent's conversation, which resumes its session."""
    body = {"agent": agent, "message": "hi"}
    async with async_session_factory() as db:
        earlier = (
            await db.execute(
                select(Run.conversation_id)
                .where(Run.agent == agent)
                .order_by(Run.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    if earlier:
        body["conversation_id"] = earlier
    fake_spawn = _fake_pty([line + "\n" for line in lines])
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            resp = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json=body,
                headers=auth_headers,
            )
            assert resp.status_code == 200, resp.text
            run_id = resp.json()["run_id"]
            await _await_background_run()
    return run_id


async def _usage(run_id):
    async with async_session_factory() as db:
        usage = (await db.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))).scalar_one()
        run = await db.get(Run, run_id)
        return usage, run


async def _agent(app, auth_headers, bind_runner, name):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {name: {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner(name, cli="claude")


@pytest.mark.asyncio
async def test_three_turns_of_one_session_each_record_their_own_cost(
    app, auth_headers, bind_runner
):
    await _agent(app, auth_headers, bind_runner, "cost-claude")
    runs = [await _turn(app, auth_headers, "cost-claude", [_init("2.1.301"), t]) for t in TURNS]
    rows = [await _usage(run_id) for run_id in runs]

    assert [run.runner_version for _, run in rows] == ["2.1.301"] * 3
    assert [u.api_equivalent_usd_micros for u, _ in rows] == [2721, 309, 304]
    assert [u.output_tokens for u, _ in rows] == [31, 5, 5]
    assert [u.cache_read_tokens for u, _ in rows] == [16536, 29236, 29328]
    assert [u.cache_write_tokens for u, _ in rows] == [12700, 68, 42]
    # Fresh input plus both cache dimensions, as the per-turn `usage` reading always was.
    assert [u.input_tokens for u, _ in rows] == [29238, 29306, 29372]
    assert [u.total_tokens for u, _ in rows] == [29269, 29311, 29377]


@pytest.mark.asyncio
async def test_a_subagents_tokens_are_counted(app, auth_headers, bind_runner):
    """Research 09-27's subagent probe: `usage` wrote 9,156 cache tokens, `modelUsage` 25,753
    (the subagent's own 15,637 included)."""
    await _agent(app, auth_headers, bind_runner, "sub-claude")
    run_id = await _turn(
        app,
        auth_headers,
        "sub-claude",
        [
            _init("2.1.301", session="sess-sub"),
            _result(
                0.05539,
                {
                    "input_tokens": 6,
                    "cache_creation_input_tokens": 9156,
                    "cache_read_input_tokens": 44006,
                    "output_tokens": 200,
                },
                {
                    "inputTokens": 9,
                    "outputTokens": 400,
                    "cacheReadInputTokens": 70884,
                    "cacheCreationInputTokens": 25753,
                },
                session="sess-sub",
            ),
        ],
    )
    usage, _ = await _usage(run_id)
    assert usage.cache_write_tokens == 25753
    assert usage.output_tokens == 400


@pytest.mark.asyncio
async def test_an_older_cli_reports_per_process_and_is_recorded_as_reported(
    app, auth_headers, bind_runner
):
    await _agent(app, auth_headers, bind_runner, "old-claude")
    runs = [await _turn(app, auth_headers, "old-claude", [_init("2.1.270"), t]) for t in TURNS[:2]]
    rows = [await _usage(run_id) for run_id in runs]
    assert [u.api_equivalent_usd_micros for u, _ in rows] == [2721, 3030]
    assert [u.output_tokens for u, _ in rows] == [31, 36]


@pytest.mark.asyncio
async def test_a_session_whose_earlier_turns_carry_no_totals_records_no_cost_once(
    app, auth_headers, bind_runner
):
    """A session that began before the Hub kept totals has no baseline: its running total is not
    this turn's, so the turn keeps its own `usage` tokens and records no cost, then keeps its
    totals so the turn after differences correctly."""
    await _agent(app, auth_headers, bind_runner, "legacy-claude")
    first = await _turn(app, auth_headers, "legacy-claude", [_init("2.1.301"), TURNS[0]])
    async with async_session_factory() as db:
        row = (await db.execute(select(TurnUsage).where(TurnUsage.run_id == first))).scalar_one()
        row.session_totals = None  # as every row written before this change
        await db.commit()

    second = await _turn(app, auth_headers, "legacy-claude", [_init("2.1.301"), TURNS[1]])
    third = await _turn(app, auth_headers, "legacy-claude", [_init("2.1.301"), TURNS[2]])
    second_usage, _ = await _usage(second)
    third_usage, _ = await _usage(third)
    assert second_usage.api_equivalent_usd_micros is None
    assert second_usage.output_tokens == 5
    assert second_usage.session_totals is not None
    assert third_usage.api_equivalent_usd_micros == 304
    assert third_usage.output_tokens == 5
