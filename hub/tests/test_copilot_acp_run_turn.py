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

import json

import pytest

import hub.copilot_acp as copilot_acp
from hub.copilot_acp import ACPProcess, CopilotACPError, TurnOutcome, run_turn

pytestmark = pytest.mark.asyncio

SESSION_ID = "ea76eb05-6a87-4257-8280-d7cc9e571ba5"  # a real session id, r1-probe-agent.log:5
AGENT_NAME = "probe-builder"  # the real agent name r1-probe-agent.log selected
AGENT_MARKER = f"AgentWeave agent {AGENT_NAME} — context rendered by the AgentWeave Hub"  # D4
AGENT_MODE_URI = "https://agentclientprotocol.com/protocol/session-modes#agent"  # VERIFIED wire
PLAN_MODE_URI = "https://agentclientprotocol.com/protocol/session-modes#plan"  # VERIFIED,
# r1-probe-plan.log:8 (`session/set_mode` params: `{"sessionId": ..., "modeId": <this URI>}`)


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
