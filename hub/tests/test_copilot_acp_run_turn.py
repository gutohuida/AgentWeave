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
task's coverage under this one's name. Cases (b)-(w) remain, all of them, for later parts; this
part covers (a) only, nothing else in tasks.md 1.9's list. (Part 5/N correction: this paragraph
originally said "18 lettered cases total, a-s" and tasks.md's own part 4/N note repeated that
miscount ("cases (e)-(s), 14 of 18, remain") -- re-counting tasks.md's Assert list directly, fresh,
while writing part 5/N found it actually runs `(a)` through `(w)`, 23 cases, not 18. Both counts are
corrected here and in tasks.md's part 5/N note; do not carry the "18"/"a-s" figure forward.)

Confirmed red: `pytest hub/tests/test_copilot_acp_run_turn.py -q` fails at collection,
`ModuleNotFoundError: No module named 'hub.copilot_acp'`.
"""

import asyncio
import contextlib
import dataclasses
import inspect
import json
import os
import time

import pytest

import hub.copilot_acp as copilot_acp
from hub.codex_appserver import AppServerError
from hub.copilot_acp import ACPProcess, CopilotACPError, TurnOutcome, run_turn

pytestmark = pytest.mark.asyncio

SESSION_ID = "ea76eb05-6a87-4257-8280-d7cc9e571ba5"  # a real session id, r1-probe-agent.log:5
AGENT_NAME = "probe-builder"  # the real agent name r1-probe-agent.log selected
AGENT_MARKER = f"AgentWeave agent {AGENT_NAME} — context rendered by the AgentWeave Hub"  # D4
AGENT_MODE_URI = "https://agentclientprotocol.com/protocol/session-modes#agent"  # VERIFIED wire
PLAN_MODE_URI = "https://agentclientprotocol.com/protocol/session-modes#plan"  # VERIFIED,
# r1-probe-plan.log:8 (`session/set_mode` params: `{"sessionId": ..., "modeId": <this URI>}`)
AUTOPILOT_MODE_URI = "https://agentclientprotocol.com/protocol/session-modes#autopilot"  # CODE,
# design.md:78 ("The mode ids are `…session-modes#agent`, `#plan`, `#autopilot`"), not itself in
# an evidence log -- by symmetry with AGENT_MODE_URI/PLAN_MODE_URI, both VERIFIED wire values that
# share this same `…session-modes#<name>` shape.


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
        its answer appended to `sent_responses`;
      - ``{"error": {"code": ..., "message": ..., "data": {...}}}`` -- part 3/N: ends the
        in-flight `request()` call by *raising* `CopilotACPError(message, code=code, data=data)`
        instead of returning, mirroring design.md's own stated translation ("`ACPProcess.request`
        raises `CopilotACPError(code=<error.code>)` for a response holding `error`", `:1175`, R3
        adds `.data`, `:1179`) -- a JSON-RPC error response is never handed back as a plain dict
        the way the three other entry kinds are. `message`/`data` default to `None` if the entry
        omits them; a real response always carries `message` (JSON-RPC requires it) but this
        fake does not enforce that, since no case needs to test a malformed error.
      - ``{"process_exited": True}`` -- part 14/N, case (n)'s second scenario: "a process that
        exits after the prompt is written", not a JSON-RPC error at all -- the transport itself is
        gone, so there is no `error` object to translate. Ends the in-flight `request()` call by
        setting `self._running = False` and *raising* `self.process_ended_error(method)`, an
        `AppServerError` (not `CopilotACPError`: no JSON-RPC `.code`/`.data` exists for a death
        with no response), mirroring `test_codex_appserver_run_turn.py`'s `_FakeSession
        .process_ended_error` -- same three composed facts (`exit_code`, `method`, `stderr_tail`),
        same reason (every reader of `str(exc)` gets them without being changed, D12's docstring).
        `run_turn` itself has no separate poll loop the way Codex's does (this file's module
        docstring, above) -- draining happens inside one `request()` call -- so the fake, standing
        in for `ACPProcess.request()`, is the only place this scenario can be raised from; the real
        `ACPProcess` would detect the same condition on its own read loop hitting EOF.
    """

    def __init__(
        self,
        script,
        *,
        on_notification=None,
        on_server_request=None,
        stderr_tail="",
        returncode=None,
    ):
        self._script = list(script)
        self._on_notification = on_notification
        self._on_server_request = on_server_request
        self.sent_requests = []
        self.sent_notifications = []
        self.sent_responses = []
        self._running = True
        self.closed_with_force = None
        # part 14/N: previously hardcoded "" (no case needed the plumbing); now configurable so a
        # post-prompt failure's `TurnOutcome.stderr_tail` can be proven to carry it through,
        # mirroring Codex's own fake (`test_codex_appserver_run_turn.py:26-36`).
        self._stderr_tail = stderr_tail
        self.returncode = returncode

    async def request(self, method, params, *, timeout=30.0):
        self.sent_requests.append((method, params))
        while self._script:
            entry = self._script.pop(0)
            if "response" in entry:
                return entry["response"]
            if "error" in entry:
                err = entry["error"]
                raise CopilotACPError(
                    err.get("message"), code=err.get("code"), data=err.get("data")
                )
            if "process_exited" in entry:
                self._running = False
                raise self.process_ended_error(method)
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
        return self._stderr_tail

    def process_ended_error(self, method):
        # part 14/N: unlike Codex's fake (`process_ended_error(message, method=None)`, called by
        # `codex_appserver.py`'s own poll loop with a message it already composed), this fake's
        # only call site is its own `request()`, above, which has just the pending method name in
        # hand -- so this composes the message itself, from that one fact, rather than taking one
        # it can't supply.
        return AppServerError(
            f"copilot process ended before responding to {method}",
            exit_code=self.returncode,
            method=method,
            stderr_tail=self._stderr_tail,
        )

    async def close(self, force=False):
        self._running = False
        self.closed_with_force = force


def _patch_spawn(monkeypatch, fake, *, captured_cmds=None):
    async def _fake_spawn(cmd, *, cwd=None, env=None, **kwargs):
        # Part 2/N: forward whatever notification/server-request handlers `run_turn`'s own
        # `ACPProcess.spawn` call supplies onto the *same* fake the test already built its
        # script into, overriding the test's own (usually absent) constructor default. This is
        # necessary, not cosmetic: the property tests like `TestResumedSessionSequence` check is
        # what run_turn's *own* notification handling does with a delivered update (arm/drop),
        # so the handler invoked here must be run_turn's real one, not a test-written stand-in
        # that would make the assertion pass vacuously. `ACPProcess.spawn` taking these two
        # keywords is this file's own least-invented reading (same status as its other inferred
        # surfaces, see the module docstring) -- if the real module instead sets a handler via
        # some other means (e.g. an attribute on the returned object), this forwarding is a
        # no-op and a script with notification entries fails loudly (`script exhausted` /
        # `on_notification handler` AssertionError) rather than silently passing for the wrong
        # reason.
        # Part 10/N: also capture the argv itself, when a test asks for it, so a case (like
        # 1.9(j)'s spawn-argv claim) can inspect exactly what `run_turn` handed to `spawn`
        # without needing its own bespoke patch.
        if captured_cmds is not None:
            captured_cmds.append(list(cmd))
        if kwargs.get("on_notification") is not None:
            fake._on_notification = kwargs["on_notification"]
        if kwargs.get("on_server_request") is not None:
            fake._on_server_request = kwargs["on_server_request"]
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


class _FakeCopilotProbe:
    """Part 16/N, case (p): a stand-in for `hub.copilot_probe.CopilotProbe` (D15), which does not
    exist yet -- design.md names its read side (`CopilotProbe.verdict()`, used verbatim across
    the doc) but never its write side, only the effect ("`run_turn` writes that verdict into
    `CopilotProbe` ... before raising", `:1215-1217`). `record(present, authorized, reason)` is
    this file's own least-invented guess at that write call, symmetric with the read-side name;
    flagged for a future round the same way part 1/N flagged its own invented names. Starts
    `authorized=True` so a `run_turn` that never reaches this fake at all (the real singleton
    turns out to be wired some other way) leaves `verdict()` reporting authorized and the test
    fails loudly on that, rather than passing for the wrong reason."""

    def __init__(self):
        self.recorded = []
        self._verdict = {"present": True, "authorized": True, "reason": None}

    def record(self, *, present, authorized, reason):
        self.recorded.append({"present": present, "authorized": authorized, "reason": reason})
        self._verdict = {"present": present, "authorized": authorized, "reason": reason}

    def verdict(self):
        return dict(self._verdict)


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


INIT_RESPONSE = {
    "protocolVersion": 1,
    "agentCapabilities": {"loadSession": True},
    "agentInfo": {"name": "Copilot", "title": "Copilot", "version": "1.0.88"},
}  # same shape as TestNewSessionSequence's, reused so this file has one source for it

RESUME_ID = "b193bf66-5c0d-4cae-aa21-a9f218216191"  # a real session id, r1-probe-load.log:8 --
# that capture's own session/load call for it gets -32002 (case (c), not this one: that session
# was never prompted), so only the id's *format* is real here, not this test's outcome for it.


def _replay_chunk(session_update, text):
    """A `session/update` notification's wire envelope for a replayed history chunk. D7 (line
    549) names the two update types (`user_message_chunk`, `agent_message_chunk`); their
    `content` shape is the mapper's own known one (`test_copilot_acp_mapper.py`'s
    `{"sessionUpdate": ..., "content": {"type": "text", "text": ...}}`), not a capture -- neither
    evidence log has a `session/load` that actually finds a session to replay (checked directly:
    both of `r1-probe-load.log`'s calls target an unprompted id and get -32002), so this shape is
    synthetic, flagged the same way parts 3-6 of `test_copilot_acp_mapper.py` flagged their own
    synthetic fixtures for uncaptured cases."""
    return {
        "notification": "session/update",
        "params": {
            "sessionId": RESUME_ID,
            "update": {"sessionUpdate": session_update, "content": {"type": "text", "text": text}},
        },
    }


def _load_response():
    """`session/load`'s success response body. Neither evidence log captures one (see
    `RESUME_ID`'s own comment), and D7 says nothing about its shape beyond the request echoing
    `mcpServers: []` -- INFERRED by symmetry with `session/new`'s own response (`modes` +
    `configOptions`), since the agent-selection step right after it (D6/D7 line 500) reads
    `configOptions` regardless of which of the two calls produced them. No `sessionId` key: unlike
    `session/new`, the id is already known (it was in the request), so nothing here invents a
    second, possibly-conflicting source for it."""
    return {
        "modes": {"currentModeId": AGENT_MODE_URI},
        "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
    }


class TestResumedSessionSequence:
    """Tasks.md 1.9(b): `session/load` is used instead of `session/new` when a `resume_session_id`
    is given, and any history replay delivered before the prompt produces no event -- design.md's
    own line 96 flags the replay stream's order relative to the load response itself as INFERRED
    ("handled order-independently", D7), so both orders are tested here rather than just one.

    Wiring note: `_patch_spawn` (module-level, see its own updated docstring) forwards whatever
    `on_notification` keyword `run_turn`'s real `ACPProcess.spawn` call supplies onto this fake,
    so the handler a script's notification entries reach is `run_turn`'s own -- the point of
    these tests is what its arming gate does with a delivered update, not what a test-written
    stand-in does.
    """

    async def _run(self, monkeypatch, script):
        events = []
        sessions_bound = []
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=RESUME_ID,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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
        return fake, events, sessions_bound, outcome

    def _assert_load_not_new(self, fake):
        methods = [m for m, _ in fake.sent_requests]
        assert "session/new" not in methods, methods
        load_calls = [(m, p) for m, p in fake.sent_requests if m == "session/load"]
        assert len(load_calls) == 1, methods
        load_params = load_calls[0][1]
        assert load_params["sessionId"] == RESUME_ID
        assert load_params["cwd"] == "C:\\work"
        assert load_params["mcpServers"] == []

    async def test_replayed_chunks_before_load_response_produce_no_event(self, monkeypatch):
        # Both replay notifications pop before `session/load`'s own response entry, so the fake
        # delivers them while that call is still in flight -- the order r1-probe-load.log:9-10
        # itself proves is real for a *different* notification (`available_commands_update`,
        # case (c)'s -32002 path), reused here to place this test's own chunks in the same slot.
        script = [
            {"response": INIT_RESPONSE},
            _replay_chunk("user_message_chunk", "earlier question"),
            _replay_chunk("agent_message_chunk", "earlier answer"),
            {"response": _load_response()},
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here too
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake, events, sessions_bound, outcome = await self._run(monkeypatch, script)

        self._assert_load_not_new(fake)
        assert events == [], "replayed history chunks before the prompt must produce no event"
        assert sessions_bound == [RESUME_ID], "on_session must bind the resumed id before return"
        assert outcome == TurnOutcome(session_id=RESUME_ID, status="completed", error=None)

    async def test_replayed_chunks_after_load_response_before_prompt_produce_no_event(
        self, monkeypatch
    ):
        # Same two chunks, moved past `session/load`'s response and into the wait for the next
        # request (`session/set_config_option`) -- still strictly before `session/prompt` is
        # written, which is D7's actual line: "any update before that point ... is dropped",
        # not "any update before the load response". This is the other half of "order-
        # independently" that the previous test's placement does not cover.
        script = [
            {"response": INIT_RESPONSE},
            {"response": _load_response()},
            _replay_chunk("user_message_chunk", "earlier question"),
            _replay_chunk("agent_message_chunk", "earlier answer"),
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent
            {"response": {}},  # session/set_mode
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake, events, sessions_bound, outcome = await self._run(monkeypatch, script)

        self._assert_load_not_new(fake)
        assert events == [], "replayed history chunks before the prompt must produce no event"
        assert sessions_bound == [RESUME_ID], "on_session must bind the resumed id before return"
        assert outcome == TurnOutcome(session_id=RESUME_ID, status="completed", error=None)


class TestSessionLoadNotFoundRebinds:
    """Tasks.md 1.9(c): `session/load` answered `-32002` -> `session/new` follows and
    `on_session_missing` fires -- D7's *A load that finds nothing* paragraph (design.md:556-568).

    The `-32002` half is VERIFIED, not synthetic: `r1-probe-load.log:8-12` is a real capture of
    exactly this error, for exactly this reason (the loaded id, `RESUME_ID`, was never prompted in
    that session, so it was never persisted) -- reused here verbatim (`code`, `message`, `data`).
    But that capture never re-sends `session/new` afterward; it goes straight to a doomed
    `session/prompt` on the dead id, itself erroring `-32602` (`r1-probe-load.log:11-12`, a
    different, unrelated error this case does not cover). So the "`session/new` follows" half is
    NOT captured behavior -- it is D7's own stated recovery path (design.md:560), synthetic in the
    same sense case (b)'s replayed-chunk shape was: built from a design rule, not a capture, and
    flagged as such rather than asserted as VERIFIED.

    This part also extends `_FakeACPSession` with its first error-response script entry (see the
    class docstring's new `{"error": ...}` bullet and `request()`'s new branch) -- until now every
    script in this file only ever used success `response` dicts, so a JSON-RPC error path had no
    way to be scripted at all.
    """

    async def test_load_not_found_starts_new_session_and_notifies_the_missing_id(self, monkeypatch):
        events = []
        sessions_bound = []
        sessions_missing = []

        script = [
            {"response": INIT_RESPONSE},
            {
                "error": {
                    "code": -32002,
                    "message": f"Resource not found: Session {RESUME_ID} not found",
                    "data": {"uri": f"Session {RESUME_ID} not found"},
                }
            },  # session/load -- VERIFIED, r1-probe-load.log:10
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
                }
            },  # session/new, following the failed load -- D7's stated recovery, not a capture
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent
            {"response": {}},  # session/set_mode
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=RESUME_ID,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
            on_session_missing=_collector(sessions_missing),
        )

        methods = [m for m, _ in fake.sent_requests]

        def _first(method):
            for i, (m, _p) in enumerate(fake.sent_requests):
                if m == method:
                    return i
            raise AssertionError(f"{method!r} was never sent; got {methods}")

        i_load = _first("session/load")
        i_new = _first("session/new")
        assert i_load < i_new, methods
        assert methods.count("session/new") == 1, methods

        load_params = fake.sent_requests[i_load][1]
        assert load_params["sessionId"] == RESUME_ID

        new_params = fake.sent_requests[i_new][1]
        assert new_params["cwd"] == "C:\\work"
        assert new_params["mcpServers"] == []

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1, events
        payload = diagnostics[0].payload
        assert payload["code"] == "copilot.session_missing"
        assert payload["severity"] == "info"
        assert RESUME_ID in payload["summary"], payload["summary"]

        assert sessions_missing == [RESUME_ID], "on_session_missing must name the dead old id"
        assert sessions_bound == [SESSION_ID], "on_session must bind the new id, once, not the old"
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)


