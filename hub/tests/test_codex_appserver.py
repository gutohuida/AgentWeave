"""Tests for codex_appserver.decide_approval and map_item_to_events.

Fixtures are trimmed real payloads captured from a live `codex app-server` (CLI 0.146.0,
Windows) during openspec change 2026-08-06-agent-messaging-delivery's task 2.1-2.5
investigation — not hand-guessed shapes. `decide_approval`'s command-approval test in
particular reproduces the exact probe that verified `{"decision": "decline"}` (not
`{"decision": "denied"}`/`{"decision": "approved"}`) is the shape this method actually
accepts: a real out-of-workspace write attempt, declined this way, produced no file.
"""

from hub.codex_appserver import (
    COMMAND_APPROVAL_METHOD,
    ELICITATION_METHOD,
    FILE_CHANGE_APPROVAL_METHOD,
    PERMISSIONS_APPROVAL_METHOD,
    decide_approval,
    map_item_to_events,
    map_token_usage_notification,
    map_turn_failure,
)

OWN_SERVER = "agentweave"


class TestDecideApproval:
    def test_own_server_mcp_tool_call_is_approved(self):
        params = {
            "serverName": OWN_SERVER,
            "mode": "form",
            "_meta": {"codex_approval_kind": "mcp_tool_call"},
        }
        assert decide_approval(
            ELICITATION_METHOD, params, yolo=False, own_server_name=OWN_SERVER
        ) == {"action": "accept"}

    def test_different_server_mcp_tool_call_is_denied(self):
        params = {
            "serverName": "some_other_server",
            "mode": "form",
            "_meta": {"codex_approval_kind": "mcp_tool_call"},
        }
        assert decide_approval(
            ELICITATION_METHOD, params, yolo=False, own_server_name=OWN_SERVER
        ) == {"action": "decline"}

    def test_own_server_but_not_a_tool_call_is_denied(self):
        """Both conditions required (implications.md §3) — server name alone isn't enough."""
        params = {"serverName": OWN_SERVER, "_meta": {"codex_approval_kind": "something_else"}}
        assert decide_approval(
            ELICITATION_METHOD, params, yolo=False, own_server_name=OWN_SERVER
        ) == {"action": "decline"}

    def test_yolo_does_not_affect_elicitation_decision(self):
        """Task 2.13: yolo is not required for (and does not change) tool-call approval."""
        params = {
            "serverName": OWN_SERVER,
            "_meta": {"codex_approval_kind": "mcp_tool_call"},
        }
        assert decide_approval(
            ELICITATION_METHOD, params, yolo=True, own_server_name=OWN_SERVER
        ) == {"action": "accept"}
        assert decide_approval(
            ELICITATION_METHOD, params, yolo=False, own_server_name=OWN_SERVER
        ) == {"action": "accept"}

    def test_command_execution_denied_for_non_yolo(self):
        # Real captured params from a live probe (see module docstring).
        params = {
            "threadId": "019fd621-0f5f-7072-be36-9d8c618b8696",
            "turnId": "019fd621-0ffa-7110-8014-700892cad990",
            "itemId": "call_jVD4v7zfSBshPffeK9QjeMXp",
            "reason": "Do you want to allow writing the requested file outside the writable workspace?",
            "command": "powershell -Command \"Set-Content -Path 'C:\\\\outside\\\\file.txt' -Value x\"",
            "availableDecisions": ["accept", "cancel"],
        }
        assert decide_approval(
            COMMAND_APPROVAL_METHOD, params, yolo=False, own_server_name=OWN_SERVER
        ) == {"decision": "decline"}

    def test_command_execution_approved_for_yolo(self):
        params = {"command": "rm -rf /outside"}
        assert decide_approval(
            COMMAND_APPROVAL_METHOD, params, yolo=True, own_server_name=OWN_SERVER
        ) == {"decision": "accept"}

    def test_file_change_follows_same_yolo_rule(self):
        assert decide_approval(
            FILE_CHANGE_APPROVAL_METHOD, {}, yolo=False, own_server_name=OWN_SERVER
        ) == {"decision": "decline"}
        assert decide_approval(
            FILE_CHANGE_APPROVAL_METHOD, {}, yolo=True, own_server_name=OWN_SERVER
        ) == {"decision": "accept"}

    def test_permissions_request_denies_without_yolo(self):
        assert decide_approval(
            PERMISSIONS_APPROVAL_METHOD, {}, yolo=False, own_server_name=OWN_SERVER
        ) == {"permissions": {}}

    def test_permissions_request_grants_for_yolo(self):
        result = decide_approval(
            PERMISSIONS_APPROVAL_METHOD, {}, yolo=True, own_server_name=OWN_SERVER
        )
        assert result["permissions"]  # non-empty grant

    def test_unrecognised_method_is_denied_not_ignored(self):
        """Task 2.12: an unrecognised server->client request must still get an answer,
        and the answer must be a denial — implications.md §2's "silence becomes a
        deadlock" means returning nothing is never acceptable."""
        result = decide_approval(
            "some/future/method/notInTheSchemaYet", {}, yolo=True, own_server_name=OWN_SERVER
        )
        assert result == {"decision": "decline"}

    def test_unrecognised_method_denied_regardless_of_yolo(self):
        assert decide_approval(
            "totally/unknown", {}, yolo=False, own_server_name=OWN_SERVER
        ) == decide_approval("totally/unknown", {}, yolo=True, own_server_name=OWN_SERVER)


