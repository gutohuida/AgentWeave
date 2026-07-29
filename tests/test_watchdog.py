"""Tests for watchdog dispatch logic."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentweave.stream_events import STREAM_EVENT_KINDS, ContextUsageSample, ParsedRunnerLine
from agentweave.watchdog import (
    CodexRolloutCollector,
    RunnerUsageCollector,
    _agent_ping_cmd,
    _build_codex_mcp_tool_call,
    _claude_tool_result_text,
    _claude_usage_sample,
    _codex_rollout_session_id,
    _codex_rollout_usage_sample,
    _codex_working_dir,
    _extract_codex_mcp_result,
    _extract_jsonl_session_id,
    _KimiCodeParser,
    _parse_claude_stream_line,
    _parse_codex_stream_line,
    _parse_copilot_stream_line,
    _parse_opencode_stdout_line,
    _resolve_codex_rollout_path,
    _run_agent_subprocess,
    _run_codex_mcp_turn,
    _select_codex_usage,
    _write_codex_context_usage,
)


class TestAgentPingCmdKimi:
    """Tests for _agent_ping_cmd with kimi v1.x (kimi-cli, e.g. 1.47.0).

    kimi-cli v1.x uses: --print -p <prompt> --output-format stream-json
    and emits chat events with no top-level "type" field. kimi 1.47.0
    rejects --wire as a modifier of --print ("Cannot combine --print, --wire.")
    so the watchdog uses --print --output-format stream-json -p instead.
    """

    @pytest.fixture(autouse=True)
    def setup_session(self, tmp_path):
        """Set up a temporary session with kimi agents."""
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.agents_dir = self.session_dir / "agents"
        self.agents_dir.mkdir()
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir()

        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "kimi-dev": {"runner": "kimi", "model": "kimi-k2"},
                "kimi-qa": {"runner": "kimi"},
            },
        }

        from agentweave.session import Session

        self.session = Session(session_data)

        # Force v1.x detection so these tests are deterministic regardless of
        # which kimi binary is installed in the runtime environment.
        with patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir), patch(
            "agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir
        ), patch("agentweave.session.Session.load", return_value=self.session), patch(
            "agentweave.watchdog._KIMI_VERSION_CACHE", "1"
        ):
            yield

    def test_kimi_with_model(self):
        """Model flag is appended when agent config has a model."""
        cmd = _agent_ping_cmd("kimi-dev", "do the task")
        assert cmd == [
            "kimi",
            "--print",
            "--output-format",
            "stream-json",
            "--model",
            "kimi-k2",
            "-p",
            "do the task",
        ]
        assert "--wire" not in cmd

    def test_kimi_without_model(self):
        """No --model flag when model is not configured."""
        cmd = _agent_ping_cmd("kimi-qa", "do the task")
        assert cmd == [
            "kimi",
            "--print",
            "--output-format",
            "stream-json",
            "-p",
            "do the task",
        ]
        assert "--wire" not in cmd

    def test_kimi_resume_with_model(self):
        """Resume keeps the configured model flag and uses -S."""
        cmd = _agent_ping_cmd("kimi-dev", "do the task", session_id="sess-123")
        assert cmd == [
            "kimi",
            "--print",
            "--output-format",
            "stream-json",
            "--model",
            "kimi-k2",
            "-S",
            "sess-123",
            "-p",
            "do the task",
        ]
        assert "--wire" not in cmd


class TestAgentPingCmdKimiCode:
    """Tests for _agent_ping_cmd with kimi-code v0.x standalone (e.g. 0.16.0).

    kimi-code v0.x uses a different CLI surface than kimi v1.x:
      -p "<prompt>" + --output-format stream-json
    and emits chat-history persistence events (no real-time streaming).
    Detection is by parsing the major version of `kimi --version`.

    -y (--yolo) is only appended when the agent's session config has
    yolo: True — kimi v0.x rejects -y combined with -p.
    """

    @pytest.fixture(autouse=True)
    def setup_session(self, tmp_path):
        """Set up a temporary session with kimi agents and force v0.x detection."""
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.agents_dir = self.session_dir / "agents"
        self.agents_dir.mkdir()
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir()

        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "kimi-dev": {"runner": "kimi", "model": "kimi-k2"},
                "kimi-qa": {"runner": "kimi"},
                "kimi-yolo": {"runner": "kimi", "yolo": True},
            },
        }

        from agentweave.session import Session

        self.session = Session(session_data)

        with patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir), patch(
            "agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir
        ), patch("agentweave.session.Session.load", return_value=self.session), patch(
            "agentweave.watchdog._KIMI_VERSION_CACHE", "0"
        ):
            yield

    def test_kimi_code_with_model(self):
        """kimi-code v0: --output-format stream-json + -m <model> + -p (no -y unless enabled)."""
        cmd = _agent_ping_cmd("kimi-dev", "do the task")
        assert cmd == [
            "kimi",
            "--output-format",
            "stream-json",
            "-m",
            "kimi-k2",
            "-p",
            "do the task",
        ]
        assert "-y" not in cmd

    def test_kimi_code_without_model(self):
        """kimi-code v0: no -m flag when model is not configured; no -y unless enabled."""
        cmd = _agent_ping_cmd("kimi-qa", "do the task")
        assert cmd == [
            "kimi",
            "--output-format",
            "stream-json",
            "-p",
            "do the task",
        ]
        assert "-y" not in cmd

    def test_kimi_code_resume(self):
        """kimi-code v0: -S <id> placed before -p for session resume; no -y unless enabled."""
        cmd = _agent_ping_cmd("kimi-dev", "do the task", session_id="ses-uuid-here")
        assert cmd == [
            "kimi",
            "--output-format",
            "stream-json",
            "-m",
            "kimi-k2",
            "-S",
            "ses-uuid-here",
            "-p",
            "do the task",
        ]
        assert "-y" not in cmd

    def test_kimi_code_with_yolo_appends_dash_y(self):
        """kimi-code v0: -y is appended when the agent's session config has yolo=True."""
        cmd = _agent_ping_cmd("kimi-yolo", "do the task")
        assert "-y" in cmd
        assert cmd == [
            "kimi",
            "--output-format",
            "stream-json",
            "-y",
            "-p",
            "do the task",
        ]

    def test_kimi_code_with_yolo_and_resume(self):
        """kimi-code v0: -y + -S <id> + -p when both yolo and session_id are set."""
        cmd = _agent_ping_cmd("kimi-yolo", "do the task", session_id="ses-uuid-here")
        assert cmd == [
            "kimi",
            "--output-format",
            "stream-json",
            "-y",
            "-S",
            "ses-uuid-here",
            "-p",
            "do the task",
        ]


class TestKimiCodeParser:
    """Tests for _KimiCodeParser: the canonical kimi `-p ... --output-format
    stream-json` adapter.

    The unprefixed tests below cover the flat role/content/tool_calls shape
    confirmed live against an installed Kimi Code CLI 0.29.1 (2026-07-29) — this is
    the actual, currently-shipping wire format and the primary target of task 2.11.
    The `legacy_wrapped_`-prefixed tests cover the older `{"type":
    "context.append_message","message":{...}}` shape: existing regression coverage
    only, not observed in any live 0.29.1 probe (task 2.11: preserve, do not expand).
    """

    # ── flat shape confirmed live for Kimi Code 0.29.1 ──────────────────────

    def test_assistant_text_becomes_text_event(self):
        parser = _KimiCodeParser()
        parsed = parser.feed('{"role":"assistant","content":[{"type":"text","text":"Hi there"}]}')
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "Hi there"

    def test_assistant_think_becomes_thinking_event(self):
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"role":"assistant","content":[{"type":"think","think":"pondering..."}]}'
        )
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "thinking"
        assert parsed.events[0].content == "pondering..."

    def test_assistant_text_and_think_render_in_order(self):
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"role":"assistant","content":['
            '{"type":"think","think":"hmm"},'
            '{"type":"text","text":"answer"}]}'
        )
        assert [e.kind for e in parsed.events] == ["thinking", "text"]
        assert [e.content for e in parsed.events] == ["hmm", "answer"]

    def test_assistant_tool_calls_snake_case_becomes_tool_use_event(self):
        """Kimi Code 0.29.1 emits tool calls with the snake_case key 'tool_calls'."""
        args = json.dumps({"agent": "kimi"})
        parser = _KimiCodeParser()
        evt = json.dumps(
            {
                "role": "assistant",
                "content": [],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "tool_pelW6gHcdtL5l8MURuDTqmVZ",
                        "function": {"name": "get_inbox", "arguments": args},
                    }
                ],
            }
        )
        parsed = parser.feed(evt)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_use"
        assert event.call_id == "tool_pelW6gHcdtL5l8MURuDTqmVZ"
        assert event.payload["tool"] == "get_inbox"

    def test_assistant_think_plus_tool_calls_renders_both(self):
        args = json.dumps({"agent": "kimi"})
        parser = _KimiCodeParser()
        evt = json.dumps(
            {
                "role": "assistant",
                "content": [{"type": "think", "think": "calling inbox"}],
                "tool_calls": [
                    {
                        "type": "function",
                        "id": "call-1",
                        "function": {"name": "get_inbox", "arguments": args},
                    }
                ],
            }
        )
        parsed = parser.feed(evt)
        assert [e.kind for e in parsed.events] == ["thinking", "tool_use"]

    def test_tool_result_string_content_becomes_tool_result_event(self):
        """Kimi Code 0.29.1 emits tool content as a plain string, not a list."""
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"role":"tool","content":"<system>Tool output is empty.</system>",'
            '"tool_call_id":"tool_pelW6gHcdtL5l8MURuDTqmVZ"}'
        )
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_result"
        assert event.call_id == "tool_pelW6gHcdtL5l8MURuDTqmVZ"
        assert event.payload["output"] == "<system>Tool output is empty.</system>"
        assert event.payload["is_error"] is False

    def test_tool_result_empty_string_falls_back_to_ok(self):
        parser = _KimiCodeParser()
        parsed = parser.feed('{"role":"tool","content":"","tool_call_id":"call-1"}')
        assert len(parsed.events) == 1
        assert parsed.events[0].payload["output"] == "ok"

    def test_user_message_is_skipped(self):
        parser = _KimiCodeParser()
        parsed = parser.feed('{"role":"user","content":[{"type":"text","text":"hello"}]}')
        assert parsed.events == []

    def test_event_with_unknown_role_is_skipped(self):
        parser = _KimiCodeParser()
        parsed = parser.feed('{"role":"system","content":[{"type":"text","text":"sys"}]}')
        assert parsed.events == []

    def test_full_inbox_flow_emits_think_call_result_and_final_text(self):
        """End-to-end check: simulate a get_inbox round-trip.

        Three events arrive in order:
          1. assistant with think + tool_calls (caller)
          2. tool with string content (result)
          3. assistant with think + text (final summary)
        """
        args = json.dumps({"agent": "kimi"})
        parser = _KimiCodeParser()
        events = [
            json.dumps(
                {
                    "role": "assistant",
                    "content": [{"type": "think", "think": "I need to check inbox"}],
                    "tool_calls": [
                        {
                            "type": "function",
                            "id": "call-1",
                            "function": {"name": "get_inbox", "arguments": args},
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "role": "tool",
                    "content": "<system>Tool output is empty.</system>",
                    "tool_call_id": "call-1",
                }
            ),
            json.dumps(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "think", "think": "inbox is empty"},
                        {"type": "text", "text": "No new messages."},
                    ],
                }
            ),
        ]
        kinds = []
        for e in events:
            kinds.extend(event.kind for event in parser.feed(e).events)
        assert kinds == ["thinking", "tool_use", "tool_result", "thinking", "text"]

    def test_assistant_string_content_becomes_text_event(self):
        """Kimi Code 0.29.1 `--no-thinking` emits the final summary as a plain
        string in `content` (not a list of typed parts)."""
        parser = _KimiCodeParser()
        parsed = parser.feed('{"role":"assistant","content":"Done! I wrote helloworld.py."}')
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "Done! I wrote helloworld.py."

    def test_assistant_empty_string_content_emits_nothing(self):
        parser = _KimiCodeParser()
        parsed = parser.feed('{"role":"assistant","content":""}')
        assert parsed.events == []

    def test_assistant_string_content_with_tool_call_renders_both(self):
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"role":"assistant","content":"short answer",'
            '"tool_calls":[{"type":"function","id":"x",'
            '"function":{"name":"noop","arguments":"{}"}}]}'
        )
        assert [e.kind for e in parsed.events] == ["text", "tool_use"]

    def test_tool_result_multi_part_content_renders_all_text_parts(self):
        """Tool results with multiple text parts (e.g. <system>...</system> +
        actual stdout) must render all parts, not just the first."""
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"role":"tool","content":['
            '{"type":"text","text":"<system>Command executed successfully.</system>"},'
            '{"type":"text","text":"Hello, World!\\r\\n"}'
            '],"tool_call_id":"call-2"}'
        )
        assert len(parsed.events) == 2
        assert (
            parsed.events[0].payload["output"] == "<system>Command executed successfully.</system>"
        )
        assert parsed.events[1].payload["output"] == "Hello, World!"

    def test_tool_result_empty_list_falls_back_to_ok(self):
        parser = _KimiCodeParser()
        parsed = parser.feed('{"role":"tool","content":[],"tool_call_id":"x"}')
        assert len(parsed.events) == 1
        assert parsed.events[0].payload["output"] == "ok"

    def test_no_thinking_assistant_emits_tool_calls_only(self):
        """`--no-thinking` emits assistant events with empty content + tool_calls.
        Parser should render the tool call, no think/text events."""
        parser = _KimiCodeParser()
        parsed = parser.feed(
            json.dumps(
                {
                    "role": "assistant",
                    "content": [],
                    "tool_calls": [
                        {
                            "type": "function",
                            "id": "x",
                            "function": {
                                "name": "WriteFile",
                                "arguments": '{"path": "helloworld.py"}',
                            },
                        }
                    ],
                }
            )
        )
        assert [e.kind for e in parsed.events] == ["tool_use"]
        assert parsed.events[0].payload["tool"] == "WriteFile"

    def test_session_resume_hint_becomes_session_change(self):
        """The trailing `role="meta"` event carries the real session ID (with its
        "session_" prefix) that `--session` must be given verbatim to resume —
        confirmed live: passing the prefixed ID back on a follow-up turn correctly
        recalled prior-turn context."""
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"role":"meta","type":"session.resume_hint",'
            '"session_id":"session_2b9bd712-cc0f-4d85-8b4f-6fea27c83c3b",'
            '"command":"kimi -r session_2b9bd712-cc0f-4d85-8b4f-6fea27c83c3b",'
            '"content":"To resume this session: kimi -r '
            'session_2b9bd712-cc0f-4d85-8b4f-6fea27c83c3b"}'
        )
        assert parsed.events == []
        assert parsed.session_change is not None
        assert parsed.session_change.session_id == "session_2b9bd712-cc0f-4d85-8b4f-6fea27c83c3b"

    def test_malformed_json_is_skipped(self):
        parser = _KimiCodeParser()
        assert parser.feed("not-json").events == []
        assert parser.feed("").events == []

    # ── legacy wrapped shape (not observed live; regression-only) ───────────

    def test_legacy_wrapped_metadata_event_is_skipped(self):
        parser = _KimiCodeParser()
        parsed = parser.feed('{"type":"metadata","protocol_version":"1.0","created_at":12345}')
        assert parsed.events == []

    def test_legacy_wrapped_user_message_is_skipped(self):
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"type":"context.append_message","message":{"role":"user",'
            '"content":[{"type":"text","text":"hi"}]}}'
        )
        assert parsed.events == []

    def test_legacy_wrapped_assistant_text_becomes_text_event(self):
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"type":"context.append_message","message":{"role":"assistant",'
            '"content":[{"type":"text","text":"Hello there"}]}}'
        )
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "Hello there"

    def test_legacy_wrapped_assistant_think_becomes_thinking_event(self):
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"type":"context.append_message","message":{"role":"assistant",'
            '"content":[{"type":"think","think":"pondering..."}]}}'
        )
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "thinking"

    def test_legacy_wrapped_assistant_tool_call_becomes_tool_use_event(self):
        args = json.dumps({"agent": "kimi"})
        parser = _KimiCodeParser()
        evt = json.dumps(
            {
                "type": "context.append_message",
                "message": {
                    "role": "assistant",
                    "content": [],
                    "toolCalls": [
                        {
                            "type": "function",
                            "id": "call-1",
                            "function": {"name": "get_inbox", "arguments": args},
                        }
                    ],
                },
            }
        )
        parsed = parser.feed(evt)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "tool_use"
        assert parsed.events[0].call_id == "call-1"

    def test_legacy_wrapped_tool_result_becomes_tool_result_event(self):
        parser = _KimiCodeParser()
        parsed = parser.feed(
            '{"type":"context.append_message","message":{"role":"tool",'
            '"content":[{"type":"text","text":"done"}],"toolCallId":"call-1"}}'
        )
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "tool_result"
        assert parsed.events[0].payload["output"] == "done"
        assert parsed.events[0].call_id == "call-1"