class TestVersionGateFailsBeforeAnySessionRequest:
    """Tasks.md 1.9(d): a Copilot CLI below `COPILOT_MIN_VERSION` fails before any `session/*`
    request is sent -- D12 (design.md:1155-1165). The client compares `initialize.result.
    agentInfo.version` (dotted integers) against `COPILOT_MIN_VERSION`; below it, or missing
    entirely (":1165", 'A missing version is treated as too old'), `run_turn` raises
    `CopilotACPError` -- never `session/new`/`session/load` -- with the message design.md gives
    verbatim (":1163-1165"): "Copilot CLI <v> is older than the supported 1.0.81. Update it with
    `copilot update` or npm."

    Both tests script only `initialize`'s response and nothing after it. That is deliberate, not
    an oversight: `_FakeACPSession.request()` raises its own `AssertionError` ("script exhausted")
    if a second `request()` call is made and finds nothing left to pop, so a real implementation
    that incorrectly sent `session/new`/`session/load` past the gate would fail loudly on that
    `AssertionError`, not silently pass -- the same proof-by-exhaustion the module docstring's
    `_FakeACPSession` doc already relies on, applied here to "no second request happens" rather
    than to a scripted response.

    The exact text `<v>` renders as for the *missing*-version half is not stated anywhere in
    design.md, so `test_version_missing_is_treated_as_too_old` asserts only the fixed half of the
    sentence (the part every case must share) and does not assert what stands in for `<v>` -- an
    invented literal there would be this file's own guess, not design.md's.
    """

    async def _run_and_capture_raise(self, monkeypatch, agent_info):
        events = []
        sessions_bound = []
        script = [
            {"response": {"protocolVersion": 1, "agentCapabilities": {}, "agentInfo": agent_info}}
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        with pytest.raises(CopilotACPError) as exc_info:
            await run_turn(
                cwd="C:\\work",
                env=None,
                prompt="Anything changed since I left?",
                model=None,
                resume_session_id=None,
                agent=AGENT_NAME,
                per_turn_context="## Workspace\n- root: C:\\work",
                tool_surface_context="## Tools\n- agentweave-send_message",
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
        return fake, exc_info.value

    async def test_version_below_minimum_fails_before_any_session_request(self, monkeypatch):
        assert copilot_acp.COPILOT_MIN_VERSION == "1.0.81", "design.md:1155's own stated minimum"

        fake, err = await self._run_and_capture_raise(
            monkeypatch, {"name": "Copilot", "title": "Copilot", "version": "1.0.75"}
        )

        assert str(err) == (
            "Copilot CLI 1.0.75 is older than the supported 1.0.81. Update it with "
            "`copilot update` or npm."
        )
        assert fake.sent_requests == [
            ("initialize", fake.sent_requests[0][1])
        ], "no session/new or session/load may be sent once the gate fails"
        assert fake.sent_requests[0][0] == "initialize"
        assert len(fake.sent_requests) == 1
        assert fake.closed_with_force is False, "D17: the process is still closed, not forced"

    async def test_version_missing_is_treated_as_too_old(self, monkeypatch):
        fake, err = await self._run_and_capture_raise(
            monkeypatch, {"name": "Copilot", "title": "Copilot"}  # no "version" key at all
        )

        assert "is older than the supported 1.0.81. Update it with `copilot update` or npm." in str(
            err
        ), str(err)
        assert (
            len(fake.sent_requests) == 1 and fake.sent_requests[0][0] == "initialize"
        ), "a missing version must fail the gate before any session/* request too"
        assert fake.closed_with_force is False, "D17: the process is still closed, not forced"


class TestFullAccessWithNoAllowAllOption:
    """Tasks.md 1.9(e): full access with no `allow_all` option -- a diagnostic, and requests are
    judged as `workspace`. D8 (design.md:794-813): after session/new (or load) and agent selection,
    under full access (design.md:654-660's mapping table sends `permission_mode="bypassPermissions"`
    there), the client tries to turn `allow_all` on. "If `allow_all` is absent, or the set fails
    ..., the run does not answer every request with ALLOW. That would grant through the Hub what
    the organisation withheld from Copilot. The run instead proceeds under `workspace` and emits a
    `diagnostic` event" (`:798-801`), with the exact sentence design.md quotes (`:804-806`):
    "Copilot did not grant Full access (<Copilot's error message, or "no allow-all option was
    offered">); this run is deciding each action against its workspace instead." Here the option is
    simply missing from `configOptions` (not present-but-failing-to-set), so the bracketed half is
    the literal "no allow-all option was offered" -- design.md never states the other half's
    wording, since that depends on whatever error Copilot itself would raise, which this case does
    not exercise. `configOptions` omits `allow_all` from both `session/new`'s own response and
    `session/set_config_option agent`'s, since design.md's "after session/new/load" wording and its
    later, unified posture-step listing (`:815-844`, "after new/load and agent selection") do not
    agree on which call's `configOptions` is the one actually consulted -- omitting it from both
    makes the test's absence-check true regardless of which the real implementation reads.

    `copilot.full_access_withdrawn` / `warning` is the code/severity design.md's own diagnostic
    table gives this row (`:1016`), the same convention `TestSessionLoadNotFoundRebinds` already
    uses for `copilot.session_missing` / `info`.

    Proof that the request is actually judged as `workspace`, not defensively ALLOWed (D8's other
    full-access rule, `:807-813`, for a request that reaches the handler despite `allow_all`
    genuinely being on): the scripted `session/request_permission` is an `edit` naming a path
    *outside* `workspace`, which `workspace`'s judge (`_decide("Write", ...)`, design.md:637)
    REJECTs and full access's own defensive ALLOW would not -- the same distinguishing technique
    `test_codex_appserver_run_turn.py`'s `test_an_outside_workspace_decline_is_reported` already
    uses for Codex. The `toolCall`/`options` shapes are CODE-only (design.md:60-61) -- neither
    evidence log has a captured `session/request_permission` at all (design.md:74, "`acp4…log`
    holds no `session/request_permission`"), so this fixture is synthetic, flagged the same way
    `test_copilot_acp_mapper.py`'s `TestEditDiffToolUse` flags its own synthetic edit fixture.
    """

    EDIT_CALL_ID = "call_synthetic_full_access_edit_1"
    OUTSIDE_PATH = "C:\\other\\evil.txt"

    async def test_diagnostic_and_outside_workspace_edit_rejected(self, monkeypatch):
        events = []
        sessions_bound = []

        script = [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option("")],  # no allow_all option
                }
            },
            {
                "response": {
                    "configOptions": [_mode_option(), _agent_option(AGENT_NAME)]
                }  # session/set_config_option agent -- still no allow_all option
            },
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here
            {
                "server_request": {
                    "id": 1,
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": SESSION_ID,
                        "toolCall": {
                            "toolCallId": self.EDIT_CALL_ID,
                            "title": "Edit evil.txt",
                            "kind": "edit",
                            "rawInput": {"fileName": self.OUTSIDE_PATH},
                            "locations": [{"path": self.OUTSIDE_PATH}],
                        },
                        "options": [
                            {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
                            {
                                "optionId": "allow_always",
                                "name": "Always Allow",
                                "kind": "allow_always",
                            },
                            {"optionId": "reject_once", "name": "Reject", "kind": "reject_once"},
                        ],
                    },
                }
            },
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Please edit a file outside the workspace.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode="bypassPermissions",
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        allow_all_sets = [
            (m, p)
            for m, p in fake.sent_requests
            if m == "session/set_config_option" and p.get("configId") == "allow_all"
        ]
        assert (
            allow_all_sets == []
        ), "an absent allow_all option must not be set -- there is nothing there to set"

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1, events
        payload = diagnostics[0].payload
        assert payload["code"] == "copilot.full_access_withdrawn", payload
        assert payload["severity"] == "warning", payload
        assert payload["summary"] == (
            "Copilot did not grant Full access (no allow-all option was offered); this run is "
            "deciding each action against its workspace instead."
        ), payload["summary"]

        assert fake.sent_responses == [
            (1, {"outcome": {"outcome": "selected", "optionId": "reject_once"}})
        ], "an edit outside the workspace must be REJECTed once judged as workspace, not ALLOWed"

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)
        assert fake.closed_with_force is False, "D17: ACPProcess.close() on every exit, not forced"


class TestAgentMarkerMismatchFallsBackToResourceBlock:
    """Tasks.md 1.9(f): an `agent` option whose description is not the marker -- the stable
    context goes as a `resource` block, with a diagnostic. D6 (design.md:498-536): after
    `session/set_config_option {agent: <name>}`, the client proceeds only when the option exists,
    `currentValue == <name>` **and** the selected value's `description` equals the marker written
    in D4 (`f"AgentWeave agent {agent} — context rendered by the AgentWeave Hub"`, this file's own
    `AGENT_MARKER`). This part covers the "foreign description" branch of that check specifically
    (`currentValue` *is* the agent, but `description` is someone else's text) -- a repository
    `.claude/agents/<agent>.md`/`.github/agents/<agent>.md` with the same name standing in for the
    Hub's file, exactly D6's own stated scenario (`:508-517`). The check's other two failure
    branches (no `agent` option at all; a refused set) are not this bullet's to invent a case for
    -- tasks.md's own wording names only "whose description is not the marker".

    On failure the run (D6, `:519-524`) sends the stable context as an ACP `resource` content
    block -- the exact shape design.md gives (`:520-522`): `{"type": "resource", "resource":
    {"uri": "agentweave://context/<agent>/stable", "mimeType": "text/markdown", "text": …}}` --
    **ahead of** the usual `COPILOT_TURN_CONTEXT_HEAD` block, and emits one `diagnostic` whose
    summary is design.md's own sentence (`:522-524`): "Copilot did not select the AgentWeave agent
    file (<reason>); this turn's context was sent with the prompt instead." `<reason>` is never
    given a literal wording for any of the three branches, so only the sentence's fixed halves are
    asserted here, the same discipline `TestVersionGateFailsBeforeAnySessionRequest` applies to
    the missing-version case's `<v>`. `copilot.agent_not_selected` / `warning` is D10's diagnostic
    table's only row naming D6 (`:1014`, source "D6 fallback") -- read the table fresh rather than
    assume a second, more specific code exists for this branch: no other row names D6 at all, so
    the one row covers every branch of the same check, this one included.

    **The deselect is scripted, not asserted here.** D6 (`:526-536`, review finding 6) also sends
    `session/set_config_option {agent: ""}` before the prompt on the same failure, and raises if it
    does not read back `""` -- that is tasks.md 1.9(t)'s own case, already named for a later part.
    This part's script answers that call so a real implementation reaches the prompt at all (a
    script omitting it would exhaust on the extra request), but makes no assertion about its
    params or the raise path -- inventing that coverage under (f)'s name would duplicate (t) before
    (t) exists. Ordering: design.md's own "posture step, every turn" paragraph (`:815-821`) states
    the posture step (which sends `session/set_mode`) runs "after new/load **and agent selection
    (D6)**" -- so the deselect, being part of D6, is scripted before `session/set_mode` here, not
    after; `_FakeACPSession` pops script entries strictly in call order regardless of method name,
    so a real implementation calling them in the other order would consume the wrong entries and
    fail loudly (either `script exhausted` or an unexpected shape reaching a later request), not
    pass silently for the wrong reason.
    """

    FOREIGN_DESCRIPTION = "A custom repository agent, unrelated to AgentWeave"

    async def test_foreign_description_sends_resource_block_and_diagnostic(self, monkeypatch):
        events = []
        sessions_bound = []
        stable_context = "## Charter\n- Ship safely.\n## Project instructions\n- Use py -3.11."
        per_turn_context = "## Workspace\n- root: C:\\work"
        tool_surface_context = "## Tools\n- agentweave-send_message"
        raw_prompt = "Please review the open PR."

        script = [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
                }
            },  # session/new
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME, description=self.FOREIGN_DESCRIPTION),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent -- foreign description, D6's check fails
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(""),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent "" -- D6's deselect, reads back "" (case (t)'s
            # territory, unasserted here)
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here too
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
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
            stable_context=stable_context,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1, events
        payload = diagnostics[0].payload
        assert payload["code"] == "copilot.agent_not_selected", payload
        assert payload["severity"] == "warning", payload
        assert payload["summary"].startswith(
            "Copilot did not select the AgentWeave agent file ("
        ), payload["summary"]
        assert payload["summary"].endswith(
            "); this turn's context was sent with the prompt instead."
        ), payload["summary"]

        methods = [m for m, _ in fake.sent_requests]
        prompt_calls = [(m, p) for m, p in fake.sent_requests if m == "session/prompt"]
        assert len(prompt_calls) == 1, methods
        prompt_params = prompt_calls[0][1]
        blocks = prompt_params["prompt"]
        assert len(blocks) >= 3, "resource block, context block and message must all be present"
        assert blocks[0] == {
            "type": "resource",
            "resource": {
                "uri": f"agentweave://context/{AGENT_NAME}/stable",
                "mimeType": "text/markdown",
                "text": stable_context,
            },
        }, blocks[0]
        assert blocks[1]["text"].startswith(copilot_acp.COPILOT_TURN_CONTEXT_HEAD)
        assert per_turn_context in blocks[1]["text"]
        assert tool_surface_context in blocks[1]["text"]
        assert (
            blocks[-1]["text"] == raw_prompt
        ), "the operator's message must still reach the wire byte-identical"

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)
        assert fake.closed_with_force is False, "D17: ACPProcess.close() on every exit, not forced"


