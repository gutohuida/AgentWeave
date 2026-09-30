"""Task 1.9 part 1/N: `hub.copilot_acp.run_turn`, the per-turn ACP orchestrator.

Every symbol this file names (`run_turn`, `ACPProcess`, `COPILOT_RAW_EVENTS`,
`COPILOT_TURN_CONTEXT_HEAD`, `TurnOutcome`) is checked against `hub/hub/copilot_acp.py`, which does
not exist yet (confirmed directly: no such file, unlike `hub.copilot_probe`, `hub.copilot_home`,
etc., which also don't exist -- this task's own module and every module it would import from are
all still unbuilt). `ACPProcess.close()` is the one name design.md cites literally (`:1502`,
D17); `COPILOT_RAW_EVENTS` and `COPILOT_TURN_CONTEXT_HEAD` are the two other names design.md
gives in backticks as this slice's own constants (D10 `:1130`, D5 review note `:479`). Every other
name here -- `run_turn`'s own keyword surface, `TurnOutcome`'s fields, `ACPProcess.spawn`'s
signature -- is this file's least-invented reading of D18's `RpcTurnRequest`/`RpcCallbacks`
field lists (design.md:1520-1531) and of `codex_appserver.run_turn`'s analogous shape, not a
design citation. A future part or round should confirm or correct this surface against whatever
`copilot_acp.py` actually needs, the same discipline `test_copilot_acp_mapper.py` states for
`CopilotEventMapper`'s method names.

**The harness, and why it isn't `test_codex_appserver_run_turn.py`'s `_FakeSession` verbatim.**
That fake's `request()` returns its canned result the instant it is called; Codex's own protocol
never needs a request's response gated behind notifications -- `turn/start` acks immediately and
`turn/completed` arrives later as its own notification, read through a separate
`next_notification()` queue. Copilot's `session/prompt` is different in exactly the way this
task's own opening sentence states: the real capture (`acp4…log`) sends `session/prompt` at line 5
and gets its `result` back at line 54, after every notification of that turn. A fake whose
`request("session/prompt", …)` just returns a canned dict, with no notification passing through
it, would let a `run_turn` that never drains notifications during that call pass this file
anyway -- the property under test would not be under test.

So `_FakeACPSession.request()` instead pops a single ordered script in wire order: a notification
entry is delivered to a caller-supplied handler before the call returns, and only a response entry
ends it. This reproduces the real ordering directly rather than asserting it separately, at the
cost of modelling one strictly-ordered stream instead of two independent queues -- adequate for a
protocol whose server never answers two client requests out of order (unverified generally, true
of every capture in `evidence/`). A script entry can also be a `server_request` (Copilot asking
*us* something, e.g. `session/request_permission`), answered through a second caller-supplied
handler; this part's script has none, but later parts (h), (k), (p) will.

**Scope, this part.** Only tasks.md 1.9's case (a): the plain new-session sequence --
`initialize` (subscribing this slice's raw events), `session/new` with `mcpServers: []`,
`session/set_config_option` selecting the agent, then `session/prompt` whose first content block
is `per_turn_context`/`tool_surface_context` behind `COPILOT_TURN_CONTEXT_HEAD` and whose second is
the caller's own `prompt`, unchanged. `session/set_mode`, which D8's posture step sends
unconditionally right after agent selection on every turn including this one, is scripted (its
real response is a bare `{}`, VERIFIED at `r1-probe-plan.log:12`) so a real implementation calling
it does not exhaust the script, but this part makes no assertion about it -- that is D8's posture
step, not case (a)'s own four waypoints, and asserting its params here would invent a second
task's coverage under this one's name. Cases (b)-(s) (18 lettered cases total, a-s) remain, all of
them, for later parts; this part covers (a) only, nothing else in tasks.md 1.9's list.

Confirmed red: `pytest hub/tests/test_copilot_acp_run_turn.py -q` fails at collection,
`ModuleNotFoundError: No module named 'hub.copilot_acp'`.
"""

import pytest

import hub.copilot_acp as copilot_acp
from hub.copilot_acp import ACPProcess, TurnOutcome, run_turn