class TestParseOpencodeStdoutLine:
    """Tests for _parse_opencode_stdout_line: the canonical OpenCode `run --format
    json` adapter. Fixtures are taken from a live OpenCode CLI 1.18.5 probe
    (2026-07-29), including a `reasoning` sample captured with `--thinking`; see
    the module docstring on _parse_opencode_stdout_line for details.
    """

    def test_text_event(self):
        line = json.dumps(
            {
                "type": "text",
                "sessionID": "ses_1",
                "part": {"type": "text", "text": "events.jsonl\nstderr.log\n\ndone"},
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"

    def test_session_id_is_captured_from_any_event(self):
        session_ref = [None]
        line = json.dumps({"type": "step_start", "sessionID": "ses_053255", "part": {}})
        _parse_opencode_stdout_line(line, session_ref)
        assert session_ref[0] == "ses_053255"

    def test_reasoning_event_becomes_thinking(self):
        line = json.dumps(
            {
                "type": "reasoning",
                "sessionID": "ses_1",
                "part": {"type": "reasoning", "text": "17 * 24 = 408"},
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events[0].kind == "thinking"
        assert parsed.events[0].content == "17 * 24 = 408"

    def test_step_start_produces_no_event(self):
        line = json.dumps(
            {"type": "step_start", "sessionID": "ses_1", "part": {"type": "step-start"}}
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events == []
        assert parsed.usage is None

    def test_tool_use_non_terminal_status_becomes_tool_use_event(self):
        line = json.dumps(
            {
                "type": "tool_use",
                "sessionID": "ses_1",
                "part": {
                    "type": "tool",
                    "tool": "read",
                    "callID": "call_1",
                    "state": {"status": "running", "input": {"filePath": "x.txt"}},
                },
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events[0].kind == "tool_use"
        assert parsed.events[0].call_id == "call_1"

    def test_tool_use_completed_status_becomes_tool_result_only(self):
        # A fast tool call can jump straight to "completed" with no separate
        # "running" line (confirmed live); this must not fabricate a tool_use
        # that was never independently observed.
        line = json.dumps(
            {
                "type": "tool_use",
                "sessionID": "ses_1",
                "part": {
                    "type": "tool",
                    "tool": "read",
                    "callID": "call_2",
                    "state": {"status": "completed", "output": "<path>x.txt</path>"},
                },
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "tool_result"
        assert parsed.events[0].call_id == "call_2"
        assert parsed.events[0].payload["is_error"] is False

    def test_tool_use_error_status_marks_tool_result_as_error(self):
        line = json.dumps(
            {
                "type": "tool_use",
                "sessionID": "ses_1",
                "part": {
                    "type": "tool",
                    "tool": "bash",
                    "callID": "call_3",
                    "state": {"status": "error", "output": "permission denied"},
                },
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events[0].payload["is_error"] is True

    def test_step_finish_becomes_measured_context_sample(self):
        line = json.dumps(
            {
                "type": "step_finish",
                "sessionID": "ses_1",
                "part": {
                    "type": "step-finish",
                    "reason": "stop",
                    "tokens": {
                        "total": 12537,
                        "input": 217,
                        "output": 10,
                        "reasoning": 22,
                        "cache": {"write": 0, "read": 12288},
                    },
                    "cost": 0,
                },
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events == []
        assert parsed.usage is not None
        assert parsed.usage.status == "measured"
        assert parsed.usage.basis == "provider_context"
        assert parsed.usage.context_tokens == 12515  # total - reasoning
        assert parsed.usage.breakdown["cache_read_tokens"] == 12288

    def test_second_step_finish_would_replace_not_accumulate(self):
        # The parser is per-line/stateless by design: each step_finish stands on
        # its own, so the caller naturally uses only the latest sample rather
        # than summing — there is nothing here that could accumulate.
        first = json.dumps(
            {
                "type": "step_finish",
                "part": {"tokens": {"total": 100, "input": 90, "output": 10, "reasoning": 0}},
            }
        )
        second = json.dumps(
            {
                "type": "step_finish",
                "part": {"tokens": {"total": 12537, "input": 217, "output": 10, "reasoning": 22}},
            }
        )
        first_parsed = _parse_opencode_stdout_line(first, [None])
        second_parsed = _parse_opencode_stdout_line(second, [None])
        assert first_parsed.usage.context_tokens == 100
        assert second_parsed.usage.context_tokens == 12515

    def test_error_event(self):
        line = json.dumps(
            {
                "type": "error",
                "sessionID": "ses_1",
                "error": {
                    "name": "ProviderAuthError",
                    "data": {"message": "invalid api key", "ref": "abc123"},
                },
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events[0].kind == "error"
        assert "invalid api key" in parsed.events[0].content
        assert "abc123" in parsed.events[0].content

    def test_malformed_json_yields_no_events(self):
        parsed = _parse_opencode_stdout_line("not json {{{", [None])
        assert parsed.events == []
        assert parsed.usage is None

    def test_unknown_event_type_is_ignored(self):
        line = json.dumps({"type": "message_start", "sessionID": "ses_1"})
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events == []


class TestAgentPingCmdOpencode:
    """Tests for _agent_ping_cmd with opencode runner."""

    @pytest.fixture(autouse=True)
    def setup_session(self, tmp_path):
        """Set up a temporary session with an opencode agent."""
        self.tmp_path = tmp_path
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.agents_dir = self.session_dir / "agents"
        self.agents_dir.mkdir()
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir()

        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "opencode-dev": {"runner": "opencode", "model": "ollama/qwen2.5-coder:7b"},
                "opencode-qa": {"runner": "opencode"},
            },
        }
        session_file = self.session_dir / "session.json"
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        self.session = Session(session_data)

        with patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir), patch(
            "agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir
        ), patch("agentweave.session.Session.load", return_value=self.session):
            yield

    def test_opencode_basic_no_session_no_model(self):
        """Basic dispatch without session or model.

        On first run (no captured real sessionID yet), opencode is invoked
        with --title so it creates a new session. The real sessionID
        (ses_...) is then captured from the JSON output and persisted for
        the next run, which will use --session instead. --dir pins the
        working directory to the project root so opencode finds the
        mcp.agentweave block in opencode.json.
        """
        cmd = _agent_ping_cmd("opencode-qa", "do the task")
        assert cmd[0] == "opencode"
        assert cmd[1] == "run"
        assert cmd[2] == "--title"
        assert cmd[3] == "agentweave-opencode-qa"
        assert cmd[4] == "--dir"
        assert cmd[6] == "--format"
        assert cmd[7] == "json"
        assert cmd[8] == "do the task"

    def test_opencode_with_model(self):
        """Dispatch with model flag when agent config has a model."""
        cmd = _agent_ping_cmd("opencode-dev", "do the task")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "ollama/qwen2.5-coder:7b"

    def test_opencode_with_context_file(self):
        """Role file injected when present, with absolute path so opencode
        can find it from any cwd (including UNC paths like \\wsl.localhost\\...)."""
        context_file = self.context_dir / "opencode-dev.md"
        context_file.write_text("# Context")
        cmd = _agent_ping_cmd("opencode-dev", "do the task")
        assert "--file" in cmd
        idx = cmd.index("--file")
        file_arg = Path(cmd[idx + 1])
        # Path must be absolute so it resolves from any cwd the opencode
        # subprocess inherits (notably UNC paths under WSL where Windows
        # CMD cannot chdir).
        assert file_arg.is_absolute()
        assert file_arg.name == "opencode-dev.md"
        # The resolved file must actually point at the context file we wrote.
        assert file_arg.resolve() == context_file.resolve()

    def test_opencode_context_path_works_under_unc_cwd(self, tmp_path, monkeypatch):
        r"""Regression: when the watchdog is launched from a UNC path
        (e.g. \\wsl.localhost\Ubuntu\... under WSL), Windows CMD cannot
        chdir there, so the opencode subprocess inherits a bad cwd and
        cannot resolve relative paths. The --file arg must therefore be
        absolute, not relative to AGENT_CONTEXT_DIR."""
        from agentweave import watchdog as wd
        from agentweave.session import Session

        # Simulate a UNC cwd
        monkeypatch.chdir(tmp_path)

        # Build a separate test project on disk; resolve the context dir
        # against a real absolute path.
        project_root = tmp_path / "project"
        project_root.mkdir()
        ctx_dir = project_root / ".agentweave" / "context"
        ctx_dir.mkdir(parents=True)
        (ctx_dir / "opencode-unc.md").write_text("# Context")

        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "opencode-unc": {"runner": "opencode", "model": "minimax/M3"},
            },
        }
        session = Session(session_data)
        with patch(
            "agentweave.watchdog.AGENTS_DIR", project_root / ".agentweave" / "agents"
        ), patch("agentweave.watchdog.AGENT_CONTEXT_DIR", ctx_dir), patch(
            "agentweave.session.Session.load", return_value=session
        ):
            cmd = wd._agent_ping_cmd("opencode-unc", "do the task")

        idx = cmd.index("--file")
        file_arg = Path(cmd[idx + 1])
        assert file_arg.is_absolute(), f"opencode --file must be absolute, got relative: {file_arg}"
        # Must point to the actual file regardless of cwd
        assert file_arg.exists()

    def test_opencode_without_context_file(self):
        """No --file flag when context file does not exist."""
        cmd = _agent_ping_cmd("opencode-qa", "do the task")
        assert "--file" not in cmd

    def test_opencode_uses_session_flag_for_real_session_id(self):
        """A real opencode sessionID (ses_...) is passed via --session to
        continue the previous conversation."""
        real_sid = "ses_13e16807bffe1TAS5GVCeHxZ0z"
        cmd = _agent_ping_cmd("opencode-dev", "do the task", session_id=real_sid)
        assert "--session" in cmd
        assert "--title" not in cmd
        idx = cmd.index("--session")
        assert cmd[idx + 1] == real_sid

    def test_opencode_rejects_legacy_stable_id_as_session(self):
        """Legacy stable IDs like 'agentweave-opencode' (saved before we
        captured real sessionIDs) must NOT be passed to --session — that
        would cause 'Session not found'. They should be silently ignored
        and replaced with --title instead."""
        cmd = _agent_ping_cmd("opencode-dev", "do the task", session_id="agentweave-opencode")
        assert "--title" in cmd
        assert "--session" not in cmd
        idx = cmd.index("--title")
        assert cmd[idx + 1] == "agentweave-opencode-dev"

    def test_opencode_does_not_pre_save_title_as_session_id(self):
        """First run uses --title; the real sessionID will be saved by
        _run_cmd at exit from the JSON output. We must NOT pre-save the
        title into the agent session file because that's not a valid
        opencode sessionID and would cause the next run to fail."""
        session_file = self.agents_dir / "opencode-qa-session.json"
        assert not session_file.exists()
        _agent_ping_cmd("opencode-qa", "do the task")
        # The pre-save from _agent_ping_cmd has been removed; the real
        # sessionID write happens in _run_cmd after the opencode process
        # has emitted at least one JSON event with the real ses_ ID.
        assert not session_file.exists()

    def test_opencode_pins_dir_to_project_root(self):
        """opencode must be invoked with --dir pointing at the project
        root so it can find opencode.json (which holds the mcp.agentweave
        block). Without this, when the watchdog runs from a UNC cwd,
        opencode falls back to C:\\Windows and never loads the project
        config, leaving MCP tools unavailable to the agent."""
        from pathlib import Path as _Path

        cmd = _agent_ping_cmd("opencode-qa", "do the task")
        assert "--dir" in cmd
        idx = cmd.index("--dir")
        dir_arg = _Path(cmd[idx + 1])
        assert dir_arg.is_absolute()
        # The dir must be the parent of .agentweave/context
        # (i.e. the project root that contains opencode.json)
        expected_root = self.context_dir.resolve().parent.parent
        assert dir_arg == expected_root


class TestOpencodeEnvForwarding:
    """Tests for env-var forwarding from session.json to the opencode subprocess.

    Mirrors the proxy test at tests/test_diagnostics.py:90-127, but for the
    opencode runner. Verifies the generic {name: name} resolution pass added
    to _run_cmd in watchdog.py.
    """

    def test_opencode_resolves_name_to_name_env_var(self, tmp_path, monkeypatch):
        """MINIMAX_API_KEY declared in env_vars resolves to its os.environ value."""
        from agentweave import watchdog as wd
        from agentweave.session import Session

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key-value")
        session = Session.create(name="Test", agents=["opencode-dev"])
        session.set_runner_config(
            "opencode-dev",
            "opencode",
            {
                "model": "minimax/M3",
                "env_vars": {"MINIMAX_API_KEY": "MINIMAX_API_KEY"},
            },
        )
        session.save()
        monkeypatch.setattr("agentweave.diagnostics.shutil.which", lambda _cli: "/usr/bin/opencode")
        monkeypatch.setattr("agentweave.locking.acquire_lock", lambda *_a, **_k: True)
        monkeypatch.setattr("agentweave.locking.release_lock", lambda *_a, **_k: None)
        popen = MagicMock()
        # Popen returns an object with .communicate() / .wait() that doesn't hang
        popen.return_value.communicate.return_value = ("", "")
        popen.return_value.wait.return_value = 0
        popen.return_value.stdout = iter([])
        popen.return_value.stderr = iter([])
        popen.return_value.returncode = 0
        monkeypatch.setattr(wd.subprocess, "Popen", popen)
        transport = MagicMock()

        _run_agent_subprocess(
            "opencode-dev",
            ["opencode", "run", "do the task"],
            "subject",
            transport,
            False,
            {"MINIMAX_API_KEY": "MINIMAX_API_KEY"},
        )

        popen.assert_called()
        _, kwargs = popen.call_args
        env = kwargs.get("env")
        assert env is not None
        assert env["MINIMAX_API_KEY"] == "test-key-value"

    def test_opencode_warns_and_launches_when_env_var_unset(self, tmp_path, monkeypatch, caplog):
        """Missing env var is a warning, not a blocker, for opencode agents."""
        from agentweave import watchdog as wd
        from agentweave.session import Session

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        session = Session.create(name="Test", agents=["opencode-dev"])
        session.set_runner_config(
            "opencode-dev",
            "opencode",
            {
                "model": "minimax/M3",
                "env_vars": {"MINIMAX_API_KEY": "MINIMAX_API_KEY"},
            },
        )
        session.save()
        monkeypatch.setattr("agentweave.diagnostics.shutil.which", lambda _cli: "/usr/bin/opencode")
        monkeypatch.setattr("agentweave.locking.acquire_lock", lambda *_a, **_k: True)
        monkeypatch.setattr("agentweave.locking.release_lock", lambda *_a, **_k: None)
        popen = MagicMock()
        popen.return_value.communicate.return_value = ("", "")
        popen.return_value.wait.return_value = 0
        popen.return_value.stdout = iter([])
        popen.return_value.stderr = iter([])
        popen.return_value.returncode = 0
        monkeypatch.setattr(wd.subprocess, "Popen", popen)
        transport = MagicMock()

        with caplog.at_level("WARNING", logger="agentweave.watchdog"):
            _run_agent_subprocess(
                "opencode-dev",
                ["opencode", "run", "do the task"],
                "subject",
                transport,
                False,
                {"MINIMAX_API_KEY": "MINIMAX_API_KEY"},
            )

        # opencode does NOT block on missing keys (unlike claude_proxy)
        popen.assert_called()
        # a [WARN] was emitted via logger.warning (Q1: print -> logger migration)
        assert any(
            "MINIMAX_API_KEY" in rec.getMessage() and "not set" in rec.getMessage()
            for rec in caplog.records
        )

    def test_opencode_env_vars_entry_skips_name_to_name_resolution_for_literal_values(
        self, tmp_path, monkeypatch
    ):
        """Literal-value entries (key != value) are passed through unchanged."""
        from agentweave import watchdog as wd
        from agentweave.session import Session

        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("LITERAL_VAR", "should-not-be-overridden")
        session = Session.create(name="Test", agents=["opencode-dev"])
        # claude_proxy-style: a literal value mapping (key != value) should
        # NOT be touched by the generic resolution pass.
        session.set_runner_config(
            "opencode-dev",
            "opencode",
            {
                "model": "minimax/M3",
                "env_vars": {"LITERAL_VAR": "literal-value"},
            },
        )
        session.save()
        monkeypatch.setattr("agentweave.diagnostics.shutil.which", lambda _cli: "/usr/bin/opencode")
        monkeypatch.setattr("agentweave.locking.acquire_lock", lambda *_a, **_k: True)
        monkeypatch.setattr("agentweave.locking.release_lock", lambda *_a, **_k: None)
        popen = MagicMock()
        popen.return_value.communicate.return_value = ("", "")
        popen.return_value.wait.return_value = 0
        popen.return_value.stdout = iter([])
        popen.return_value.stderr = iter([])
        popen.return_value.returncode = 0
        monkeypatch.setattr(wd.subprocess, "Popen", popen)
        transport = MagicMock()

        _run_agent_subprocess(
            "opencode-dev",
            ["opencode", "run", "do the task"],
            "subject",
            transport,
            False,
            {"LITERAL_VAR": "literal-value"},
        )

        popen.assert_called()
        _, kwargs = popen.call_args
        env = kwargs.get("env")
        assert env is not None
        # Literal value passes through; not replaced by os.environ value
        assert env["LITERAL_VAR"] == "literal-value"


class TestAgentPingCmdCodex:
    """Tests for _agent_ping_cmd with codex runner."""

    @pytest.fixture(autouse=True)
    def setup_session(self, tmp_path):
        """Set up a temporary session with a codex agent."""
        self.tmp_path = tmp_path
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.agents_dir = self.session_dir / "agents"
        self.agents_dir.mkdir()
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir()
        self.shared_dir = self.session_dir / "shared"
        self.shared_dir.mkdir()
        self.context_usage_dir = self.shared_dir / "context_usage"
        self.context_usage_dir.mkdir()

        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "codex-dev": {"runner": "codex", "model": "gpt-5.5"},
                "codex-qa": {"runner": "codex"},
                "codex-mcp": {"runner": "codex_mcp", "model": "gpt-5.5", "yolo": True},
                "codex-memory-off": {"runner": "codex", "runner_options": {"memory": False}},
            },
        }
        session_file = self.session_dir / "session.json"
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        self.session = Session(session_data)

        with patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir), patch(
            "agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir
        ), patch("agentweave.watchdog.CONTEXT_USAGE_DIR", self.context_usage_dir), patch(
            "agentweave.session.Session.load", return_value=self.session
        ):
            yield

    def test_codex_first_ping_no_session(self):
        """First ping without session starts fresh."""
        cmd = _agent_ping_cmd("codex-qa", "do the task")
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert cmd[2] == "--json"
        assert cmd[3] == "--skip-git-repo-check"
        # Default (no yolo): use the modern --sandbox workspace-write flag.
        # The deprecated --full-auto flag is no longer used.
        assert "--sandbox" in cmd
        idx = cmd.index("--sandbox")
        assert cmd[idx + 1] == "workspace-write"
        assert "--full-auto" not in cmd
        assert cmd[-1] == "do the task"
        assert "resume" not in cmd

    def test_codex_resume_with_session(self):
        """Resume when session_id is provided."""
        cmd = _agent_ping_cmd("codex-qa", "do the task", session_id="thread-abc-123")
        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "resume" in cmd
        idx = cmd.index("resume")
        assert cmd[idx + 1] == "thread-abc-123"
        assert cmd[idx + 2] == "--json"
        assert cmd[idx + 3] == "--skip-git-repo-check"

    def test_codex_with_context_file(self):
        """Context file injected via -c model_instructions_file."""
        context_file = self.context_dir / "codex-dev.md"
        context_file.write_text("# Context")
        cmd = _agent_ping_cmd("codex-dev", "do the task")
        assert "-c" in cmd
        idx = cmd.index("-c")
        assert "model_instructions_file=" in cmd[idx + 1]
        assert str(context_file) in cmd[idx + 1]

    def test_codex_without_context_file(self):
        """No -c flag when context file does not exist."""
        cmd = _agent_ping_cmd("codex-qa", "do the task")
        flags = [c for c in cmd if c.startswith("-c")]
        assert len(flags) == 0

    def test_codex_with_model(self):
        """Model flag appended when agent config has a model."""
        cmd = _agent_ping_cmd("codex-dev", "do the task")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "gpt-5.5"

    def test_codex_without_model(self):
        """No --model flag when model is not configured."""
        cmd = _agent_ping_cmd("codex-qa", "do the task")
        assert "--model" not in cmd

    def test_codex_memory_disabled(self):
        """Memory disabled flag when runner_options.memory is false."""
        cmd = _agent_ping_cmd("codex-memory-off", "do the task")
        assert "-c" in cmd
        # Should have at least one -c for memory_mode
        memory_flags = [c for c in cmd if "memory_mode=disabled" in c]
        assert len(memory_flags) == 1

    def test_codex_memory_default(self):
        """No memory flag when runner_options is absent or memory is true."""
        cmd = _agent_ping_cmd("codex-qa", "do the task")
        memory_flags = [c for c in cmd if "memory_mode" in c]
        assert len(memory_flags) == 0

    def test_codex_yolo_adds_bypass_flag(self):
        """Adds --dangerously-bypass-approvals-and-sandbox when yolo=true."""
        # codex-dev has yolo=False by default in the fixture
        cmd = _agent_ping_cmd("codex-dev", "do the task")
        assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
        assert "--full-auto" not in cmd
        # Default: modern --sandbox workspace-write
        idx = cmd.index("--sandbox")
        assert cmd[idx + 1] == "workspace-write"

        # Patch session to add yolo=True
        from agentweave.session import Session

        yolo_session = Session(
            {
                "id": "test-session",
                "name": "Test",
                "mode": "hierarchical",
                "principal": "claude",
                "agents": {
                    "codex-dev": {"runner": "codex", "yolo": True},
                },
            }
        )
        with patch("agentweave.session.Session.load", return_value=yolo_session):
            cmd = _agent_ping_cmd("codex-dev", "do the task")
            assert "--dangerously-bypass-approvals-and-sandbox" in cmd
            assert "--full-auto" not in cmd

    def test_codex_working_dir_is_project_root_side_directory(self):
        """Headless Codex should run from the repository root, not .agentweave."""
        assert _codex_working_dir() == self.tmp_path
        assert ".agentweave" not in _codex_working_dir().parts

    def test_codex_mcp_ping_command_starts_server(self):
        """codex_mcp runner starts the Codex MCP server."""
        cmd = _agent_ping_cmd("codex-mcp", "do the task")
        assert cmd == ["codex", "mcp-server"]

    def test_codex_mcp_initial_tool_call_includes_context(self):
        """Initial Codex MCP call includes developer instructions from context."""
        context_file = self.context_dir / "codex-mcp.md"
        context_file.write_text("AGENTWEAVE_CONTEXT_MARKER")

        tool, args = _build_codex_mcp_tool_call("codex-mcp", "do the task")

        assert tool == "codex"
        assert args["prompt"] == "do the task"
        assert args["cwd"] == str(self.tmp_path)
        assert args["model"] == "gpt-5.5"
        assert args["approval-policy"] == "never"
        assert args["sandbox"] == "danger-full-access"
        assert args["developer-instructions"] == "AGENTWEAVE_CONTEXT_MARKER"

    def test_codex_mcp_reply_tool_call_uses_thread_id_only(self):
        """Follow-up Codex MCP calls continue an existing thread."""
        tool, args = _build_codex_mcp_tool_call(
            "codex-mcp",
            "continue",
            thread_id="thread-123",
        )

        assert tool == "codex-reply"
        assert args == {"threadId": "thread-123", "prompt": "continue"}

    def test_extract_codex_mcp_structured_result(self):
        """Extracts threadId and content from MCP structuredContent."""
        thread_id, content = _extract_codex_mcp_result(
            {"structuredContent": {"threadId": "thread-123", "content": "Done"}}
        )

        assert thread_id == "thread-123"
        assert content == "Done"

    def test_codex_mcp_stale_thread_retries_as_new_thread(self):
        """A stale Codex MCP thread id should fall back to a fresh thread."""

        class FakeClient:
            def __init__(self):
                self.calls = []

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "codex-reply":
                    raise RuntimeError("Codex MCP error: Session not found for thread_id: old")
                return {
                    "structuredContent": {
                        "threadId": "new-thread",
                        "content": "Started fresh",
                    }
                }

        class FakeTransport:
            def __init__(self):
                self.outputs = []

            def post_agent_output(self, agent, content, session_id=None):
                self.outputs.append((agent, content, session_id))

        fake_client = FakeClient()
        fake_transport = FakeTransport()

        with patch("agentweave.watchdog._get_codex_mcp_client", return_value=fake_client):
            thread_id, output_count = _run_codex_mcp_turn(
                "codex-mcp",
                "continue",
                "old-thread",
                fake_transport,
                True,
            )

        assert thread_id == "new-thread"
        assert output_count == 1
        assert fake_client.calls[0][0] == "codex-reply"
        assert fake_client.calls[1][0] == "codex"
        assert fake_transport.outputs == [("codex-mcp", "Started fresh", "new-thread")]

    def test_codex_mcp_stale_thread_content_retries_as_new_thread(self):
        """A stale-thread response returned as normal content should also retry."""

        class FakeClient:
            def __init__(self):
                self.calls = []

            def call_tool(self, name, arguments):
                self.calls.append((name, arguments))
                if name == "codex-reply":
                    return {
                        "structuredContent": {
                            "threadId": None,
                            "content": "Session not found for thread_id: old",
                        }
                    }
                return {
                    "structuredContent": {
                        "threadId": "new-thread",
                        "content": "Started fresh",
                    }
                }

        class FakeTransport:
            def __init__(self):
                self.outputs = []

            def post_agent_output(self, agent, content, session_id=None):
                self.outputs.append((agent, content, session_id))

        fake_client = FakeClient()
        fake_transport = FakeTransport()

        with patch("agentweave.watchdog._get_codex_mcp_client", return_value=fake_client):
            thread_id, output_count = _run_codex_mcp_turn(
                "codex-mcp",
                "continue",
                "old-thread",
                fake_transport,
                True,
            )

        assert thread_id == "new-thread"
        assert output_count == 1
        assert fake_client.calls[0][0] == "codex-reply"
        assert fake_client.calls[1][0] == "codex"
        assert fake_transport.outputs == [("codex-mcp", "Started fresh", "new-thread")]


class TestExtractJsonlSessionId:
    """Tests for data-driven JSONL session ID extraction."""

    def test_extracts_thread_id_for_codex(self):
        """Reads thread_id from thread.started for codex runner."""
        line = json.dumps({"type": "thread.started", "thread_id": "abc-123"})
        result = _extract_jsonl_session_id(line, "codex")
        assert result == "abc-123"

    def test_returns_none_for_wrong_event_type(self):
        """Ignores events that don't match session_event_type."""
        line = json.dumps({"type": "turn.completed", "thread_id": "abc-123"})
        result = _extract_jsonl_session_id(line, "codex")
        assert result is None

    def test_extracts_session_id_for_claude(self):
        """Reads session_id from any JSONL for claude runner."""
        line = json.dumps({"type": "assistant", "session_id": "sess-456"})
        result = _extract_jsonl_session_id(line, "claude")
        assert result == "sess-456"

    def test_returns_none_for_non_jsonl_runner(self):
        """Returns None for runners without jsonl session_source."""
        line = json.dumps({"type": "thread.started", "thread_id": "abc-123"})
        result = _extract_jsonl_session_id(line, "kimi")
        assert result is None

    def test_returns_none_for_invalid_json(self):
        """Returns None for invalid JSON lines."""
        result = _extract_jsonl_session_id("not json", "codex")
        assert result is None


class TestParseCodexStreamLine:
    """Tests for _parse_codex_stream_line: the canonical Codex `exec --json` adapter.

    Fixtures for agent_message/command_execution/file_change are taken from a
    live Codex CLI 0.145.0 probe (read-only and workspace-write, 2026-07-29);
    see the module docstring on _parse_codex_stream_line for details.
    """

    def test_parses_turn_completed_usage_as_estimated_cumulative(self):
        line = json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 200,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 500,
                    "reasoning_output_tokens": 50,
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events == []
        assert parsed.usage is not None
        assert parsed.usage.status == "estimated"
        assert parsed.usage.basis == "cumulative_delta"
        assert parsed.usage.context_tokens == 1500  # input + output, reasoning excluded
        assert parsed.usage.breakdown["cached_input_tokens"] == 200

    def test_turn_completed_without_usage_yields_no_sample(self):
        parsed = _parse_codex_stream_line(json.dumps({"type": "turn.completed"}))
        assert parsed.usage is None

    def test_parses_agent_message(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "Hello world"},
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "Hello world"
        assert parsed.usage is None

    def test_agent_message_started_produces_no_event(self):
        # agent_message only ever appears fully-formed at item.completed.
        line = json.dumps(
            {"type": "item.started", "item": {"id": "item_0", "type": "agent_message"}}
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events == []

    def test_mcp_tool_call_started_and_completed_share_call_id(self):
        started = json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "server": "agentweave",
                    "tool": "get_inbox",
                    "arguments": {"agent": "codex"},
                },
            }
        )
        completed = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "server": "agentweave",
                    "tool": "get_inbox",
                },
            }
        )
        use_parsed = _parse_codex_stream_line(started)
        result_parsed = _parse_codex_stream_line(completed)
        assert use_parsed.events[0].kind == "tool_use"
        assert "get_inbox" in use_parsed.events[0].payload["tool"]
        assert use_parsed.events[0].call_id == result_parsed.events[0].call_id == "item_0"
        assert result_parsed.events[0].kind == "tool_result"
        assert result_parsed.events[0].payload["is_error"] is False

    def test_mcp_tool_call_error_marks_tool_result_as_error(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "get_inbox",
                    "error": {"message": "user cancelled"},
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "tool_result"
        assert parsed.events[0].payload["is_error"] is True
        assert "user cancelled" in parsed.events[0].content

    def test_command_execution_started_becomes_tool_use(self):
        line = json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "Get-ChildItem",
                    "aggregated_output": "",
                    "exit_code": None,
                    "status": "in_progress",
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "tool_use"
        assert parsed.events[0].call_id == "item_1"

    def test_command_execution_completed_becomes_paired_tool_result(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "command_execution",
                    "command": "Get-ChildItem",
                    "aggregated_output": "file1\nfile2",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "tool_result"
        assert parsed.events[0].call_id == "item_1"
        assert parsed.events[0].payload["is_error"] is False
        assert "file1" in parsed.events[0].payload["output"]

    def test_command_execution_nonzero_exit_is_error(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "command_execution",
                    "command": "false",
                    "aggregated_output": "",
                    "exit_code": 1,
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].payload["is_error"] is True

    def test_file_change_started_becomes_tool_use_with_changes_summary(self):
        line = json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "item_1",
                    "type": "file_change",
                    "changes": [{"path": "C:\\probe.txt", "kind": "add"}],
                    "status": "in_progress",
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "tool_use"
        assert "add" in parsed.events[0].content
        assert "probe.txt" in parsed.events[0].content

    def test_file_change_failed_completion_is_error(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "file_change",
                    "changes": [{"path": "C:\\probe.txt", "kind": "add"}],
                    "status": "failed",
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "tool_result"
        assert parsed.events[0].payload["is_error"] is True

    def test_file_change_completed_success_is_not_error(self):
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "file_change",
                    "changes": [{"path": "C:\\probe.txt", "kind": "add"}],
                    "status": "completed",
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].payload["is_error"] is False

    def test_reasoning_completed_becomes_thinking_event(self):
        # Best-effort mapping: not observed in the live probe (see module docstring).
        line = json.dumps(
            {"type": "item.completed", "item": {"id": "item_5", "type": "reasoning", "text": "hmm"}}
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "thinking"
        assert parsed.events[0].content == "hmm"

    def test_reasoning_started_produces_no_event(self):
        line = json.dumps({"type": "item.started", "item": {"id": "item_5", "type": "reasoning"}})
        parsed = _parse_codex_stream_line(line)
        assert parsed.events == []

    def test_web_search_started_and_completed_are_paired(self):
        # Best-effort mapping: not observed in the live probe (see module docstring).
        started = json.dumps(
            {
                "type": "item.started",
                "item": {"id": "item_6", "type": "web_search", "query": "codex cli changelog"},
            }
        )
        completed = json.dumps(
            {"type": "item.completed", "item": {"id": "item_6", "type": "web_search"}}
        )
        use_parsed = _parse_codex_stream_line(started)
        result_parsed = _parse_codex_stream_line(completed)
        assert use_parsed.events[0].kind == "tool_use"
        assert use_parsed.events[0].call_id == result_parsed.events[0].call_id == "item_6"
        assert result_parsed.events[0].kind == "tool_result"

    def test_plan_update_becomes_status_event_with_plan_phase(self):
        # Best-effort mapping: not observed in the live probe (see module docstring).
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_7",
                    "type": "todo_list",
                    "items": [{"text": "write tests"}, {"text": "run suite"}],
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "status"
        assert parsed.events[0].payload["phase"] == "plan"
        assert "write tests" in parsed.events[0].content

    def test_unrecognized_item_type_becomes_bounded_diagnostic(self):
        line = json.dumps(
            {"type": "item.completed", "item": {"id": "item_9", "type": "some_future_item"}}
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "diagnostic"
        assert "some_future_item" in parsed.events[0].content

    def test_turn_failed_becomes_error_event(self):
        line = json.dumps({"type": "turn.failed", "error": {"message": "network timeout"}})
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "error"
        assert "network timeout" in parsed.events[0].content

    def test_top_level_error_becomes_error_event(self):
        line = json.dumps({"type": "error", "message": "Session not found for thread_id abc-123"})
        parsed = _parse_codex_stream_line(line)
        assert parsed.events[0].kind == "error"
        assert "Session not found for thread_id" in parsed.events[0].content

    def test_ignores_thread_and_turn_started_events(self):
        for evt in ["thread.started", "turn.started"]:
            parsed = _parse_codex_stream_line(json.dumps({"type": evt}))
            assert parsed.events == []
            assert parsed.usage is None

    def test_ignores_unknown_top_level_event_types(self):
        parsed = _parse_codex_stream_line(json.dumps({"type": "unknown.event", "data": "x"}))
        assert parsed.events == []
        assert parsed.usage is None

    def test_passes_through_non_json_as_text_event(self):
        parsed = _parse_codex_stream_line("some plain text")
        assert len(parsed.events) == 1
        assert parsed.events[0].content == "some plain text"

    def test_blank_non_json_line_yields_no_events(self):
        parsed = _parse_codex_stream_line("   ")
        assert parsed.events == []


class TestClaudeUsageSample:
    """Tests for _claude_usage_sample: additive input + cache read + cache creation."""

    def test_adds_cache_fields_once(self):
        sample = _claude_usage_sample(
            {"input_tokens": 100, "cache_read_input_tokens": 40, "cache_creation_input_tokens": 5},
            source="claude",
        )
        assert sample.context_tokens == 145
        assert sample.basis == "latest_request_input"
        assert sample.status == "measured"
        assert sample.breakdown == {
            "input_tokens": 100,
            "cache_read_tokens": 40,
            "cache_creation_tokens": 5,
        }

    def test_missing_cache_fields_default_to_zero(self):
        sample = _claude_usage_sample({"input_tokens": 50}, source="claude")
        assert sample.context_tokens == 50

    def test_missing_input_tokens_yields_no_sample(self):
        assert _claude_usage_sample({"cache_read_input_tokens": 40}, source="claude") is None


class TestClaudeToolResultText:
    """Tests for _claude_tool_result_text content-block extraction."""

    def test_string_content_passes_through(self):
        assert _claude_tool_result_text("plain output") == "plain output"

    def test_text_blocks_are_joined(self):
        content = [{"type": "text", "text": "line one"}, {"type": "text", "text": "line two"}]
        assert _claude_tool_result_text(content) == "line one\nline two"

    def test_non_text_blocks_are_skipped(self):
        content = [{"type": "image", "source": {}}, {"type": "text", "text": "kept"}]
        assert _claude_tool_result_text(content) == "kept"

    def test_unrecognized_shape_yields_empty_string(self):
        assert _claude_tool_result_text(None) == ""


class TestParseClaudeStreamLine:
    """Tests for _parse_claude_stream_line: the canonical Claude/claude_proxy adapter."""

    def test_assistant_text_becomes_text_event(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "Hello there"}]},
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "Hello there"
        assert parsed.usage is None

    def test_assistant_thinking_becomes_thinking_event(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "thinking", "thinking": "considering..."}]},
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "thinking"
        assert parsed.events[0].content == "considering..."

    def test_assistant_multiple_blocks_preserve_order(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "step one"},
                        {"type": "text", "text": "the answer"},
                    ]
                },
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert [event.kind for event in parsed.events] == ["thinking", "text"]

    def test_assistant_tool_use_block_becomes_tool_use_event(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call_1",
                            "name": "bash",
                            "input": {"command": "ls"},
                        }
                    ]
                },
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_use"
        assert event.call_id == "call_1"
        assert event.payload["tool"] == "bash"

    def test_assistant_usage_is_captured_as_context_sample(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "text", "text": "hi"}],
                    "usage": {
                        "input_tokens": 100,
                        "cache_read_input_tokens": 20,
                        "cache_creation_input_tokens": 0,
                    },
                },
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert parsed.usage is not None
        assert parsed.usage.context_tokens == 120

    def test_usage_without_displayable_content_is_not_fabricated_as_output(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [],
                    "usage": {"input_tokens": 10, "cache_read_input_tokens": 0},
                },
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert parsed.events == []
        assert parsed.usage is not None
        assert parsed.usage.context_tokens == 10

    def test_user_tool_result_becomes_tool_result_event_paired_by_call_id(self):
        use_line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "id": "call_9", "name": "bash", "input": {}}]
                },
            }
        )
        result_line = json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_9",
                            "content": "file.txt",
                            "is_error": False,
                        }
                    ]
                },
            }
        )
        use_parsed = _parse_claude_stream_line(use_line)
        result_parsed = _parse_claude_stream_line(result_line)
        assert use_parsed.events[0].call_id == result_parsed.events[0].call_id == "call_9"
        assert result_parsed.events[0].kind == "tool_result"
        assert result_parsed.events[0].payload["is_error"] is False

    def test_failed_tool_result_is_marked_is_error(self):
        line = json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call_2",
                            "content": "not found",
                            "is_error": True,
                        }
                    ]
                },
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert parsed.events[0].payload["is_error"] is True

    def test_successful_result_becomes_completed_status_event(self):
        line = json.dumps({"type": "result", "subtype": "success", "total_cost_usd": 0.0123})
        parsed = _parse_claude_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "status"
        assert parsed.events[0].payload["phase"] == "completed"
        assert "0.0123" in parsed.events[0].content

    def test_failed_result_becomes_error_event(self):
        line = json.dumps({"type": "result", "subtype": "error", "error": "rate limited"})
        parsed = _parse_claude_stream_line(line)
        assert parsed.events[0].kind == "error"
        assert "rate limited" in parsed.events[0].content

    def test_result_usage_is_not_used_as_context_sample(self):
        # Only assistant-message usage is canonical for now (see module docstring);
        # a result record's usage is not converted into a context sample.
        line = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "usage": {"input_tokens": 999},
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert parsed.usage is None

    def test_system_events_are_ignored(self):
        line = json.dumps({"type": "system", "subtype": "init"})
        parsed = _parse_claude_stream_line(line)
        assert parsed.events == []
        assert parsed.usage is None

    def test_non_json_line_becomes_text_event(self):
        parsed = _parse_claude_stream_line("some plain text")
        assert len(parsed.events) == 1
        assert parsed.events[0].content == "some plain text"

    def test_blank_non_json_line_yields_no_events(self):
        parsed = _parse_claude_stream_line("   ")
        assert parsed.events == []
        assert parsed.usage is None

    def test_run_id_is_propagated_to_events(self):
        line = json.dumps(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
        )
        parsed = _parse_claude_stream_line(line, run_id="run-42")
        assert parsed.events[0].run_id == "run-42"