class TestMapItemToEvents:
    def test_agent_message_completed_emits_text(self):
        item = {"type": "agentMessage", "id": "msg_1", "text": "OK", "phase": "final_answer"}
        events = map_item_to_events(item, is_start=False)
        assert len(events) == 1
        assert events[0].kind == "text"
        assert events[0].content == "OK"

    def test_agent_message_started_emits_nothing(self):
        item = {"type": "agentMessage", "id": "msg_1", "text": "", "phase": "commentary"}
        assert map_item_to_events(item, is_start=True) == []

    def test_empty_agent_message_emits_nothing(self):
        item = {"type": "agentMessage", "id": "msg_1", "text": "", "phase": "final_answer"}
        assert map_item_to_events(item, is_start=False) == []

    def test_command_execution_started_emits_tool_use(self):
        # Real captured shape.
        item = {
            "type": "commandExecution",
            "id": "call_6by8oiB5dsweI9lNUvNRNoUS",
            "command": "\"C:\\\\...\\\\powershell.exe\" -Command 'echo hello-from-appserver-probe'",
            "cwd": "C:\\workspace",
            "status": "inProgress",
        }
        events = map_item_to_events(item, is_start=True)
        assert len(events) == 1
        assert events[0].kind == "tool_use"
        assert events[0].payload["tool"] == "shell"
        assert events[0].call_id == "call_6by8oiB5dsweI9lNUvNRNoUS"

    def test_command_execution_completed_success_emits_tool_result(self):
        item = {
            "type": "commandExecution",
            "id": "call_6by8oiB5dsweI9lNUvNRNoUS",
            "aggregatedOutput": "hello-from-appserver-probe\r\n",
            "exitCode": 0,
            "status": "completed",
        }
        events = map_item_to_events(item, is_start=False)
        assert len(events) == 1
        assert events[0].kind == "tool_result"
        assert events[0].payload["is_error"] is False
        assert "hello-from-appserver-probe" in events[0].payload["output"]

    def test_command_execution_completed_failure_is_marked_error(self):
        item = {
            "type": "commandExecution",
            "id": "call_x",
            "aggregatedOutput": "boom",
            "exitCode": 1,
        }
        events = map_item_to_events(item, is_start=False)
        assert events[0].payload["is_error"] is True

    def test_command_execution_declined_is_marked_error_despite_null_exit_code(self):
        """Task 2.14's live breach test: a declined command never runs, so `exitCode` is
        null — `status: "declined"` (schema: CommandExecutionStatus) is what actually
        distinguishes a refused command from a successful one here."""
        item = {
            "type": "commandExecution",
            "id": "call_x",
            "aggregatedOutput": "",
            "exitCode": None,
            "status": "declined",
        }
        events = map_item_to_events(item, is_start=False)
        assert events[0].payload["is_error"] is True

    def test_file_change_started_emits_tool_use(self):
        item = {
            "type": "fileChange",
            "id": "call_1",
            "changes": [
                {"path": "C:\\workspace\\out.txt", "diff": "BREACH\n", "kind": {"type": "add"}}
            ],
        }
        events = map_item_to_events(item, is_start=True)
        assert len(events) == 1
        assert events[0].kind == "tool_use"
        assert events[0].payload["tool"] == "apply_patch"
        assert events[0].call_id == "call_1"

    def test_file_change_completed_success_is_not_marked_error(self):
        item = {
            "type": "fileChange",
            "id": "call_1",
            "status": "completed",
            "changes": [
                {"path": "C:\\workspace\\out.txt", "diff": "hi\n", "kind": {"type": "add"}}
            ],
        }
        events = map_item_to_events(item, is_start=False)
        assert events[0].kind == "tool_result"
        assert events[0].payload["is_error"] is False

    def test_file_change_declined_is_marked_error(self):
        """Task 2.14's live breach test caught this live: an out-of-workspace `apply_patch`
        attempt, declined via `decide_approval`, reports `status: "declined"` (schema:
        PatchApplyStatus) — not "failed". The original `== "failed"` check missed this and
        reported a refused sandbox-escape attempt as a successful tool call."""
        item = {
            "type": "fileChange",
            "id": "call_1",
            "status": "declined",
            "changes": [
                {
                    "path": "C:\\outside\\OUTSIDE_BREACH_MARKER.txt",
                    "diff": "BREACH\n",
                    "kind": {"type": "add"},
                }
            ],
        }
        events = map_item_to_events(item, is_start=False)
        assert events[0].kind == "tool_result"
        assert events[0].payload["is_error"] is True

    def test_file_change_failed_is_marked_error(self):
        item = {
            "type": "fileChange",
            "id": "call_1",
            "status": "failed",
            "changes": [
                {"path": "C:\\workspace\\out.txt", "diff": "hi\n", "kind": {"type": "add"}}
            ],
        }
        events = map_item_to_events(item, is_start=False)
        assert events[0].payload["is_error"] is True

    def test_mcp_tool_call_started_emits_tool_use_with_server_qualified_name(self):
        item = {
            "type": "mcpToolCall",
            "id": "call_1",
            "server": "agentweave",
            "tool": "send_message",
            "arguments": {"to_agent": "x", "subject": "y", "content": "z"},
        }
        events = map_item_to_events(item, is_start=True)
        assert events[0].payload["tool"] == "agentweave.send_message"
        assert events[0].payload["category"] == "mcp"

    def test_mcp_tool_call_completed_with_error_field_is_error(self):
        item = {
            "type": "mcpToolCall",
            "id": "call_1",
            "server": "agentweave",
            "tool": "send_message",
            "error": {"message": "Hub API error 405: Method Not Allowed"},
        }
        events = map_item_to_events(item, is_start=False)
        assert events[0].payload["is_error"] is True
        assert "405" in events[0].content

    def test_mcp_tool_call_completed_success(self):
        item = {
            "type": "mcpToolCall",
            "id": "call_1",
            "server": "agentweave",
            "tool": "list_tasks",
            "status": "completed",
            "result": {"content": [{"type": "text", "text": '{"result":[]}'}]},
        }
        events = map_item_to_events(item, is_start=False)
        assert events[0].kind == "tool_result"
        assert events[0].payload["is_error"] is False

    def test_reasoning_with_empty_summary_and_content_emits_nothing(self):
        # Real captured shape: reasoning effort sometimes yields no visible text.
        item = {"type": "reasoning", "id": "rs_1", "summary": [], "content": []}
        assert map_item_to_events(item, is_start=False) == []

    def test_unrecognised_item_type_emits_nothing_not_an_exception(self):
        item = {"type": "someBrandNewItemType", "id": "x"}
        assert map_item_to_events(item, is_start=False) == []
        assert map_item_to_events(item, is_start=True) == []

    def test_user_message_item_is_not_re_emitted(self):
        item = {"type": "userMessage", "id": "u1", "content": [{"type": "text", "text": "hi"}]}
        assert map_item_to_events(item, is_start=True) == []
        assert map_item_to_events(item, is_start=False) == []


