"""Task 1.8 part 1/N: replay `evidence/acp4-turn-mcp-shell-1.0.88.log`'s `session/update`
notifications, in their recorded order, through `CopilotEventMapper` (design.md:942-980).

`CopilotEventMapper`'s exact method surface is not named in design.md, except for the raw-event
dispatch `_on_armed_raw_event(type, data, params)` (design.md:1818-1820), which "hands [params]
to `CopilotEventMapper`" -- read here as a same-named, same-signature `on_raw_event(type, data,
params)` method: the least invented reading available, not a design citation for that exact name.
For the ACP `session/update` notification (design.md:947-980's own dispatch table, keyed on
`update["sessionUpdate"]`), no method name is given at all; this file assumes
`on_session_update(update) -> list[RunEvent]`, mirroring that naming, and a `flush() ->
list[RunEvent]` for "flushed ... at prompt completion" (design.md:948). A future round should
confirm or correct this surface against the real implementation's needs, not treat it as settled.

Covers, this part: tasks.md 1.8's first bullet (one `text` event per contiguous message block, for
both the "any non-message update arrives" flush and the "prompt completion" flush), the shell half
of the second bullet (`tool_use` then `tool_result` sharing a call id) and the third bullet (a
streamed partial shell output emits nothing until the terminal update), plus the task's closing
ordering rule, proven directly against this fixture's own two notifications rather than an
invented pair.

Part 2/N adds the MCP half of bullet 2 and the R3 MCP-naming bullet, replayed from the 1.1 fixture
(`hub/tests/fixtures/copilot_acp/turn_write_shell_mcp.jsonl`), which has 9 `tool.execution_start`/
`tool.execution_complete` raw events each (checked directly by count; the sub-note this replaces
said "ten", off by one) -- including one real MCP call, `agentweave-list_tasks`
(`toolCallId: call_GfOgPoS504CrdMt9ry34xI6a`). `tasks.md`'s own bullet names the example
`mcpToolName: "create_task"`; the fixture never calls that tool (checked directly, no
`"create_task"` anywhere in the file), only `list_tasks`, so `TestMcpToolNaming` below uses the
real captured name throughout rather than inventing the example's.

Part 3/N adds the two R3 diagnostic-payload bullets: every `diagnostic` payload carries
`version`/`stream`/`severity`/`summary` (design.md:1005-1007), and an `agentweave` server status
that is not `connected` becomes the `copilot.mcp_server_unavailable` diagnostic -- not the
`copilot_mcp_server_failed` error -- when the run's told access path is not `mcp` (design.md:
1066-1079). Neither fixture has a failed `session.mcp_servers_loaded`/`session.mcp_server_status_
changed` (both real captures' own `agentweave` entries read `status: "connected"`, checked
directly: the evidence log at the line quoted above, the 1.1 fixture at its own line 14), so both
events below are synthetic, built from the real captures' own wire shape for
`session.mcp_servers_loaded` (`data: {"servers": [{"name", "status", ...}]}`, 1.1 fixture line 14)
with only `status` changed to a non-connected value (`"failed"`, chosen for symmetry with the
`copilot_mcp_server_failed`/`copilot.mcp_server_unavailable` codes -- not a captured or
CODE-cited enum member, since design.md gives no status enum beyond the observed `"connected"`/
`"disabled"`). `session.mcp_server_status_changed` never appears in either capture at all (it is
only ever a subscribed event name, never a received one -- checked directly), so its per-server
(singular, not a `servers` list) shape is INFERRED from `session.mcp_servers_loaded`'s and from
design.md:727's "updated by `session.mcp_server_status_changed`" language describing a single
map entry, not cited as CODE -- flagged the same way as this file's other inferred surfaces, for
a future round to confirm.

`CopilotEventMapper`'s constructor is also given a `told_access_path` keyword here for the first
time, to carry `RpcTurnRequest.told_access_path` (D18) into the mapper -- the design names the
field but never the mapper's own surface for receiving it (flagged in the next_action that queued
this part); a keyword on the existing single-mapper-per-turn constructor is the least invented
reading available, matching how the rest of this file constructs one mapper per turn.

Part 4/N adds the edit/diff bullet and the warning/info-text bullets, both synthetic for the same
reason recorded above (checked directly again here: no `edit`-kind `tool_call` and no
`session.warning`/`session.info` event in either capture). It also closes out, without a new test,
the `next_action` caution that queued this part: whether "an `agentweave` server status `failed`
emits one error" (`tasks.md`'s own bullet, for *this* file) is the same code path as part 3/N's
`copilot_mcp_server_failed`/`copilot.mcp_server_unavailable` pair, or D8's differently-sourced
`copilot.hub_server_unverified` diagnostic (design.md:1023, `:732-736`). Read fresh: D8's
`hub_server_unverified` fires from `decide_permission`'s own MCP-server-identification step (the
load-time condition over `calls`/`servers` inside `mcp_server._decide`'s caller,
`test_permission_approver.py`'s file, tasks 1.6/1.7) -- a different function, a different test
file, and a diagnostic this mapper never builds. D10's "The Hub's own server failing" paragraph
(design.md:1066-1079), the one this bullet actually annotates (it sits directly under D10 in both
this file's docstring and `tasks.md`'s own bullet list, which is scoped to `CopilotEventMapper`
throughout), is exactly the `copilot_mcp_server_failed`/`copilot.mcp_server_unavailable` pair
`TestMcpServerUnavailableDiagnostic` already covers (`test_mcp_told_path_emits_the_error_not_the_
diagnostic` is the `told_access_path == "mcp"` -> error half). So the bullet is satisfied already;
this part adds no test for it, and `tasks.md`'s sub-note below says so explicitly rather than
silently dropping it.

Part 5/N adds `TestSessionErrorRootVsSubagent`: a synthetic root `session.error` (no `agentId`
anywhere) becomes an `error_event(code="copilot_session_error")`, never `text`; a subagent's
(envelope `agentId`, tested separately from `data.parentToolCallId`) becomes a
`diagnostic_event(code="copilot.subagent_error")` instead, also never `text`. Both variants use
this slice's own direct classification rule (design.md:986-994's `Error:` match ->
`error_event`, symmetric with the already-tested `Warning:`/`Info:` -> `diagnostic_event` rule),
not slice 5's future different chunk-drop mechanism (design.md:1030-1034, explicitly "slice 5's
to change"). Turn failure/success is deliberately not asserted: `on_raw_event`/`on_session_update`
return `RunEvent` lists, never a `TurnOutcome`, and `codex_appserver.py`'s own `run_turn`
(`:1150-1195`, checked directly) decides `status`/`error` from raw notification types inline, not
from a mapper's returned events -- so whether Copilot's `run_turn` reads the mapper's `error` vs
`diagnostic` split, or re-inspects the raw `session.error` itself, is task 1.9's
(`test_copilot_acp_run_turn.py`) question. See that class's own docstring for the full reasoning.

**Task 1.8 was not fully covered through part 5/N**, despite part 4/N's own closing claim to the
contrary. Re-reading `tasks.md`'s Assert list fresh (part 5/N's own correction) found two bullets
no earlier part addressed: the model-substitution diagnostic (`session.model_change`/
`session.auto_mode_resolved`/`session.tools_updated`, design.md:1096-1108) and the
mapper-testable half of the `user_message_chunk`-before-arming bullet (design.md:977's "Dropped"
set, independent of the arming gate that lives outside this file).

Part 6/N closes both, re-reading design.md:1096-1108 and :977 fresh rather than off that summary,
per the correction's own instruction:

- `TestModelSubstitutionDiagnostic`: exercises `session.tools_updated {model}` -- the one of the
  three raw shapes design.md says the real capture actually shows (`:1084-1085`;
  `session.model_change`/`session.auto_mode_resolved` never appear in either capture, checked
  directly, so their CODE-cited shapes -- `{newModel, previousModel?}` and `{chosenModel,
  availableModels?}`, design.md:1081-1083 -- are used only for the "first raw event wins" test
  below, to prove the rule is about *event order*, not about which of the three shapes arrived).
  `CopilotEventMapper`'s constructor is given a second inferred keyword here, `requested_model`,
  the same way part 3/N added `told_access_path`: to carry `RpcTurnRequest.model` (design.md:1527)
  into the mapper, not named anywhere in design.md, flagged the same way. Four cases: a resolved
  model that differs from the requested one emits one `copilot.model_substituted` diagnostic
  (`severity="info"`, design.md:1018); an unchanged model emits none; a requested model of
  `"auto"` emits none even when the resolved model differs (design.md:1088's own gate); and the
  *first* of the three raw event types the mapper sees decides the resolved model -- a second,
  differently-shaped event arriving afterward does not re-diagnose (design.md:1086-1087's "takes
  the resolved model from the first ... it sees"). The illustrative message text and `"this plan
  allows: [...]"` list format (design.md:1089-1091) are not asserted byte-exact, per the
  `next_action` that queued this part -- only `code`/`severity`/`stream` and that the two model
  names appear in `summary`.
- `TestUserMessageChunkDropped`: `on_session_update` returns nothing for a `user_message_chunk`
  update, and one arriving while an `agent_message_chunk` block is still open neither flushes it
  nor contributes its own text to it -- the block's later `flush()` still yields exactly the agent
  text. The "before arming" half of the original bullet stays out of this file's scope, per the
  resolution already recorded above for the `agentweave`-server-status bullet and for
  `TestMcpServerUnavailableDiagnostic`.

With both closed, task 1.8's Assert list (`tasks.md:251-262`) is fully covered by this file: every
bullet either has a direct test above, or is explicitly recorded as out of this file's scope (the
"before arming" half) or already covered by another bullet's test (the `agentweave`-server-status
bullet, part 4/N). The next firing should move to task 1.9 (`test_copilot_acp_run_turn.py`), not
invent a part 7/N.
"""