class TestAgentPingCmdCopilot:
    """Tests for _agent_ping_cmd with the copilot runner."""

    @pytest.fixture(autouse=True)
    def setup_session(self, tmp_path):
        """Set up a temporary session with copilot agents."""
        self.tmp_path = tmp_path
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.agents_dir = self.session_dir / "agents"
        self.agents_dir.mkdir()
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir()

        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "copilot-dev": {"runner": "copilot", "model": "claude-opus-4.5"},
                "copilot-qa": {"runner": "copilot"},
                "copilot-yolo": {"runner": "copilot", "model": "claude-sonnet-4-5", "yolo": True},
            },
        }
        session_file = self.session_dir / "session.json"
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        self.session = Session(session_data)

        with patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir), patch(
            "agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir
        ), patch("agentweave.session.Session.load", return_value=self.session):
            yield

    def test_copilot_basic_no_session_no_model(self):
        """Basic dispatch without session or model uses --allow-all-tools by default."""
        cmd = _agent_ping_cmd("copilot-qa", "do the task")
        assert cmd[0] == "copilot"
        assert "--output-format" in cmd
        idx = cmd.index("--output-format")
        assert cmd[idx + 1] == "json"
        assert "--no-ask-user" in cmd
        assert "--allow-all-tools" in cmd
        assert "--yolo" not in cmd
        assert "--model" not in cmd
        assert "--resume" not in cmd and not any(c.startswith("--resume=") for c in cmd)
        assert cmd[-2] == "-p"
        assert cmd[-1] == "do the task"

    def test_copilot_with_model(self):
        """--model is appended when the agent config has a model, choosing
        e.g. claude-opus-4.5 or claude-sonnet-4-5 for the Copilot CLI."""
        cmd = _agent_ping_cmd("copilot-dev", "do the task")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-opus-4.5"

    def test_copilot_without_model_configured(self):
        """No --model flag when the agent config has no model set."""
        cmd = _agent_ping_cmd("copilot-qa", "do the task")
        assert "--model" not in cmd

    def test_copilot_yolo_uses_yolo_flag_not_allow_all_tools(self):
        """yolo=true swaps --allow-all-tools for the broader --yolo flag,
        while still forwarding the configured model."""
        cmd = _agent_ping_cmd("copilot-yolo", "do the task")
        assert "--yolo" in cmd
        assert "--allow-all-tools" not in cmd
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "claude-sonnet-4-5"

    def test_copilot_resume_with_session(self):
        """Resume uses the single-arg --resume=<uuid> form to avoid the
        interactive session picker."""
        cmd = _agent_ping_cmd("copilot-dev", "do the task", session_id="sess-uuid-1234")
        resume_args = [c for c in cmd if c.startswith("--resume=")]
        assert resume_args == ["--resume=sess-uuid-1234"]
        # Model flag is still present alongside resume.
        assert "--model" in cmd


