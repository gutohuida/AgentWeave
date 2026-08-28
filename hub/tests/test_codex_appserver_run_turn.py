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

    def __init__(self, responses, notifications, *, returncode=None, stderr_tail=""):
        self._responses = dict(responses)
        self._notifications = list(notifications)
        self.sent_requests = []
        self.sent_responses = []
        self._running = True
        self.closed_with_force = None
        # The real session exposes both, and `run_turn` reports them when a process dies. A fake
        # that omits them would let a regression in that reporting pass unnoticed here.
        self.returncode = returncode
        self._stderr_tail = stderr_tail

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

    def stderr_tail(self, limit=2000):
        return self._stderr_tail

    def process_ended_error(self, message, method=None):
        return codex_appserver.AppServerError(
            message,
            exit_code=self.returncode,
            method=method,
            stderr_tail=self._stderr_tail,
        )

    async def close(self, force=False):
        self._running = False
        self.closed_with_force = force


def _patch_spawn(monkeypatch, fake_session):
    async def _fake_spawn(cmd, *, cwd=None, env=None):
        return fake_session

    # `run_turn` resolves the executable *before* it spawns, so patching `spawn` alone still left
    # these 16 tests requiring a real `codex` on PATH — which every developer machine here has and
    # no CI runner does. They were green locally and had never once run in CI, because `hub-test`
    # was failing at its install step. Resolution is `test_pty_runner`'s subject, not this file's:
    # what is under test here is `run_turn`'s notification-handling loop against a scripted session.
    monkeypatch.setattr(codex_appserver, "resolve_executable", lambda cmd: list(cmd))
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
            notifications=[
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}
            ],
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
    async def test_on_thread_started_fires_before_turn_start_and_before_any_event(
        self, monkeypatch
    ):
        """Task 2.8's integration needs the thread id before any `on_event` call, to bind
        `Conversation.provider_session_id` the same way the `exec` path resolves
        `session_id` before that line's own events are recorded."""
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=list(_HAPPY_PATH_NOTIFICATIONS),
        )
        _patch_spawn(monkeypatch, fake)

        calls = []

        async def _on_thread_started(thread_id):
            calls.append(("thread_started", thread_id))

        async def _on_event(event):
            calls.append(("event", event.kind))

        await run_turn(
            cli="codex",
            cwd="/workspace",
            env=None,
            prompt="hi",
            model=None,
            resume_thread_id=None,
            yolo=False,
            mcp_command=None,
            on_event=_on_event,
            on_thread_started=_on_thread_started,
        )

        assert calls[0] == ("thread_started", "019fd61e-d230-7d61-8d80-5cf5840c94f8")
        assert all(call[0] == "event" for call in calls[1:])
        methods_called = [m for m, _ in fake.sent_requests]
        assert methods_called.index("thread/start") < methods_called.index("turn/start")

    @pytest.mark.asyncio
    async def test_mcp_command_is_registered_in_thread_start_config(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}
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


class TestRunTurnConfigOverrides:
    """F99 — config-style controls reach `thread/start`.

    Codex's Effort control renders to `-c model_reasoning_effort=<value>` in the argv
    `build_command` produces, and app-server ignores argv entirely: it takes the same overrides
    as `thread/start`'s `config` object. Measured live 2026-08-28 against CLI 0.146.0 — a bogus
    value passed this way is rejected by the provider exactly as `codex exec -c` is, and a valid
    one is written to the rollout's `turn_context` as `"effort": "xhigh"`. So the map is honoured,
    and these assert the Hub actually fills it.
    """

    @pytest.mark.asyncio
    async def test_config_overrides_reach_thread_start(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}
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
            config_overrides={"model_reasoning_effort": "xhigh"},
            on_event=_noop,
        )

        start_params = next(p for m, p in fake.sent_requests if m == "thread/start")
        assert start_params["config"]["model_reasoning_effort"] == "xhigh"

    @pytest.mark.asyncio
    async def test_config_overrides_and_mcp_server_share_one_config(self, monkeypatch):
        """The two inputs to `config` are unrelated and must not evict each other — the map used
        to be built only `if mcp_command`, which is the shape that dropped every control."""
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}
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
            mcp_command=["python", "mcp_server.py"],
            config_overrides={"model_reasoning_effort": "high"},
            on_event=_noop,
        )

        config = next(p for m, p in fake.sent_requests if m == "thread/start")["config"]
        assert config["model_reasoning_effort"] == "high"
        assert config["mcp_servers"]["agentweave"]["command"] == "python"

    @pytest.mark.asyncio
    async def test_no_config_key_when_there_is_nothing_to_put_in_it(self, monkeypatch):
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}
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
            config_overrides={},
            on_event=_noop,
        )

        assert "config" not in next(p for m, p in fake.sent_requests if m == "thread/start")