import json
from pathlib import Path

from hub.copilot_acp import CopilotEventMapper

EVIDENCE_LOG = (
    Path(__file__).resolve().parents[2]
    / "openspec"
    / "changes"
    / "archive"
    / "2026-09-30-a-copilot-agent-runs-over-acp"
    / "evidence"
    / "acp4-turn-mcp-shell-1.0.88.log"
)

MCP_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "copilot_acp" / "turn_write_shell_mcp.jsonl"
)

ECHO_CALL_ID = "call_FMTN3GGfBZkcTYnhaKzhENeh"
MCP_LIST_TASKS_CALL_ID = "call_GfOgPoS504CrdMt9ry34xI6a"


def _session_updates() -> list:
    """The **first turn's own** `session/update` notifications' `update` dicts, in recorded
    order -- the log's request `"id": 3` (`session/prompt`) through its matching `"id": 3`
    result, checked directly at lines 5 and 54. The log actually captures three prompts on one
    session (the turn, then `/usage`, then `/context`); scoping to the first turn's own
    notifications matches D10's per-turn mapper lifecycle and, concretely, keeps this file's
    sole `agent_message_chunk` ("DONE") from silently concatenating with the next two prompts'
    unrelated reply text -- confirmed by first collecting all 15 updates in the raw log and
    finding 3 `agent_message_chunk` entries, not 1, before adding this scope.

    Line 1 (the `>>> initialize` request, before this scope even starts) is malformed in the
    capture itself -- its `clientCapabilities` event list is cut short by a literal embedded
    newline (checked directly: every other line parses; only line 1 fails, at the exact byte
    where the array is still open). Skipped the same defensive way as a line outside the id-3
    window, for the same reason: not a `session/update` notification either way.
    """
    updates = []
    in_turn = False
    with open(EVIDENCE_LOG, encoding="utf-8") as f:
        for raw_line in f:
            for prefix in (">>> ", "<<< ", "<<N "):
                if raw_line.startswith(prefix):
                    body = raw_line[len(prefix) :]
                    break
            else:
                continue
            try:
                msg = json.loads(body)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 3 and msg.get("method") == "session/prompt":
                in_turn = True
                continue
            if msg.get("id") == 3 and "result" in msg:
                break
            if in_turn and msg.get("method") == "session/update":
                updates.append(msg["params"]["update"])
    return updates