class TestParseCopilotStreamLine:
    """Tests for _parse_copilot_stream_line: the canonical GitHub Copilot CLI
    `--output-format json` adapter. Fixtures are taken from a live Copilot CLI 1.0.75
    probe (2026-07-29): a plain reply, a successful tool call, and a failing tool call;
    see the module docstring on _parse_copilot_stream_line for details.
    """

    def test_assistant_message_becomes_text_event(self):
        line = json.dumps({"type": "assistant.message", "data": {"content": "hello there"}})
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "hello there"

    def test_assistant_message_empty_content_emits_nothing(self):
        line = json.dumps({"type": "assistant.message", "data": {"content": ""}})
        parsed = _parse_copilot_stream_line(line)
        assert parsed.events == []

    def test_assistant_message_tool_requests_are_not_double_rendered(self):
        """toolRequests on assistant.message are announcements, not the canonical tool_use
        source — tool.execution_start/complete (which report success/failure) are — so
        toolRequests must never produce a second tool_use event."""
        line = json.dumps(
            {
                "type": "assistant.message",
                "data": {
                    "content": "Reading the file now.",
                    "toolRequests": [
                        {
                            "toolCallId": "call_1",
                            "name": "view",
                            "arguments": {"path": "sample.txt"},
                        }
                    ],
                },
            }
        )
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"

    def test_tool_execution_start_becomes_tool_use_event(self):
        line = json.dumps(
            {
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "call_zT36faYEOU07a12VoWjJdz8P",
                    "toolName": "view",
                    "arguments": {"path": "sample.txt"},
                    "turnId": "0",
                    "model": "gpt-5-mini",
                },
            }
        )
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_use"
        assert event.call_id == "call_zT36faYEOU07a12VoWjJdz8P"
        assert event.payload["tool"] == "view"

    def test_tool_execution_complete_success_becomes_tool_result_event(self):
        line = json.dumps(
            {
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "call_zT36faYEOU07a12VoWjJdz8P",
                    "success": True,
                    "result": {"content": "1. hello from probe file\n2. "},
                },
            }
        )
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_result"
        assert event.call_id == "call_zT36faYEOU07a12VoWjJdz8P"
        assert event.payload["output"] == "1. hello from probe file\n2. "
        assert event.payload["is_error"] is False

    def test_tool_execution_complete_failure_becomes_error_tool_result_event(self):
        """Confirmed live: a failed tool.execution_complete carries success=False plus a
        structured error.message, unlike Kimi's flat print stream which has no such
        indicator at all."""
        line = json.dumps(
            {
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "call_321pnY4E9GcBig6DPLUzoyJ8",
                    "success": False,
                    "error": {"message": "Path does not exist", "code": "failure"},
                },
            }
        )
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_result"
        assert event.payload["output"] == "Path does not exist"
        assert event.payload["is_error"] is True

    def test_reasoning_with_empty_content_emits_nothing(self):
        """Confirmed live: assistant.reasoning.content was empty/opaque in every probe
        (gpt-5-mini does not expose readable reasoning by default). Only reasoningId, an
        encrypted blob, was present — which must never be copied into content."""
        line = json.dumps(
            {"type": "assistant.reasoning", "data": {"reasoningId": "opaque-blob", "content": ""}}
        )
        parsed = _parse_copilot_stream_line(line)
        assert parsed.events == []

    def test_reasoning_with_readable_content_becomes_thinking_event(self):
        line = json.dumps({"type": "assistant.reasoning", "data": {"content": "considering..."}})
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "thinking"
        assert parsed.events[0].content == "considering..."

    def test_result_success_becomes_completed_status_event(self):
        line = json.dumps(
            {
                "type": "result",
                "sessionId": "165446f2-1b83-4a73-9a99-0e0fa5dce8a5",
                "exitCode": 0,
                "usage": {"premiumRequests": 0},
            }
        )
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "status"
        assert parsed.events[0].payload["phase"] == "completed"

    def test_result_nonzero_exit_becomes_error_event(self):
        line = json.dumps({"type": "result", "exitCode": 1})
        parsed = _parse_copilot_stream_line(line)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "error"
        assert event.payload["exit_code"] == 1

    def test_session_lifecycle_events_are_skipped(self):
        for evt in (
            "session.mcp_server_status_changed",
            "session.mcp_servers_loaded",
            "session.skills_loaded",
            "session.tools_updated",
            "session.auto_mode_resolved",
            "session.usage_checkpoint",
            "user.message",
            "assistant.turn_start",
            "assistant.turn_end",
            "assistant.idle",
            "model.call_start",
            "assistant.message_start",
            "assistant.message_delta",
            "assistant.tool_call_delta",
        ):
            line = json.dumps({"type": evt, "data": {}})
            parsed = _parse_copilot_stream_line(line)
            assert parsed.events == [], f"{evt} should not produce events"

    def test_no_usage_sample_is_ever_produced(self):
        """Context/usage tracking for Copilot is OTel-only (design.md decision 4); the
        stdout adapter must never fabricate a ContextUsageSample."""
        for line in (
            json.dumps({"type": "assistant.message", "data": {"content": "hi"}}),
            json.dumps({"type": "result", "exitCode": 0, "usage": {"premiumRequests": 2}}),
        ):
            assert _parse_copilot_stream_line(line).usage is None

    def test_malformed_json_falls_back_to_text_event(self):
        parsed = _parse_copilot_stream_line("not-json")
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "not-json"

    def test_empty_line_emits_nothing(self):
        assert _parse_copilot_stream_line("").events == []

    def test_unknown_event_type_is_skipped(self):
        line = json.dumps({"type": "some.future.event", "data": {"foo": "bar"}})
        assert _parse_copilot_stream_line(line).events == []


