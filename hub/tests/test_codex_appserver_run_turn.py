"""Tests for codex_appserver.run_turn — the per-turn orchestrator.

`run_turn` hardcodes spawning `[cli, "app-server"]` (task 2.1's per-turn-process design), so
it can't be pointed at a stand-in script the way `AppServerProcess` itself is tested
(`test_codex_appserver_process.py`). Instead these patch `AppServerProcess.spawn` to return a
scripted fake session — the same real message sequences captured live in
`testbed/scratch/probe_appserver_turn.py` and `probe_appserver_approval.py`, replayed through
`run_turn`'s actual notification-handling loop rather than a fresh guess at the shapes.
"""

import asyncio

import pytest

from hub import codex_appserver
from hub.codex_appserver import TurnOutcome, run_turn


class _FakeSession:
    """Drives `run_turn` through a scripted request/response and notification sequence.

    `responses` maps method name -> the `result` dict `request()` should return.
    `notifications` is consumed in order by `next_notification()`.
    """

    def __init__(self, responses, notifications):
        self._responses = dict(responses)
        self._notifications = list(notifications)
        self.sent_requests = []
        self.sent_responses = []
        self._running = True
        self.closed_with_force = None

    async def request(self, method, params, timeout=30.0):
        self.sent_requests.append((method, params))
        return {"id": 0, "result": self._responses[method]}

    async def notify(self, method, params):
        pass

    async def respond(self, request_id, result):
        self.sent_responses.append((request_id, result))

    async def next_notification(self, timeout=None):
        if not self._notifications:
            await asyncio.sleep(0)
            raise asyncio.TimeoutError()
        return self._notifications.pop(0)

    def is_running(self):
        return self._running

    async def close(self, force=False):
        self._running = False
        self.closed_with_force = force


def _patch_spawn(monkeypatch, fake_session):
    async def _fake_spawn(cmd, *, cwd=None, env=None):
        return fake_session

    monkeypatch.setattr(codex_appserver.AppServerProcess, "spawn", _fake_spawn)


async def _noop(item):
    pass


def _collector(target_list):
    async def _append(item):
        target_list.append(item)

    return _append


THREAD_START_RESULT = {"thread": {"id": "019fd61e-d230-7d61-8d80-5cf5840c94f8"}}
TURN_START_RESULT = {"turn": {"id": "019fd61e-d2fe-7281-a345-b80af4674630"}}

# Trimmed from a real captured sequence (probe_appserver_turn.py): agentMessage -> commandExecution
# -> tokenUsage -> final agentMessage -> turn/completed.
_HAPPY_PATH_NOTIFICATIONS = [
    {
        "method": "item/completed",
        "params": {"item": {"type": "agentMessage", "text": "I'm on it.", "phase": "commentary"}},
    },
    {
        "method": "item/started",
        "params": {"item": {"type": "commandExecution", "id": "call_1", "command": "echo hi"}},
    },
    {
        "method": "item/completed",
        "params": {
            "item": {
                "type": "commandExecution",
                "id": "call_1",
                "aggregatedOutput": "hi\n",
                "exitCode": 0,
            }
        },
    },
    {
        "method": "thread/tokenUsage/updated",
        "params": {
            "tokenUsage": {
                "last": {"inputTokens": 100, "outputTokens": 10},
                "modelContextWindow": 200000,
            }
        },
    },
    {
        "method": "item/completed",
        "params": {"item": {"type": "agentMessage", "text": "OK", "phase": "final_answer"}},
    },
    {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
]


class TestRunTurnHappyPath:
    @pytest.mark.asyncio
    async def test_completed_turn_emits_events_in_order_and_returns_completed(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=list(_HAPPY_PATH_NOTIFICATIONS),
        )
        _patch_spawn(monkeypatch, fake)

        events = []
        usages = []
        accountings = []

        outcome = await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="do the thing",
            model="gpt-5.4-mini",
            resume_thread_id=None,
            yolo=False,
            mcp_command=None,
            on_event=_collector(events),
            on_usage=_collector(usages),
            on_accounting=_collector(accountings),
        )

        assert outcome == TurnOutcome(
            thread_id="019fd61e-d230-7d61-8d80-5cf5840c94f8", status="completed", error=None
        )
        kinds = [e.kind for e in events]
        assert kinds == ["text", "tool_use", "tool_result", "text"]
        assert usages[0].limit_tokens == 200000
        assert accountings[0].total_tokens is not None or accountings[0].input_tokens == 100
        assert fake.closed_with_force is False

    @pytest.mark.asyncio
    async def test_resume_uses_thread_resume_not_thread_start(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/resume": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[{"method": "turn/completed", "params": {"turn": {"status": "completed"}}}],
        )
        _patch_spawn(monkeypatch, fake)

        await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="continue",
            model=None,
            resume_thread_id="019fd481-71f1-7e90-98dc-9033753492bc",
            yolo=False,
            mcp_command=None,
            on_event=_noop,
        )

        methods_called = [m for m, _ in fake.sent_requests]
        assert "thread/resume" in methods_called
        assert "thread/start" not in methods_called
        resume_params = next(p for m, p in fake.sent_requests if m == "thread/resume")
        assert resume_params["threadId"] == "019fd481-71f1-7e90-98dc-9033753492bc"

    @pytest.mark.asyncio
    async def test_mcp_command_is_registered_in_thread_start_config(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[{"method": "turn/completed", "params": {"turn": {"status": "completed"}}}],
        )
        _patch_spawn(monkeypatch, fake)

        await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=False,
            mcp_command=["python", "mcp_server.py"],
            on_event=_noop,
        )

        start_params = next(p for m, p in fake.sent_requests if m == "thread/start")
        mcp_config = start_params["config"]["mcp_servers"]["agentweave"]
        assert mcp_config["command"] == "python"
        assert mcp_config["args"] == ["mcp_server.py"]
        assert "HUB_URL" in mcp_config["env_vars"]