class TestStopSendsSessionCancelAndInterrupts:
    """Tasks.md 1.9(g): stop -- `session/cancel` is sent, and `stopReason: cancelled` ->
    `interrupted`. D17 (design.md:1481-1505): once a stop is requested the client (1) sends
    `session/cancel {sessionId}` as a *notification*, not a request (design.md's own words,
    `:1486`) -- unlike Codex's `turn/interrupt`, a request Codex's own client awaits
    (`test_codex_appserver_run_turn.py::TestRunTurnInterrupt`); (2) waits (up to 10 s, `:1488`,
    not itself timed by this test) for the pending `session/prompt` to return
    `stopReason:"cancelled"`; (3) maps that to `TurnOutcome.status == "interrupted"` (`:1493`,
    "as for Codex"); (4) closes the process with `terminate_process_tree(pid, force=True)`, "not
    `proc.kill()`" (`:1489-1491`, because `copilot.exe` runs its shells as children a
    single-process kill would orphan) -- the one case in this file so far where
    `closed_with_force` is **not** `False`.

    **The stop signal itself, and where `should_interrupt` is polled, is this file's own
    least-invented reading, flagged as such.** D18 names `should_interrupt` as one of the
    callbacks this slice's `run_turn` takes (design.md:1514-1517), the same name Codex's own
    `run_turn` already has; D17's own "the client polls it as Codex does" cites Codex's `while
    True` loop, which checks `should_interrupt()` once per notification it reads
    (`codex_appserver.py:1022-1029`). This file's fake has no such loop of its own -- a
    `session/prompt` call's notifications are delivered to `on_notification` from *inside* the
    single `request()` call that also returns that prompt's eventual response (see the module
    docstring) -- so the only point this fake can give a real `run_turn` a chance to notice a
    stop while `session/prompt` is still pending is during that callback. This test's script
    places one otherwise-unremarkable `session/update` notification ahead of `session/prompt`'s
    own `stopReason:"cancelled"` response for exactly that reason: if a real implementation
    instead polls on some tick this fake cannot produce, this test fails loudly (the ordering
    assertion below, or `session/cancel` never sent), not silently.

    **Ordering is instrumented, not assumed.** `_CancelOrderingFake` (below) records whether
    `session/cancel` was sent *before* `session/prompt`'s own `request()` call has returned to
    its caller -- proving the notification precedes the response causally, not merely appearing
    first in some unordered set. A `run_turn` that instead waited for the full response and only
    then decided, after the fact, to call `session/cancel` would still produce the same set of
    sent messages but would fail this specific check (the CLAUDE.md ordering-evidence rule).
    """

    class _CancelOrderingFake(_FakeACPSession):
        def __init__(self, script):
            super().__init__(script)
            self.prompt_call_returned = False
            self.cancel_sent_before_prompt_returned = None

        async def request(self, method, params, *, timeout=30.0):
            result = await super().request(method, params, timeout=timeout)
            if method == "session/prompt":
                self.prompt_call_returned = True
            return result

        async def notify(self, method, params):
            await super().notify(method, params)
            if method == "session/cancel" and self.cancel_sent_before_prompt_returned is None:
                self.cancel_sent_before_prompt_returned = not self.prompt_call_returned

    async def test_should_interrupt_sends_session_cancel_and_returns_interrupted(self, monkeypatch):
        events = []
        sessions_bound = []

        script = [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
                }
            },  # session/new
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here too
            {
                "notification": "session/update",
                "params": {
                    "sessionId": SESSION_ID,
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "wor"},
                    },
                },
            },  # the one in-flight notification giving run_turn's own on_notification callback
            # the sole reentrant point this fake has while session/prompt is still pending --
            # see the class docstring
            {"response": {"stopReason": "cancelled"}},  # session/prompt's eventual result
        ]
        fake = self._CancelOrderingFake(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Please review the open PR.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
            should_interrupt=lambda: True,
        )

        cancel_calls = [(m, p) for m, p in fake.sent_notifications if m == "session/cancel"]
        assert len(cancel_calls) == 1, fake.sent_notifications
        assert cancel_calls[0][1] == {"sessionId": SESSION_ID}
        assert (
            fake.cancel_sent_before_prompt_returned is True
        ), "session/cancel must be sent while session/prompt is still pending, not after"
        assert (
            "session/cancel",
            {"sessionId": SESSION_ID},
        ) not in fake.sent_requests, "session/cancel is a notification (D17), not a request"

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="interrupted", error=None)
        assert fake.closed_with_force is True, "D17: terminate_process_tree(force=True) on a stop"