def _updates_for_call(call_id: str) -> list:
    return [u for u in _session_updates() if u.get("toolCallId") == call_id]


def _mcp_fixture_events() -> list:
    """Every received ACP `session/update` and raw `github.com/copilot/sessionEvent`
    notification in `MCP_FIXTURE`, in recorded order, as `("update", <update dict>)` or
    `("raw", <sessionEvent params dict>)` pairs.

    No turn-scoping is needed here the way `_session_updates()` needed it above: this fixture
    logs exactly one uninterrupted `session/prompt` turn, request `"id": 4` through its
    matching result (checked directly at lines 8 and 386) -- nothing else shares its session.
    """
    events = []
    with open(MCP_FIXTURE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("dir") != "recv":
                continue
            msg = entry["msg"]
            method = msg.get("method")
            if method == "session/update":
                events.append(("update", msg["params"]["update"]))
            elif method == "github.com/copilot/sessionEvent":
                events.append(("raw", msg["params"]))
    return events


def _mcp_events_for_call(call_id: str) -> list:
    """`_mcp_fixture_events()`, filtered to the given `toolCallId`, still tagged and ordered."""
    matching = []
    for tag, payload in _mcp_fixture_events():
        call = (
            payload.get("toolCallId")
            if tag == "update"
            else payload.get("data", {}).get("toolCallId")
        )
        if call == call_id:
            matching.append((tag, payload))
    return matching


class TestTextEventGrouping:
    def test_two_chunks_flush_as_one_text_event_when_a_non_message_update_arrives(self):
        mapper = CopilotEventMapper()
        events = []
        events += mapper.on_session_update(
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Hello, "}}
        )
        events += mapper.on_session_update(
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "world"}}
        )
        assert events == []  # the block is still open; nothing to flush yet

        events += mapper.on_session_update(
            {
                "sessionUpdate": "tool_call",
                "toolCallId": "call_1",
                "title": "List current directory",
                "kind": "execute",
                "status": "pending",
                "rawInput": {"command": "ls"},
            }
        )
        kinds = [e.kind for e in events]
        assert kinds[0] == "text"
        assert events[0].content == "Hello, world"
        assert kinds[1] == "tool_use"

    def test_final_message_flushes_only_at_prompt_completion(self):
        mapper = CopilotEventMapper()
        events = []
        for update in _session_updates():
            events += mapper.on_session_update(update)
        # The log's last `agent_message_chunk` ("DONE") has nothing after it in the same
        # stream -- design.md:948's other trigger, "at prompt completion", is what flushes it.
        assert not any(e.kind == "text" and e.content == "DONE" for e in events)

        events += mapper.flush()
        text_events = [e for e in events if e.kind == "text" and e.content == "DONE"]
        assert len(text_events) == 1


class TestShellToolCorrelationAndStreaming:
    def test_shell_tool_use_then_result_share_call_id_in_recorded_order(self):
        mapper = CopilotEventMapper()
        events = []
        for update in _updates_for_call(ECHO_CALL_ID):
            events += mapper.on_session_update(update)

        tool_use = [e for e in events if e.kind == "tool_use" and e.call_id == ECHO_CALL_ID]
        tool_result = [e for e in events if e.kind == "tool_result" and e.call_id == ECHO_CALL_ID]
        assert len(tool_use) == 1
        assert len(tool_result) == 1
        assert events.index(tool_use[0]) < events.index(tool_result[0])

        assert tool_use[0].payload["category"] == "command"
        assert "echo hookprobe ." in tool_use[0].payload["input"]

    def test_streamed_partial_output_emits_nothing_until_the_terminal_update(self):
        mapper = CopilotEventMapper()
        updates = _updates_for_call(ECHO_CALL_ID)
        # updates[0] is the `tool_call`; updates[1] and [2] are the two streamed, non-terminal
        # `tool_call_update`s (no `status` key at all -- confirmed directly against the log);
        # updates[3] is the terminal `status: "completed"` update.
        assert "status" not in updates[1]
        assert "status" not in updates[2]
        assert updates[3].get("status") == "completed"

        events = []
        events += mapper.on_session_update(updates[0])
        events += mapper.on_session_update(updates[1])
        events += mapper.on_session_update(updates[2])
        assert not any(e.kind == "tool_result" for e in events)

        events += mapper.on_session_update(updates[3])
        results = [e for e in events if e.kind == "tool_result"]
        assert len(results) == 1
        assert "hookprobe" in results[0].payload["output"]
        assert "<shellId: 0 completed with exit code 0>" in results[0].payload["output"]