pytestmark = pytest.mark.asyncio

SESSION_ID = "ea76eb05-6a87-4257-8280-d7cc9e571ba5"  # a real session id, r1-probe-agent.log:5
AGENT_NAME = "probe-builder"  # the real agent name r1-probe-agent.log selected
AGENT_MARKER = f"AgentWeave agent {AGENT_NAME} — context rendered by the AgentWeave Hub"  # D4
AGENT_MODE_URI = "https://agentclientprotocol.com/protocol/session-modes#agent"  # VERIFIED wire


def _mode_option(current=AGENT_MODE_URI):
    return {
        "type": "select",
        "id": "mode",
        "name": "Mode",
        "currentValue": current,
        "options": [{"value": AGENT_MODE_URI, "name": "Agent", "description": "…"}],
        "category": "mode",
    }


def _allow_all_option(current="off"):
    return {
        "type": "select",
        "id": "allow_all",
        "name": "Allow All",
        "currentValue": current,
        "options": [
            {"value": "on", "name": "On", "description": "…"},
            {"value": "off", "name": "Off", "description": "…"},
        ],
        "category": "permissions",
    }


def _agent_option(current_value, *, description=None):
    """The `agent` `configOption` shape r1-probe-agent.log:5 actually captured, `currentValue`
    and the selected value's own `description` (not the option's) are what D6 checks."""
    options = [{"value": "", "name": "Copilot", "description": "Default Copilot agent"}]
    if current_value:
        options.append(
            {
                "value": current_value,
                "name": current_value,
                "description": description if description is not None else AGENT_MARKER,
            }
        )
    return {
        "type": "select",
        "id": "agent",
        "name": "Agent",
        "currentValue": current_value,
        "options": options,
        "category": "_agent",
    }


class _FakeACPSession:
    """Drives `run_turn` through one strictly-ordered script of responses, notifications and
    server-initiated requests -- see the module docstring for why this differs from
    `test_codex_appserver_run_turn.py`'s `_FakeSession`.

    `script` entries are dicts, each exactly one of:
      - ``{"response": {...}}``                        -- ends the in-flight `request()` call;
      - ``{"notification": method, "params": {...}}``   -- delivered via `on_notification` first;
      - ``{"server_request": {"id", "method", "params"}}`` -- delivered via `on_server_request`,
        its answer appended to `sent_responses`.
    """

    def __init__(self, script, *, on_notification=None, on_server_request=None):
        self._script = list(script)
        self._on_notification = on_notification
        self._on_server_request = on_server_request
        self.sent_requests = []
        self.sent_notifications = []
        self.sent_responses = []
        self._running = True
        self.closed_with_force = None

    async def request(self, method, params, *, timeout=30.0):
        self.sent_requests.append((method, params))
        while self._script:
            entry = self._script.pop(0)
            if "response" in entry:
                return entry["response"]
            if "notification" in entry:
                if self._on_notification is None:
                    raise AssertionError(
                        f"script has a notification but no on_notification handler was given "
                        f"(pending request: {method!r})"
                    )
                await self._on_notification(entry["notification"], entry.get("params", {}))
                continue
            if "server_request" in entry:
                if self._on_server_request is None:
                    raise AssertionError(
                        f"script has a server_request but no on_server_request handler was "
                        f"given (pending request: {method!r})"
                    )
                req = entry["server_request"]
                result = await self._on_server_request(req["method"], req["params"])
                self.sent_responses.append((req.get("id"), result))
                continue
            raise AssertionError(f"unrecognised script entry: {entry!r}")
        raise AssertionError(f"script exhausted before a response to {method!r}")

    async def notify(self, method, params):
        self.sent_notifications.append((method, params))

    def is_running(self):
        return self._running

    def stderr_tail(self, limit=2000):
        return ""

    async def close(self, force=False):
        self._running = False
        self.closed_with_force = force