class TestMapTokenUsageNotification:
    def test_measured_sample_uses_self_reported_context_window(self):
        # Real captured shape.
        params = {
            "tokenUsage": {
                "total": {"totalTokens": 30432, "inputTokens": 30243, "outputTokens": 189},
                "last": {
                    "totalTokens": 15236,
                    "inputTokens": 15231,
                    "cachedInputTokens": 14720,
                    "cacheWriteInputTokens": 0,
                    "outputTokens": 5,
                    "reasoningOutputTokens": 0,
                },
                "modelContextWindow": 258400,
            }
        }
        mapped = map_token_usage_notification(params, model="gpt-5.4-mini")
        usage = mapped["usage"]
        assert usage.status == "measured"
        assert usage.limit_tokens == 258400
        assert usage.context_tokens == 15231 + 5  # last.inputTokens + last.outputTokens

    def test_missing_context_window_is_unavailable_not_a_substituted_default(self):
        params = {"tokenUsage": {"last": {"inputTokens": 100, "outputTokens": 10}}}
        mapped = map_token_usage_notification(params, model="unknown-model")
        assert mapped["usage"].status == "unavailable"
        assert mapped["usage"].limit_tokens is None

    def test_accounting_uses_last_not_cumulative_total(self):
        params = {
            "tokenUsage": {
                "total": {"totalTokens": 999999},
                "last": {"totalTokens": 15236, "inputTokens": 15231, "outputTokens": 5},
            }
        }
        mapped = map_token_usage_notification(params, model="gpt-5.4-mini")
        assert mapped["accounting"].total_tokens == 15236


class TestMapTurnFailure:
    def test_turn_failure_maps_to_error_event(self):
        event = map_turn_failure({"error": {"message": "boom"}})
        assert event.kind == "error"
        assert "boom" in event.content