class TestMcpToolNaming:
    """Task 1.8 part 2/N: the MCP half of bullet 2 (`tool_use` then `tool_result` sharing a
    call id) and the R3 MCP-naming bullet, replayed from the 1.1 fixture's real
    `agentweave-list_tasks` call, in its recorded order: raw `tool.execution_start` ->
    `session/update` `tool_call` -> raw `tool.execution_complete` -> `session/update`
    `tool_call_update` (checked directly, all four for `MCP_LIST_TASKS_CALL_ID`). The raw
    events arrive first each time, matching design.md:1112-1116's "from spawn onward,
    unarmed" -- `calls` already holds this call's `mcpServerName`/`mcpToolName` by the time the
    `tool_call` update needs to name it.

    This call's own `tool_call` update already carries `kind: "read"` (checked directly), not
    the `"edit"` that `YDo` would guess for a `create_task`-shaped name -- but the bullet's
    point is that MCP recognition from `calls` wins over *any* `kind` guess (design.md:953-958),
    not specifically the `edit` one, so asserting `category == "mcp"` on this real, unedited
    capture exercises the same rule without inventing a `create_task` event this fixture never
    recorded.
    """

    @staticmethod
    def _replay() -> list:
        mapper = CopilotEventMapper()
        events = []
        for tag, payload in _mcp_events_for_call(MCP_LIST_TASKS_CALL_ID):
            if tag == "raw":
                events += mapper.on_raw_event(payload["type"], payload["data"], payload)
            else:
                events += mapper.on_session_update(payload)
        return events

    def test_mcp_tool_use_then_result_share_call_id_in_recorded_order(self):
        events = self._replay()

        tool_use = [
            e for e in events if e.kind == "tool_use" and e.call_id == MCP_LIST_TASKS_CALL_ID
        ]
        tool_result = [
            e for e in events if e.kind == "tool_result" and e.call_id == MCP_LIST_TASKS_CALL_ID
        ]
        assert len(tool_use) == 1
        assert len(tool_result) == 1
        assert events.index(tool_use[0]) < events.index(tool_result[0])
        # the fixture's own MCP call fails (Hub unreachable) -- the terminal update's `status`
        # is `"failed"` (checked directly), so the result must say so
        assert tool_result[0].payload["is_error"] is True

    def test_mcp_call_is_named_and_categorised_from_calls_not_from_its_guessed_kind(self):
        events = self._replay()
        tool_use = [
            e for e in events if e.kind == "tool_use" and e.call_id == MCP_LIST_TASKS_CALL_ID
        ][0]

        assert tool_use.payload["tool"] == "agentweave-list_tasks"
        assert tool_use.payload["category"] == "mcp"
        # never `file_change`/`edit` -- the category a `kind`-only guess of `"read"` (this
        # call's own `kind`, checked directly) or a `create_task`-shaped name would produce
        assert tool_use.payload["category"] not in ("edit", "file_change")


class TestOrderingRule:
    """The CLAUDE.md ordering rule: a test for code that consumes an ordered stream must use the
    order the real transport actually emits, and some test must fail if that order is reversed.
    `test_shell_tool_use_then_result_share_call_id_in_recorded_order` above asserts the `tool_use`
    event's index precedes the `tool_result` event's index -- a positional assertion that a
    reversed feed would break. This test proves that concretely, from design.md's own literal
    builder rules (`tool_call` unconditionally becomes a `tool_use_event` "on first sight of a
    toolCallId"; a terminal `tool_call_update` unconditionally becomes a `tool_result_event"; design.md:952-971) --
    neither is gated on having already seen the other, so feeding them in reverse order reverses
    the events' order too, deterministically, not just hypothetically.
    """

    def test_reversing_tool_call_and_its_terminal_update_reverses_the_event_order(self):
        tool_call = _updates_for_call(ECHO_CALL_ID)[0]
        terminal_update = _updates_for_call(ECHO_CALL_ID)[3]

        mapper = CopilotEventMapper()
        events = []
        events += mapper.on_session_update(terminal_update)  # reversed: update before call
        events += mapper.on_session_update(tool_call)

        kinds = [e.kind for e in events]
        assert kinds == ["tool_result", "tool_use"]  # inverted from the real, recorded order


class TestMcpServerUnavailableDiagnostic:
    """Task 1.8 part 3/N, first R3 diagnostic bullet: an `agentweave` server status that is not
    `connected` becomes the `copilot.mcp_server_unavailable` diagnostic, not the
    `copilot_mcp_server_failed` error, when the run's told access path is not `mcp`
    (design.md:1066-1079); the reverse (`told_access_path == "mcp"`) gets the error, not the
    diagnostic, proving the gating is real and not incidental. Both raw events are synthetic --
    see the module docstring for why and for their inferred shape -- and both feed `servers` the
    same way `calls` is fed elsewhere in this file: directly through `on_raw_event`, with no
    separate "arming" step in the mapper itself (that gate lives in `_on_armed_raw_event`,
    outside this class, design.md:1112-1116).
    """

    @staticmethod
    def _failed_mcp_servers_loaded() -> tuple:
        data = {"servers": [{"name": "agentweave", "status": "failed"}]}
        params = {
            "sessionId": "synthetic-session",
            "type": "session.mcp_servers_loaded",
            "timestamp": "2026-09-30T00:00:00.000Z",
            "data": data,
        }
        return "session.mcp_servers_loaded", data, params

    @staticmethod
    def _failed_mcp_server_status_changed() -> tuple:
        data = {"name": "agentweave", "status": "failed"}
        params = {
            "sessionId": "synthetic-session",
            "type": "session.mcp_server_status_changed",
            "timestamp": "2026-09-30T00:00:01.000Z",
            "data": data,
        }
        return "session.mcp_server_status_changed", data, params

    def test_non_mcp_told_path_emits_the_diagnostic_not_the_error(self):
        mapper = CopilotEventMapper(told_access_path="cli")
        type_, data, params = self._failed_mcp_servers_loaded()
        events = mapper.on_raw_event(type_, data, params)

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1
        assert diagnostics[0].payload["code"] == "copilot.mcp_server_unavailable"
        assert not any(e.kind == "error" for e in events)

    def test_mcp_told_path_emits_the_error_not_the_diagnostic(self):
        mapper = CopilotEventMapper(told_access_path="mcp")
        type_, data, params = self._failed_mcp_servers_loaded()
        events = mapper.on_raw_event(type_, data, params)

        assert not any(e.kind == "diagnostic" for e in events)
        errors = [e for e in events if e.kind == "error"]
        assert len(errors) == 1
        assert errors[0].payload["code"] == "copilot_mcp_server_failed"

    def test_diagnostic_emitted_once_per_turn_across_both_event_types(self):
        mapper = CopilotEventMapper(told_access_path="cli")
        loaded_type, loaded_data, loaded_params = self._failed_mcp_servers_loaded()
        first = mapper.on_raw_event(loaded_type, loaded_data, loaded_params)

        status_type, status_data, status_params = self._failed_mcp_server_status_changed()
        second = mapper.on_raw_event(status_type, status_data, status_params)

        assert len([e for e in first if e.kind == "diagnostic"]) == 1
        # once per turn: the second failure report of the same server names no new diagnostic
        assert len([e for e in second if e.kind == "diagnostic"]) == 0