class TestStreamAdapterConformance:
    """Cross-adapter conformance tests (task 2.13): every runner adapter must return
    only the seven canonical event kinds, degrade safely on unrecognized or malformed
    input, and keep stream events and context-usage samples strictly independent —
    neither is ever fabricated to satisfy the other.

    Covers all five runners migrated in this change: Claude, Codex, OpenCode, Copilot
    (stdout adapters), and Kimi (_KimiCodeParser). Each is wrapped in a thin lambda so
    every adapter can be driven through the same one-line-in, ParsedRunnerLine-out
    calling convention despite their differing native signatures (OpenCode threads a
    session_id_ref list; Kimi is a stateful parser instance; the rest are pure
    functions).
    """

    ADAPTERS = [
        ("claude", lambda line: _parse_claude_stream_line(line)),
        ("codex", lambda line: _parse_codex_stream_line(line)),
        ("opencode", lambda line: _parse_opencode_stdout_line(line, [None])),
        ("copilot", lambda line: _parse_copilot_stream_line(line)),
        ("kimi", lambda line: _KimiCodeParser().feed(line)),
    ]

    # Syntactically valid JSON that is not the expected object shape, plus assorted
    # malformed/edge-case text. Every adapter parses raw JSON with `.get("type", ...)`
    # right after `json.loads` — a bare scalar or array (e.g. "null", "42", "[]") parses
    # successfully but has no `.get`, so this battery guards against exactly that class
    # of crash (caught live: all five adapters raised AttributeError on these before a
    # dict-shape check was added alongside this test).
    GARBAGE_LINES = [
        "",
        "   ",
        "not-json",
        "{",
        "[]",
        "null",
        "42",
        "true",
        '"just a string"',
        "{}",
        '{"type": "some.totally.unknown.future.event", "data": {"nested": {"deep": [1, 2, 3]}}}',
        '{"role": "totally-unknown-role", "content": "x"}',
        "🎉 emoji line with no structure 🎉",
        "x" * 5000,
    ]

    @pytest.mark.parametrize("adapter_name,adapter", ADAPTERS)
    @pytest.mark.parametrize("line", GARBAGE_LINES)
    def test_garbage_input_never_raises_and_stays_in_taxonomy(self, adapter_name, adapter, line):
        parsed = adapter(line)
        assert isinstance(parsed, ParsedRunnerLine)
        for event in parsed.events:
            assert event.kind in STREAM_EVENT_KINDS, (
                f"{adapter_name} produced an out-of-taxonomy kind {event.kind!r} "
                f"for input {line!r}"
            )
        assert parsed.usage is None or isinstance(parsed.usage, ContextUsageSample)

    @pytest.mark.parametrize("adapter_name,adapter", ADAPTERS)
    def test_empty_line_produces_neither_events_nor_usage(self, adapter_name, adapter):
        parsed = adapter("")
        assert parsed.events == []
        assert parsed.usage is None

    def test_claude_usage_only_line_keeps_events_and_usage_independent(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [],
                    "usage": {"input_tokens": 10, "cache_read_input_tokens": 0},
                },
            }
        )
        parsed = _parse_claude_stream_line(line)
        assert parsed.events == []
        assert isinstance(parsed.usage, ContextUsageSample)

    def test_codex_usage_only_line_keeps_events_and_usage_independent(self):
        line = json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 200,
                    "output_tokens": 500,
                    "reasoning_output_tokens": 50,
                },
            }
        )
        parsed = _parse_codex_stream_line(line)
        assert parsed.events == []
        assert isinstance(parsed.usage, ContextUsageSample)

    def test_opencode_usage_only_line_keeps_events_and_usage_independent(self):
        line = json.dumps(
            {
                "type": "step_finish",
                "part": {"tokens": {"total": 12537, "input": 217, "output": 10, "reasoning": 22}},
            }
        )
        parsed = _parse_opencode_stdout_line(line, [None])
        assert parsed.events == []
        assert isinstance(parsed.usage, ContextUsageSample)

    def test_copilot_never_produces_a_usage_sample(self):
        """Copilot's context tracking is OTel-only (design.md decision 4); the stdout
        adapter must never populate ParsedRunnerLine.usage for any line."""
        lines = [
            json.dumps({"type": "assistant.message", "data": {"content": "hi"}}),
            json.dumps({"type": "result", "exitCode": 0, "usage": {"premiumRequests": 3}}),
            json.dumps({"type": "tool.execution_complete", "data": {"success": True}}),
        ]
        for line in lines:
            assert _parse_copilot_stream_line(line).usage is None

    def test_kimi_never_produces_a_usage_sample(self):
        """Kimi's print-stream adapter carries no usage field at all (design.md decision
        4); context tracking for Kimi is the session-status/Wire auxiliary collector."""
        lines = [
            '{"role":"assistant","content":"hi"}',
            '{"role":"meta","type":"session.resume_hint","session_id":"session_abc"}',
        ]
        for line in lines:
            assert _KimiCodeParser().feed(line).usage is None

    def test_every_adapter_produces_a_text_event_for_its_own_fixture(self):
        """Sanity check that the taxonomy assertions above exercise real conformant
        output, not vacuous passes because every adapter returned nothing — each
        adapter's plain-text fixture must yield at least one canonical `text` event."""
        fixtures = {
            "claude": json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
            ),
            "codex": json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "1", "type": "agent_message", "text": "hi"},
                }
            ),
            "opencode": json.dumps(
                {"type": "text", "sessionID": "ses_1", "part": {"type": "text", "text": "hi"}}
            ),
            "copilot": json.dumps({"type": "assistant.message", "data": {"content": "hi"}}),
            "kimi": '{"role":"assistant","content":[{"type":"text","text":"hi"}]}',
        }
        adapters = dict(self.ADAPTERS)
        for name, line in fixtures.items():
            parsed = adapters[name](line)
            assert any(
                e.kind == "text" for e in parsed.events
            ), f"{name} did not produce a text event for its own fixture"