class TestRunTurnMcpStartupFailure:
    """F101 — the Hub's own MCP server failing to start is the loudest thing that can happen
    to a turn, and it used to be the quietest.

    Live capture, 2026-08-28: `mcpServer/startupStatus/updated` reported
    `status: "failed"` with *"MCP client for `agentweave` failed to start: … connection closed:
    initialize response"*, the notification was dropped, the agent answered "Unavailable" when
    asked for an AgentWeave tool, and the run finalised `completed` with `Run.error` NULL. An
    agent with no collaboration surface — no messages, evidence, task updates or questions —
    looked exactly like an agent that had simply done nothing.
    """

    @staticmethod
    def _fake(notifications):
        return _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                *notifications,
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
            ],
        )

    @staticmethod
    def _startup(name, status, error=None):
        return {
            "method": "mcpServer/startupStatus/updated",
            "params": {"name": name, "status": status, "error": error},
        }

    async def _drive(self, monkeypatch, notifications):
        fake = self._fake(notifications)
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
            mcp_command=["python", "mcp_server.py"],
            on_event=_collector(events),
        )
        return outcome, events

    @pytest.mark.asyncio
    async def test_own_server_failing_to_start_is_reported_and_names_the_consequence(
        self, monkeypatch
    ):
        outcome, events = await self._drive(
            monkeypatch,
            [
                self._startup("agentweave", "starting"),
                self._startup(
                    "agentweave",
                    "failed",
                    "MCP client for `agentweave` failed to start: connection closed",
                ),
            ],
        )

        assert [e.kind for e in events] == ["error"]
        assert events[0].payload["code"] == "codex_mcp_server_failed"
        assert "no AgentWeave tools" in events[0].content
        assert "connection closed" in events[0].content
        # Not a turn failure: a model with no tools may still be useful, and that is the
        # operator's call to make — but only if they are told.
        assert outcome.status == "completed"

    @pytest.mark.asyncio
    async def test_a_repeated_failure_notification_is_reported_once(self, monkeypatch):
        """The app-server repeats every startup transition; measured live, twice each."""
        failure = self._startup("agentweave", "failed", "connection closed")
        _, events = await self._drive(monkeypatch, [failure, failure])

        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_starting_ready_and_cancelled_are_not_reported(self, monkeypatch):
        """`cancelled` is on the path a failing server takes to `failed` — reporting it would
        report the same failure twice under two names."""
        _, events = await self._drive(
            monkeypatch,
            [
                self._startup("agentweave", "starting"),
                self._startup("agentweave", "cancelled"),
                self._startup("agentweave", "ready"),
            ],
        )

        assert events == []

    @pytest.mark.asyncio
    async def test_another_servers_failure_is_reported_without_claiming_this_turn_is_toolless(
        self, monkeypatch
    ):
        """`codex_apps` and anything else in the operator's own Codex config: worth saying,
        but it costs this Hub's collaboration surface nothing."""
        _, events = await self._drive(monkeypatch, [self._startup("codex_apps", "failed", "boom")])

        assert len(events) == 1
        assert "codex_apps" in events[0].content
        assert "no AgentWeave tools" not in events[0].content


class TestRunTurnFailureModes:
    @pytest.mark.asyncio
    async def test_turn_completed_with_failed_status_is_a_failure(self, monkeypatch):
        """F100 — `turn/completed` means the turn ENDED, not that it succeeded.

        CLI 0.146.0's `ServerNotification` schema has no `turn/failed` at all; a provider error
        arrives as `turn/completed` carrying `turn.status == "failed"` and a `TurnError`. Reading
        the method name alone reported a 400 as a completed run with zero output and no error.
        This payload is the live one, captured 2026-08-28.
        """
        provider_error = (
            '{"type": "error", "error": {"type": "invalid_request_error", "message": '
            '"[ReasoningEffortParam] [reasoning.effort] [invalid_enum_value] Invalid value."}, '
            '"status": 400}'
        )
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "019fd61e-d230-7d61-8d80-5cf5840c94f8",
                        "turn": {
                            "id": "t1",
                            "items": [],
                            "status": "failed",
                            "error": {"message": provider_error, "codexErrorInfo": "other"},
                        },
                    },
                }
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
        assert "invalid_enum_value" in outcome.error
        assert [e.kind for e in events] == ["error"]

    @pytest.mark.asyncio
    async def test_turn_completed_with_interrupted_status_is_not_a_completion(self, monkeypatch):
        """A turn stopped by something other than this Hub's own `should_interrupt`."""
        fake = _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                {
                    "method": "turn/completed",
                    "params": {"turn": {"id": "t1", "items": [], "status": "interrupted"}},
                }
            ],
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
        )

        assert outcome.status == "interrupted"

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
            notifications=[
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}}
            ],
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