class TestDiagnosticPayloadShape:
    """Task 1.8 part 3/N, second R3 bullet: every `diagnostic` payload this mapper produces
    carries `version`, `stream == "copilot"`, `severity` and `summary` (design.md:1005-1007's
    `diagnostic_event` builder shape). The only diagnostic this file can trigger so far is
    `copilot.mcp_server_unavailable` (above); the warning/info-text and model-substitution
    diagnostics are left for a later part, per the module docstring.
    """

    def test_mcp_server_unavailable_diagnostic_has_the_full_payload_shape(self):
        mapper = CopilotEventMapper(told_access_path="cli")
        type_, data, params = TestMcpServerUnavailableDiagnostic._failed_mcp_servers_loaded()
        events = mapper.on_raw_event(type_, data, params)

        diagnostic = [e for e in events if e.kind == "diagnostic"][0]
        payload = diagnostic.payload
        assert payload["version"] == 1
        assert payload["stream"] == "copilot"
        assert payload["severity"] == "warning"
        assert isinstance(payload["summary"], str) and payload["summary"]


class TestEditDiffToolUse:
    """Task 1.8 part 4/N, the edit/diff bullet: "the edit's `tool_use` carries the file path and
    diff". Synthetic -- neither capture has an `edit`-kind `tool_call` (design.md:2476-2480,
    checked directly again for this part). Built from design.md:637's ACP shape for an edit
    request (`kind:"edit"`, `locations[].path`) and design.md:964-965's `input_data` rule: `title`,
    `rawInput`, `locations`, plus `"changes": [{path, oldText, newText}]` from any `content` item
    of type `diff`. `tool_use_event`'s own `input` field (`runner_events.py:178`) is the
    redacted, stringified `input_data`, not a separate structured field -- the same field this
    file's shell test already reads a substring out of
    (`test_shell_tool_use_then_result_share_call_id_in_recorded_order`).
    """

    EDIT_CALL_ID = "call_synthetic_edit_1"
    EDIT_PATH = "C:\\workspace\\probe.py"

    @classmethod
    def _edit_tool_call(cls) -> dict:
        return {
            "sessionUpdate": "tool_call",
            "toolCallId": cls.EDIT_CALL_ID,
            "title": "Edit probe.py",
            "kind": "edit",
            "status": "pending",
            "rawInput": {"fileName": cls.EDIT_PATH},
            "locations": [{"path": cls.EDIT_PATH}],
            "content": [
                {
                    "type": "diff",
                    "path": cls.EDIT_PATH,
                    "oldText": "old probe body",
                    "newText": "new probe body",
                }
            ],
        }

    def test_edit_tool_use_carries_the_path_and_the_diff(self):
        mapper = CopilotEventMapper()
        events = mapper.on_session_update(self._edit_tool_call())

        tool_use = [e for e in events if e.kind == "tool_use" and e.call_id == self.EDIT_CALL_ID]
        assert len(tool_use) == 1
        payload = tool_use[0].payload
        assert payload["tool"] == "edit"
        assert payload["category"] == "file_change"
        # `input` is the stringified `input_data` (`runner_events.py:178`); the path and both
        # sides of the diff must all survive into it. Substring-only, not an exact backslash
        # match: `json.dumps` may re-escape `\` and this is not the escaping's own test.
        assert "probe.py" in payload["input"]
        assert "old probe body" in payload["input"]
        assert "new probe body" in payload["input"]


class TestWarningInfoTextClassification:
    """Task 1.8 part 4/N, the warning/info-text bullet: a synthetic message `"Warning: X"` with a
    matching raw `session.warning` becomes `diagnostic`, and without one stays `text`
    (design.md:982-994). Symmetric coverage of the `"Info: X"`/`session.info` half is included:
    design.md states both under the same rule and the same table row (`copilot.<warningType>` /
    `copilot.<infoType>`, design.md:1013), so the rule under test is identical for either.

    Both raw events are synthetic -- neither capture has a `session.warning`/`session.info` event
    (design.md:2481-2486, checked directly again for this part) -- built from design.md:987-988's
    CODE-cited shapes (`session.warning: {warningType, message, url?, remediation?}`,
    `session.info: {infoType, message, tip?, url?}`). Fed through `on_raw_event` before the
    matching message block, the same order `TestMcpServerUnavailableDiagnostic` above uses for its
    own raw events, and matching design.md:1112-1116's "raw events feed [...] from spawn onward,
    unarmed" -- the raw event must already be known by the time the block it explains is flushed.
    """

    @staticmethod
    def _warning_event(warning_type: str, message: str) -> tuple:
        data = {"warningType": warning_type, "message": message}
        params = {
            "sessionId": "synthetic-session",
            "type": "session.warning",
            "timestamp": "2026-09-30T00:00:02.000Z",
            "data": data,
        }
        return "session.warning", data, params

    @staticmethod
    def _info_event(info_type: str, message: str) -> tuple:
        data = {"infoType": info_type, "message": message}
        params = {
            "sessionId": "synthetic-session",
            "type": "session.info",
            "timestamp": "2026-09-30T00:00:03.000Z",
            "data": data,
        }
        return "session.info", data, params

    def test_message_block_matching_a_raw_warning_becomes_a_diagnostic(self):
        mapper = CopilotEventMapper()
        type_, data, params = self._warning_event(
            "rate_limit_warning", "You are near your rate limit"
        )
        mapper.on_raw_event(type_, data, params)

        events = mapper.on_session_update(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "Warning: You are near your rate limit"},
            }
        )
        events += mapper.flush()

        assert not any(e.kind == "text" for e in events)
        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1
        payload = diagnostics[0].payload
        assert payload["code"] == "copilot.rate_limit_warning"
        assert payload["severity"] == "warning"
        assert payload["stream"] == "copilot"
        assert "near your rate limit" in payload["summary"]

    def test_message_block_matching_a_raw_info_becomes_a_diagnostic(self):
        mapper = CopilotEventMapper()
        type_, data, params = self._info_event("model_tip", "Try /model to switch")
        mapper.on_raw_event(type_, data, params)

        events = mapper.on_session_update(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "Info: Try /model to switch"},
            }
        )
        events += mapper.flush()

        assert not any(e.kind == "text" for e in events)
        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1
        payload = diagnostics[0].payload
        assert payload["code"] == "copilot.model_tip"
        assert payload["severity"] == "info"

    def test_message_block_with_no_matching_raw_event_stays_text(self):
        mapper = CopilotEventMapper()
        # No `on_raw_event` call at all: nothing this turn explains a "Warning:" prefix, so the
        # block must fall through to plain text -- the bullet's other half.
        events = mapper.on_session_update(
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "Warning: You are near your rate limit"},
            }
        )
        events += mapper.flush()

        assert not any(e.kind == "diagnostic" for e in events)
        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 1
        assert text_events[0].content == "Warning: You are near your rate limit"