class TestEveryRequestPermissionAnsweredExactlyOnce:
    """Tasks.md 1.9(h): every `session/request_permission` is answered exactly once. Tasks.md
    states only the bare bullet; design.md's own contract for it is D8 step 5 (`:597-600`):
    "answer through one function that writes the JSON-RPC response ... . Every decision reaches
    the recorders, whichever step made it" -- i.e. each server-initiated request gets exactly one
    correlated JSON-RPC response, not zero (silently dropped) and not more than one (double
    answered), and the response it gets is the one *its own* id's decision produced, not another
    request's.

    A single request answered correctly is not evidence of this: a `run_turn` that always sent
    exactly one response regardless of which request it was answering would still pass a
    single-request script. This test therefore scripts **two** `session/request_permission`
    requests in one turn, judged to *different* outcomes under the `workspace` posture (an `edit`
    inside the workspace, and one outside -- design.md:637, and the same
    inside/outside-workspace distinguishing technique `TestFullAccessWithNoAllowAllOption` already
    uses for its own single request), each with its own id and `toolCallId`. Answering both
    correctly, in order, correlated by id, is evidence against dropping one, answering one twice,
    or swapping the two answers; answering only one, or answering one of them twice, or swapping
    the two responses, all fail the assertion below.
    """

    INSIDE_CALL_ID = "call_synthetic_exactly_once_edit_inside"
    OUTSIDE_CALL_ID = "call_synthetic_exactly_once_edit_outside"
    INSIDE_PATH = "C:\\work\\notes.txt"
    OUTSIDE_PATH = "C:\\other\\evil.txt"

    @staticmethod
    def _request_permission_entry(request_id, call_id, path):
        return {
            "server_request": {
                "id": request_id,
                "method": "session/request_permission",
                "params": {
                    "sessionId": SESSION_ID,
                    "toolCall": {
                        "toolCallId": call_id,
                        "title": f"Edit {path}",
                        "kind": "edit",
                        "rawInput": {"fileName": path},
                        "locations": [{"path": path}],
                    },
                    "options": [
                        {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
                        {
                            "optionId": "allow_always",
                            "name": "Always Allow",
                            "kind": "allow_always",
                        },
                        {"optionId": "reject_once", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            }
        }

    async def test_two_requests_in_one_turn_each_answered_once_and_correctly_correlated(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []

        script = [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
                }
            },  # session/new
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here too
            self._request_permission_entry(1, self.INSIDE_CALL_ID, self.INSIDE_PATH),
            self._request_permission_entry(2, self.OUTSIDE_CALL_ID, self.OUTSIDE_PATH),
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Please edit two files.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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

        ids_answered = [request_id for request_id, _ in fake.sent_responses]
        assert ids_answered == [1, 2], (
            "each session/request_permission must be answered exactly once, in order, "
            f"correlated by its own id; got {fake.sent_responses}"
        )
        assert fake.sent_responses == [
            (1, {"outcome": {"outcome": "selected", "optionId": "allow_once"}}),
            (2, {"outcome": {"outcome": "selected", "optionId": "reject_once"}}),
        ], "an edit inside the workspace and one outside must not be answered the same way"

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)
        assert fake.closed_with_force is False, "D17: ACPProcess.close() on every exit, not forced"


class TestUsageUpdateProducesMeasuredSampleWithResolvedModel:
    """Tasks.md 1.9(i): `usage_update` -> `on_usage` with a measured sample and the resolved
    model. D11 (design.md:1134-1136): `usage_update {used, size}` -> `ContextUsageSample(
    status="measured", source="copilot_acp", basis="provider_context", context_tokens=used,
    limit_tokens=size, model=<resolved model or requested>, breakdown=None)`. The raw shape --
    `sessionUpdate: "usage_update", used, size` under a `session/update` notification -- is
    VERIFIED directly against the real capture (`evidence/acp4-turn-mcp-shell-1.0.88.log:18`),
    not invented.

    **"the resolved model", not the requested one, is what this test is evidence for.** D10
    (`:1086-1088`) resolves the model from the first of `session.model_change`,
    `session.auto_mode_resolved` or `session.tools_updated` the client sees -- already the
    mapper's own job, tested directly in
    `test_copilot_acp_mapper.py::TestModelSubstitutionDiagnostic` via `session.tools_updated`. A
    `run_turn` that stamped its own `model` argument onto every `ContextUsageSample`, ignoring
    whatever the mapper resolved, would still pass a fixture whose resolved and requested models
    happen to match -- so the primary case below requests one model and resolves a *different*
    one via a `session.tools_updated` raw event (`github.com/copilot/sessionEvent {sessionId,
    type, timestamp, data}`, VERIFIED wire shape `design.md:73`) delivered before the
    `usage_update`, and asserts the sample carries the resolved name, not the requested one.

    **Where `run_turn` reads "the resolved model" from is this file's own least-invented reading,
    flagged as such** (same status as this file's other inferred surfaces, see the module
    docstring): no design.md line names the object that hands D11's step its resolved model: the
    mapper is the only place a resolved model is tracked at all (D10), so this test treats that
    tracking as D11's source too, without design.md saying so in those words. A future part or
    round should confirm or correct this against whatever `copilot_acp.py` actually does.

    A second test covers D11's own "or requested" half: with no raw event ever resolving a model
    before `usage_update` arrives, the sample must fall back to the turn's requested `model`
    argument -- otherwise a `None` model would reach the meter for a turn where Copilot resolves a
    model too early for this client to have subscribed a raw event catching it.
    """

    @staticmethod
    def _tools_updated_notification(model):
        return {
            "notification": "github.com/copilot/sessionEvent",
            "params": {
                "sessionId": SESSION_ID,
                "type": "session.tools_updated",
                "timestamp": "2026-09-30T00:00:07.000Z",
                "data": {"model": model},
            },
        }

    @staticmethod
    def _usage_update_notification(used, size):
        return {
            "notification": "session/update",
            "params": {
                "sessionId": SESSION_ID,
                "update": {"sessionUpdate": "usage_update", "used": used, "size": size},
            },
        }

    @staticmethod
    def _standard_prefix():
        return [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
                }
            },  # session/new
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here too
        ]

    async def test_resolved_model_from_tools_updated_overrides_the_requested_model(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []
        usages = []

        script = self._standard_prefix() + [
            self._tools_updated_notification("mai-code-1.1-flash"),
            self._usage_update_notification(12122, 128000),
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="What model is running?",
            model="claude-haiku-4.5",
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
            on_usage=_collector(usages),
        )

        assert len(usages) == 1, usages
        sample = usages[0]
        assert sample.status == "measured"
        assert sample.source == "copilot_acp"
        assert sample.basis == "provider_context"
        assert sample.context_tokens == 12122
        assert sample.limit_tokens == 128000
        assert sample.breakdown is None
        assert sample.model == "mai-code-1.1-flash", (
            "the sample must carry the model session.tools_updated resolved, not the requested "
            f"claude-haiku-4.5; got {sample.model!r}"
        )

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)

    async def test_falls_back_to_the_requested_model_when_nothing_has_resolved_one_yet(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []
        usages = []

        script = self._standard_prefix() + [
            self._usage_update_notification(12056, 128000),  # no tools_updated first
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="What model is running?",
            model="claude-haiku-4.5",
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
            on_usage=_collector(usages),
        )

        assert len(usages) == 1, usages
        assert usages[0].model == "claude-haiku-4.5", (
            "with no raw event ever resolving a model, D11's 'or requested' half must supply the "
            f"turn's own requested model; got {usages[0].model!r}"
        )
        assert usages[0].status == "measured"
        assert usages[0].context_tokens == 12056
        assert usages[0].limit_tokens == 128000

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)


class TestSpecTurnRestrictsWritesAndAllowAll:
    """Tasks.md 1.9(j): a specification turn (`restrict_spec_writes=True`), consistency pass
    2026-09-28, slice 3's D16, D9. The bare bullet names four independent sub-claims -- the spawn
    argv's `--excluded-tools` flag, full access never setting `allow_all` on plus judging a
    non-`edit` request as `workspace`, a `create` `edit` refused and recorded through
    `_on_refusal`, and (switch patched on) `set_mode` carrying the full plan URI before the
    prompt -- so, per this task's own queued caution (case (h) needed two requests, part 9/N
    needed two tests), this part gives each its own test rather than one test whose assertions
    could pass or fail together for the wrong reason.

    `decide_permission`'s own `spec_turn=True` decision table (which posture answers which
    `toolCall.kind` how) is already covered directly, case by case, in
    `test_copilot_acp_decide.py::TestSpecTurn` -- including the exact PowerShell-outside-workspace
    row this part's second test reuses (`test_spec_turn_under_full_access_judges_powershell_as_
    workspace`, `"Remove-Item ..\\..\\x"` -> REJECT) and the exact inside-workspace-edit-is-
    REJECTed-anyway row this part's third test reuses (`test_edit_inside_workspace_is_rejected_
    under_every_posture_on_a_spec_turn`). This file's job is only the wiring around that pure
    table: that `run_turn` actually builds the spec-turn argv, passes `spec_turn=True` through to
    `decide_permission`, and answers/records through the callbacks tasks.md 1.9(j) names -- not to
    re-derive `decide_permission`'s own table a second time.
    """

    @staticmethod
    def _standard_prefix(*, allow_all_current="off"):
        return [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [
                        _mode_option(),
                        _agent_option(""),
                        _allow_all_option(allow_all_current),
                    ],
                }
            },  # session/new
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option(allow_all_current),
                    ]
                }
            },  # session/set_config_option agent
        ]

    async def test_spawn_argv_excludes_copilots_edit_tools_but_keeps_create(self, monkeypatch):
        """Design.md:181-186 (D3), :211-218: one comma-joined argv word,
        `--excluded-tools=apply_patch,edit,str_replace,str_replace_editor`, sent unconditionally
        for a spec turn, including under full access -- and `create` is never in it, since a spec
        turn's own `shim` access path must still write its args file (D9 item 1)."""
        events = []
        sessions_bound = []
        captured_cmds = []

        script = self._standard_prefix() + [
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake, captured_cmds=captured_cmds)

        await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Write the specification document.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="shim",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=True,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        assert len(captured_cmds) == 1, "exactly one spawn per turn"
        cmd = captured_cmds[0]
        excluded_flags = [a for a in cmd if a.startswith("--excluded-tools=")]
        assert excluded_flags == [
            "--excluded-tools=apply_patch,edit,str_replace,str_replace_editor"
        ], cmd
        assert "create" not in excluded_flags[0].split("=", 1)[1].split(","), (
            "create is never excluded on a spec turn -- the shim access path must still write "
            "its own args file (D9 item 1)"
        )

    async def test_full_access_never_sets_allow_all_and_judges_execute_as_workspace(
        self, monkeypatch
    ):
        """D8 full-access bullet + D9 item 1a's closing paragraph (design.md:807-813, 904-908;
        operator decision 2026-09-28, open question 13, option (c)): a spec turn under full access
        never attempts `session/set_config_option allow_all=on` -- it reads `off` off both
        `session/new`'s and `session/set_config_option agent`'s own `configOptions` and leaves it
        there -- and its non-`edit` requests are judged as `workspace`, never the defensive ALLOW
        an ordinary full-access turn would give. Reusing `test_copilot_acp_decide.py::TestSpecTurn.
        test_spec_turn_under_full_access_judges_powershell_as_workspace`'s own outside-workspace
        command (`"Remove-Item ..\\..\\x"`) rather than inventing a new one."""
        events = []
        sessions_bound = []

        script = self._standard_prefix() + [
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here
            {
                "server_request": {
                    "id": 1,
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": SESSION_ID,
                        "toolCall": {
                            "toolCallId": "call_synthetic_spec_turn_execute_outside",
                            "title": "Run a PowerShell command",
                            "kind": "execute",
                            "rawInput": {"command": "Remove-Item ..\\..\\x"},
                        },
                        "options": [
                            {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
                            {
                                "optionId": "allow_always",
                                "name": "Always Allow",
                                "kind": "allow_always",
                            },
                            {"optionId": "reject_once", "name": "Reject", "kind": "reject_once"},
                        ],
                    },
                }
            },
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Please write the spec and run a check.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode="bypassPermissions",
            workspace="C:\\work",
            restrict_spec_writes=True,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        allow_all_sets = [
            (m, p)
            for m, p in fake.sent_requests
            if m == "session/set_config_option" and p.get("configId") == "allow_all"
        ]
        assert allow_all_sets == [], (
            "a spec turn never sets allow_all on, even under full access -- it never asks "
            f"Copilot for it at all; got {allow_all_sets}"
        )

        assert fake.sent_responses == [
            (1, {"outcome": {"outcome": "selected", "optionId": "reject_once"}})
        ], "an outside-workspace execute must be REJECTed once judged as workspace, not ALLOWed"

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)

    async def test_create_edit_is_rejected_and_recorded_through_on_refusal(self, monkeypatch):
        """D9 item 1a (design.md:896-908): until slice 3 lands there is no step-3 allow, so every
        `edit` request on a spec turn is REJECTed, in every posture -- including one naming a path
        *inside* the workspace, which the ordinary `workspace` posture would otherwise ALLOW
        outright (the same fixture `test_copilot_acp_decide.py::TestSpecTurn.
        test_edit_inside_workspace_is_rejected_under_every_posture_on_a_spec_turn` already proves
        at `decide_permission`'s own level) -- proving this is item 1a's blanket rule and not
        merely the ordinary workspace judge repeated. `create` is the Copilot tool this actually
        exercises in practice (never excluded by the spawn argv, unlike `apply_patch`/`edit`/
        `str_replace`/`str_replace_editor`), reported to the ACP client as an ordinary
        `kind:"edit"` request the same as any other edit tool (design.md gives no separate ACP
        `toolCall.kind` for it).

        `_on_refusal`'s exact `(method, subject)` shape for Copilot is not itself stated anywhere
        in design.md beyond "the same `_on_refusal` shape Codex uses" (design.md:866) -- this
        test's own least-invented reading, flagged the same way this file flags its other inferred
        surfaces, is that `method` is the wire method the refused request arrived on
        (`session/request_permission`) and `subject` is built from that request's own `toolCall`,
        so it asserts only what should hold under any reasonable reading of that sentence: exactly
        one refusal is recorded, tagged with that method, and identifying the request that was
        refused by the path it named.
        """
        events = []
        sessions_bound = []
        refusals = []

        async def _on_refusal(method, subject):
            refusals.append((method, subject))

        inside_path = "C:\\work\\x.py"
        script = self._standard_prefix() + [
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here
            {
                "server_request": {
                    "id": 1,
                    "method": "session/request_permission",
                    "params": {
                        "sessionId": SESSION_ID,
                        "toolCall": {
                            "toolCallId": "call_synthetic_spec_turn_create_x_py",
                            "title": "Create x.py",
                            "kind": "edit",
                            "rawInput": {"fileName": inside_path},
                            "locations": [{"path": inside_path}],
                        },
                        "options": [
                            {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
                            {
                                "optionId": "allow_always",
                                "name": "Always Allow",
                                "kind": "allow_always",
                            },
                            {"optionId": "reject_once", "name": "Reject", "kind": "reject_once"},
                        ],
                    },
                }
            },
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Please write the specification.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=True,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
            on_refusal=_on_refusal,
        )

        assert fake.sent_responses == [
            (1, {"outcome": {"outcome": "selected", "optionId": "reject_once"}})
        ], "an edit not naming the spec turn's own args file must be REJECTed, even inside the workspace"

        assert len(refusals) == 1, refusals
        method, subject = refusals[0]
        assert method == "session/request_permission", (method, subject)
        # Checked against the bare filename, not the full `inside_path`: `json.dumps` escapes
        # the path's own backslashes, so a direct substring check against the unescaped Python
        # string would fail even for a correct implementation.
        assert "x.py" in json.dumps(
            subject
        ), f"the recorded subject must identify which request was refused; got {subject!r}"

        assert sessions_bound == [SESSION_ID]
        assert outcome == TurnOutcome(session_id=SESSION_ID, status="completed", error=None)

    async def test_plan_mode_set_mode_carries_the_full_plan_uri_before_the_prompt(
        self, monkeypatch
    ):
        """D9 item 2 (design.md:909-919): with `SPEC_TURN_USES_PLAN_MODE` patched on, `run_turn`
        sends `session/set_mode` with the full URI `…session-modes#plan` (VERIFIED accepted,
        `r1-probe-plan.log:8`) after agent selection and before `session/prompt`. "The per-turn
        `set_mode` of D8's posture step sets `#agent` on every other turn either way" (`:937`)
        reads as: on *this* turn it does not also send a second, `#agent` one -- so this test
        scripts exactly one `session/set_mode` response and asserts exactly one such call was
        made, carrying the plan URI, not the ordinary agent-mode one."""
        monkeypatch.setattr(copilot_acp, "SPEC_TURN_USES_PLAN_MODE", True)
        events = []
        sessions_bound = []

        script = self._standard_prefix() + [
            {"response": {}},  # session/set_mode -- the #plan call this test asserts
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Draft the specification.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=True,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        methods = [m for m, _ in fake.sent_requests]
        set_mode_calls = [(m, p) for m, p in fake.sent_requests if m == "session/set_mode"]
        assert len(set_mode_calls) == 1, (
            "a plan-mode spec turn must send exactly one session/set_mode, carrying the plan "
            f"URI, not also D8's ordinary #agent one; got {set_mode_calls}"
        )
        _, params = set_mode_calls[0]
        assert params == {"sessionId": SESSION_ID, "modeId": PLAN_MODE_URI}, params

        i_set_mode = methods.index("session/set_mode")
        i_prompt = methods.index("session/prompt")
        assert i_set_mode < i_prompt, methods


class TestPrePromptErrorRaisesCopilotACPErrorAsAppServerError:
    """Tasks.md 1.9(k) (R2, narrowed in R3): a JSON-RPC `error` response to a request **before**
    the prompt (e.g. `session/new`) raises `CopilotACPError` carrying `.code` and `.data`, and it
    **is** an `AppServerError`. Read D12 fresh by grepping "AppServerError"/"CopilotACPError"
    rather than assuming a line range, landing on design.md:1167-1179: `CopilotACPError`
    subclasses `codex_appserver.AppServerError` specifically so the executor's pre-spawn `except
    (FileNotFoundError, AppServerError, asyncio.TimeoutError, OSError)` (`agent_trigger.py:3244`)
    catches it, and `.data` (`:1179`, needed by slice 4's contract item 12, `:1777`) is not yet
    asserted anywhere in this file.

    Case (c)'s `TestSessionLoadNotFoundRebinds` already scripts an `{"error": {...}}` entry, but
    for `session/load`'s own `-32002`, which is *recovered* (a fresh `session/new` follows, per
    D7) rather than re-raised -- it never reaches a `pytest.raises` at all, and asserts neither
    `.code` nor `.data`, so this is new coverage, not a duplicate. Case (p) (tasks.md 1.9(p))
    separately covers `session/new` answered exactly `-32000`, an auth-specific error with its own
    `CopilotProbe`-verdict assertion; this part deliberately scripts a *different* code so its own
    scope -- the generic "any pre-prompt error raises, is an `AppServerError`, and carries
    `.code`/`.data`" -- is not confused with (p)'s auth-specific one. The exact code/message/data
    used here (`-32603`, `"Internal error"`, `{"detail": ...}`) is not captured in any evidence
    log -- CODE-only, synthetic, flagged the same way case (b)'s replayed-chunk shape was,
    standing in for "some pre-prompt error that is neither -32002 nor -32000".
    """

    async def test_session_new_error_raises_copilot_acp_error_as_app_server_error(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []

        script = [
            {"response": INIT_RESPONSE},
            {
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"detail": "synthetic pre-prompt failure, not captured evidence"},
                }
            },  # session/new
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        with pytest.raises(CopilotACPError) as exc_info:
            await run_turn(
                cwd="C:\\work",
                env=None,
                prompt="Anything changed since I left?",
                model=None,
                resume_session_id=None,
                agent=AGENT_NAME,
                per_turn_context="## Workspace\n- root: C:\\work",
                tool_surface_context="## Tools\n- agentweave-send_message",
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

        err = exc_info.value
        assert isinstance(err, AppServerError), (
            "CopilotACPError must subclass codex_appserver.AppServerError (D12) so the "
            "executor's pre-spawn except tuple (agent_trigger.py:3244) catches it"
        )
        assert err.code == -32603, err.code
        assert err.data == {
            "detail": "synthetic pre-prompt failure, not captured evidence"
        }, err.data

        methods = [m for m, _ in fake.sent_requests]
        assert methods == [
            "initialize",
            "session/new",
        ], "no session/prompt may be sent once a pre-prompt request errors"
        assert fake.closed_with_force is False, "D17: the process is still closed, not forced"
        assert sessions_bound == [], "on_session must never fire when no session was ever bound"


class TestSessionNewAuthErrorMarksProbeNotAuthorized:
    """Tasks.md 1.9(p) (R3): `session/new` answered `-32000` raises, and `CopilotProbe`'s verdict
    reads not authorized before the raise propagates.

    Case (k)'s `TestPrePromptErrorRaisesCopilotACPErrorAsAppServerError` already covers the
    generic "any pre-prompt error raises, is an `AppServerError`, carries `.code`/`.data`" claim
    with a deliberately different code (`-32603`), so its scope stays distinct from this one
    (that class's own docstring says so). This case is scoped to the auth-specific consequence
    design.md `:1215-1217` names: *"When ... `session/new` fails `-32000`, `run_turn` writes that
    verdict into `CopilotProbe` (D15) before raising."* `-32000` and its message "Authentication
    required" are CODE (design.md `:1398-1399`, `app.js` `newSession` -> `ps.authRequired()`); the
    `reason` sentence asserted below ("Copilot CLI is not signed in. Run `copilot login`.") is
    D15's own table row for this state (design.md `:1409`), reused here as the least-invented
    reading of "that verdict" -- `run_turn` presumably writes the same verdict shape
    `CopilotProbe`'s own refresh would have concluded, not a distinct message of its own.

    `hub.copilot_probe.CopilotProbe` does not exist yet, and design.md never names its write
    side, only the read one (`CopilotProbe.verdict()`, used verbatim three times). This part
    invents a `CopilotProbe.record(present=, authorized=, reason=)` call (`_FakeCopilotProbe`,
    module-level above) as the least-invented symmetric guess, flagged for a future round the way
    part 1/N flagged its own invented names. `copilot_acp.CopilotProbe` is patched the same way
    `_patch_spawn` already patches `copilot_acp.resolve_copilot_executable` -- `raising=False`, so
    a real implementation that reaches the singleton some other way (not a name bound directly in
    `copilot_acp`'s own namespace) makes this patch a no-op, and the untouched fake's
    `authorized=True` starting state then fails the assertion loudly instead of passing for the
    wrong reason.
    """

    async def test_session_new_auth_error_raises_and_marks_probe_not_authorized(self, monkeypatch):
        events = []
        sessions_bound = []

        script = [
            {"response": INIT_RESPONSE},
            {"error": {"code": -32000, "message": "Authentication required"}},  # session/new
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        fake_probe = _FakeCopilotProbe()
        monkeypatch.setattr(copilot_acp, "CopilotProbe", fake_probe, raising=False)

        with pytest.raises(CopilotACPError) as exc_info:
            await run_turn(
                cwd="C:\\work",
                env=None,
                prompt="Anything changed since I left?",
                model=None,
                resume_session_id=None,
                agent=AGENT_NAME,
                per_turn_context="## Workspace\n- root: C:\\work",
                tool_surface_context="## Tools\n- agentweave-send_message",
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

        err = exc_info.value
        assert err.code == -32000, err.code

        verdict = fake_probe.verdict()
        assert verdict["authorized"] is False, (
            "run_turn must write an unauthorized verdict into CopilotProbe before the -32000 "
            f"raise propagates (design.md:1215-1217); got {verdict!r}"
        )
        assert verdict["present"] is True, (
            "the executable ran and answered -- absent would be a different D15 row (not "
            f"resolvable at all); got {verdict!r}"
        )
        assert verdict["reason"] == "Copilot CLI is not signed in. Run `copilot login`.", verdict[
            "reason"
        ]

        methods = [m for m, _ in fake.sent_requests]
        assert methods == [
            "initialize",
            "session/new",
        ], "no session/prompt may be sent once session/new errors"
        assert sessions_bound == [], "on_session must never fire when no session was ever bound"


def _minimal_valid_run_turn_kwargs():
    """The same 17-keyword surface `TestNewSessionSequence` calls `run_turn` with (this file's
    own least-invented reading of `run_turn`'s signature, not a design citation) -- reused here
    only to prove a rejected extra keyword, never awaited, so no script/fake session is needed."""
    return {
        "cwd": "C:\\work",
        "env": None,
        "prompt": "Anything changed since I left?",
        "model": None,
        "resume_session_id": None,
        "agent": AGENT_NAME,
        "per_turn_context": "## Workspace\n- root: C:\\work",
        "tool_surface_context": "## Tools\n- agentweave-send_message",
        "stable_context": None,
        "control_overrides": None,
        "told_access_path": "mcp",
        "permission_mode": None,
        "workspace": "C:\\work",
        "restrict_spec_writes": False,
        "extra_flags": None,
        "on_event": lambda *a, **k: None,
        "on_session": lambda *a, **k: None,
    }


class TestNoRemovedRawEventCallbackOrOutcomeFields:
    """Tasks.md 1.9(l) (R2, amended in R3), second half only. The first half -- `initialize`
    subscribing `clientCapabilities._meta["github.com/copilot"].events` to
    `COPILOT_RAW_EVENTS`, de-duplicated, including `tool.execution_start` and `session.error` --
    is already asserted directly by `TestNewSessionSequence`
    (`test_initialize_new_agent_then_prompt_in_order_with_context_first`, `:324-329`); repeating
    it here under a new name would duplicate that part's own coverage, not add to it.

    What remains uncovered is (l)'s *negative* clause: "there is no `on_raw_event` callback and
    no `prompt_usage`/`session_was_new` field". Read D10's full R3 paragraph fresh
    (design.md:1118-1130, plus its restatements at `:1546`, `:1712`, `:1777-1781`) rather than
    trusting this docstring's own summary of it: R2 had added an `on_raw_event` callback and two
    `TurnOutcome` fields, `prompt_usage`/`session_was_new`, for slice 4; R3 removed all three
    because slice 1's rule is that no member exists without a caller, and slice 4 (its own D2,
    "why not slice 2's `on_raw_event`", and its contract item 11) does not consume them --
    consuming them here would put a Copilot ledger inside the generic executor. Slice 4 instead
    gets an internal dispatch point (`_on_armed_raw_event`), the prompt result read in one place,
    and a local `session_was_new`, none of which cross `run_turn`'s own public boundary.

    No evidence-log line constrains this claim -- it is a negative shape assertion about the
    module's own contract, not a captured wire behaviour -- so the exact mechanism is this part's
    own judgment call, flagged the same way this file flags its other inferred surfaces:
    (1) `dataclasses.fields(TurnOutcome)` must not name `prompt_usage` or `session_was_new`;
    (2) calling `run_turn` with an `on_raw_event=` keyword, in addition to its ordinary surface,
    must raise `TypeError` for an unexpected keyword argument -- proved dynamically (the call
    itself, never awaited) rather than only by static `inspect.signature` inspection, so a
    `run_turn(**kwargs)` catch-all sink that silently swallowed the keyword would still fail this
    test, not just a `run_turn` that spells the parameter out by name.
    """

    async def test_turn_outcome_has_no_prompt_usage_or_session_was_new_field(self):
        field_names = {f.name for f in dataclasses.fields(TurnOutcome)}
        assert "prompt_usage" not in field_names, (
            "R3 removed prompt_usage from TurnOutcome (D10); slice 4 owns its own usage "
            "sample instead"
        )
        assert (
            "session_was_new" not in field_names
        ), "R3 removed session_was_new from TurnOutcome (D10); it stays a local inside run_turn"

    async def test_run_turn_rejects_an_on_raw_event_keyword(self):
        kwargs = _minimal_valid_run_turn_kwargs()
        kwargs["on_raw_event"] = lambda *a, **k: None
        with pytest.raises(TypeError):
            run_turn(**kwargs)

        assert "on_raw_event" not in inspect.signature(run_turn).parameters, (
            "R3 removed the on_raw_event callback (D10); slice 4's needs are met inside "
            "run_turn, not through a caller-supplied hook"
        )


class TestProcessTerminatedWithForceOnAFailedTurnToo:
    """Tasks.md 1.9(m) (R2): "the process tree is terminated on a failed turn too, not only on a
    stop". Read D17 fresh (design.md:1481-1505) rather than trusting the queued caution's own
    paraphrase, together with tasks.md's (n)/(o) bullets, before deciding what this case actually
    narrows to.

    D17 step 3 gives a stop's own close: `terminate_process_tree(pid, force=True)`, "not
    `proc.kill()`", because "`copilot.exe` runs its shells as children" (`:1489-1491`). `:1501-1503`
    then generalises: "`ACPProcess.close()` therefore uses `terminate_process_tree` on **every**
    exit, not only after a stop: a turn that fails or times out with a shell still running would
    otherwise leave `powershell.exe` behind exactly as a stop would." Two different things are
    bundled in that sentence, and only one is testable from this file's own vantage point:

    - *which primitive* `ACPProcess.close()` calls internally (`terminate_process_tree` vs a bare
      single-process kill) is invisible here -- `_patch_spawn` hands `run_turn` this file's own
      `_FakeACPSession` in place of the real `ACPProcess`, so `run_turn` never touches the real
      `close()` body at all. That half of D17's claim is `ACPProcess`'s own unit to prove (not yet
      written; task 1.9 tests `run_turn`, not `ACPProcess` directly), not this file's.
    - what this file *can* observe is the `force` value `run_turn` itself passes to `close()` --
      already exercised for every *pre-prompt* failure this file has covered so far (the version
      gate, part 4/N; a pre-prompt JSON-RPC error, part 11/N), each asserting `force is False`, on
      the reasoning (this file's own inference, not yet checked against this sentence until now)
      that no shell could be running before `session/prompt` is ever sent, so `force=False`
      (`SIGTERM` via `terminate_process_tree`, `pty_runner.py:213`) is enough there. This case is
      the first *post*-prompt failure this file scripts, and the reconciliation holds: `:1501-1503`
      draws the line at "a shell still running", which is only possible once `session/prompt` has
      actually been sent -- so a pre-prompt failure keeping `force=False` and a post-prompt failure
      getting `force=True` are not a contradiction, they are the same rule read at two different
      points in the turn. Task 1.9(n) is the one that will fully test this scenario's returned
      `TurnOutcome` (the error, `stderr_tail`) and the "process exits after the prompt is written"
      variant; this case's own test reuses (n)'s first scenario (a JSON-RPC `error` response to
      `session/prompt` itself) only far enough to prove the close-force claim, and does not repeat
      (n)'s own assertions in full here, matching this file's usual don't-duplicate-a-later-case's-
      coverage discipline (e.g. case (i)'s note on `test_copilot_acp_mapper.py`, part 9/N).
    """

    async def test_close_uses_force_true_when_session_prompt_itself_errors(self, monkeypatch):
        sessions_bound = []
        events = []

        script = [
            {"response": INIT_RESPONSE},
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
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"detail": "synthetic post-prompt failure, not captured evidence"},
                }
            },  # session/prompt itself errors -- a shell could already be running by now
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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

        # Corroboration only, not this test's main claim (that is (n)'s job in full): a
        # `run_turn` that raised instead of returning, or that somehow reported success, would
        # not be exercising the failure path this case is about at all.
        assert outcome.status == "failed", (
            "the fake's session/prompt error must reach run_turn as a failed turn, not "
            "propagate as an uncaught exception (that is (n)'s own claim, sanity-checked here "
            "only so far as to confirm this is the scenario under test)"
        )
        assert fake.closed_with_force is True, (
            "D17 :1501-1503: a shell could be running by the time session/prompt has been "
            "sent, so a failure from this point on must close with force=True, exactly as a "
            "stop does -- not force=False as this file's pre-prompt failures do"
        )


def _session_established_script(*, tail_entry=None, tail_entries=None):
    """The four waypoints every case in this file scripts before a turn can fail *after* the
    prompt is written -- `initialize` / `session/new` / `session/set_config_option agent` /
    `session/set_mode` -- exactly as `TestProcessTerminatedWithForceOnAFailedTurnToo` (part
    13/N) scripts them, plus whatever stands in for `session/prompt` itself: either a single
    `tail_entry` (part 14/N's shape, kept for its two already-committed call sites) or an
    ordered `tail_entries` list (part 15/N: case (o) needs an armed `session.error` notification
    delivered *during* the still-pending `session/prompt` call, ahead of its own response entry
    -- the same in-flight-notification mechanism `TestStopSendsSessionCancelAndInterrupts`
    (part 6/N) already relies on, not a new one). Exactly one of the two must be given. Factored
    out here because every case built on top of this helper differs in nothing else."""
    if (tail_entry is None) == (tail_entries is None):
        raise AssertionError("pass exactly one of tail_entry or tail_entries")
    return [
        {"response": INIT_RESPONSE},
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
        *([tail_entry] if tail_entries is None else tail_entries),
    ]


class TestPostPromptFailuresReturnFailedOutcomeNotRaise:
    """Tasks.md 1.9(n): "a `session/prompt` answered with a JSON-RPC error, and separately a
    process that exits after the prompt is written, each **return** `TurnOutcome(status="failed")`
    with the error and `stderr_tail`, and raise nothing."

    Design.md `:1207` ("**Returns** `TurnOutcome(status="failed", error=…, stderr_tail=…)`:
    anything after [the prompt is written]. That covers a JSON-RPC error answering the prompt
    …, process exit before the prompt resolves, a timeout, and an armed `session.error`")
    confirms `stderr_tail` is a real field, not this file's own invention -- read fresh here
    rather than assumed, since no earlier part in this file had asserted it (part 13/N's own
    case (m) test checked only `outcome.status`, deliberately deferring the error/`stderr_tail`
    shape to this case, `:2010-2011`). `codex_appserver.TurnOutcome.stderr_tail` (`:901`) is
    `Optional[str] = None` with a doc-comment reason ("the only route by which the child's own
    complaint reaches the operator") that applies identically here, so this file's own
    `TurnOutcome` is read the same way: a field with a default, not a required one, consistent
    with every earlier `TurnOutcome(session_id=.., status="completed", error=None)` equality
    check in this file never having had to pass it.

    Scenario 2 -- "a process that exits after the prompt is written" -- had no way to be
    expressed by this file's harness before this part: `_FakeACPSession.is_running()` always
    returned `True` until `close()` was called, and `request()` only ever returned, raised a
    JSON-RPC `CopilotACPError`, or drained a notification/server_request -- none of which model
    "the process is simply gone, no response is or ever will be coming". Extended the fake with
    a fourth script-entry kind, `{"process_exited": True}` (documented in `_FakeACPSession`'s own
    docstring, the same way part 2/N documented extending `_patch_spawn`): it sets
    `self._running = False` and raises `self.process_ended_error(method)`, a new fake method
    returning `codex_appserver.AppServerError` (not `CopilotACPError` -- there is no JSON-RPC
    `.code`/`.data` for a death with no response at all), mirroring
    `test_codex_appserver_run_turn.py`'s own `_FakeSession.process_ended_error`. Also gave the
    fake a configurable `stderr_tail` constructor argument (previously hardcoded `""`, since no
    earlier case needed the plumbing) so both scenarios below can prove it reaches
    `TurnOutcome.stderr_tail` unchanged.
    """

    async def test_session_prompt_json_rpc_error_returns_failed_outcome_with_stderr_tail(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []

        script = _session_established_script(
            tail_entry={
                "error": {
                    "code": -32603,
                    "message": "Internal error",
                    "data": {"detail": "synthetic post-prompt failure, not captured evidence"},
                }
            }  # session/prompt itself errors
        )
        fake = _FakeACPSession(script, stderr_tail="shell exited 1: file not found\n")
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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

        assert outcome.status == "failed"
        assert outcome.session_id == SESSION_ID, (
            "the session was already bound (session/new succeeded) before session/prompt "
            "failed -- a failure this late must not report the outcome as sessionless"
        )
        assert outcome.error is not None and "Internal error" in outcome.error, (
            "the JSON-RPC error's own message must reach the caller through outcome.error, "
            f"got {outcome.error!r}"
        )
        assert outcome.stderr_tail == "shell exited 1: file not found\n", (
            "design.md:1207's stderr_tail must be the session's own tail, not dropped, "
            f"got {outcome.stderr_tail!r}"
        )

    async def test_process_exit_after_prompt_written_returns_failed_outcome_not_raise(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []

        script = _session_established_script(tail_entry={"process_exited": True})
        fake = _FakeACPSession(script, stderr_tail="powershell.exe: Access is denied.\n")
        _patch_spawn(monkeypatch, fake)

        # No pytest.raises: (n)'s own text is "raise nothing" for this scenario too, exactly as
        # for the JSON-RPC-error one above -- a run_turn that let the fake's AppServerError
        # propagate would fail this call itself, not just an assertion below.
        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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

        assert outcome.status == "failed"
        assert outcome.session_id == SESSION_ID
        assert outcome.error is not None and "session/prompt" in outcome.error, (
            "the pending request's own method name must reach the caller through outcome.error "
            f"(mirroring codex_appserver's own process-death message shape), got "
            f"{outcome.error!r}"
        )
        assert (
            outcome.stderr_tail == "powershell.exe: Access is denied.\n"
        ), f"got {outcome.stderr_tail!r}"
        assert fake.is_running() is False, (
            "the fake's own process_exited entry already marks it dead -- run_turn must not "
            "re-resurrect it, e.g. by unconditionally setting _running back to True somewhere"
        )


class TestArmedSessionErrorFailsUnlessStopWins:
    """Tasks.md 1.9(o): "an armed raw `session.error` followed by `stopReason: end_turn` returns
    `status == "failed"` with the event's `message`. With `stopReason: cancelled` it is
    `interrupted`."

    Design.md's own statement of the rule (`:1040-1046`, "A session error fails the turn (R3)"):
    a raw `session.error` armed in this turn ends the turn `TurnOutcome(status="failed",
    error=<its message>)`, *whatever stop reason `session/prompt` returns, unless the stop
    reason is `cancelled`* -- "a stop wins, D17" (`:1043`, also restated at `:1209-1210`, "A stop
    still wins, and gives `interrupted` (D17)"). Copilot turns the error into message text and
    may still answer `end_turn` (`:1044`) -- the whole reason this rule exists is that, without
    it, a turn where the model call itself failed would otherwise read `completed`.

    This case's `session.error` is the **root** agent's: its envelope carries no `agentId`, so
    D10's separate "only a root `session.error` fails the turn" carve-out (`:1053-1059`, "review
    finding 8", cited by tasks.md's own case list as bullet 19 of the *Provided to slices 3-5*
    section, not case (o)) does not apply here and is not this case's to test -- a subagent's
    envelope shape belongs with whichever later part covers that finding.

    Both scenarios below arm the raw event the same way `TestUsageUpdateProducesMeasuredSample
    WithResolvedModel` (part 9/N) armed `session.tools_updated`: a `notification` script entry
    for `github.com/copilot/sessionEvent` delivered *during* the still-in-flight `session/prompt`
    call, immediately before that call's own response entry -- the one point this fake's
    strictly-ordered script can deliver anything to `run_turn` while `session/prompt` is still
    pending (this file's module docstring). Neither scenario calls `should_interrupt`: (o)'s own
    text ties the `interrupted` outcome to `session/prompt`'s returned `stopReason` alone, not to
    the client having requested a stop, so `run_turn` is given no reason to send `session/cancel`
    itself, and neither test asserts on it.

    `_session_established_script`'s `tail_entries` (part 15/N's own extension, above) supplies
    the four pre-prompt waypoints and this case's two-entry tail in one call; case (n)'s two
    already-committed tests keep using its single-entry `tail_entry` form unchanged.
    """

    @staticmethod
    def _armed_session_error_notification(message):
        return {
            "notification": "github.com/copilot/sessionEvent",
            "params": {
                "sessionId": SESSION_ID,
                "type": "session.error",
                "timestamp": "2026-09-30T00:00:09.000Z",
                "data": {"errorType": "model_error", "message": message},
            },
        }

    async def test_armed_session_error_then_end_turn_returns_failed_with_events_message(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []
        message = "Model call failed: upstream rate limited"

        script = _session_established_script(
            tail_entries=[
                self._armed_session_error_notification(message),
                {
                    "response": {
                        "stopReason": "end_turn",
                        "usage": {"inputTokens": 1, "outputTokens": 1},
                    }
                },  # session/prompt's own eventual result -- Copilot still answers end_turn
            ]
        )
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Summarise the failing build.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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

        assert outcome.status == "failed", (
            "design.md:1040-1046: an armed session.error fails the turn whatever stopReason "
            f"session/prompt returns, including end_turn -- got status {outcome.status!r}"
        )
        assert outcome.session_id == SESSION_ID
        assert outcome.error is not None and message in outcome.error, (
            "the event's own message must reach outcome.error, " f"got {outcome.error!r}"
        )

    async def test_armed_session_error_then_cancelled_returns_interrupted(self, monkeypatch):
        events = []
        sessions_bound = []
        message = "Model call failed: upstream rate limited"

        script = _session_established_script(
            tail_entries=[
                self._armed_session_error_notification(message),
                {"response": {"stopReason": "cancelled"}},  # a stop wins over the armed error
            ]
        )
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Summarise the failing build.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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

        assert outcome == TurnOutcome(session_id=SESSION_ID, status="interrupted", error=None), (
            "design.md:1043, 1209-1210: 'a stop wins' -- stopReason cancelled must give "
            f"interrupted even with an armed session.error pending, got {outcome!r}"
        )


class TestPromptOrderingAndControlOverridesArgv:
    """Tasks.md 1.9(q) (`:282`): "the prompt's first text block is `per_turn_context` then
    `tool_surface_context`, and `control_overrides {"effort": "high"}` puts
    `--reasoning-effort high` on the spawn argv." Two independent sub-claims -- one about
    `session/prompt`'s own content, the other about the spawned argv -- so, per this task's own
    queued caution (case (j) needed four tests, case (h) needed two), each gets its own test.

    **Ordering.** Design.md `:473-477`: "`per_turn`, then `tool_surface`, go into the
    `session/prompt` content as the first text block" -- an ordering claim, not just the
    both-present check case (a)'s own `TestNewSessionSequence` already makes (part 1/N, `:410-411`,
    ``per_turn_context in blocks[0]["text"]`` / ``tool_surface_context in blocks[0]["text"]``, no
    relative position asserted). This part reuses that same first-block shape but additionally
    checks `per_turn_context`'s own position precedes `tool_surface_context`'s.

    **Control overrides.** Design.md `:1537-1541` (D18, R3): `control_overrides` is the raw
    catalog controls, added because Copilot's Effort is a **flag** control (D13 `:1259-1261`,
    `ApplySpec("flag", "--reasoning-effort {value}")`) that `render_control_config` (the rendering
    `config_overrides` already gets) skips -- "without the raw controls `run_turn` could not
    produce `--reasoning-effort`." D13 `:1266-1267` (R2): "the effort control is rendered to argv
    by `render_control_args("copilot", overrides)` inside the Copilot `run_turn` (D3), since the
    trigger builds no Copilot argv." `render_control_args` itself already exists and is not this
    slice's own (`hub/hub/model_catalog.py:612-646`, shared with Codex) -- confirmed there that a
    `"flag"`-style spec renders `rendered.split(" ")` (`:645`), i.e. two argv words,
    `"--reasoning-effort"` then `"high"`, not one `--reasoning-effort=high` word (that spelling is
    case (j)'s `--excluded-tools=...`, a different control's own single-word style, not this one's
    -- checked, not assumed, per this file's part 5/N correction about not carrying a spelling
    across cases without checking). This test's job is only that `run_turn` wires
    `control_overrides` through to that existing renderer and onto the real spawn argv -- not to
    re-derive `render_control_args`'s own behaviour a second time.
    """

    async def test_first_prompt_block_orders_per_turn_context_before_tool_surface_context(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []
        per_turn_context = "## Workspace\n- root: C:\\work"
        tool_surface_context = "## Tools\n- agentweave-send_message"

        script = _session_established_script(
            tail_entry={
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            }
        )
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Summarise the failing build.",
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

        prompt_calls = [(m, p) for m, p in fake.sent_requests if m == "session/prompt"]
        assert len(prompt_calls) == 1, "exactly one session/prompt per turn"
        blocks = prompt_calls[0][1]["prompt"]
        first_text = blocks[0]["text"]
        assert per_turn_context in first_text and tool_surface_context in first_text
        assert first_text.index(per_turn_context) < first_text.index(tool_surface_context), (
            "design.md:473-477: per_turn_context must precede tool_surface_context in the "
            f"first block, got {first_text!r}"
        )

    async def test_control_overrides_effort_high_puts_reasoning_effort_on_spawn_argv(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []
        captured_cmds = []

        script = _session_established_script(
            tail_entry={
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            }
        )
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake, captured_cmds=captured_cmds)

        await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Summarise the failing build.",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides={"effort": "high"},
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        assert len(captured_cmds) == 1, "exactly one spawn per turn"
        cmd = captured_cmds[0]
        assert "--reasoning-effort" in cmd, cmd
        i = cmd.index("--reasoning-effort")
        assert cmd[i + 1] == "high", (
            "design.md:1260-1261, 1266-1267: the effort control is a 'flag' ApplySpec, rendered "
            f"as two argv words by render_control_args's own split(' ') -- got {cmd!r}"
        )
        assert "--reasoning-effort=high" not in cmd, (
            "the flag style is two words, not one '=' word (that spelling belongs to "
            "--excluded-tools, case (j), a different control)"
        )


class TestEmptyContextStillOpensWithHeadNotAMessageSlashCommand:
    """Tasks.md 1.9(r) (`:283`, review note 15 and the D5 answer): "the first block opens with
    `COPILOT_TURN_CONTEXT_HEAD`; with `per_turn_context` and `tool_surface_context` both empty
    and the message `/allow-all on`, the prompt still has two blocks and the first does not
    start with `/`."

    Design.md `:482-488` (review, finding 15): Copilot runs a one-block prompt starting with `/`
    as a slash command (`/allow-all`, `/permissions`, `/autopilot` and `/add-dir` exist), so a
    message from another agent that happens to read `/allow-all on` must never become that one
    block -- `COPILOT_TURN_CONTEXT_HEAD` "makes the first block non-empty and non-`/` even when
    `per_turn_context` and `tool_surface_context` are both empty, and the message is always a
    block of its own after it." This is an invariant about the empty-context edge, not the
    ordering claim case (q)'s own `TestPromptOrderingAndControlOverridesArgv` already covers (that
    test's fixtures both have non-empty context strings) -- so it needs its own fixture: empty
    `per_turn_context`/`tool_surface_context` and a message that literally reads `/allow-all on`.
    """

    async def test_empty_context_head_line_alone_keeps_two_blocks_first_not_starting_with_slash(
        self, monkeypatch
    ):
        events = []
        sessions_bound = []
        message = "/allow-all on"

        script = _session_established_script(
            tail_entry={
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            }
        )
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        await run_turn(
            cwd="C:\\work",
            env=None,
            prompt=message,
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="",
            tool_surface_context="",
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

        prompt_calls = [(m, p) for m, p in fake.sent_requests if m == "session/prompt"]
        assert len(prompt_calls) == 1, "exactly one session/prompt per turn"
        blocks = prompt_calls[0][1]["prompt"]
        assert len(blocks) >= 2, (
            "design.md:482-488: the prompt must never collapse to one block even when both "
            f"context strings are empty -- got {blocks!r}"
        )
        first_text = blocks[0]["text"]
        assert first_text.startswith(copilot_acp.COPILOT_TURN_CONTEXT_HEAD), (
            "the head line alone must open the first block regardless of empty context, "
            f"got {first_text!r}"
        )
        assert not first_text.startswith("/"), (
            "a first block starting with '/' would run as a Copilot slash command, not text -- "
            f"got {first_text!r}"
        )
        assert blocks[-1]["text"] == message, (
            "the operator's message, even one that reads like a slash command, must reach the "
            "wire byte-identical as its own block, never merged into the first"
        )
        assert not blocks[-1]["text"].startswith(copilot_acp.COPILOT_TURN_CONTEXT_HEAD)


class TestPostureStepEveryTurn:
    """Tasks.md 1.9(s) (`:284`, review finding 4): a five-clause bullet -- "a `session/load`
    response with `currentModeId` `#plan` on a non-spec turn -> `set_mode #agent` is sent before
    the prompt; `#autopilot` likewise; `allow_all` `on` after load under `workspace` -> `off` is
    set and read back; an `off` that reads back `on` -> `run_turn` raises and **no**
    `session/prompt` is sent; an armed `session.mode_changed` into `#autopilot` under `workspace`
    -> `session/cancel`, a `copilot_posture_escalated` error, status `failed`."

    Read design.md's *The posture step, every turn* fresh (`:815-843`, review 2026-09-28, finding
    4) rather than assuming the bullet's own clause boundaries: it turns out to be that section's
    numbered steps 1, 3 and 4, restated for `session/load` specifically (step 2, full access, is
    a different case's scope, already covered by `TestSpecTurnRestrictsWritesAndAllowAll`'s
    `test_full_access_never_sets_allow_all_and_judges_execute_as_workspace`, and by no non-spec
    case yet). Five independent sub-claims by count, and per this task's own queued caution (case
    (j) needed four tests, case (h) two, case (q) two) each gets its own test here too, rather
    than one test whose assertions could pass or fail together for the wrong reason:

    1. step 1, "Always `session/set_mode`... whatever the load reported" -- `#plan` loaded, `#agent`
       sent;
    2. the same step 1 rule, `#autopilot` loaded;
    3. step 3's success half: `allow_all` read `"on"` off the load response is set `"off"` and the
       set's own response confirms it read back `"off"` -- the turn proceeds to the prompt;
    4. step 3's failure half: the set's own response still reads back `"on"` -- `run_turn` raises
       before the prompt (D12, the message design.md gives verbatim, `:838-839`) and no
       `session/prompt` is ever sent;
    5. step 4: an **armed** `session.mode_changed` into `#autopilot`, delivered while
       `session/prompt` is still in flight (the same in-flight-notification mechanism
       `TestArmedSessionErrorFailsUnlessStopWins` (case (o), part 15/N) already relies on) ->
       `session/cancel` sent as a notification (D17, mirroring `TestStopSendsSessionCancelAnd
       Interrupts`'s own assertion style) and status `failed` with an `error`-kind event carrying
       `payload["code"] == "copilot_posture_escalated"` (design.md:1027: this code, unlike this
       slice's `copilot.<name>` diagnostics, is an `error_event`, kept underscore-named like
       Codex's `codex_mcp_server_failed" -- `test_codex_appserver_run_turn.py:623,782` is this
       file's model for asserting an `error`-kind event by `payload["code"]`).

    All five use `restrict_spec_writes=False` (a non-spec turn, as clauses 1-2 say explicitly, and
    as the other three's own silence about a spec turn implies -- D9's spec-turn carve-out is a
    different case's scope, `TestSpecTurnRestrictsWritesAndAllowAll`, and `permission_mode=None`
    (`workspace`, this file's existing convention for it, e.g. `TestNewSessionSequence`), since
    clauses 3-5 name `workspace` explicitly and 1-2 don't depend on posture at all.

    `session.mode_changed`'s own wire envelope is not captured in any evidence log (unlike
    `session.error`'s, reused from `TestUsageUpdateProducesMeasuredSampleWithResolvedModel`'s own
    citation) -- design.md only names it as a member of `COPILOT_RAW_EVENTS` (`:1104`) delivered
    over the same `github.com/copilot/sessionEvent` channel as every other raw event in that list
    (`:1094-1096`, VERIFIED wire shape for the channel itself, though not for this event's own
    `data`). This test's `_armed_mode_changed_notification` therefore invents a `data.newModeId`
    field the same way `_replay_chunk` and `_armed_session_error_notification` before it flagged
    their own synthetic shapes -- what matters to the assertions below is only that `run_turn`
    reacts to *some* delivered `session.mode_changed` naming `#autopilot`, not this fixture's exact
    field name, which a future round should confirm or correct against the real module.
    """

    @staticmethod
    def _load_prefix(*, current_mode_id, allow_all_current="off"):
        return [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "modes": {"currentModeId": current_mode_id},
                    "configOptions": [
                        _mode_option(current=current_mode_id),
                        _agent_option(""),
                        _allow_all_option(allow_all_current),
                    ],
                }
            },  # session/load
            {
                "response": {
                    "configOptions": [
                        _mode_option(current=current_mode_id),
                        _agent_option(AGENT_NAME),
                        _allow_all_option(allow_all_current),
                    ]
                }
            },  # session/set_config_option agent
        ]

    @staticmethod
    def _armed_mode_changed_notification(mode_uri):
        return {
            "notification": "github.com/copilot/sessionEvent",
            "params": {
                "sessionId": SESSION_ID,
                "type": "session.mode_changed",
                "timestamp": "2026-09-30T00:00:09.000Z",
                "data": {"newModeId": mode_uri},
            },
        }

    async def _run(self, monkeypatch, script, *, resume_session_id=RESUME_ID):
        events = []
        sessions_bound = []
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=resume_session_id,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
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
        return fake, events, sessions_bound, outcome

    async def test_loaded_plan_mode_sends_set_mode_agent_before_prompt(self, monkeypatch):
        script = self._load_prefix(current_mode_id=PLAN_MODE_URI) + [
            {"response": {}},  # session/set_mode -- the #agent call this test asserts
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake, _events, _sessions_bound, outcome = await self._run(monkeypatch, script)

        methods = [m for m, _ in fake.sent_requests]
        set_mode_calls = [(m, p) for m, p in fake.sent_requests if m == "session/set_mode"]
        assert len(set_mode_calls) == 1, (
            "a non-spec turn must send exactly one session/set_mode, the ordinary #agent one, "
            f"even though the load reported #plan; got {set_mode_calls}"
        )
        _, params = set_mode_calls[0]
        assert params == {"sessionId": RESUME_ID, "modeId": AGENT_MODE_URI}, (
            "design.md:823-829: set_mode must be sent #agent 'whatever the load reported' -- "
            f"got {params}"
        )
        i_set_mode = methods.index("session/set_mode")
        i_prompt = methods.index("session/prompt")
        assert i_set_mode < i_prompt, methods
        assert outcome.status == "completed"

    async def test_loaded_autopilot_mode_sends_set_mode_agent_before_prompt(self, monkeypatch):
        script = self._load_prefix(current_mode_id=AUTOPILOT_MODE_URI) + [
            {"response": {}},  # session/set_mode -- the #agent call this test asserts
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake, _events, _sessions_bound, outcome = await self._run(monkeypatch, script)

        methods = [m for m, _ in fake.sent_requests]
        set_mode_calls = [(m, p) for m, p in fake.sent_requests if m == "session/set_mode"]
        assert len(set_mode_calls) == 1, (
            "a non-spec turn must send exactly one session/set_mode, the ordinary #agent one, "
            f"even though the load reported #autopilot; got {set_mode_calls}"
        )
        _, params = set_mode_calls[0]
        assert params == {"sessionId": RESUME_ID, "modeId": AGENT_MODE_URI}, (
            "design.md:823-829: set_mode must be sent #agent 'whatever the load reported', "
            f"including autopilot; got {params}"
        )
        i_set_mode = methods.index("session/set_mode")
        i_prompt = methods.index("session/prompt")
        assert i_set_mode < i_prompt, methods
        assert outcome.status == "completed"

    async def test_allow_all_on_after_load_under_workspace_is_set_off_and_read_back(
        self, monkeypatch
    ):
        script = self._load_prefix(current_mode_id=AGENT_MODE_URI, allow_all_current="on") + [
            {"response": {}},  # session/set_mode -- D8 step 1, unasserted here
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option allow_all off -- reads back off, the success half
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake, _events, sessions_bound, outcome = await self._run(monkeypatch, script)

        methods = [m for m, _ in fake.sent_requests]
        allow_all_sets = [
            (m, p)
            for m, p in fake.sent_requests
            if m == "session/set_config_option" and p.get("configId") == "allow_all"
        ]
        assert len(allow_all_sets) == 1, (
            "design.md:836-838: allow_all read 'on' under workspace must be set 'off' exactly "
            f"once; got {allow_all_sets}"
        )
        _, params = allow_all_sets[0]
        assert params["value"] == "off", params
        i_allow_all = methods.index(
            "session/set_config_option", methods.index("session/set_mode") + 1
        )
        i_prompt = methods.index("session/prompt")
        assert i_allow_all < i_prompt, (
            "the allow_all off-and-read-back exchange must finish before the prompt is written, "
            f"got {methods}"
        )
        assert sessions_bound == [RESUME_ID]
        assert outcome == TurnOutcome(session_id=RESUME_ID, status="completed", error=None)

    async def test_allow_all_reading_back_on_raises_and_sends_no_prompt(self, monkeypatch):
        script = self._load_prefix(current_mode_id=AGENT_MODE_URI, allow_all_current="on") + [
            {"response": {}},  # session/set_mode -- D8 step 1, unasserted here
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("on"),  # the set was refused/ignored -- still "on"
                    ]
                }
            },  # session/set_config_option allow_all off -- reads back on, the failure half
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        with pytest.raises(CopilotACPError) as exc_info:
            await run_turn(
                cwd="C:\\work",
                env=None,
                prompt="Anything changed since I left?",
                model=None,
                resume_session_id=RESUME_ID,
                agent=AGENT_NAME,
                per_turn_context="## Workspace\n- root: C:\\work",
                tool_surface_context="## Tools\n- agentweave-send_message",
                stable_context=None,
                control_overrides=None,
                told_access_path="mcp",
                permission_mode=None,
                workspace="C:\\work",
                restrict_spec_writes=False,
                extra_flags=None,
                on_event=_collector([]),
                on_session=_collector([]),
            )

        assert str(exc_info.value) == (
            "Copilot kept allow-all on for this session; AgentWeave did not start the turn, "
            "because no action would have been put to it."
        ), str(exc_info.value)
        methods = [m for m, _ in fake.sent_requests]
        assert "session/prompt" not in methods, (
            "design.md:837-839: a readback that is still 'on' must raise before the prompt -- "
            f"session/prompt must never be sent; got {methods}"
        )
        assert fake.closed_with_force is False, "D17: the process is still closed, not forced"

    async def test_armed_mode_changed_into_autopilot_under_workspace_cancels_and_fails(
        self, monkeypatch
    ):
        script = self._load_prefix(current_mode_id=AGENT_MODE_URI) + [
            {"response": {}},  # session/set_mode -- D8 step 1, unasserted here
            self._armed_mode_changed_notification(AUTOPILOT_MODE_URI),
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt's own eventual result -- Copilot may still answer end_turn
        ]
        fake, events, sessions_bound, outcome = await self._run(monkeypatch, script)

        cancel_calls = [(m, p) for m, p in fake.sent_notifications if m == "session/cancel"]
        assert len(cancel_calls) == 1, (
            "design.md:841-843: an armed change into #autopilot under workspace must send "
            f"session/cancel; got {fake.sent_notifications}"
        )
        assert cancel_calls[0][1] == {"sessionId": RESUME_ID}
        assert (
            "session/cancel",
            {"sessionId": RESUME_ID},
        ) not in fake.sent_requests, "session/cancel is a notification (D17), not a request"

        assert (
            outcome.status == "failed"
        ), f"design.md:841-843: the turn must end failed, got status {outcome.status!r}"
        error_events = [e for e in events if e.kind == "error"]
        assert len(error_events) == 1, events
        assert error_events[0].payload["code"] == "copilot_posture_escalated", error_events[0]
        assert sessions_bound == [RESUME_ID]


class TestDeselectOnMarkerMismatch:
    """Tasks.md 1.9(t) (`:285`, review finding 6): "an `agent` option whose description is not
    the marker -> `set_config_option agent \"\"` is sent before the prompt; a deselect that does
    not read back \"\" raises and sends no prompt." D6's own deselect paragraph (design.md
    `:526-536`, review 2026-09-28 finding 6) states the mechanism: on any marker-check failure --
    this file's case (f) exercises the "foreign description" branch of that check
    (`TestAgentMarkerMismatchFallsBackToResourceBlock`, part 6/N) -- the client additionally sends
    `session/set_config_option {configId: "agent", value: ""}` before the prompt and reads back
    `currentValue == ""`; if the deselect is refused or the read-back value is not empty,
    `run_turn` **raises** before the prompt (D12) with design.md's own verbatim sentence
    (`:533-535`): "Copilot kept a custom agent named <agent> that AgentWeave did not write
    selected; this turn was not started." `<agent>` is substituted with the turn's own `agent`
    argument -- a value this test supplies itself, unlike case (d)'s `<v>`, which design.md never
    states a literal for -- so the exact string is asserted here, the same discipline
    `TestVersionGateFailsBeforeAnySessionRequest`'s own known-CLI-version test applies to
    `"Copilot CLI 1.0.75 is older than..."`.

    **Division of labour confirmed against part 6/N's test, read fresh, not assumed.** That
    class's own script already includes this same deselect call (`:1015-1024`, its own comment:
    "case (t)'s territory, unasserted here") so a real implementation can reach the prompt in that
    test at all, but its assertions never inspect `fake.sent_requests` for the deselect's own
    params or exercise the raise path (its own docstring: "inventing that coverage under (f)'s
    name would duplicate (t) before (t) exists") -- confirming both of this case's sub-claims are
    new coverage, not a duplicate of (f)'s.

    Two independent sub-claims, tasks.md's own semicolon splitting them exactly as case (h)'s and
    (q)'s bullets did, so each gets its own test here too, per this task's queued caution:

    1. the successful-deselect ordering claim: after a marker mismatch, a **second**
       `session/set_config_option` request with `configId == "agent"` is sent with `value == ""`,
       distinct from the first (mismatched) selection, and it precedes `session/prompt`;
    2. the raises-before-prompt claim: if that second call's own response still reads back a
       non-empty `currentValue` for the `agent` option (the deselect refused or ignored),
       `run_turn` raises `CopilotACPError` with the exact message above, and `session/prompt` is
       never sent.

    Both tests build the marker-mismatch prefix (`initialize` / `session/new` / the first,
    mismatched `session/set_config_option agent`) the same way part 6/N's own test does, with the
    same `FOREIGN_DESCRIPTION` fixture, so the only difference between them is the deselect
    response's own read-back value -- isolating exactly the fact each test is evidence of.
    """

    FOREIGN_DESCRIPTION = "A custom repository agent, unrelated to AgentWeave"

    def _mismatch_prefix(self):
        return [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option()],
                }
            },  # session/new
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME, description=self.FOREIGN_DESCRIPTION),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent -- foreign description, D6's check fails
        ]

    async def test_successful_deselect_sends_set_config_option_agent_empty_before_prompt(
        self, monkeypatch
    ):
        script = self._mismatch_prefix() + [
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(""),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent "" -- the deselect, reads back "" -- this
            # test's own claim
            {"response": {}},  # session/set_mode -- D8's posture step, unasserted here
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context="## Charter\n- Ship safely.",
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=None,
            on_event=_collector([]),
            on_session=_collector([]),
        )

        agent_call_indices = [
            i
            for i, (m, p) in enumerate(fake.sent_requests)
            if m == "session/set_config_option" and p.get("configId") == "agent"
        ]
        assert len(agent_call_indices) == 2, (
            "the initial (mismatched) selection and the deselect must be two separate "
            f"session/set_config_option(agent) calls; got {fake.sent_requests}"
        )
        i_first, i_deselect = agent_call_indices
        first_params = fake.sent_requests[i_first][1]
        deselect_params = fake.sent_requests[i_deselect][1]
        assert first_params["value"] == AGENT_NAME, first_params
        assert deselect_params["value"] == "", (
            "design.md:530-531: the deselect must send configId=agent, value=''; "
            f"got {deselect_params}"
        )
        methods = [m for m, _ in fake.sent_requests]
        i_prompt = methods.index("session/prompt")
        assert i_first < i_deselect < i_prompt, (
            "both agent set_config_option calls must precede session/prompt; " f"got {methods}"
        )
        assert outcome.status == "completed"
        assert fake.closed_with_force is False, "D17: ACPProcess.close() on every exit, not forced"

    async def test_deselect_reading_back_nonempty_raises_and_sends_no_prompt(self, monkeypatch):
        script = self._mismatch_prefix() + [
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME, description=self.FOREIGN_DESCRIPTION),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent "" -- refused/ignored, still reads back
            # AGENT_NAME (the failure half)
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake)

        with pytest.raises(CopilotACPError) as exc_info:
            await run_turn(
                cwd="C:\\work",
                env=None,
                prompt="Anything changed since I left?",
                model=None,
                resume_session_id=None,
                agent=AGENT_NAME,
                per_turn_context="## Workspace\n- root: C:\\work",
                tool_surface_context="## Tools\n- agentweave-send_message",
                stable_context="## Charter\n- Ship safely.",
                control_overrides=None,
                told_access_path="mcp",
                permission_mode=None,
                workspace="C:\\work",
                restrict_spec_writes=False,
                extra_flags=None,
                on_event=_collector([]),
                on_session=_collector([]),
            )

        assert str(exc_info.value) == (
            f"Copilot kept a custom agent named {AGENT_NAME} that AgentWeave did not write "
            "selected; this turn was not started."
        ), str(exc_info.value)
        methods = [m for m, _ in fake.sent_requests]
        assert "session/prompt" not in methods, (
            "design.md:532-535: a deselect that does not read back empty must raise before the "
            f"prompt -- session/prompt must never be sent; got {methods}"
        )
        assert fake.closed_with_force is False, "D17: the process is still closed, not forced"


class TestRunnerFlagWideningStrippedFromArgv:
    """Tasks.md 1.9(u) (`:286`, review finding 10): "`build_acp_argv` with runner flags `--yolo
    --allow-tool=shell --add-dir C:\\x --config-dir C:\\y --deny-tool=x` under `workspace` keeps
    only `--deny-tool=x` and emits one `copilot.runner_flag_removed` per removed flag; under full
    access it keeps all but `--config-dir`."

    Read design.md `:176-201` fresh (D3, "Runner flags that widen approvals", review 2026-09-28
    finding 10) rather than trusting this task's own queued figure -- that note guessed "twelve
    total" for `COPILOT_WIDENING_FLAGS`, itself flagged as unreliable. Recounting directly: the
    paragraph's own naming sentence lists eight flags Copilot self-approves on
    (`--yolo`, `--allow-all`, `--allow-all-tools`, `--allow-all-paths`, `--allow-all-urls`,
    `--allow-tool`, `--allow-url`, `--add-dir`), then says `COPILOT_WIDENING_FLAGS` is "those seven,
    plus `--autopilot`, `--mode`, `--plan`, `--assisted-approval` and `--config-dir`" -- "those
    seven" undercounts the eight just named by one. `--add-dir` cannot be the omitted one despite
    that: the SHOULD-FIX ledger entry for this same finding (`:2384-2386`) separately confirms, by
    code (`app.js`), that `--allow-tool`, `--allow-url` **and** `--add-dir` are all members removed
    unless full access, and this case's own tasks.md example bundles `--add-dir` in among the
    flags workspace strips. So the "seven"/"twelve" arithmetic is design.md's own error, not a
    fact this test derives conclusions from -- what this test needs is only the specific flags
    case (u)'s own bullet names, not a total count.

    `extra_flags` is confirmed, not guessed, as the keyword that carries a runner's own flags
    through: `agent_trigger.py:1219-1233` reads `runner_row.flags`, strips `TRANSPORT_SENTINELS`,
    and passes what remains as `extra_flags=runner_flags` into the RPC turn request D18 describes
    (design.md `:1528-1531`); this file's every other part already threads that same keyword
    (always `None` until now) straight to `run_turn`. `test_runner_parsing.py:142,235` confirms the
    list shape: each argv word is its own list element (`extra_flags=["--effort", "high"]`), so a
    `--flag value` pair is two elements and a `--flag=value` word is one -- matching exactly how
    this case's own bullet writes `--add-dir C:\\x` (two words) beside `--allow-tool=shell` (one).

    No diagnostic table row gives `copilot.runner_flag_removed`'s summary a verbatim sentence
    (`:1020` names only the code and severity, unlike `copilot.full_access_withdrawn`'s quoted
    text this file's own `TestFullAccessWithoutAllowAllOption` asserts exactly) -- so this test
    checks only what design.md actually commits to: `code == "copilot.runner_flag_removed"`,
    `severity == "warning"`, one diagnostic per removed flag, and the removed flag's own name
    appearing in that diagnostic's `summary` ("naming the flag", `:196`) -- not a full literal
    sentence a future round would have to invent evidence for.

    Two tests, the workspace half and the full-access half of the same bullet, per this task's own
    queued caution (case (j) needed four, case (q) two) -- an argv-content assertion and a
    diagnostic-count assertion could each pass or fail independently, but both halves share the
    same `extra_flags` fixture and only differ in `permission_mode`, so they are two tests, not
    four.
    """

    EXTRA_FLAGS = [
        "--yolo",
        "--allow-tool=shell",
        "--add-dir",
        "C:\\x",
        "--config-dir",
        "C:\\y",
        "--deny-tool=x",
    ]

    async def test_workspace_keeps_only_deny_tool_and_diagnoses_every_removal(self, monkeypatch):
        events = []
        sessions_bound = []
        captured_cmds = []

        script = _session_established_script(
            tail_entry={
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            }
        )
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake, captured_cmds=captured_cmds)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode=None,
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=self.EXTRA_FLAGS,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        assert len(captured_cmds) == 1, "exactly one spawn per turn"
        cmd = captured_cmds[0]
        removed = ["--yolo", "--allow-tool=shell", "--add-dir", "C:\\x", "--config-dir", "C:\\y"]
        for token in removed:
            assert token not in cmd, (
                f"design.md:194-196: under workspace every widening flag must be stripped -- "
                f"{token!r} must not reach the spawn argv; got {cmd!r}"
            )
        assert "--deny-tool=x" in cmd, (
            "--deny-tool is not a widening flag and must reach the spawn argv unchanged -- "
            f"got {cmd!r}"
        )

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        # The bare flag name, not the "--flag=value" token: design.md says only "naming the
        # flag" (`:196`), and a diagnostic that quoted `--allow-tool=shell` in full would still
        # satisfy that wording, but this test does not assume the value rides along -- only the
        # flag identity is asserted.
        removed_flag_names = ["--yolo", "--allow-tool", "--add-dir", "--config-dir"]
        assert len(diagnostics) == len(removed_flag_names), (
            "design.md:196: one copilot.runner_flag_removed diagnostic per removed flag -- "
            f"expected {len(removed_flag_names)}, got {diagnostics}"
        )
        for payload in (d.payload for d in diagnostics):
            assert payload["code"] == "copilot.runner_flag_removed", payload
            assert payload["severity"] == "warning", payload
        remaining = list(removed_flag_names)
        for payload in (d.payload for d in diagnostics):
            named = [f for f in remaining if f in payload["summary"]]
            assert named, (
                f"diagnostic summary {payload['summary']!r} must name one of the still-unmatched "
                f"removed flags {remaining!r}"
            )
            remaining.remove(named[0])
        assert (
            remaining == []
        ), f"every removed flag must get its own diagnostic; missing {remaining}"

        assert outcome.status == "completed"
        assert fake.closed_with_force is False, "D17: ACPProcess.close() on every exit, not forced"

    async def test_full_access_keeps_all_but_config_dir(self, monkeypatch):
        events = []
        sessions_bound = []
        captured_cmds = []

        script = [
            {"response": INIT_RESPONSE},
            {
                "response": {
                    "sessionId": SESSION_ID,
                    "modes": {"currentModeId": AGENT_MODE_URI},
                    "configOptions": [_mode_option(), _agent_option(""), _allow_all_option("off")],
                }
            },  # session/new
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("off"),
                    ]
                }
            },  # session/set_config_option agent
            {"response": {}},  # session/set_mode #agent -- posture step 1, unasserted here
            {
                "response": {
                    "configOptions": [
                        _mode_option(),
                        _agent_option(AGENT_NAME),
                        _allow_all_option("on"),
                    ]
                }
            },  # session/set_config_option allow_all=on -- posture step 2 (D8 full access),
            # reads back "on"; unasserted here, this case's scope is build_acp_argv, not D8
            {
                "response": {
                    "stopReason": "end_turn",
                    "usage": {"inputTokens": 1, "outputTokens": 1},
                }
            },  # session/prompt
        ]
        fake = _FakeACPSession(script)
        _patch_spawn(monkeypatch, fake, captured_cmds=captured_cmds)

        outcome = await run_turn(
            cwd="C:\\work",
            env=None,
            prompt="Anything changed since I left?",
            model=None,
            resume_session_id=None,
            agent=AGENT_NAME,
            per_turn_context="## Workspace\n- root: C:\\work",
            tool_surface_context="## Tools\n- agentweave-send_message",
            stable_context=None,
            control_overrides=None,
            told_access_path="mcp",
            permission_mode="bypassPermissions",
            workspace="C:\\work",
            restrict_spec_writes=False,
            extra_flags=self.EXTRA_FLAGS,
            on_event=_collector(events),
            on_session=_collector(sessions_bound),
        )

        assert len(captured_cmds) == 1, "exactly one spawn per turn"
        cmd = captured_cmds[0]
        kept = ["--yolo", "--allow-tool=shell", "--add-dir", "C:\\x", "--deny-tool=x"]
        for token in kept:
            assert token in cmd, (
                "design.md:196: under full access every widening flag except --config-dir must "
                f"reach the spawn argv unchanged -- {token!r} missing from {cmd!r}"
            )
        assert "--config-dir" not in cmd and "C:\\y" not in cmd, (
            "design.md:196: --config-dir is removed under every posture, including full access -- "
            f"got {cmd!r}"
        )

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1, (
            "only --config-dir is removed under full access, so exactly one "
            f"copilot.runner_flag_removed diagnostic is expected; got {diagnostics}"
        )
        payload = diagnostics[0].payload
        assert payload["code"] == "copilot.runner_flag_removed", payload
        assert payload["severity"] == "warning", payload
        assert "--config-dir" in payload["summary"], payload["summary"]

        assert outcome.status == "completed"