class TestCopilotUsesPat:
    """Tests for _copilot_uses_pat() — determines whether the serialization
    lock should be skipped for concurrent copilot agent execution."""

    def setup_method(self):
        from agentweave.watchdog import _copilot_uses_pat

        self._fn = _copilot_uses_pat

    def test_pat_in_env_vars_and_environment(self, monkeypatch):
        """Self-referential env_vars + matching env var → PAT detected."""
        monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "ghp_abc123")
        assert self._fn({"COPILOT_GITHUB_TOKEN": "COPILOT_GITHUB_TOKEN"}) is True

    def test_gh_token_in_env_vars_and_environment(self, monkeypatch):
        """GH_TOKEN variant is also recognised."""
        monkeypatch.setenv("GH_TOKEN", "ghp_xyz")
        assert self._fn({"GH_TOKEN": "GH_TOKEN"}) is True

    def test_github_token_in_env_vars_and_environment(self, monkeypatch):
        """GITHUB_TOKEN variant is also recognised."""
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_zzz")
        assert self._fn({"GITHUB_TOKEN": "GITHUB_TOKEN"}) is True

    def test_env_vars_key_present_but_env_not_set(self, monkeypatch):
        """env_vars has the key but env var is unset → not PAT (fallback to OAuth)."""
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert self._fn({"COPILOT_GITHUB_TOKEN": "COPILOT_GITHUB_TOKEN"}) is False

    def test_no_env_vars_no_environment(self, monkeypatch):
        """No config, no env var → OAuth assumed, lock should apply."""
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert self._fn(None) is False

    def test_no_env_vars_but_token_in_environment(self, monkeypatch):
        """Token set globally in env without agent env_vars config → PAT detected."""
        monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "ghp_global")
        assert self._fn(None) is True

    def test_empty_env_vars_dict_token_in_environment(self, monkeypatch):
        """Empty env_vars dict, token in env → PAT detected."""
        monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "ghp_global")
        assert self._fn({}) is True

    def test_unrelated_env_vars_no_pat(self, monkeypatch):
        """env_vars has unrelated keys and no PAT vars set → OAuth assumed."""
        monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        assert self._fn({"SOME_OTHER_VAR": "SOME_OTHER_VAR"}) is False


class TestWriteCodexContextUsage:
    """Tests for _write_codex_context_usage."""

    @pytest.fixture(autouse=True)
    def setup_dirs(self, tmp_path):
        self.tmp_path = tmp_path
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.shared_dir = self.session_dir / "shared"
        self.shared_dir.mkdir()
        self.context_usage_dir = self.shared_dir / "context_usage"
        self.context_usage_dir.mkdir()

        with patch("agentweave.watchdog.CONTEXT_USAGE_DIR", self.context_usage_dir):
            yield

    def test_known_model_limit(self, tmp_path, monkeypatch):
        """Uses correct limit for known Codex models."""
        monkeypatch.chdir(tmp_path)
        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {"codex-dev": {"runner": "codex", "model": "gpt-5.5"}},
        }
        session_file = tmp_path / ".agentweave" / "session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        sess = Session(session_data)
        with patch("agentweave.session.Session.load", return_value=sess):
            usage_data = {"input_tokens": 136000, "output_tokens": 10000, "cached_input_tokens": 0}
            result = _write_codex_context_usage("codex-dev", usage_data)
            assert result is not None
            assert result["tokens_limit"] == 272000
            assert result["tokens_used"] == 146000
            assert result["percent"] == 53

    def test_unknown_model_fallback(self, tmp_path, monkeypatch):
        """Falls back to 128000 for unknown models."""
        monkeypatch.chdir(tmp_path)
        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {"codex-dev": {"runner": "codex", "model": "unknown-model"}},
        }
        session_file = tmp_path / ".agentweave" / "session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        sess = Session(session_data)
        with patch("agentweave.session.Session.load", return_value=sess):
            usage_data = {"input_tokens": 64000, "output_tokens": 10000, "cached_input_tokens": 0}
            result = _write_codex_context_usage("codex-dev", usage_data)
            assert result is not None
            assert result["tokens_limit"] == 128000
            assert result["percent"] == 57

    def test_warning_threshold(self, tmp_path, monkeypatch):
        """Sets warning=True when percent >= 70."""
        monkeypatch.chdir(tmp_path)
        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {"codex-dev": {"runner": "codex", "model": "gpt-4o"}},
        }
        session_file = tmp_path / ".agentweave" / "session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        sess = Session(session_data)
        with patch("agentweave.session.Session.load", return_value=sess):
            # 70% of 128000 = 89600
            usage_data = {"input_tokens": 80000, "output_tokens": 9600, "cached_input_tokens": 0}
            result = _write_codex_context_usage("codex-dev", usage_data)
            assert result is not None
            assert result["warning"] is True
            assert result["critical"] is False

    def test_critical_threshold(self, tmp_path, monkeypatch):
        """Sets critical=True when percent >= 90."""
        monkeypatch.chdir(tmp_path)
        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {"codex-dev": {"runner": "codex", "model": "gpt-4o"}},
        }
        session_file = tmp_path / ".agentweave" / "session.json"
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(json.dumps(session_data))

        from agentweave.session import Session

        sess = Session(session_data)
        with patch("agentweave.session.Session.load", return_value=sess):
            # 90% of 128000 = 115200
            usage_data = {"input_tokens": 105000, "output_tokens": 10200, "cached_input_tokens": 0}
            result = _write_codex_context_usage("codex-dev", usage_data)
            assert result is not None
            assert result["warning"] is True
            assert result["critical"] is True