class TestSessionErrorRootVsSubagent:
    """Task 1.8 part 5/N, the last bullet on tasks.md's list: "a `session.error` whose envelope
    carries `agentId` (and separately one whose `data` carries `parentToolCallId`) emits a
    `copilot.subagent_error` diagnostic, its `Error:` echo is dropped, and the mapper does not
    mark the turn failed; a root `session.error` still does" (review, cross-slice,
    design.md:1040-1062, re-read fresh for this part per D10's review-finding-8 paragraph and
    contract item 19, design.md:1832-1834).

    Synthetic throughout -- neither capture has any `session.error` at all (checked directly
    again for this part, same as every other synthetic class in this file).

    **This slice's classification rule, not slice 5's future one.** design.md:986-994 gives this
    slice's direct rule -- "An `Error:` match -> `error_event(code="copilot_session_error",
    message=...)`" -- symmetric with the already-tested `Warning:`/`Info:` -> `diagnostic_event`
    rule above (`TestWarningInfoTextClassification`): the raw `session.error` arrives first and
    is remembered, unmatched; the matching `"Error: " + message` chunk is what turns into the
    event, never surviving as `text`. Slice 5's *different*, chunk-level "dropped on arrival,
    before accumulation, nothing held" mechanism (design.md:1030-1034) and its re-coding to
    `copilot.<errorType>` are its own future change ("That is slice 5's to change" -- the same
    paragraph says so directly) and are not this slice's rule; this class tests only what this
    slice actually builds. The root/subagent split is the review finding layered on top: the
    *same* match-and-classify mechanism, routed to `error_event` for a root `session.error` and
    to `diagnostic_event(code="copilot.subagent_error")` for a subagent's, per design.md:1054-1057
    ("its `Error:` echo is matched and dropped like a root one" -- read here as "classified the
    same way", i.e. it does not stay `text` either, not literally discarded with no event, which
    is what slice 5 alone changes to).

    A subagent's `session.error` is identified by **any of three** signals (design.md:1054-1056,
    SDK-cited): the envelope's own `agentId` (the third positional argument this file's other
    raw-event tests already pass as `params`, e.g. `TestMcpServerUnavailableDiagnostic`), or
    `data["agentId"]`, or `data["parentToolCallId"]`. Only the envelope-`agentId` and
    `data.parentToolCallId` variants are tested below, matching the bullet's own two named cases
    ("and separately one whose `data` carries `parentToolCallId`") -- `data.agentId` is the same
    `data`-level check as `data.parentToolCallId` and is not re-tested separately.

    **Turn failure is explicitly NOT asserted here.** "Ends the turn `TurnOutcome(status="failed",
    ...)`" (design.md:1040-1043) names a `TurnOutcome`, a `run_turn`-level object
    (`test_copilot_acp_run_turn.py`, task 1.9) this mapper-only file has no way to construct or
    observe: `on_raw_event`/`on_session_update` return `RunEvent` lists, never a `TurnOutcome`.
    What this file *can* prove, and does, is the fact task 1.9 would need to act on: the mapper
    emits an `error`-kind event for a root `session.error` and never for a subagent's, which emits
    a `diagnostic` instead -- the distinction `run_turn` would read to decide pass/fail. Whether
    `run_turn` actually reads it that way, or instead re-inspects the raw `session.error`'s own
    `agentId`/`data` directly (as `codex_appserver.py`'s `run_turn` decides `status`/`error` from
    specific raw notification types inline, not from what a mapper returned -- checked directly,
    `codex_appserver.py:1150-1195`), is task 1.9's question, not this file's to force an answer to.
    """

    @staticmethod
    def _root_session_error(message: str) -> tuple:
        data = {"errorType": "internal", "message": message}
        params = {
            "sessionId": "synthetic-session",
            "type": "session.error",
            "timestamp": "2026-09-30T00:00:04.000Z",
            "data": data,
        }
        return "session.error", data, params

    @staticmethod
    def _subagent_session_error_via_envelope(message: str, agent_id: str) -> tuple:
        data = {"errorType": "internal", "message": message}
        params = {
            "sessionId": "synthetic-session",
            "type": "session.error",
            "timestamp": "2026-09-30T00:00:05.000Z",
            "agentId": agent_id,
            "data": data,
        }
        return "session.error", data, params

    @staticmethod
    def _subagent_session_error_via_parent_tool_call(message: str, parent_call_id: str) -> tuple:
        data = {
            "errorType": "internal",
            "message": message,
            "parentToolCallId": parent_call_id,
        }
        params = {
            "sessionId": "synthetic-session",
            "type": "session.error",
            "timestamp": "2026-09-30T00:00:06.000Z",
            "data": data,
        }
        return "session.error", data, params

    @staticmethod
    def _error_echo_chunk(message: str) -> dict:
        return {
            "sessionUpdate": "agent_message_chunk",
            "content": {"type": "text", "text": f"Error: {message}"},
        }

    # Slice 5 group A (`a-copilot-agent-uses-hooks-and-its-own-agents` D5) replaced this slice's
    # rule, as the paragraph above says it would: the raw `session.error` is the error event,
    # emitted when it arrives and coded `copilot.<errorType>`, and its echo chunk is dropped on
    # arrival. A subagent's error is an error event naming the subagent, no longer a diagnostic.
    # So the events below are collected from `on_raw_event` as well.

    def test_root_session_error_becomes_an_error_event_not_text(self):
        mapper = CopilotEventMapper()
        type_, data, params = self._root_session_error("model call failed")
        events = mapper.on_raw_event(type_, data, params)

        events += mapper.on_session_update(self._error_echo_chunk("model call failed"))
        events += mapper.flush()

        assert not any(e.kind == "text" for e in events)
        assert not any(e.kind == "diagnostic" for e in events)
        errors = [e for e in events if e.kind == "error"]
        assert len(errors) == 1
        assert errors[0].payload["code"] == "copilot.internal"
        assert "model call failed" in errors[0].payload["message"]
        assert mapper.root_error == "model call failed"

    def test_subagent_session_error_via_envelope_agent_id_is_an_error_naming_it(self):
        mapper = CopilotEventMapper()
        type_, data, params = self._subagent_session_error_via_envelope(
            "subagent tool crashed", "agent-explore-1"
        )
        events = mapper.on_raw_event(type_, data, params)

        events += mapper.on_session_update(self._error_echo_chunk("subagent tool crashed"))
        events += mapper.flush()

        assert not any(e.kind == "text" for e in events)
        assert not any(e.kind == "diagnostic" for e in events)
        errors = [e for e in events if e.kind == "error"]
        assert len(errors) == 1
        assert errors[0].payload["subagent_id"] == "agent-explore-1"
        assert mapper.root_error is None, "a subagent's error does not fail the turn"

    def test_subagent_session_error_via_data_parent_tool_call_id_is_an_error_naming_it(self):
        mapper = CopilotEventMapper()
        type_, data, params = self._subagent_session_error_via_parent_tool_call(
            "code-review subagent crashed", "call_parent_1"
        )
        events = mapper.on_raw_event(type_, data, params)

        events += mapper.on_session_update(self._error_echo_chunk("code-review subagent crashed"))
        events += mapper.flush()

        assert not any(e.kind == "text" for e in events)
        assert not any(e.kind == "diagnostic" for e in events)
        errors = [e for e in events if e.kind == "error"]
        assert len(errors) == 1
        assert errors[0].payload["subagent_id"] == "call_parent_1"
        assert mapper.root_error is None, "a subagent's error does not fail the turn"


