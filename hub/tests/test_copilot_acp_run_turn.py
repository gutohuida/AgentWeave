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
from hub.copilot_acp import ACPProcess, CopilotACPError, TurnOutcome, run_turn

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
        its answer appended to `sent_responses`;
      - ``{"error": {"code": ..., "message": ..., "data": {...}}}`` -- part 3/N: ends the
        in-flight `request()` call by *raising* `CopilotACPError(message, code=code, data=data)`
        instead of returning, mirroring design.md's own stated translation ("`ACPProcess.request`
        raises `CopilotACPError(code=<error.code>)` for a response holding `error`", `:1175`, R3
        adds `.data`, `:1179`) -- a JSON-RPC error response is never handed back as a plain dict
        the way the three other entry kinds are. `message`/`data` default to `None` if the entry
        omits them; a real response always carries `message` (JSON-RPC requires it) but this
        fake does not enforce that, since no case needs to test a malformed error.
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
            if "error" in entry:
                err = entry["error"]
                raise CopilotACPError(
                    err.get("message"), code=err.get("code"), data=err.get("data")
                )
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
