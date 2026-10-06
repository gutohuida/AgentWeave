"""F489: a Copilot turn that failed in a way a retry cannot fix is not retried.

One operator message to a Copilot agent whose key was invalid made three runs, each ending in the
same `copilot.authentication` error, before the Hub gave up. The decision
(`spec-queue/DECISIONS.md` `f489-retry-signal`, option a): Copilot's root `session.error` with
`errorType` `authentication` or `quota` sets `TurnOutcome.retryable = False`; the RPC executor
passes it to `return_run_entries`, which withdraws the entry at once with its own reason. Every
other failure keeps today's retry behaviour.
"""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

import hub.api.v1.agent_trigger as agent_trigger
from hub.copilot_acp import TurnOutcome, run_turn
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, InboundQueueEntry, Run

from .test_a_refused_turn_holds_the_queue import (  # noqa: F401 - fixture
    _copilot_agent,
    _copilot_installed,
)
from .test_copilot_acp_run_turn import (
    AGENT_NAME,
    SESSION_ID,
    WORK,
    _collector,
    _FakeACPSession,
    _patch_spawn,
    _session_established_script,
)


def _session_error(error_type):
    return {
        "notification": "github.com/copilot/sessionEvent",
        "params": {
            "sessionId": SESSION_ID,
            "type": "session.error",
            "timestamp": "2026-10-04T00:00:09.000Z",
            "data": {"errorType": error_type, "message": "Authorization error", "statusCode": 401},
        },
    }


async def _turn_with_root_error(monkeypatch, error_type):
    script = _session_established_script(
        tail_entries=[
            _session_error(error_type),
            {"response": {"stopReason": "end_turn", "usage": {"inputTokens": 1}}},
        ]
    )
    _patch_spawn(monkeypatch, _FakeACPSession(script))
    return await run_turn(
        cwd=WORK,
        env=None,
        prompt="hello",
        model=None,
        resume_session_id=None,
        agent=AGENT_NAME,
        per_turn_context="## Workspace\n- root: C:\\work",
        tool_surface_context="## Tools\n- agentweave-send_message",
        stable_context=None,
        control_overrides=None,
        told_access_path="mcp",
        permission_mode=None,
        workspace=WORK,
        restrict_spec_writes=False,
        extra_flags=None,
        on_event=_collector([]),
        on_session=_collector([]),
    )


@pytest.mark.parametrize("error_type", ["authentication", "quota"])
async def test_an_authentication_or_quota_error_is_not_retryable(monkeypatch, error_type):
    outcome = await _turn_with_root_error(monkeypatch, error_type)
    assert outcome.status == "failed"
    assert outcome.retryable is False
    assert outcome.error_kind == error_type


async def test_any_other_session_error_keeps_todays_retry(monkeypatch):
    outcome = await _turn_with_root_error(monkeypatch, "model_error")
    assert outcome.status == "failed"
    assert outcome.retryable is None


def _failing_turn(**fields):
    async def _run(**kwargs):
        await kwargs["on_session"]("sess-f489")
        return TurnOutcome(session_id="sess-f489", status="failed", error="401", **fields)

    return AsyncMock(side_effect=_run)


async def _send(app, auth_headers, agent, fake):
    from unittest.mock import patch

    with patch("hub.copilot_acp.run_turn", fake):
        response = await app.post(
            "/api/v1/projects/proj-test/agent/trigger",
            json={"agent": agent, "message": "please do it", "session_mode": "new"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        # The real scheduler: a returned entry is re-delivered, so a retry shows as a call.
        for _ in range(10):
            if not agent_trigger._background_runs:
                break
            for task in list(agent_trigger._background_runs):
                await task
    return response.json()["run_id"]


async def _entries(agent):
    async with async_session_factory() as db:
        result = await db.execute(select(InboundQueueEntry).where(InboundQueueEntry.agent == agent))
        return list(result.scalars().all())


async def test_an_unretryable_copilot_failure_is_withdrawn_after_one_run(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    agent = "f489-auth"
    await _copilot_agent(app, auth_headers, bind_runner, agent)
    fake = _failing_turn(retryable=False, error_kind="authentication")

    run_id = await _send(app, auth_headers, agent, fake)

    assert fake.await_count == 1, "an authentication failure must not be retried"
    [entry] = await _entries(agent)
    assert entry.state == "withdrawn"
    assert entry.delivery_attempts == 1
    assert entry.delivered_in_run_id == run_id
    assert "authentication" in entry.abandoned_reason
    assert "not retry" in entry.abandoned_reason
    async with async_session_factory() as db:
        assert (await db.get(Run, run_id)).status == "failed"
        events = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "queue_entry_abandoned")
                )
            )
            .scalars()
            .all()
        )
    assert [e.data["entry_id"] for e in events] == [entry.id]


async def test_a_retryable_copilot_failure_is_still_retried(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    agent = "f489-model"
    await _copilot_agent(app, auth_headers, bind_runner, agent)
    fake = _failing_turn()

    await _send(app, auth_headers, agent, fake)

    assert fake.await_count == 3, "today's three attempts are unchanged for other failures"
    [entry] = await _entries(agent)
    assert entry.state == "withdrawn"
    assert entry.delivery_attempts == 3


async def test_a_quota_failure_with_a_reset_ahead_is_held_not_withdrawn(
    app, auth_headers, bind_runner, _copilot_installed  # noqa: F811
):
    """The refusal wins: a spent allowance with a stated reset is a wait, not a give-up."""
    import time

    from .test_a_refused_turn_holds_the_queue import _rejected_copilot_sample

    agent = "f489-quota"
    await _copilot_agent(app, auth_headers, bind_runner, agent)
    sample = _rejected_copilot_sample(int(time.time()) + 3600)

    async def _run(**kwargs):
        await kwargs["on_session"]("sess-f489q")
        await kwargs["on_accounting"](sample)
        return TurnOutcome(
            session_id="sess-f489q",
            status="failed",
            error="quota",
            retryable=False,
            error_kind="quota",
        )

    fake = AsyncMock(side_effect=_run)
    await _send(app, auth_headers, agent, fake)

    assert fake.await_count == 1
    [entry] = await _entries(agent)
    assert entry.state == "queued"
    assert entry.delivery_attempts == 0
    assert entry.allowance_refusals == 1