class TestRunTurnReportsRefusals:
    """A refusal this runtime decides by itself has to reach the operator.

    Claude's refusals reach the event log through `approve_tool_call`, which is a
    `--permission-prompt-tool` flag and therefore Claude-only. A Codex agent declined by its own
    sandbox produced nothing: no event, no SSE frame, no line in the timeline. Found live, when a
    reviewing agent was refused permission to write its own review file, said so in prose, and the
    Hub's durable record showed a clean run.

    `decide_approval` stays pure -- `test_codex_appserver.py` asserts that as a table -- so the
    reporting is the caller's, and these cover the caller.
    """

    @staticmethod
    def _approval(method="item/commandExecution/requestApproval", params=None):
        return {"id": 0, "method": method, "params": params or {"command": "rm -rf /"}}

    @staticmethod
    def _session(request):
        return _FakeSession(
            responses={
                "initialize": {},
                "thread/start": THREAD_START_RESULT,
                "turn/start": TURN_START_RESULT,
            },
            notifications=[
                request,
                {"method": "turn/completed", "params": {"turn": {"status": "completed"}}},
            ],
        )

    async def _run(self, monkeypatch, request, **kwargs):
        fake = self._session(request)
        _patch_spawn(monkeypatch, fake)
        refusals = []

        async def _on_refusal(method, subject):
            refusals.append((method, subject))

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
            on_refusal=_on_refusal,
            **kwargs,
        )
        return fake, refusals

    @pytest.mark.asyncio
    async def test_a_decline_is_reported(self, monkeypatch):
        fake, refusals = await self._run(monkeypatch, self._approval())

        assert fake.sent_responses == [(0, {"decision": "decline"})]
        assert len(refusals) == 1
        method, subject = refusals[0]
        assert method == "item/commandExecution/requestApproval"
        assert subject["command"] == "rm -rf /"

    @pytest.mark.asyncio
    async def test_an_outside_workspace_decline_is_reported(self, monkeypatch):
        """The posture that produced the live finding: `workspace`, refusing a path outside it."""
        request = self._approval(params={"command": "ls", "cwd": "/somewhere/else"})
        fake, refusals = await self._run(
            monkeypatch, request, posture="workspace", workspace="/workspace"
        )

        assert fake.sent_responses == [(0, {"decision": "decline"})]
        assert [method for method, _ in refusals] == ["item/commandExecution/requestApproval"]

    @pytest.mark.asyncio
    async def test_an_accepted_action_is_not_reported(self, monkeypatch):
        """An event per allowed action buries the refusals among them."""
        fake, refusals = await self._run(
            monkeypatch,
            self._approval(params={"command": "ls", "cwd": "/workspace/sub"}),
            posture="workspace",
            workspace="/workspace",
        )

        assert fake.sent_responses == [(0, {"decision": "accept"})]
        assert refusals == []

    @pytest.mark.asyncio
    async def test_an_operator_answered_refusal_is_not_reported_twice(self, monkeypatch):
        """That path already records the refusal through the request the operator answered.

        Telling them twice that one action was refused is worse than the silence this fixes.
        """
        fake = self._session(self._approval())
        _patch_spawn(monkeypatch, fake)
        refusals = []

        async def _on_refusal(method, subject):
            refusals.append((method, subject))

        async def _ask(method, subject):
            return False  # the operator refuses

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
            posture="operator",
            request_approval=_ask,
            on_refusal=_on_refusal,
        )

        assert fake.sent_responses == [(0, {"decision": "decline"})]
        assert refusals == []

    @pytest.mark.asyncio
    async def test_an_unrecognised_method_decline_is_reported(self, monkeypatch):
        _, refusals = await self._run(
            monkeypatch, self._approval(method="something/new", params={})
        )
        assert [method for method, _ in refusals] == ["something/new"]

    @pytest.mark.asyncio
    async def test_a_turn_without_a_reporter_still_answers_every_request(self, monkeypatch):
        """`on_refusal` is optional, and silence must never become a deadlock."""
        fake = self._session(self._approval())
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


class TestApprovalLabel:
    def test_the_refused_action_reads_as_a_thing(self):
        """The timeline renders "{agent} refused {tool_name}"."""
        assert codex_appserver.approval_label("item/commandExecution/requestApproval") == "Bash"
        assert codex_appserver.approval_label("item/fileChange/requestApproval") == "Write"

    def test_an_unknown_method_is_passed_through_rather_than_hidden(self):
        assert codex_appserver.approval_label("future/method") == "future/method"