def _write_codex_rollout(
    path: Path,
    *,
    session_id: str,
    token_count_events: list,
    meta_session_id=None,
    trailing_partial: bool = False,
) -> None:
    """Write a minimal Codex rollout JSONL file for collector tests.

    `token_count_events` is a list of `info` dicts (each becomes one
    `event_msg`/`token_count` line); the file's `session_meta` line uses
    `meta_session_id` (defaulting to `session_id`) so tests can construct a
    mismatched/stale file on purpose.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "timestamp": "2026-07-29T00:00:00.000Z",
                "type": "session_meta",
                "payload": {"session_id": meta_session_id or session_id},
            }
        )
    ]
    for info in token_count_events:
        lines.append(
            json.dumps(
                {
                    "timestamp": "2026-07-29T00:00:01.000Z",
                    "type": "event_msg",
                    "payload": {"type": "token_count", "info": info},
                }
            )
        )
    text = "\n".join(lines) + "\n"
    if trailing_partial:
        text += '{"timestamp":"2026-07-29T00:00:02.000Z","type":"event_msg","payl'
    path.write_text(text, encoding="utf-8")


class TestCodexRolloutPathResolution:
    """Tests for _resolve_codex_rollout_path (task 3.2)."""

    def test_resolves_by_filename_suffix(self, tmp_path):
        """Primary resolution matches the session ID embedded in the filename."""
        session_id = "019fab26-b116-7fa0-b1d1-30d53a9b4aeb"
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        rollout = day_dir / f"rollout-2026-07-29T00-54-27-{session_id}.jsonl"
        _write_codex_rollout(rollout, session_id=session_id, token_count_events=[])

        resolved = _resolve_codex_rollout_path(session_id, codex_home=tmp_path)
        assert resolved == rollout

    def test_no_sessions_dir_returns_none(self, tmp_path):
        """Missing rollout: no sessions directory at all."""
        assert _resolve_codex_rollout_path("some-session", codex_home=tmp_path) is None

    def test_no_matching_file_returns_none(self, tmp_path):
        """Missing rollouts: sessions dir exists but has no matching file, no fallback window."""
        other = tmp_path / "sessions" / "2026" / "07" / "29" / "rollout-x-other-session.jsonl"
        _write_codex_rollout(other, session_id="other-session", token_count_events=[])
        assert _resolve_codex_rollout_path("target-session", codex_home=tmp_path) is None

    def test_bounded_fallback_verifies_session_meta(self, tmp_path):
        """When no filename matches, a recent file is accepted only if its own
        session_meta confirms the session ID."""
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        # Filename does not carry the session ID (simulating a naming edge case),
        # but the session_meta payload inside does.
        rollout = day_dir / "rollout-2026-07-29T00-00-00-mismatched-name.jsonl"
        _write_codex_rollout(
            rollout, session_id="ignored", meta_session_id="target-session", token_count_events=[]
        )

        found = _resolve_codex_rollout_path("target-session", codex_home=tmp_path, since=0.0)
        assert found == rollout

    def test_bounded_fallback_rejects_stale_session(self, tmp_path):
        """A file within the time window but bound to a different session is rejected."""
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        rollout = day_dir / "rollout-2026-07-29T00-00-00-mismatched-name.jsonl"
        _write_codex_rollout(
            rollout,
            session_id="ignored",
            meta_session_id="a-different-session",
            token_count_events=[],
        )

        assert _resolve_codex_rollout_path("target-session", codex_home=tmp_path, since=0.0) is None

    def test_bounded_fallback_without_since_does_not_scan(self, tmp_path):
        """Without a `since` bound, the fallback never triggers (no unscoped newest-file scan)."""
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        rollout = day_dir / "rollout-2026-07-29T00-00-00-mismatched-name.jsonl"
        _write_codex_rollout(
            rollout, session_id="ignored", meta_session_id="target-session", token_count_events=[]
        )

        assert _resolve_codex_rollout_path("target-session", codex_home=tmp_path) is None


class TestCodexRolloutSessionId:
    """Tests for _codex_rollout_session_id."""

    def test_reads_session_id_from_leading_meta(self, tmp_path):
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(rollout, session_id="abc-123", token_count_events=[])
        assert _codex_rollout_session_id(rollout) == "abc-123"

    def test_missing_file_returns_none(self, tmp_path):
        assert _codex_rollout_session_id(tmp_path / "does-not-exist.jsonl") is None

    def test_non_meta_first_line_returns_none(self, tmp_path):
        rollout = tmp_path / "rollout.jsonl"
        rollout.write_text('{"type":"event_msg","payload":{"type":"task_started"}}\n')
        assert _codex_rollout_session_id(rollout) is None


class TestCodexRolloutUsageSample:
    """Tests for _codex_rollout_usage_sample (tasks 3.2, 3.3)."""

    def test_fresh_turn_arithmetic(self, tmp_path):
        """Context tokens = total - reasoning; limit = model_context_window;
        cached input stays a breakdown only."""
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(
            rollout,
            session_id="s1",
            token_count_events=[
                {
                    "last_token_usage": {
                        "input_tokens": 15594,
                        "cached_input_tokens": 0,
                        "cache_write_input_tokens": 0,
                        "output_tokens": 5,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 15599,
                    },
                    "total_token_usage": {
                        "input_tokens": 15594,
                        "output_tokens": 5,
                        "total_tokens": 15599,
                    },
                    "model_context_window": 272000,
                }
            ],
        )
        sample = _codex_rollout_usage_sample(rollout, session_id="s1")
        assert sample is not None
        assert sample.status == "measured"
        assert sample.basis == "provider_context"
        assert sample.context_tokens == 15599
        assert sample.limit_tokens == 272000
        assert sample.session_id == "s1"
        assert sample.breakdown["cached_input_tokens"] == 0

    def test_resumed_turn_uses_latest_not_cumulative(self, tmp_path):
        """A resumed session's rollout has multiple token_count events; the
        latest `last_token_usage` (non-cumulative) must win, not the aggregate
        `total_token_usage`."""
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(
            rollout,
            session_id="s1",
            token_count_events=[
                {
                    "last_token_usage": {"total_tokens": 15599, "reasoning_output_tokens": 0},
                    "total_token_usage": {"total_tokens": 15599},
                    "model_context_window": 272000,
                },
                {
                    "last_token_usage": {"total_tokens": 15616, "reasoning_output_tokens": 0},
                    "total_token_usage": {"total_tokens": 31215},
                    "model_context_window": 272000,
                },
            ],
        )
        sample = _codex_rollout_usage_sample(rollout, session_id="s1")
        assert sample is not None
        assert sample.context_tokens == 15616

    def test_reasoning_tokens_excluded_from_context(self, tmp_path):
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(
            rollout,
            session_id="s1",
            token_count_events=[
                {
                    "last_token_usage": {
                        "total_tokens": 20000,
                        "reasoning_output_tokens": 4000,
                        "input_tokens": 15000,
                        "output_tokens": 1000,
                    },
                    "model_context_window": 128000,
                }
            ],
        )
        sample = _codex_rollout_usage_sample(rollout, session_id="s1")
        assert sample is not None
        assert sample.context_tokens == 16000
        assert sample.breakdown["reasoning_tokens"] == 4000

    def test_cached_input_never_added_to_context(self, tmp_path):
        """Codex `input_tokens` already includes cached input; adding
        `cached_input_tokens` again would double-count it."""
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(
            rollout,
            session_id="s1",
            token_count_events=[
                {
                    "last_token_usage": {
                        "input_tokens": 15610,
                        "cached_input_tokens": 15104,
                        "output_tokens": 6,
                        "reasoning_output_tokens": 0,
                        "total_tokens": 15616,
                    },
                    "model_context_window": 258400,
                }
            ],
        )
        sample = _codex_rollout_usage_sample(rollout, session_id="s1")
        assert sample is not None
        assert sample.context_tokens == 15616
        assert sample.breakdown["cached_input_tokens"] == 15104

    def test_missing_model_context_window_omits_limit(self, tmp_path):
        """Unknown model limits SHALL produce a token-only sample, not zero."""
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(
            rollout,
            session_id="s1",
            token_count_events=[
                {"last_token_usage": {"total_tokens": 5000, "reasoning_output_tokens": 0}}
            ],
        )
        sample = _codex_rollout_usage_sample(rollout, session_id="s1")
        assert sample is not None
        assert sample.limit_tokens is None
        assert sample.percent is None
        assert sample.context_tokens == 5000

    def test_partial_final_line_is_skipped(self, tmp_path):
        """A record still being written (partial final line) must not fail the
        whole read — the last complete record still wins."""
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(
            rollout,
            session_id="s1",
            token_count_events=[
                {
                    "last_token_usage": {"total_tokens": 12000, "reasoning_output_tokens": 0},
                    "model_context_window": 128000,
                }
            ],
            trailing_partial=True,
        )
        sample = _codex_rollout_usage_sample(rollout, session_id="s1")
        assert sample is not None
        assert sample.context_tokens == 12000

    def test_no_token_count_event_returns_none(self, tmp_path):
        rollout = tmp_path / "rollout.jsonl"
        _write_codex_rollout(rollout, session_id="s1", token_count_events=[])
        assert _codex_rollout_usage_sample(rollout, session_id="s1") is None

    def test_missing_file_returns_none(self, tmp_path):
        assert _codex_rollout_usage_sample(tmp_path / "nope.jsonl", session_id="s1") is None


class TestSelectCodexUsage:
    """Tests for _select_codex_usage (task 3.4: guarded cumulative-delta fallback)."""

    def _measured(self):
        return ContextUsageSample(
            status="measured", source="codex_rollout", basis="provider_context", context_tokens=100
        )

    def _estimated(self):
        return ContextUsageSample(
            status="estimated", source="codex", basis="cumulative_delta", context_tokens=999
        )

    def test_prefers_exact_rollout_sample(self):
        rollout = self._measured()
        estimate = self._estimated()
        assert _select_codex_usage(rollout, estimate) is rollout

    def test_falls_back_to_estimate_when_rollout_unavailable(self):
        estimate = self._estimated()
        assert _select_codex_usage(None, estimate) is estimate

    def test_none_when_neither_available(self):
        assert _select_codex_usage(None, None) is None


class TestRunnerUsageCollectorInterface:
    """Tests for the RunnerUsageCollector base class (task 3.1)."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            RunnerUsageCollector()  # type: ignore[abstract]

    def test_final_poll_defaults_to_observe(self):
        calls = []

        class _Stub(RunnerUsageCollector):
            def bind(self, *, session_id):
                pass

            def observe(self):
                calls.append("observe")
                return None

        stub = _Stub()
        stub.final_poll()
        assert calls == ["observe"]

    def test_setup_and_close_are_optional_no_ops(self):
        class _Stub(RunnerUsageCollector):
            def bind(self, *, session_id):
                pass

            def observe(self):
                return None

        stub = _Stub()
        stub.setup(agent="a")  # must not raise
        stub.close()  # must not raise


class TestCodexRolloutCollector:
    """Tests for CodexRolloutCollector (tasks 3.1-3.5)."""

    def test_is_a_runner_usage_collector(self):
        assert issubclass(CodexRolloutCollector, RunnerUsageCollector)

    def test_observe_before_bind_returns_none(self, tmp_path):
        collector = CodexRolloutCollector(codex_home=tmp_path)
        assert collector.observe() is None

    def test_observe_resolves_and_reads_bound_session(self, tmp_path):
        session_id = "s-live"
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        rollout = day_dir / f"rollout-2026-07-29T00-00-00-{session_id}.jsonl"
        _write_codex_rollout(
            rollout,
            session_id=session_id,
            token_count_events=[
                {
                    "last_token_usage": {"total_tokens": 8000, "reasoning_output_tokens": 0},
                    "model_context_window": 128000,
                }
            ],
        )
        collector = CodexRolloutCollector(codex_home=tmp_path)
        collector.bind(session_id=session_id)
        sample = collector.observe()
        assert sample is not None
        assert sample.context_tokens == 8000
        assert sample.session_id == session_id

    def test_observe_missing_rollout_returns_none(self, tmp_path):
        collector = CodexRolloutCollector(codex_home=tmp_path)
        collector.bind(session_id="never-written")
        assert collector.observe() is None

    def test_final_poll_reflects_a_late_write(self, tmp_path):
        """A trailing rollout write that lands after the process closes must
        still be eligible for delivery through final_poll."""
        session_id = "s-late"
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        rollout = day_dir / f"rollout-2026-07-29T00-00-00-{session_id}.jsonl"

        collector = CodexRolloutCollector(codex_home=tmp_path)
        collector.bind(session_id=session_id)
        assert collector.observe() is None  # nothing written yet

        _write_codex_rollout(
            rollout,
            session_id=session_id,
            token_count_events=[
                {
                    "last_token_usage": {"total_tokens": 4000, "reasoning_output_tokens": 0},
                    "model_context_window": 64000,
                }
            ],
        )
        sample = collector.final_poll()
        assert sample is not None
        assert sample.context_tokens == 4000

    def test_rebind_forces_path_reresolution(self, tmp_path):
        """Binding to a new session must not keep serving the previous
        session's cached rollout path."""
        first_id, second_id = "s-first", "s-second"
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        for sid, tokens in ((first_id, 1000), (second_id, 2000)):
            _write_codex_rollout(
                day_dir / f"rollout-2026-07-29T00-00-00-{sid}.jsonl",
                session_id=sid,
                token_count_events=[
                    {
                        "last_token_usage": {"total_tokens": tokens, "reasoning_output_tokens": 0},
                        "model_context_window": 64000,
                    }
                ],
            )

        collector = CodexRolloutCollector(codex_home=tmp_path)
        collector.bind(session_id=first_id)
        assert collector.observe().context_tokens == 1000

        collector.bind(session_id=second_id)
        assert collector.observe().context_tokens == 2000

    def test_rejects_mismatched_session_id_in_resolved_file(self, tmp_path):
        """Guard against a stale/mismatched file slipping past resolution:
        even if a path is resolved, a sample whose own session_id disagrees
        with the bound session must be rejected."""
        session_id = "bound-session"
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        # Filename matches the bound session, but the file's own session_meta
        # (as would happen with a corrupted/reused file) disagrees.
        rollout = day_dir / f"rollout-2026-07-29T00-00-00-{session_id}.jsonl"
        _write_codex_rollout(
            rollout,
            session_id=session_id,
            meta_session_id="a-completely-different-session",
            token_count_events=[
                {
                    "last_token_usage": {"total_tokens": 9000, "reasoning_output_tokens": 0},
                    "model_context_window": 64000,
                }
            ],
        )
        collector = CodexRolloutCollector(codex_home=tmp_path)
        collector.bind(session_id=session_id)
        assert collector.observe() is None

    def test_close_clears_cached_path(self, tmp_path):
        session_id = "s-close"
        day_dir = tmp_path / "sessions" / "2026" / "07" / "29"
        rollout = day_dir / f"rollout-2026-07-29T00-00-00-{session_id}.jsonl"
        _write_codex_rollout(
            rollout,
            session_id=session_id,
            token_count_events=[
                {
                    "last_token_usage": {"total_tokens": 3000, "reasoning_output_tokens": 0},
                    "model_context_window": 64000,
                }
            ],
        )
        collector = CodexRolloutCollector(codex_home=tmp_path)
        collector.bind(session_id=session_id)
        assert collector.observe() is not None
        collector.close()
        assert collector._rollout_path is None
        # Still resolvable again after close (close only clears the cache).
        assert collector.observe() is not None


class TestPopenUsesUtf8Encoding:
    """M5 — subprocess.Popen calls in watchdog.py that use text=True must
    also pass encoding="utf-8" and errors="replace". Without it, a Kimi
    agent emitting non-ASCII characters (Chinese, emoji) crashes
    proc.stderr mid-thread on Windows (cp1252 codec).

    The two affected sites are:
    - _CodexMcpClient.start (line 1598)
    - _do_run_agent_subprocess._run_cmd (line 2576)
    """

    def test_watchdog_does_not_call_popen_with_text_only(self):
        """Source-level check: every Popen call in watchdog.py that
        passes text=True must also pass encoding="utf-8".

        This is a portable regression guard — works on every platform
        and tells future contributors exactly which kwargs are
        required.
        """
        from pathlib import Path

        src = Path("src/agentweave/watchdog.py").read_text(encoding="utf-8")
        # Find every `subprocess.Popen(` call site and check the
        # next 8 lines contain both `text=True` (or `text=`) and
        # `encoding="utf-8"`. If a call site has text=True but no
        # encoding, that's a bug.
        issues = []
        lines = src.splitlines()
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if "subprocess.Popen(" in stripped:
                look_ahead = "\n".join(lines[i : i + 12])
                if "text=" in look_ahead and 'encoding="utf-8"' not in look_ahead:
                    issues.append((i + 1, line.rstrip()))
        assert not issues, (
            "M5 regression: subprocess.Popen(text=True, ...) calls without "
            "encoding='utf-8' in watchdog.py:\n"
            + "\n".join(f"  watchdog.py:{ln}: {line}" for ln, line in issues)
        )

    def test_watchdog_popen_kwargs_include_errors_replace(self):
        """Defense in depth: Popen calls that use text=True should also
        pass errors='replace' so a decode error in the child doesn't
        crash the parent thread."""
        from pathlib import Path

        src = Path("src/agentweave/watchdog.py").read_text(encoding="utf-8")
        # If a Popen uses text=True, it should also use errors="replace"
        lines = src.splitlines()
        issues = []
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if "subprocess.Popen(" in stripped:
                look_ahead = "\n".join(lines[i : i + 12])
                if "text=" in look_ahead and 'errors="replace"' not in look_ahead:
                    issues.append((i + 1, line.rstrip()))
        assert not issues, (
            "M5 regression: subprocess.Popen(text=True, ...) calls without "
            'errors="replace" in watchdog.py:\n'
            + "\n".join(f"  watchdog.py:{ln}: {line}" for ln, line in issues)
        )