class TestPermissionJudgeRunsOffTheEventLoop:
    """Tasks.md 1.9(v) (`:287`, review finding 7, design.md:617-628): "with os.path.realpath
    patched to sleep 2 s, a coroutine running beside the turn makes progress while a path
    request is decided (the judge runs in asyncio.to_thread)." Design.md's own paragraph, read
    fresh ("The judge runs off the event loop"), states the mechanism directly: `_where`
    (`mcp_server.py:1113-1133`) calls `os.path.realpath` on every path, measured by the
    reviewer at 21 s for a UNC path on this machine, and moving that judge into the Hub process
    would otherwise freeze every project, run and route sharing this event loop for however long
    one model-written path takes to resolve. So the client is required to
    `await asyncio.to_thread(decide_permission, …)`, never judge a `session/request_permission`
    inline -- this case proves that operationally, the same "measure it, don't read it"
    discipline case (u)'s own sanity check used for the argv-stripping rule, rather than by
    reading source (unlike almost everything else in this class-per-case file, which asserts
    on wire shape and ordering, not timing).

    **The test's own mechanism.** `os.path.realpath` is patched so that calls naming this case's
    own `INSIDE_PATH` specifically -- not every call -- add a real, synchronous `time.sleep(2.0)`
    before delegating to the original function (not `asyncio.sleep`, since the point is proving
    the *event loop* stays free while this specific call occupies a worker thread). Scoping the
    delay to one path, rather than blocking every `os.path.realpath` call for the test's
    duration, matters operationally, not just stylistically: pytest's own machinery (assertion
    rewriting, `pathlib` resolution during fixture teardown, `pytest-asyncio`'s own bookkeeping)
    calls `os.path.realpath` an unbounded, unpredictable number of times around the test body,
    and delaying all of them compounds into a hang rather than a bounded 2s wait -- confirmed
    directly: an earlier draft patched every call unconditionally and the test did not return
    within a 120s timeout, killed rather than diagnosed further, before this narrower version
    was written. A background coroutine ticks a counter every 0.05 s
    via `asyncio.sleep` for as long as `run_turn` is in flight. `_FakeACPSession.request()`'s
    `server_request` branch (module docstring, above) awaits `run_turn`'s own `on_server_request`
    handler and appends its result to `sent_responses` immediately afterward (`:212-213`) -- this
    class's own `_patch_spawn_recording_ticks_at_response`, a `_patch_spawn` variant, wraps
    *that* handler (not `_FakeACPSession.request` itself, which this file does not subclass) so
    the counter's own value is captured at the exact instant the permission decision concludes,
    before `run_turn` does anything else with the result. If `run_turn` called
    `decide_permission` directly on the event loop instead of through `asyncio.to_thread`, the
    blocking `time.sleep` call never yields control back to the loop, so the ticking coroutine
    could not run even once during the whole two seconds -- the captured count would be exactly
    0, not merely low. A correctly offloaded implementation lets the ticking coroutine run on the
    event loop the whole time `os.path.realpath` blocks a worker thread, so the captured count
    should land within rounding of `2.0 / 0.05 == 40`; the assertion below only requires "well
    above zero, and not merely the one or two ticks that scheduling jitter around the await
    boundary could produce on its own" (10, a quarter of the theoretical maximum) precisely so it
    does not depend on the exact thread-pool and event-loop scheduling latency of the machine
    running it.

    Sanity-checked against a throwaway stand-in (`hub/hub/copilot_acp.py`, not committed) two
    ways: (1) `await asyncio.to_thread(os.path.realpath, path)` in the stand-in's
    `on_server_request` handler -- the captured tick count was in the high 30s, comfortably
    above the 10-tick floor, and the test passed; (2) the same handler calling
    `os.path.realpath(path)` directly, inline, with no `to_thread` -- the captured count was
    exactly 0 every run, failing the floor assertion as designed, not by timing out or raising.
    Restored nothing (the stand-in was never part of this file), deleted the stand-in and its
    `__pycache__` entry, confirmed red again at the same `ModuleNotFoundError`.

    The permission request itself is an ordinary in-workspace `edit`, reusing
    `TestFullAccessWithNoAllowAllOption`'s (part 11/N) `toolCall`/`options` shape. This case does
    not care which verdict `decide_permission` reaches (ALLOW or REJECT) -- only that judging it
    does not stall the loop -- so the response's `optionId` is checked only for being one the
    request actually offered, not for a specific value.
    """

    EDIT_CALL_ID = "call_synthetic_offloaded_edit_1"
    INSIDE_PATH = "C:\\work\\slow.txt"
    TICK_INTERVAL = 0.05
    REALPATH_DELAY = 2.0
    TICK_FLOOR = 10

    def _permission_request_entry(self, path):
        return {
            "server_request": {
                "id": 1,
                "method": "session/request_permission",
                "params": {
                    "sessionId": SESSION_ID,
                    "toolCall": {
                        "toolCallId": self.EDIT_CALL_ID,
                        "title": "Edit slow.txt",
                        "kind": "edit",
                        "rawInput": {"fileName": path},
                        "locations": [{"path": path}],
                    },
                    "options": [
                        {"optionId": "allow_once", "name": "Allow", "kind": "allow_once"},
                        {
                            "optionId": "allow_always",
                            "name": "Always Allow",
                            "kind": "allow_always",
                        },
                        {"optionId": "reject_once", "name": "Reject", "kind": "reject_once"},
                    ],
                },
            }
        }

    @staticmethod
    def _patch_spawn_recording_ticks_at_response(monkeypatch, fake, tick_counter, snapshots):
        async def _fake_spawn(cmd, *, cwd=None, env=None, **kwargs):
            if kwargs.get("on_notification") is not None:
                fake._on_notification = kwargs["on_notification"]
            real_on_server_request = kwargs.get("on_server_request")
            if real_on_server_request is not None:

                async def _recording(method, params):
                    result = await real_on_server_request(method, params)
                    # Captured the instant the permission decision concludes -- before
                    # `_FakeACPSession.request()` itself does anything else with `result` -- so a
                    # `run_turn` that judged inline on the event loop is caught here, not
                    # papered over by whatever the loop gets around to doing afterwards.
                    snapshots.append(tick_counter["ticks"])
                    return result

                fake._on_server_request = _recording
            return fake

        monkeypatch.setattr(ACPProcess, "spawn", _fake_spawn)
        monkeypatch.setattr(
            copilot_acp,
            "resolve_copilot_executable",
            lambda *a, **k: ["copilot.exe"],
            raising=False,
        )

    async def test_ticker_advances_while_realpath_blocks_in_a_worker_thread(self, monkeypatch):
        tick_counter = {"ticks": 0}
        snapshots = []
        stop = asyncio.Event()

        async def _ticker():
            while not stop.is_set():
                await asyncio.sleep(self.TICK_INTERVAL)
                tick_counter["ticks"] += 1

        real_realpath = os.path.realpath

        def _slow_realpath(path, *a, **k):
            if os.fspath(path) == self.INSIDE_PATH:
                time.sleep(self.REALPATH_DELAY)
            return real_realpath(path, *a, **k)

        monkeypatch.setattr(os.path, "realpath", _slow_realpath)

        script = _session_established_script(
            tail_entries=[
                self._permission_request_entry(self.INSIDE_PATH),
                {
                    "response": {
                        "stopReason": "end_turn",
                        "usage": {"inputTokens": 1, "outputTokens": 1},
                    }
                },  # session/prompt
            ]
        )
        fake = _FakeACPSession(script)
        self._patch_spawn_recording_ticks_at_response(monkeypatch, fake, tick_counter, snapshots)

        ticker_task = asyncio.ensure_future(_ticker())
        try:
            outcome = await run_turn(
                cwd="C:\\work",
                env=None,
                prompt="Please edit a file inside the workspace.",
                model=None,
                resume_session_id=None,
                agent=AGENT_NAME,
                per_turn_context="## Workspace\n- root: C:\\work",
                tool_surface_context="## Tools\n- agentweave-send_message",
                stable_context=None,
                control_overrides=None,
                told_access_path="mcp",
                permission_mode=None,
                workspace="C:\\work",
                restrict_spec_writes=False,
                extra_flags=None,
                on_event=_collector([]),
                on_session=_collector([]),
            )
        finally:
            stop.set()
            ticker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker_task

        assert len(snapshots) == 1, (
            "exactly one session/request_permission must have been answered; " f"got {snapshots}"
        )
        assert snapshots[0] >= self.TICK_FLOOR, (
            "the ticking coroutine must have made real progress on the event loop while "
            "os.path.realpath blocked a worker thread for 2s -- a count this low (or zero) "
            "means run_turn judged the permission request inline on the event loop instead of "
            f"through asyncio.to_thread; got {snapshots[0]} ticks, floor is {self.TICK_FLOOR}"
        )

        offered_ids = {
            o["optionId"]
            for o in self._permission_request_entry(self.INSIDE_PATH)["server_request"]["params"][
                "options"
            ]
        }
        assert fake.sent_responses[0][0] == 1, fake.sent_responses
        assert fake.sent_responses[0][1]["outcome"]["optionId"] in offered_ids, (
            "this case does not pin down which verdict decide_permission reaches, only that "
            f"reaching one did not stall the loop; got {fake.sent_responses}"
        )

        assert outcome.session_id == SESSION_ID
        assert outcome.status == "completed"
        assert fake.closed_with_force is False, "D17: ACPProcess.close() on every exit, not forced"