class TestRunTurnServerRequests:
    @pytest.mark.asyncio
    async def test_command_approval_is_answered_via_decide_approval(self, monkeypatch):
        # Real captured shape (probe_appserver_approval.py), minus the fields run_turn ignores.
        approval_request = {
            "id": 0,
            "method": "item/commandExecution/requestApproval",
            "params": {"command": "write outside workspace"},
        }
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                approval_request,
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
            ],
        )
        _patch_spawn(monkeypatch, fake)

        await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=False,
            mcp_command=None,
            on_event=_noop,
        )

        assert fake.sent_responses == [(0, {"decision": "decline"})]

    @pytest.mark.asyncio
    async def test_yolo_approves_command_execution(self, monkeypatch):
        approval_request = {
            "id": 0,
            "method": "item/commandExecution/requestApproval",
            "params": {},
        }
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                approval_request,
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
            ],
        )
        _patch_spawn(monkeypatch, fake)

        await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=True,
            mcp_command=None,
            on_event=_noop,
        )

        assert fake.sent_responses == [(0, {"decision": "accept"})]


class TestRunTurnFailureModes:
    @pytest.mark.asyncio
    async def test_turn_failed_notification_is_reported(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                {"method": "turn/failed", "params": {"error": {"message": "model unavailable"}}}
            ],
        )
        _patch_spawn(monkeypatch, fake)

        events = []
        outcome = await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=False,
            mcp_command=None,
            on_event=_collector(events),
        )

        assert outcome.status == "failed"
        assert "model unavailable" in outcome.error
        assert events[0].kind == "error"

    @pytest.mark.asyncio
    async def test_process_death_mid_turn_fails_fast_not_after_full_timeout(self, monkeypatch):
        """Task 2.7: process death mid-turn must not hang for the full turn_timeout."""
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[],  # process "dies" before anything else arrives
        )
        fake._running = False  # simulate the process having already exited
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=False,
            mcp_command=None,
            on_event=_noop,
            turn_timeout=120.0,  # would hang 2 minutes if death weren't detected
        )

        assert outcome.status == "failed"
        assert "ended" in outcome.error

    @pytest.mark.asyncio
    async def test_timeout_fails_and_closes_session(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[],  # nothing ever arrives
        )
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=False,
            mcp_command=None,
            on_event=_noop,
            turn_timeout=0.3,
        )

        assert outcome.status == "failed"
        assert "timed out" in outcome.error
        assert fake.is_running() is False


class TestRunTurnInterrupt:
    @pytest.mark.asyncio
    async def test_should_interrupt_sends_turn_interrupt_and_force_closes(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
                "turn/interrupt": {},
            },
            notifications=[{"method": "turn/completed", "params": {"turn": {"status": "completed"}}}],
        )
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=False,
            mcp_command=None,
            on_event=_noop,
            should_interrupt=lambda: True,
        )

        assert outcome.status == "interrupted"
        assert "turn/interrupt" in [m for m, _ in fake.sent_requests]
        assert fake.closed_with_force is True