class TestSpecSync:
    """Spec-file discovery and mtime-diff push logic (http transport only)."""

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        """Empty project root as CWD (spec paths are CWD-relative)."""
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def _make_watchdog(self):
        from agentweave.watchdog import Watchdog

        transport = MagicMock()
        transport.get_transport_type.return_value = "http"
        transport.poll_interval = 5.0
        transport.push_spec.return_value = True
        return Watchdog(transport=transport), transport

    def _write_specs(self, root: Path) -> None:
        change_dir = root / "spec" / "changes" / "add-thing"
        change_dir.mkdir(parents=True)
        (root / "spec" / "spec.html").write_text("<html>main</html>", encoding="utf-8")
        (change_dir / "spec.html").write_text("<html>change</html>", encoding="utf-8")

    def test_discover_spec_files(self, project):
        from agentweave.watchdog import _discover_spec_files

        self._write_specs(project)
        specs = _discover_spec_files()
        assert set(specs.keys()) == {
            "spec/spec.html",
            "spec/changes/add-thing/spec.html",
        }

    def test_discover_spec_files_empty(self, project):
        from agentweave.watchdog import _discover_spec_files

        assert _discover_spec_files() == {}

    def test_discover_spec_files_recurses_beyond_the_two_legacy_globs(self, project):
        """M1 regression: system maps, roadmaps, and archived changes are now
        discovered without a spec/index.json entry (the old implementation
        only matched spec/spec.html and spec/changes/*/spec.html)."""
        from agentweave.watchdog import _discover_spec_files

        (project / "spec" / "roadmaps").mkdir(parents=True)
        (project / "spec" / "system-map.html").write_text("<html>map</html>", encoding="utf-8")
        (project / "spec" / "roadmaps" / "epic.html").write_text(
            "<html>roadmap</html>", encoding="utf-8"
        )
        archived = project / "spec" / "changes" / "archive" / "old-thing"
        archived.mkdir(parents=True)
        (archived / "spec.html").write_text("<html>archived</html>", encoding="utf-8")

        specs = _discover_spec_files()
        assert set(specs.keys()) == {
            "spec/system-map.html",
            "spec/roadmaps/epic.html",
            "spec/changes/archive/old-thing/spec.html",
        }

    def test_push_all_seeds_mtimes(self, project):
        self._write_specs(project)
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        pushed = {call.args[0] for call in transport.push_spec.call_args_list}
        assert pushed == {"spec/spec.html", "spec/changes/add-thing/spec.html"}
        assert set(wd.known_spec_mtimes.keys()) == pushed
        # Content is passed through as UTF-8 text
        contents = {call.args[0]: call.args[1] for call in transport.push_spec.call_args_list}
        assert contents["spec/spec.html"] == "<html>main</html>"

    def test_unchanged_specs_not_repushed(self, project):
        self._write_specs(project)
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.push_spec.reset_mock()
        wd._sync_spec_files()
        transport.push_spec.assert_not_called()

    def test_changed_spec_repushed(self, project):
        import os

        self._write_specs(project)
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.push_spec.reset_mock()

        changed = project / "spec" / "changes" / "add-thing" / "spec.html"
        changed.write_text("<html>v2</html>", encoding="utf-8")
        new_mtime = changed.stat().st_mtime + 100
        os.utime(changed, (new_mtime, new_mtime))

        wd._sync_spec_files()
        transport.push_spec.assert_called_once_with(
            "spec/changes/add-thing/spec.html", "<html>v2</html>"
        )

    def test_new_spec_file_pushed(self, project):
        self._write_specs(project)
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.push_spec.reset_mock()

        new_change = project / "spec" / "changes" / "other-change"
        new_change.mkdir(parents=True)
        (new_change / "spec.html").write_text("<html>new</html>", encoding="utf-8")

        wd._sync_spec_files()
        transport.push_spec.assert_called_once_with(
            "spec/changes/other-change/spec.html", "<html>new</html>"
        )

    def test_failed_push_not_recorded_and_retried(self, project):
        self._write_specs(project)
        wd, transport = self._make_watchdog()
        transport.push_spec.return_value = False
        wd._sync_spec_files(push_all=True)
        assert wd.known_spec_mtimes == {}
        # Next poll retries the push
        transport.push_spec.return_value = True
        wd._sync_spec_files()
        assert set(wd.known_spec_mtimes.keys()) == {
            "spec/spec.html",
            "spec/changes/add-thing/spec.html",
        }

    def test_no_push_spec_method_is_noop(self, project):
        """Non-http transports (no push_spec) must be skipped silently."""
        self._write_specs(project)
        wd, transport = self._make_watchdog()
        del transport.push_spec  # MagicMock without the attribute
        wd._sync_spec_files(push_all=True)  # must not raise
        assert wd.known_spec_mtimes == {}


class TestSpecReconciliation:
    """Reconciliation snapshot submission (task 2.3/2.4)."""

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def _make_watchdog(self):
        from agentweave.watchdog import Watchdog

        transport = MagicMock()
        transport.get_transport_type.return_value = "http"
        transport.poll_interval = 5.0
        transport.push_spec.return_value = True
        transport.reconcile_specs.return_value = {"diagnostics": []}
        return Watchdog(transport=transport), transport

    def _write_spec(self, root: Path) -> None:
        (root / "spec").mkdir(parents=True, exist_ok=True)
        (root / "spec" / "spec.html").write_text("<html>main</html>", encoding="utf-8")

    def test_startup_sends_complete_snapshot(self, project):
        self._write_spec(project)
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.reconcile_specs.assert_called_once_with(
            manifest_text=None,
            manifest_state="absent",
            discovered_paths=["spec/spec.html"],
        )

    def test_unchanged_poll_does_not_reconcile_again(self, project):
        self._write_spec(project)
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.reconcile_specs.reset_mock()
        wd._sync_spec_files()
        transport.reconcile_specs.assert_not_called()

    def test_manifest_only_change_triggers_reconcile(self, project):
        self._write_spec(project)
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.reconcile_specs.reset_mock()

        manifest = {
            "version": 1,
            "home": "spec/spec.html",
            "documents": [
                {
                    "path": "spec/spec.html",
                    "title": "Main",
                    "kind": "baseline",
                    "status": "living",
                    "parent": None,
                    "order": 10,
                }
            ],
        }
        (project / "spec" / "index.json").write_text(json.dumps(manifest), encoding="utf-8")

        wd._sync_spec_files()
        transport.reconcile_specs.assert_called_once_with(
            manifest_text=json.dumps(manifest),
            manifest_state="valid",
            discovered_paths=["spec/spec.html"],
        )

    def test_deletion_is_reflected_in_next_snapshot(self, project):
        self._write_spec(project)
        change_dir = project / "spec" / "changes" / "add-thing"
        change_dir.mkdir(parents=True)
        (change_dir / "spec.html").write_text("<html>change</html>", encoding="utf-8")
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.reconcile_specs.reset_mock()

        (change_dir / "spec.html").unlink()

        wd._sync_spec_files()
        transport.reconcile_specs.assert_called_once_with(
            manifest_text=None,
            manifest_state="absent",
            discovered_paths=["spec/spec.html"],
        )

    def test_malformed_manifest_reports_invalid_but_still_reconciles(self, project):
        self._write_spec(project)
        (project / "spec" / "index.json").write_text("{not json", encoding="utf-8")
        wd, transport = self._make_watchdog()
        wd._sync_spec_files(push_all=True)
        transport.reconcile_specs.assert_called_once_with(
            manifest_text="{not json",
            manifest_state="invalid",
            discovered_paths=["spec/spec.html"],
        )

    def test_partial_upload_failure_suppresses_reconciliation(self, project):
        self._write_spec(project)
        (project / "spec" / "changes" / "add-thing").mkdir(parents=True)
        (project / "spec" / "changes" / "add-thing" / "spec.html").write_text(
            "<html>change</html>", encoding="utf-8"
        )
        wd, transport = self._make_watchdog()
        transport.push_spec.side_effect = [True, False]

        wd._sync_spec_files(push_all=True)

        transport.reconcile_specs.assert_not_called()

    def test_retries_reconciliation_on_next_successful_cycle(self, project):
        self._write_spec(project)
        wd, transport = self._make_watchdog()
        transport.push_spec.return_value = False
        wd._sync_spec_files(push_all=True)
        transport.reconcile_specs.assert_not_called()

        transport.push_spec.return_value = True
        wd._sync_spec_files(push_all=True)
        transport.reconcile_specs.assert_called_once()

    def test_failed_reconcile_response_does_not_update_fingerprint(self, project):
        self._write_spec(project)
        wd, transport = self._make_watchdog()
        transport.reconcile_specs.return_value = None
        wd._sync_spec_files(push_all=True)
        assert wd.known_spec_reconcile_fingerprint is None

        transport.reconcile_specs.return_value = {"diagnostics": []}
        wd._sync_spec_files()  # nothing changed on disk, but fingerprint never recorded
        transport.reconcile_specs.assert_called()

    def test_non_http_transport_is_noop(self, project):
        """Transports without reconcile_specs (e.g. local) must be skipped silently."""
        self._write_spec(project)
        wd, transport = self._make_watchdog()
        del transport.reconcile_specs
        wd._sync_spec_files(push_all=True)  # must not raise


class TestExtractKimiCodeSession:
    """Tests for _extract_kimi_code_session (kimi-code v0.x session discovery).

    kimi-code v0.x emits no session id on stdout, so the watchdog recovers it
    by matching the working directory against ~/.kimi-code/session_index.jsonl.
    kimi-code writes workDir with forward slashes; on Windows str(Path) uses
    backslashes, so comparing raw strings silently matched nothing and every
    kimi agent started a fresh session on every turn.
    """

    def _write_index(self, home: Path, records: list) -> None:
        index_dir = home / ".kimi-code"
        index_dir.mkdir(parents=True, exist_ok=True)
        index_dir.joinpath("session_index.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )

    def test_matches_forward_slash_workdir(self, tmp_path, monkeypatch):
        """A forward-slash workDir must match a native Path cwd on any OS."""
        home = tmp_path / "home"
        project = tmp_path / "proj"
        project.mkdir()
        session_dir = tmp_path / "sess"
        session_dir.mkdir()

        self._write_index(
            home,
            [
                {
                    "sessionId": "session_abc",
                    "sessionDir": str(session_dir),
                    # As kimi-code writes it: forward slashes, even on Windows.
                    "workDir": project.resolve().as_posix(),
                }
            ],
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        from agentweave.watchdog import _extract_kimi_code_session

        assert _extract_kimi_code_session(project) == "session_abc"

    def test_picks_most_recent_session_for_workdir(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        project = tmp_path / "proj"
        project.mkdir()
        old_dir = tmp_path / "old"
        old_dir.mkdir()
        new_dir = tmp_path / "new"
        new_dir.mkdir()
        os.utime(old_dir, (1000, 1000))
        os.utime(new_dir, (2000, 2000))

        self._write_index(
            home,
            [
                {
                    "sessionId": "session_old",
                    "sessionDir": str(old_dir),
                    "workDir": project.resolve().as_posix(),
                },
                {
                    "sessionId": "session_new",
                    "sessionDir": str(new_dir),
                    "workDir": project.resolve().as_posix(),
                },
            ],
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        from agentweave.watchdog import _extract_kimi_code_session

        assert _extract_kimi_code_session(project) == "session_new"

    def test_ignores_other_workdirs(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        project = tmp_path / "proj"
        project.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        session_dir = tmp_path / "sess"
        session_dir.mkdir()

        self._write_index(
            home,
            [
                {
                    "sessionId": "session_other",
                    "sessionDir": str(session_dir),
                    "workDir": other.resolve().as_posix(),
                }
            ],
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        from agentweave.watchdog import _extract_kimi_code_session

        assert _extract_kimi_code_session(project) is None

    def test_skips_malformed_records(self, tmp_path, monkeypatch):
        """A bad line, a missing workDir, and a vanished sessionDir are skipped."""
        home = tmp_path / "home"
        project = tmp_path / "proj"
        project.mkdir()
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        wd_posix = project.resolve().as_posix()

        index_dir = home / ".kimi-code"
        index_dir.mkdir(parents=True)
        index_dir.joinpath("session_index.jsonl").write_text(
            "\n".join(
                [
                    "not json at all",
                    json.dumps({"sessionId": "no_workdir", "sessionDir": str(session_dir)}),
                    json.dumps(
                        {"sessionId": "", "sessionDir": str(session_dir), "workDir": wd_posix}
                    ),
                    json.dumps(
                        {
                            "sessionId": "gone",
                            "sessionDir": str(tmp_path / "does-not-exist"),
                            "workDir": wd_posix,
                        }
                    ),
                    json.dumps(
                        {
                            "sessionId": "session_good",
                            "sessionDir": str(session_dir),
                            "workDir": wd_posix,
                        }
                    ),
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        from agentweave.watchdog import _extract_kimi_code_session

        assert _extract_kimi_code_session(project) == "session_good"

    def test_missing_index_returns_none(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        project = tmp_path / "proj"
        project.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        from agentweave.watchdog import _extract_kimi_code_session

        assert _extract_kimi_code_session(project) is None