class TestModelSubstitutionDiagnostic:
    """Task 1.8 part 6/N, the model-substitution bullet: "`session.model_change` to a different
    model emits one diagnostic" (design.md:1081-1092, re-read fresh for this part).

    The mapper "takes the resolved model from the first of `session.model_change`,
    `session.auto_mode_resolved` or `session.tools_updated` it sees" and, "when the requested
    model was not `auto` and differs from the resolved one", emits one `diagnostic_event` carrying
    `code == "copilot.model_substituted"`, `severity == "info"` (design.md:1018). Neither capture
    has a `session.model_change`/`session.auto_mode_resolved` at all (checked directly); the real
    capture *does* show `session.tools_updated {model}` (design.md:1084-1085), so the primary
    tests below use that shape, and the other two only where the point under test is specifically
    about *which of the three shapes arrived first*, not about `tools_updated` itself.

    `CopilotEventMapper` gets a second inferred constructor keyword here, `requested_model` --
    not named anywhere in design.md, added the same way `told_access_path` was in part 3/N, to
    carry `RpcTurnRequest.model` (design.md:1527) into the mapper. Flagged for a future round the
    same way.

    The example message text and `"this plan allows: [...]"` list format (design.md:1089-1091)
    are illustrative, not a byte-exact CODE citation (the `next_action` that queued this part says
    so explicitly) -- assertions below check `code`/`severity`/`stream` and that both model names
    appear in `summary`, never the exact wording.
    """

    @staticmethod
    def _tools_updated(model: str) -> tuple:
        data = {"model": model}
        params = {
            "sessionId": "synthetic-session",
            "type": "session.tools_updated",
            "timestamp": "2026-09-30T00:00:07.000Z",
            "data": data,
        }
        return "session.tools_updated", data, params

    @staticmethod
    def _model_change(new_model: str, previous_model: str | None = None) -> tuple:
        data = {"newModel": new_model}
        if previous_model is not None:
            data["previousModel"] = previous_model
        params = {
            "sessionId": "synthetic-session",
            "type": "session.model_change",
            "timestamp": "2026-09-30T00:00:08.000Z",
            "data": data,
        }
        return "session.model_change", data, params

    @staticmethod
    def _auto_mode_resolved(chosen_model: str, available_models: list | None = None) -> tuple:
        data = {"chosenModel": chosen_model}
        if available_models is not None:
            data["availableModels"] = available_models
        params = {
            "sessionId": "synthetic-session",
            "type": "session.auto_mode_resolved",
            "timestamp": "2026-09-30T00:00:09.000Z",
            "data": data,
        }
        return "session.auto_mode_resolved", data, params

    def test_resolved_model_differing_from_requested_emits_one_diagnostic(self):
        mapper = CopilotEventMapper(requested_model="claude-haiku-4.5")
        type_, data, params = self._tools_updated("mai-code-1.1-flash")
        events = mapper.on_raw_event(type_, data, params)

        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1
        payload = diagnostics[0].payload
        assert payload["code"] == "copilot.model_substituted"
        assert payload["severity"] == "info"
        assert payload["stream"] == "copilot"
        assert "mai-code-1.1-flash" in payload["summary"]
        assert "claude-haiku-4.5" in payload["summary"]

    def test_resolved_model_matching_requested_emits_no_diagnostic(self):
        mapper = CopilotEventMapper(requested_model="claude-haiku-4.5")
        type_, data, params = self._tools_updated("claude-haiku-4.5")
        events = mapper.on_raw_event(type_, data, params)

        assert not any(e.kind == "diagnostic" for e in events)

    def test_requested_model_auto_emits_no_diagnostic_even_when_resolved_differs(self):
        mapper = CopilotEventMapper(requested_model="auto")
        type_, data, params = self._tools_updated("mai-code-1.1-flash")
        events = mapper.on_raw_event(type_, data, params)

        assert not any(e.kind == "diagnostic" for e in events)

    def test_resolved_model_taken_from_the_first_raw_event_type_seen(self):
        # The first raw event seen (`session.tools_updated`) resolves the model; a second,
        # differently-shaped raw event (`session.model_change`) arriving afterward must not
        # re-diagnose against its own, different model -- design.md:1086-1087's "first ... it
        # sees" is about arrival order across all three shapes, not about `tools_updated` alone.
        mapper = CopilotEventMapper(requested_model="claude-haiku-4.5")
        first_type, first_data, first_params = self._tools_updated("mai-code-1.1-flash")
        first_events = mapper.on_raw_event(first_type, first_data, first_params)

        second_type, second_data, second_params = self._model_change(
            "gpt-5-mini", previous_model="mai-code-1.1-flash"
        )
        second_events = mapper.on_raw_event(second_type, second_data, second_params)

        first_diagnostics = [e for e in first_events if e.kind == "diagnostic"]
        second_diagnostics = [e for e in second_events if e.kind == "diagnostic"]
        assert len(first_diagnostics) == 1
        assert len(second_diagnostics) == 0
        assert "mai-code-1.1-flash" in first_diagnostics[0].payload["summary"]
        assert "gpt-5-mini" not in first_diagnostics[0].payload["summary"]