def _patch_spawn(monkeypatch, fake):
    async def _fake_spawn(cmd, *, cwd=None, env=None):
        return fake

    monkeypatch.setattr(ACPProcess, "spawn", _fake_spawn)
    # Whatever resolves the real executable (D2's `copilot_probe.resolve_copilot_executable`,
    # a module that also does not exist yet) is bypassed the same way Codex's fake bypasses
    # `resolve_executable`: patched if `copilot_acp` exposes a name for it, a no-op otherwise
    # (`raising=False`), so this file does not have to guess which of D2's module or this one
    # ends up owning the call.
    monkeypatch.setattr(
        copilot_acp, "resolve_copilot_executable", lambda *a, **k: ["copilot.exe"], raising=False
    )


def _collector(target):
    async def _append(item):
        target.append(item)

    return _append


class TestNewSessionSequence:
    """Tasks.md 1.9(a): the plain new-session sequence, nothing resumed, nothing escalated."""

    async def test_initialize_new_agent_then_prompt_in_order_with_context_first(self, monkeypatch):
        per_turn_context = "## Workspace\n- root: C:\\work"
        tool_surface_context = "## Tools\n- agentweave-send_message"
        raw_prompt = "Please review the open PR."

        events = []
        sessions_bound = []

        script = [
            {
                "response": {
                    "protocolVersion": 1,
                    "agentCapabilities": {"loadSession": True},
                    "agentInfo": {"name": "Copilot", "title": "Copilot", "version": "1.0.88"},
                }
            },
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
                }
            },
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt=raw_prompt,
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context=per_turn_context,
            tool_surface_context=tool_surface_context,
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        methods = [m for m, _ in fake.sent_requests]

        def _first(method, *, config_id=None):
            for i, (m, p) in enumerate(fake.sent_requests):
                if m == method and (config_id is None or p.get("configId") == config_id):
                    return i
            raise AssertionError(
                f"{method!r} (configId={config_id!r}) was never sent; got {methods}"
            )

        i_init = _first("initialize")
        i_new = _first("session/new")
        i_agent = _first("session/set_config_option", config_id="agent")
        i_prompt = _first("session/prompt")
        assert i_init < i_new < i_agent < i_prompt, methods

        init_params = fake.sent_requests[i_init][1]
        subscribed = init_params["clientCapabilities"]["_meta"]["github.com/copilot"]["events"]
        assert subscribed == list(copilot_acp.COPILOT_RAW_EVENTS)
        assert len(subscribed) == len(set(subscribed)), "subscription list must be de-duplicated"
        # Sanity against design.md's own list (D10 `:1130-1142`), not a re-derivation of it.
        assert "session.error" in subscribed and "tool.execution_start" in subscribed

        new_params = fake.sent_requests[i_new][1]
        assert new_params["cwd"] == "C:\\work"
        assert new_params["mcpServers"] == []

        agent_params = fake.sent_requests[i_agent][1]
        assert agent_params["sessionId"] == SESSION_ID
        assert agent_params["value"] == AGENT_NAME

        prompt_params = fake.sent_requests[i_prompt][1]
        assert prompt_params["sessionId"] == SESSION_ID
        blocks = prompt_params["prompt"]
        assert len(blocks) >= 2, "the context block and the message must never be one block (D5)"
        assert blocks[0]["text"].startswith(copilot_acp.COPILOT_TURN_CONTEXT_HEAD)
        assert per_turn_context in blocks[0]["text"]
        assert tool_surface_context in blocks[0]["text"]
        assert (
            blocks[-1]["text"] == raw_prompt
        ), "the operator's message must reach the wire byte-identical"

        assert sessions_bound == [SESSION_ID], "on_session must bind before run_turn returns"
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)
        assert fake.closed_with_force is False, "D17: ACPProcess.close() on every exit, not forced"

    async def test_reversing_new_and_agent_selection_breaks_the_ordering_assertion(self):
        """The CLAUDE.md ordering rule: a fixture whose order the route could not produce must
        fail the assertion it is fed to, or the assertion is not evidence of order at all."""
        methods = ["session/set_config_option", "initialize", "session/new", "session/prompt"]

        def _first(method):
            return methods.index(method)

        with pytest.raises(AssertionError):
            assert (
                _first("initialize")
                < _first("session/new")
                < _first("session/set_config_option")
                < _first("session/prompt")
            )
