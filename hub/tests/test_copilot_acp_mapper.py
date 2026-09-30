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

Left for a later part, and why: the R3 diagnostic-payload bullets (every `diagnostic` payload
carries `version`/`stream`/`severity`/`summary`, and the `agentweave` server status `failed` ->
`copilot.mcp_server_unavailable` case) need a *failed* `session.mcp_servers_loaded`/
`session.mcp_server_status_changed`, and this fixture's own is `status: "connected"` (line 14,
checked directly) -- no fixture has a failed one, so that bullet needs a synthetic, CODE-shaped
notification. The edit/diff bullet and the warning/info/`agentweave`-failed-status bullets are in
neither fixture (checked directly: no `edit`-kind `tool_call` and no `session.warning`/
`session.info`/`session.error` event in either file) and need synthetic, CODE-shaped notifications
too. The subagent-error bullet is likewise synthetic-only.
"""

import json
from pathlib import Path

from hub.copilot_acp import CopilotEventMapper

EVIDENCE_LOG = (
    Path(__file__).resolve().parents[2]
    / "openspec"
    / "changes"
    / "a-copilot-agent-runs-over-acp"
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