class TestUserMessageChunkDropped:
    """Task 1.8 part 6/N, the mapper-testable half of the `user_message_chunk`-before-arming
    bullet. design.md:977 lists `user_message_chunk` in the mapper's own "Dropped" set for
    `on_session_update`, unconditional on arming -- arming itself is `_on_armed_raw_event`'s gate,
    outside `CopilotEventMapper`, out of this file's scope for the same reason already recorded at
    `TestMcpServerUnavailableDiagnostic`'s docstring for the `agentweave`-server-status bullet.
    """

    def test_user_message_chunk_emits_nothing(self):
        mapper = CopilotEventMapper()
        events = mapper.on_session_update(
            {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": "echo hookprobe ."},
            }
        )
        assert events == []

    def test_user_message_chunk_does_not_flush_or_join_a_pending_agent_message_block(self):
        mapper = CopilotEventMapper()
        events = []
        events += mapper.on_session_update(
            {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Hello"}}
        )
        events += mapper.on_session_update(
            {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": "unrelated user text"},
            }
        )
        assert events == []  # neither the still-open agent block nor the dropped chunk emits yet

        events += mapper.flush()
        text_events = [e for e in events if e.kind == "text"]
        assert len(text_events) == 1
        assert text_events[0].content == "Hello"  # the dropped chunk's text never joined the block


class TestCapturedModelResolution:
    """Task 6.1, from the 1.1 capture (`turn_write_shell_mcp.jsonl` lines 10-14): Copilot's first
    model event is `session.model_change` with `newModel: "auto"` at startup -- the *request*, not
    a resolution -- and only then `session.auto_mode_resolved {chosenModel}`. Taking "the first of
    the three events" literally would resolve the model to `auto`; the mapper takes the first one
    naming a concrete model."""

    def test_the_captured_sequence_resolves_to_the_chosen_model(self):
        mapper = CopilotEventMapper(requested_model="claude-haiku-4.5")
        events = []
        for tag, payload in _mcp_fixture_events():
            if tag == "raw" and payload["type"] in (
                "session.model_change",
                "session.auto_mode_resolved",
                "session.tools_updated",
            ):
                events += mapper.on_raw_event(payload["type"], payload["data"], payload)

        assert mapper.resolved_model == "gpt-6-luna"
        diagnostics = [e for e in events if e.kind == "diagnostic"]
        assert len(diagnostics) == 1
        assert "gpt-6-luna" in diagnostics[0].payload["summary"]
        assert "claude-haiku-4.5" in diagnostics[0].payload["summary"]


class TestCapturedTurnReplay:
    """The whole 1.1 capture, in recorded order, through one mapper: every one of its nine tool
    calls opens exactly one `tool_use` and closes with one `tool_result`, and only the one MCP call
    is labelled `mcp`."""

    def test_every_call_is_used_then_resulted_once_and_only_the_mcp_call_is_mcp(self):
        mapper = CopilotEventMapper(told_access_path="mcp")
        events = []
        for tag, payload in _mcp_fixture_events():
            if tag == "raw":
                events += mapper.on_raw_event(payload["type"], payload["data"], payload)
            else:
                events += mapper.on_session_update(payload)
        events += mapper.finish()

        uses = [e for e in events if e.kind == "tool_use"]
        results = [e for e in events if e.kind == "tool_result"]
        assert len(uses) == 9 and len(results) == 9
        for use in uses:
            (result,) = [r for r in results if r.call_id == use.call_id]
            assert events.index(use) < events.index(result)
        assert [u.payload["tool"] for u in uses if u.payload["category"] == "mcp"] == [
            "agentweave-list_tasks"
        ]
        assert {u.payload["tool"] for u in uses if u.payload["category"] != "mcp"} == {
            "shell",
            "fetch",
        }
        assert any(e.kind == "text" for e in events)
        assert not any(e.kind == "error" for e in events), "the capture reported no failure"


class TestUnmatchedRootErrorIsReportedAtFinish:
    """A root `session.error` that Copilot never echoes as `Error:` text still reaches the
    timeline: it fails the turn (D10, R3), so it must not be silent. Since slice 5 (D5) it is
    recorded when the raw event arrives, so `finish()` has nothing left to report for it."""

    def test_an_unechoed_root_error_is_reported_once(self):
        mapper = CopilotEventMapper()
        data = {"errorType": "model_error", "message": "upstream rate limited"}
        params = {"sessionId": "s", "type": "session.error", "data": data}
        events = mapper.on_raw_event("session.error", data, params)
        assert mapper.root_error == "upstream rate limited"

        events += mapper.finish()
        errors = [e for e in events if e.kind == "error"]
        assert len(errors) == 1
        assert errors[0].payload["code"] == "copilot.model_error"
        assert mapper.finish() == [], "reported once"
