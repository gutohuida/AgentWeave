"""Tests for watchdog dispatch logic."""

import itertools
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agentweave.stream_events import (
    STREAM_EVENT_KINDS,
    ContextUsageSample,
    ParsedRunnerLine,
    text_event,
)
from agentweave.watchdog import (
    CodexRolloutCollector,
    CopilotOtelCollector,
    KimiWireCollector,
    RunnerUsageCollector,
    _agent_ping_cmd,
    _assign_sequence,
    _build_codex_mcp_tool_call,
    _claude_tool_result_text,
    _claude_usage_sample,
    _codex_rollout_session_id,
    _codex_rollout_usage_sample,
    _codex_working_dir,
    _copilot_latest_top_level_chat_span,
    _copilot_otel_usage_sample,
    _extract_codex_mcp_result,
    _extract_jsonl_session_id,
    _kimi_model_context_limit,
    _kimi_wire_usage_sample,
    _KimiCodeParser,
    _new_run_id,
    _opencode_model_context_limit,
    _opencode_models_catalog,
    _opencode_usage_sample,
    _parse_claude_stdout_line,
    _parse_claude_stream_line,
    _parse_codex_stdout_line,
    _parse_codex_stream_line,
    _parse_copilot_stdout_line,
    _parse_copilot_stream_line,
    _parse_kimi_stdout_line,
    _parse_opencode_stdout_line,
    _resolve_codex_rollout_path,
    _resolve_kimi_wire_path,
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


def _otel_span(
    name,
    span_id,
    *,
    parent_span_id=None,
    end_time=(0, 0),
    attributes=None,
):
    """Build a minimal OTel file-exporter span record for collector tests."""
    span = {
        "type": "span",
        "traceId": "trace-1",
        "spanId": span_id,
        "name": name,
        "kind": 2,
        "startTime": [max(0, end_time[0] - 1), end_time[1]],
        "endTime": list(end_time),
        "attributes": attributes or {},
        "status": {"code": 0},
        "events": [],
        "resource": {},
        "instrumentationScope": {},
    }
    if parent_span_id is not None:
        span["parentSpanId"] = parent_span_id
    return span


def _write_otel_jsonl(path: Path, records: list, *, trailing_partial: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    text = "\n".join(lines) + ("\n" if lines else "")
    if trailing_partial:
        text += '{"type":"span","name":"chat","attributes":{"gen_ai.usage.inp'
    path.write_text(text, encoding="utf-8")


# Attribute shapes below are trimmed from real JSONL captured live against
# GitHub Copilot CLI 1.0.75 with COPILOT_OTEL_FILE_EXPORTER_PATH set (a plain
# reply, a tool-calling turn, and a `task`-tool subagent turn); verbose fields
# irrelevant to context usage (gen_ai.tool.definitions, response.id, etc.) are
# omitted for readability. `gen_ai.usage.cache_creation.input_tokens` was never
# observed live in any probe (same caveat as the previous session's Copilot
# reasoning-content work) so its handling below is synthetic, proven only
# safe-when-absent, not proven-correct-on-real-data.


class TestCopilotLatestTopLevelChatSpan:
    """Tests for _copilot_latest_top_level_chat_span (task 3.7)."""

    def test_single_chat_span(self):
        spans = [
            _otel_span("chat auto", "chat-1", parent_span_id="root", end_time=(100, 0)),
            _otel_span("invoke_agent", "root", end_time=(101, 0)),
        ]
        selected = _copilot_latest_top_level_chat_span(spans)
        assert selected is not None
        assert selected["spanId"] == "chat-1"

    def test_aggregate_invoke_agent_excluded_multiple_chat_spans(self):
        """A tool-calling turn produces two top-level chat spans and one
        aggregate invoke_agent parent (confirmed live) -- the latest chat
        span must win, never the aggregate."""
        spans = [
            _otel_span("chat auto", "chat-1", parent_span_id="root", end_time=(100, 0)),
            _otel_span("chat auto", "chat-2", parent_span_id="root", end_time=(102, 0)),
            _otel_span("invoke_agent", "root", end_time=(103, 0)),
        ]
        selected = _copilot_latest_top_level_chat_span(spans)
        assert selected is not None
        assert selected["spanId"] == "chat-2"

    def test_subagent_chat_span_excluded(self):
        """A `task`-tool subagent nests its own invoke_agent span, so its chat
        span's parent is the nested span, not the root -- confirmed live."""
        spans = [
            _otel_span("chat gpt-5-mini", "sub-chat", parent_span_id="sub-agent", end_time=(50, 0)),
            _otel_span(
                "invoke_agent task", "sub-agent", parent_span_id="task-tool", end_time=(51, 0)
            ),
            _otel_span("execute_tool task", "task-tool", parent_span_id="root", end_time=(52, 0)),
            _otel_span("chat auto", "chat-1", parent_span_id="root", end_time=(48, 0)),
            _otel_span("chat auto", "chat-2", parent_span_id="root", end_time=(53, 0)),
            _otel_span("invoke_agent", "root", end_time=(54, 0)),
        ]
        selected = _copilot_latest_top_level_chat_span(spans)
        assert selected is not None
        assert selected["spanId"] == "chat-2"

    def test_no_root_invoke_agent_returns_none(self):
        spans = [_otel_span("chat auto", "chat-1", parent_span_id="root", end_time=(100, 0))]
        assert _copilot_latest_top_level_chat_span(spans) is None

    def test_no_chat_children_returns_none(self):
        spans = [_otel_span("invoke_agent", "root", end_time=(100, 0))]
        assert _copilot_latest_top_level_chat_span(spans) is None

    def test_malformed_end_time_does_not_crash(self):
        root = _otel_span("invoke_agent", "root", end_time=(100, 0))
        broken = _otel_span("chat auto", "chat-1", parent_span_id="root")
        broken["endTime"] = "not-a-list"
        selected = _copilot_latest_top_level_chat_span([root, broken])
        assert selected is not None
        assert selected["spanId"] == "chat-1"


class TestCopilotOtelUsageSample:
    """Tests for _copilot_otel_usage_sample (tasks 3.7, 3.8)."""

    def test_plain_reply_arithmetic(self, tmp_path):
        """Single-chat-span turn; input_tokens used directly, cache_read kept
        only as a breakdown, no limit ever reported."""
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={
                        "gen_ai.conversation.id": "91d4c03e-7db5-4286-b273-4e07b7d8cf1b",
                        "gen_ai.request.model": "auto",
                        "gen_ai.response.model": "gpt-5-mini",
                        "gen_ai.usage.input_tokens": 13335,
                        "gen_ai.usage.cache_read.input_tokens": 1792,
                        "gen_ai.usage.output_tokens": 105,
                        "gen_ai.usage.reasoning.output_tokens": 64,
                    },
                ),
                _otel_span(
                    "invoke_agent",
                    "root",
                    end_time=(101, 0),
                    attributes={"gen_ai.usage.input_tokens": 13335},
                ),
            ],
        )
        sample = _copilot_otel_usage_sample(path)
        assert sample is not None
        assert sample.status == "measured"
        assert sample.basis == "latest_request_input"
        assert sample.context_tokens == 13335
        assert sample.limit_tokens is None
        assert sample.percent is None
        assert sample.model == "gpt-5-mini"
        assert sample.session_id == "91d4c03e-7db5-4286-b273-4e07b7d8cf1b"
        assert sample.breakdown["cache_read_tokens"] == 1792

    def test_tool_call_turn_uses_latest_chat_not_aggregate(self, tmp_path):
        """Two top-level chat spans (11-run and follow-up) plus the aggregate
        invoke_agent parent -- the latest chat span's own tokens must be
        used, not the parent's summed total (confirmed live: 13342 + 14074 =
        27416, the wrong aggregate value)."""
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "execute_tool powershell",
                    "tool-1",
                    parent_span_id="root",
                    end_time=(10, 0),
                ),
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(11, 0),
                    attributes={
                        "gen_ai.response.model": "gpt-5-mini",
                        "gen_ai.usage.input_tokens": 13342,
                        "gen_ai.usage.cache_read.input_tokens": 12800,
                        "gen_ai.usage.output_tokens": 601,
                        "gen_ai.usage.reasoning.output_tokens": 512,
                    },
                ),
                _otel_span(
                    "chat auto",
                    "chat-2",
                    parent_span_id="root",
                    end_time=(12, 0),
                    attributes={
                        "gen_ai.response.model": "gpt-5-mini",
                        "gen_ai.usage.input_tokens": 14074,
                        "gen_ai.usage.cache_read.input_tokens": 13824,
                        "gen_ai.usage.output_tokens": 5,
                    },
                ),
                _otel_span(
                    "invoke_agent",
                    "root",
                    end_time=(13, 0),
                    attributes={
                        "gen_ai.usage.input_tokens": 27416,
                        "gen_ai.usage.cache_read.input_tokens": 26624,
                        "gen_ai.usage.output_tokens": 606,
                    },
                ),
            ],
        )
        sample = _copilot_otel_usage_sample(path)
        assert sample is not None
        assert sample.context_tokens == 14074
        assert sample.breakdown["cache_read_tokens"] == 13824

    def test_subagent_turn_excludes_subagent_chat_span(self, tmp_path):
        """A `task`-tool subagent turn: the subagent's own chat span (11584
        tokens) must never be selected over the root's top-level chat spans."""
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat gpt-5-mini",
                    "sub-chat",
                    parent_span_id="sub-agent",
                    end_time=(20, 0),
                    attributes={
                        "gen_ai.response.model": "gpt-5-mini",
                        "gen_ai.usage.input_tokens": 11584,
                        "gen_ai.usage.output_tokens": 66,
                    },
                ),
                _otel_span(
                    "invoke_agent task", "sub-agent", parent_span_id="task-tool", end_time=(21, 0)
                ),
                _otel_span(
                    "execute_tool task", "task-tool", parent_span_id="root", end_time=(22, 0)
                ),
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(19, 0),
                    attributes={
                        "gen_ai.response.model": "gpt-5-mini",
                        "gen_ai.usage.input_tokens": 13368,
                    },
                ),
                _otel_span(
                    "chat auto",
                    "chat-2",
                    parent_span_id="root",
                    end_time=(23, 0),
                    attributes={
                        "gen_ai.response.model": "gpt-5-mini",
                        "gen_ai.usage.input_tokens": 14074,
                    },
                ),
                _otel_span(
                    "invoke_agent",
                    "root",
                    end_time=(24, 0),
                    attributes={"gen_ai.usage.input_tokens": 27442},
                ),
            ],
        )
        sample = _copilot_otel_usage_sample(path)
        assert sample is not None
        assert sample.context_tokens == 14074

    def test_cache_creation_retained_as_breakdown_only(self, tmp_path):
        """Synthetic: cache_creation.input_tokens was never observed live, but
        if a provider ever reports it, it must stay a breakdown, never added
        to context_tokens (OTel semconv: input_tokens already includes it)."""
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={
                        "gen_ai.usage.input_tokens": 5000,
                        "gen_ai.usage.cache_creation.input_tokens": 200,
                    },
                ),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
        )
        sample = _copilot_otel_usage_sample(path)
        assert sample is not None
        assert sample.context_tokens == 5000
        assert sample.breakdown["cache_creation_tokens"] == 200

    def test_model_prefers_response_over_request(self, tmp_path):
        """`gen_ai.request.model` can be the unresolved "auto"; the actually
        used model is only on `gen_ai.response.model` (confirmed live)."""
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={
                        "gen_ai.request.model": "auto",
                        "gen_ai.response.model": "gpt-5-mini",
                        "gen_ai.usage.input_tokens": 100,
                    },
                ),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
        )
        sample = _copilot_otel_usage_sample(path)
        assert sample is not None
        assert sample.model == "gpt-5-mini"

    def test_partial_final_line_is_skipped(self, tmp_path):
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={"gen_ai.usage.input_tokens": 4200},
                ),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
            trailing_partial=True,
        )
        sample = _copilot_otel_usage_sample(path)
        assert sample is not None
        assert sample.context_tokens == 4200

    def test_no_chat_span_returns_none(self, tmp_path):
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(path, [_otel_span("invoke_agent", "root", end_time=(100, 0))])
        assert _copilot_otel_usage_sample(path) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert _copilot_otel_usage_sample(tmp_path / "nope.jsonl") is None

    def test_missing_input_tokens_returns_none(self, tmp_path):
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span("chat auto", "chat-1", parent_span_id="root", end_time=(100, 0)),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
        )
        assert _copilot_otel_usage_sample(path) is None

    def test_never_surfaces_raw_content_fields(self, tmp_path):
        """Content capture is disabled by the collector, but even if a raw
        attribute payload somehow carried message content (e.g. a
        misconfigured environment), the sample only ever extracts specific
        numeric usage keys plus model/conversation id -- nothing else can
        leak into the breakdown or the sample itself."""
        path = tmp_path / "otel.jsonl"
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={
                        "gen_ai.usage.input_tokens": 100,
                        "gen_ai.prompt": "this is sensitive user prompt content",
                        "gen_ai.completion": "this is sensitive response content",
                    },
                ),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
        )
        sample = _copilot_otel_usage_sample(path)
        assert sample is not None
        assert "sensitive" not in json.dumps(sample.breakdown)
        assert sample.model is None


class TestCopilotOtelCollector:
    """Tests for CopilotOtelCollector (tasks 3.6-3.9)."""

    def test_is_a_runner_usage_collector(self):
        assert issubclass(CopilotOtelCollector, RunnerUsageCollector)

    def test_env_empty_before_setup(self, tmp_path):
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        assert collector.env == {}

    def test_setup_produces_unique_bounded_path(self, tmp_path):
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        collector.setup(agent="copilot-dev")
        env = collector.env
        assert "COPILOT_OTEL_FILE_EXPORTER_PATH" in env
        path = Path(env["COPILOT_OTEL_FILE_EXPORTER_PATH"])
        assert path.parent == tmp_path

        other = CopilotOtelCollector(otel_dir=tmp_path)
        other.setup(agent="copilot-dev")
        assert (
            other.env["COPILOT_OTEL_FILE_EXPORTER_PATH"] != env["COPILOT_OTEL_FILE_EXPORTER_PATH"]
        )

    def test_setup_disables_content_capture(self, tmp_path):
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        collector.setup(agent="copilot-dev")
        assert collector.env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] == "false"

    def test_observe_before_setup_returns_none(self):
        collector = CopilotOtelCollector()
        assert collector.observe() is None

    def test_observe_missing_export_file_returns_none(self, tmp_path):
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        collector.setup(agent="copilot-dev")
        assert collector.observe() is None

    def test_observe_reads_bound_export(self, tmp_path):
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        collector.setup(agent="copilot-dev")
        collector.bind(session_id="conv-1")
        path = Path(collector.env["COPILOT_OTEL_FILE_EXPORTER_PATH"])
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={
                        "gen_ai.conversation.id": "conv-1",
                        "gen_ai.usage.input_tokens": 9000,
                    },
                ),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
        )
        sample = collector.observe()
        assert sample is not None
        assert sample.context_tokens == 9000

    def test_final_poll_reflects_late_write(self, tmp_path):
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        collector.setup(agent="copilot-dev")
        collector.bind(session_id="conv-2")
        assert collector.observe() is None  # nothing written yet

        path = Path(collector.env["COPILOT_OTEL_FILE_EXPORTER_PATH"])
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={
                        "gen_ai.conversation.id": "conv-2",
                        "gen_ai.usage.input_tokens": 3000,
                    },
                ),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
        )
        sample = collector.final_poll()
        assert sample is not None
        assert sample.context_tokens == 3000

    def test_rejects_mismatched_conversation_id(self, tmp_path):
        """A stale/mismatched export must be rejected even if it resolves and
        parses cleanly (design.md decision 5)."""
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        collector.setup(agent="copilot-dev")
        collector.bind(session_id="bound-session")
        path = Path(collector.env["COPILOT_OTEL_FILE_EXPORTER_PATH"])
        _write_otel_jsonl(
            path,
            [
                _otel_span(
                    "chat auto",
                    "chat-1",
                    parent_span_id="root",
                    end_time=(100, 0),
                    attributes={
                        "gen_ai.conversation.id": "a-different-session",
                        "gen_ai.usage.input_tokens": 9000,
                    },
                ),
                _otel_span("invoke_agent", "root", end_time=(101, 0)),
            ],
        )
        assert collector.observe() is None

    def test_close_removes_the_export_file(self, tmp_path):
        collector = CopilotOtelCollector(otel_dir=tmp_path)
        collector.setup(agent="copilot-dev")
        path = Path(collector.env["COPILOT_OTEL_FILE_EXPORTER_PATH"])
        path.write_text("", encoding="utf-8")
        assert path.exists()
        collector.close()
        assert not path.exists()
        assert collector.env == {}


def _write_kimi_index(path: Path, entries: list) -> None:
    """Write a minimal `session_index.jsonl` for Kimi collector tests.

    Each entry is a dict merged over the defaults below; pass
    `{"sessionId": ..., "sessionDir": ...}` at minimum.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for entry in entries:
        record = {"workDir": "C:/irrelevant"}
        record.update(entry)
        lines.append(json.dumps(record))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_kimi_wire(
    path: Path,
    *,
    usage_records: list,
    trailing_partial: bool = False,
) -> None:
    """Write a minimal Kimi Code `wire.jsonl` for collector tests.

    `usage_records` is a list of `(model_alias, usage_dict)` tuples, each
    becoming one `usage.record` line with `usageScope="turn"`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "metadata", "protocol_version": "1.5", "created_at": 0})]
    for model_alias, usage in usage_records:
        lines.append(
            json.dumps(
                {
                    "type": "usage.record",
                    "model": model_alias,
                    "usage": usage,
                    "usageScope": "turn",
                    "time": 0,
                }
            )
        )
    text = "\n".join(lines) + "\n"
    if trailing_partial:
        text += '{"type":"usage.record","model":"kimi-code/kimi-for-cod'
    path.write_text(text, encoding="utf-8")


# Field shapes below (usage.record's inputOther/inputCacheRead/inputCacheCreation/
# output, llm.request.maxTokens, session_index.jsonl's sessionId/sessionDir/workDir,
# and `kimi provider list --json`'s models.<alias>.maxContextSize) are all taken
# from real files/output captured live against Kimi Code CLI 0.29.1.


class TestResolveKimiWirePath:
    """Tests for _resolve_kimi_wire_path (task 3.11)."""

    def test_resolves_by_exact_session_id(self, tmp_path):
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        _write_kimi_wire(wire, usage_records=[])
        _write_kimi_index(
            index,
            [{"sessionId": "session_abc", "sessionDir": str(session_dir).replace("\\", "/")}],
        )
        resolved = _resolve_kimi_wire_path("session_abc", kimi_home=tmp_path)
        assert resolved == wire

    def test_no_index_file_returns_none(self, tmp_path):
        assert _resolve_kimi_wire_path("session_abc", kimi_home=tmp_path) is None

    def test_no_matching_session_id_returns_none(self, tmp_path):
        index = tmp_path / "session_index.jsonl"
        _write_kimi_index(index, [{"sessionId": "session_other", "sessionDir": "C:/nope"}])
        assert _resolve_kimi_wire_path("session_abc", kimi_home=tmp_path) is None

    def test_matching_index_entry_but_missing_wire_file_returns_none(self, tmp_path):
        """A stale index entry (session dir listed but never actually
        produced a main-agent wire.jsonl) must not resolve to a
        nonexistent path."""
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        session_dir.mkdir(parents=True)
        _write_kimi_index(
            index,
            [{"sessionId": "session_abc", "sessionDir": str(session_dir).replace("\\", "/")}],
        )
        assert _resolve_kimi_wire_path("session_abc", kimi_home=tmp_path) is None

    def test_malformed_index_lines_are_skipped(self, tmp_path):
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        _write_kimi_wire(wire, usage_records=[])
        index.parent.mkdir(parents=True, exist_ok=True)
        index.write_text(
            "not json at all\n"
            + json.dumps(
                {
                    "sessionId": "session_abc",
                    "sessionDir": str(session_dir).replace("\\", "/"),
                    "workDir": "C:/irrelevant",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        assert _resolve_kimi_wire_path("session_abc", kimi_home=tmp_path) == wire


class TestKimiWireUsageSample:
    """Tests for _kimi_wire_usage_sample (tasks 3.12, 3.13)."""

    def test_single_turn_arithmetic(self, tmp_path):
        """Context tokens = inputOther + inputCacheRead + inputCacheCreation
        + output (confirmed live)."""
        path = tmp_path / "wire.jsonl"
        _write_kimi_wire(
            path,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {
                        "inputOther": 18390,
                        "inputCacheRead": 10496,
                        "inputCacheCreation": 0,
                        "output": 29,
                    },
                )
            ],
        )
        sample = _kimi_wire_usage_sample(path, session_id="session_abc")
        assert sample is not None
        assert sample.status == "measured"
        assert sample.basis == "provider_context"
        assert sample.context_tokens == 18390 + 10496 + 29
        assert sample.model == "kimi-code/kimi-for-coding"
        assert sample.session_id == "session_abc"
        assert sample.limit_tokens is None  # no resolve_limit passed

    def test_multi_turn_uses_latest_not_accumulated(self, tmp_path):
        """A 3-turn session's later usage.record must win outright -- never
        summed with earlier turns (confirmed live: turn 2 moved most of turn
        1's input into cache_read, exactly like the OpenCode/Codex rule)."""
        path = tmp_path / "wire.jsonl"
        _write_kimi_wire(
            path,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {
                        "inputOther": 13130,
                        "inputCacheRead": 10496,
                        "inputCacheCreation": 0,
                        "output": 49,
                    },
                ),
                (
                    "kimi-code/kimi-for-coding",
                    {
                        "inputOther": 174,
                        "inputCacheRead": 23552,
                        "inputCacheCreation": 0,
                        "output": 40,
                    },
                ),
                (
                    "kimi-code/kimi-for-coding",
                    {
                        "inputOther": 349,
                        "inputCacheRead": 23552,
                        "inputCacheCreation": 0,
                        "output": 66,
                    },
                ),
            ],
        )
        sample = _kimi_wire_usage_sample(path, session_id="session_abc")
        assert sample is not None
        assert sample.context_tokens == 349 + 23552 + 66

    def test_cache_creation_included_once(self, tmp_path):
        path = tmp_path / "wire.jsonl"
        _write_kimi_wire(
            path,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {
                        "inputOther": 100,
                        "inputCacheRead": 50,
                        "inputCacheCreation": 25,
                        "output": 10,
                    },
                )
            ],
        )
        sample = _kimi_wire_usage_sample(path, session_id="session_abc")
        assert sample is not None
        assert sample.context_tokens == 100 + 50 + 25 + 10
        assert sample.breakdown["cache_creation_tokens"] == 25

    def test_llm_request_maxtokens_never_used_as_limit(self, tmp_path):
        """Adversarial: a huge, decreasing `llm.request.maxTokens` sits right
        next to the real usage.record in the same file (confirmed live:
        262144 -> 238469 -> 238378 across turns while the real context
        window stayed fixed) -- it must never leak into limit_tokens even
        without a resolve_limit callback."""
        path = tmp_path / "wire.jsonl"
        lines = [
            json.dumps({"type": "metadata", "protocol_version": "1.5", "created_at": 0}),
            json.dumps(
                {
                    "type": "llm.request",
                    "maxTokens": 999999999,
                    "model": "kimi-for-coding",
                    "modelAlias": "kimi-code/kimi-for-coding",
                    "time": 0,
                }
            ),
            json.dumps(
                {
                    "type": "usage.record",
                    "model": "kimi-code/kimi-for-coding",
                    "usage": {
                        "inputOther": 100,
                        "inputCacheRead": 0,
                        "inputCacheCreation": 0,
                        "output": 5,
                    },
                    "usageScope": "turn",
                    "time": 0,
                }
            ),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        sample = _kimi_wire_usage_sample(path, session_id="session_abc")
        assert sample is not None
        assert sample.context_tokens == 105
        assert sample.limit_tokens is None
        assert 999999999 not in (sample.breakdown or {}).values()

    def test_non_turn_usage_scope_is_ignored(self, tmp_path):
        """An accumulated/session-scoped usage record (hypothetical -- never
        observed live, but explicitly excluded per task 3.13) must not
        become the context-size source."""
        path = tmp_path / "wire.jsonl"
        lines = [
            json.dumps({"type": "metadata", "protocol_version": "1.5", "created_at": 0}),
            json.dumps(
                {
                    "type": "usage.record",
                    "model": "kimi-code/kimi-for-coding",
                    "usage": {
                        "inputOther": 999999,
                        "inputCacheRead": 0,
                        "inputCacheCreation": 0,
                        "output": 0,
                    },
                    "usageScope": "session",
                    "time": 0,
                }
            ),
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert _kimi_wire_usage_sample(path, session_id="session_abc") is None

    def test_resolve_limit_callback_supplies_limit_tokens(self, tmp_path):
        path = tmp_path / "wire.jsonl"
        _write_kimi_wire(
            path,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {"inputOther": 100, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
        )
        sample = _kimi_wire_usage_sample(
            path, session_id="session_abc", resolve_limit=lambda model: 262144
        )
        assert sample is not None
        assert sample.limit_tokens == 262144

    def test_partial_final_line_is_skipped(self, tmp_path):
        path = tmp_path / "wire.jsonl"
        _write_kimi_wire(
            path,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {"inputOther": 200, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
            trailing_partial=True,
        )
        sample = _kimi_wire_usage_sample(path, session_id="session_abc")
        assert sample is not None
        assert sample.context_tokens == 200

    def test_no_usage_record_returns_none(self, tmp_path):
        path = tmp_path / "wire.jsonl"
        _write_kimi_wire(path, usage_records=[])
        assert _kimi_wire_usage_sample(path, session_id="session_abc") is None

    def test_missing_file_returns_none(self, tmp_path):
        assert _kimi_wire_usage_sample(tmp_path / "nope.jsonl", session_id="session_abc") is None


class TestKimiModelContextLimit:
    """Tests for _kimi_model_context_limit (task 3.12)."""

    def test_resolves_max_context_size(self):
        catalog = {"models": {"kimi-code/kimi-for-coding": {"maxContextSize": 262144}}}
        assert _kimi_model_context_limit(catalog, "kimi-code/kimi-for-coding") == 262144

    def test_prefers_max_input_tokens_when_present(self):
        catalog = {
            "models": {
                "kimi-code/kimi-for-coding": {"maxInputTokens": 200000, "maxContextSize": 262144}
            }
        }
        assert _kimi_model_context_limit(catalog, "kimi-code/kimi-for-coding") == 200000

    def test_unknown_model_returns_none(self):
        catalog = {"models": {"kimi-code/kimi-for-coding": {"maxContextSize": 262144}}}
        assert _kimi_model_context_limit(catalog, "kimi-code/unknown-model") is None

    def test_none_catalog_returns_none(self):
        assert _kimi_model_context_limit(None, "kimi-code/kimi-for-coding") is None

    def test_none_model_alias_returns_none(self):
        catalog = {"models": {"kimi-code/kimi-for-coding": {"maxContextSize": 262144}}}
        assert _kimi_model_context_limit(catalog, None) is None

    def test_zero_or_negative_limit_is_rejected(self):
        catalog = {"models": {"kimi-code/kimi-for-coding": {"maxContextSize": 0}}}
        assert _kimi_model_context_limit(catalog, "kimi-code/kimi-for-coding") is None


class TestKimiWireCollector:
    """Tests for KimiWireCollector (tasks 3.11-3.14)."""

    def test_is_a_runner_usage_collector(self):
        assert issubclass(KimiWireCollector, RunnerUsageCollector)

    def test_observe_before_bind_returns_none(self, tmp_path):
        collector = KimiWireCollector(kimi_home=tmp_path)
        assert collector.observe() is None

    def test_observe_missing_index_returns_none(self, tmp_path):
        collector = KimiWireCollector(kimi_home=tmp_path)
        collector.bind(session_id="session_abc")
        assert collector.observe() is None

    def test_observe_resolves_and_reads_bound_session(self, tmp_path):
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        _write_kimi_wire(
            wire,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {"inputOther": 300, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
        )
        _write_kimi_index(
            index,
            [{"sessionId": "session_abc", "sessionDir": str(session_dir).replace("\\", "/")}],
        )
        collector = KimiWireCollector(kimi_home=tmp_path)
        collector.bind(session_id="session_abc")
        with patch(
            "agentweave.watchdog._kimi_provider_catalog",
            return_value={"models": {"kimi-code/kimi-for-coding": {"maxContextSize": 262144}}},
        ):
            sample = collector.observe()
        assert sample is not None
        assert sample.context_tokens == 300
        assert sample.limit_tokens == 262144
        assert sample.session_id == "session_abc"

    def test_missing_model_capability_yields_token_only_sample(self, tmp_path):
        """Unknown model limits SHALL produce a token-only sample, not zero."""
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        _write_kimi_wire(
            wire,
            usage_records=[
                (
                    "kimi-code/some-new-model",
                    {"inputOther": 400, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
        )
        _write_kimi_index(
            index,
            [{"sessionId": "session_abc", "sessionDir": str(session_dir).replace("\\", "/")}],
        )
        collector = KimiWireCollector(kimi_home=tmp_path)
        collector.bind(session_id="session_abc")
        with patch("agentweave.watchdog._kimi_provider_catalog", return_value={"models": {}}):
            sample = collector.observe()
        assert sample is not None
        assert sample.context_tokens == 400
        assert sample.limit_tokens is None
        assert sample.percent is None

    def test_catalog_fetched_only_once_per_collector(self, tmp_path):
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        _write_kimi_wire(
            wire,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {"inputOther": 100, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
        )
        _write_kimi_index(
            index,
            [{"sessionId": "session_abc", "sessionDir": str(session_dir).replace("\\", "/")}],
        )
        collector = KimiWireCollector(kimi_home=tmp_path)
        collector.bind(session_id="session_abc")
        with patch(
            "agentweave.watchdog._kimi_provider_catalog",
            return_value={"models": {"kimi-code/kimi-for-coding": {"maxContextSize": 262144}}},
        ) as mock_catalog:
            collector.observe()
            collector.observe()
            collector.final_poll()
        assert mock_catalog.call_count == 1

    def test_final_poll_reflects_late_write(self, tmp_path):
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        _write_kimi_index(
            index,
            [{"sessionId": "session_abc", "sessionDir": str(session_dir).replace("\\", "/")}],
        )
        collector = KimiWireCollector(kimi_home=tmp_path)
        collector.bind(session_id="session_abc")
        with patch("agentweave.watchdog._kimi_provider_catalog", return_value=None):
            assert collector.observe() is None  # nothing written yet
            _write_kimi_wire(
                wire,
                usage_records=[
                    (
                        "kimi-code/kimi-for-coding",
                        {
                            "inputOther": 500,
                            "inputCacheRead": 0,
                            "inputCacheCreation": 0,
                            "output": 0,
                        },
                    )
                ],
            )
            sample = collector.final_poll()
        assert sample is not None
        assert sample.context_tokens == 500

    def test_rebind_to_different_session_forces_reresolution(self, tmp_path):
        """A stale wire path cached from a previous bind must not leak into a
        different session (stale-session-directory guard)."""
        index = tmp_path / "session_index.jsonl"
        first_dir = tmp_path / "sessions" / "wd_x" / "session_first"
        second_dir = tmp_path / "sessions" / "wd_x" / "session_second"
        _write_kimi_wire(
            first_dir / "agents" / "main" / "wire.jsonl",
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {"inputOther": 111, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
        )
        _write_kimi_wire(
            second_dir / "agents" / "main" / "wire.jsonl",
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {"inputOther": 222, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
        )
        _write_kimi_index(
            index,
            [
                {"sessionId": "session_first", "sessionDir": str(first_dir).replace("\\", "/")},
                {"sessionId": "session_second", "sessionDir": str(second_dir).replace("\\", "/")},
            ],
        )
        collector = KimiWireCollector(kimi_home=tmp_path)
        with patch("agentweave.watchdog._kimi_provider_catalog", return_value=None):
            collector.bind(session_id="session_first")
            assert collector.observe().context_tokens == 111
            collector.bind(session_id="session_second")
            assert collector.observe().context_tokens == 222

    def test_close_clears_cached_state(self, tmp_path):
        index = tmp_path / "session_index.jsonl"
        session_dir = tmp_path / "sessions" / "wd_x" / "session_abc"
        wire = session_dir / "agents" / "main" / "wire.jsonl"
        _write_kimi_wire(
            wire,
            usage_records=[
                (
                    "kimi-code/kimi-for-coding",
                    {"inputOther": 100, "inputCacheRead": 0, "inputCacheCreation": 0, "output": 0},
                )
            ],
        )
        _write_kimi_index(
            index,
            [{"sessionId": "session_abc", "sessionDir": str(session_dir).replace("\\", "/")}],
        )
        collector = KimiWireCollector(kimi_home=tmp_path)
        collector.bind(session_id="session_abc")
        with patch("agentweave.watchdog._kimi_provider_catalog", return_value=None):
            assert collector.observe() is not None
            collector.close()
            assert collector._wire_path is None
            assert collector._catalog is None
            assert collector._catalog_fetched is False
            # Still resolvable again after close (close only clears the cache).
            assert collector.observe() is not None


class TestOpencodeModelsCatalog:
    """Tests for _opencode_models_catalog (task 3.15)."""

    def test_reads_valid_catalog_file(self, tmp_path):
        catalog = {"opencode": {"models": {"big-pickle": {"limit": {"input": 160000}}}}}
        (tmp_path / "models.json").write_text(json.dumps(catalog), encoding="utf-8")
        assert _opencode_models_catalog(tmp_path) == catalog

    def test_missing_file_returns_none(self, tmp_path):
        assert _opencode_models_catalog(tmp_path) is None

    def test_malformed_json_returns_none(self, tmp_path):
        (tmp_path / "models.json").write_text("{not valid json", encoding="utf-8")
        assert _opencode_models_catalog(tmp_path) is None

    def test_non_dict_json_returns_none(self, tmp_path):
        (tmp_path / "models.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert _opencode_models_catalog(tmp_path) is None


class TestOpencodeModelContextLimit:
    """Tests for _opencode_model_context_limit (task 3.15).

    Fixture shapes match the real `~/.cache/opencode/models.json` catalog
    live-verified against installed OpenCode 1.18.5: `opencode/big-pickle`
    declares `limit.input`; `minimax-coding-plan/MiniMax-M2` declares only
    `limit.context`.
    """

    def test_prefers_declared_input_limit(self):
        catalog = {
            "opencode": {"models": {"big-pickle": {"limit": {"context": 200000, "input": 160000}}}}
        }
        assert _opencode_model_context_limit(catalog, "opencode/big-pickle") == 160000

    def test_falls_back_to_context_limit_when_no_input_limit(self):
        catalog = {
            "minimax-coding-plan": {
                "models": {"MiniMax-M2": {"limit": {"context": 196608, "output": 128000}}}
            }
        }
        assert _opencode_model_context_limit(catalog, "minimax-coding-plan/MiniMax-M2") == 196608

    def test_model_switch_resolves_the_newly_requested_model(self):
        catalog = {
            "opencode": {
                "models": {
                    "big-pickle": {"limit": {"input": 160000}},
                    "deepseek-v4-flash-free": {"limit": {"context": 200000}},
                }
            }
        }
        assert _opencode_model_context_limit(catalog, "opencode/big-pickle") == 160000
        assert _opencode_model_context_limit(catalog, "opencode/deepseek-v4-flash-free") == 200000

    def test_model_id_containing_a_slash_splits_on_first_only(self):
        # Confirmed live: the "anyapi" provider's model IDs can themselves contain a
        # "/" (e.g. "google/gemini-2.5-flash"), so only the first "/" separates the
        # provider from the model ID.
        catalog = {"anyapi": {"models": {"google/gemini-2.5-flash": {"limit": {"input": 1000}}}}}
        assert _opencode_model_context_limit(catalog, "anyapi/google/gemini-2.5-flash") == 1000

    def test_unknown_provider_returns_none(self):
        catalog = {"opencode": {"models": {"big-pickle": {"limit": {"input": 160000}}}}}
        assert _opencode_model_context_limit(catalog, "unknown-provider/big-pickle") is None

    def test_unknown_model_returns_none(self):
        catalog = {"opencode": {"models": {"big-pickle": {"limit": {"input": 160000}}}}}
        assert _opencode_model_context_limit(catalog, "opencode/unknown-model") is None

    def test_none_catalog_returns_none(self):
        assert _opencode_model_context_limit(None, "opencode/big-pickle") is None

    def test_none_model_returns_none(self):
        catalog = {"opencode": {"models": {"big-pickle": {"limit": {"input": 160000}}}}}
        assert _opencode_model_context_limit(catalog, None) is None

    def test_model_without_slash_returns_none(self):
        catalog = {"opencode": {"models": {"big-pickle": {"limit": {"input": 160000}}}}}
        assert _opencode_model_context_limit(catalog, "big-pickle") is None

    def test_missing_limit_metadata_returns_none(self):
        catalog = {"opencode": {"models": {"big-pickle": {}}}}
        assert _opencode_model_context_limit(catalog, "opencode/big-pickle") is None

    def test_zero_or_negative_limit_is_rejected(self):
        catalog = {"opencode": {"models": {"big-pickle": {"limit": {"input": 0, "context": -5}}}}}
        assert _opencode_model_context_limit(catalog, "opencode/big-pickle") is None


class TestOpencodeUsageSampleWithLimit:
    """Tests for _opencode_usage_sample's optional model/limit_tokens params (task 3.15)."""

    def test_defaults_have_no_model_or_limit(self):
        sample = _opencode_usage_sample(
            {"total": 100, "input": 90, "output": 10, "reasoning": 0}, source="opencode"
        )
        assert sample.model is None
        assert sample.limit_tokens is None

    def test_model_and_limit_tokens_pass_through(self):
        sample = _opencode_usage_sample(
            {"total": 100, "input": 90, "output": 10, "reasoning": 0},
            source="opencode",
            model="opencode/big-pickle",
            limit_tokens=160000,
        )
        assert sample.model == "opencode/big-pickle"
        assert sample.limit_tokens == 160000
        assert sample.context_tokens == 100


class TestNewRunId:
    """_new_run_id (task 4.1): a fresh opaque id for one runner process invocation."""

    def test_returns_string(self):
        assert isinstance(_new_run_id(), str)

    def test_successive_calls_are_unique(self):
        ids = {_new_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_uses_run_prefix_like_other_generated_ids(self):
        # generate_id("run") -> "run-<32 hex chars>"; asserting the convention
        # is followed, not a specific implementation, so this stays loose.
        run_id = _new_run_id()
        assert run_id.startswith("run-")


class TestAssignSequence:
    """_assign_sequence (task 4.2): strictly increasing sequence values, assigned
    in order, after normalization and before the existing text-delivery channel."""

    def test_empty_list_returns_empty_contents(self):
        counter = itertools.count(1)
        assert _assign_sequence([], counter) == []
        assert next(counter) == 1  # counter untouched by an empty batch

    def test_assigns_strictly_increasing_sequence_in_order(self):
        events = [text_event("first"), text_event("second"), text_event("third")]
        counter = itertools.count(1)
        contents = _assign_sequence(events, counter)
        assert contents == ["first", "second", "third"]
        assert [e.sequence for e in events] == [1, 2, 3]

    def test_shares_counter_across_calls_from_the_same_run(self):
        counter = itertools.count(1)
        first_batch = [text_event("a")]
        second_batch = [text_event("b"), text_event("c")]
        _assign_sequence(first_batch, counter)
        _assign_sequence(second_batch, counter)
        assert [e.sequence for e in first_batch] == [1]
        assert [e.sequence for e in second_batch] == [2, 3]


class TestStdoutLineWrapperRunIdThreading:
    """The codex/copilot/claude stdout-line wrappers (task 4.1) accept an
    optional run_id and thread it through to every normalized event, matching
    the opencode wrapper's existing behavior and the underlying
    _parse_*_stream_line functions' existing run_id parameter."""

    def test_codex_wrapper_threads_run_id(self):
        line = json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}
        )
        parsed, _stale = _parse_codex_stdout_line(line, "codex", [None], run_id="run-abc")
        assert parsed.events
        assert all(e.run_id == "run-abc" for e in parsed.events)

    def test_codex_wrapper_defaults_run_id_to_none(self):
        line = json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}
        )
        parsed, _stale = _parse_codex_stdout_line(line, "codex", [None])
        assert all(e.run_id is None for e in parsed.events)

    def test_copilot_wrapper_threads_run_id(self):
        line = json.dumps({"type": "assistant.message", "data": {"content": "hi there"}})
        parsed = _parse_copilot_stdout_line(line, "copilot", [None], run_id="run-def")
        assert parsed.events
        assert all(e.run_id == "run-def" for e in parsed.events)

    def test_claude_wrapper_threads_run_id(self):
        line = json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "hi"}]},
            }
        )
        parsed = _parse_claude_stdout_line(line, "claude", [None], run_id="run-ghi")
        assert parsed.events
        assert all(e.run_id == "run-ghi" for e in parsed.events)


class TestKimiCodeStdoutLineRunIdAndSequence:
    """_parse_kimi_stdout_line's v0.29.x (kimi_code) branch (task 4.1/4.2):
    threads run_id into the parser and, when given a sequence counter,
    assigns sequence numbers the same way the other four runners' branches do."""

    def test_threads_run_id_and_assigns_sequence(self):
        proc = MagicMock()
        proc.stdin = None
        parser = _KimiCodeParser()
        line = json.dumps({"role": "assistant", "content": "hello"})
        counter = itertools.count(1)

        readable_lines, _usage, _compaction, _lines = _parse_kimi_stdout_line(
            line,
            parser,
            proc,
            agent="kimi-agent",
            is_wire_mode=False,
            is_kimi_code=True,
            session_id_ref=[None],
            was_in_compaction=False,
            kimi_stdout_lines=[],
            run_id="run-kimi",
            sequence_counter=counter,
        )
        assert readable_lines == ["hello"]
        assert next(counter) == 2  # one event consumed sequence 1

    def test_without_sequence_counter_falls_back_to_content_only(self):
        """Existing callers/tests that don't pass sequence_counter keep working."""
        proc = MagicMock()
        proc.stdin = None
        parser = _KimiCodeParser()
        line = json.dumps({"role": "assistant", "content": "hello"})

        readable_lines, _usage, _compaction, _lines = _parse_kimi_stdout_line(
            line,
            parser,
            proc,
            agent="kimi-agent",
            is_wire_mode=False,
            is_kimi_code=True,
            session_id_ref=[None],
            was_in_compaction=False,
            kimi_stdout_lines=[],
        )
        assert readable_lines == ["hello"]


def _fake_proc(stdout_lines, stderr_lines, returncode):
    """Build a MagicMock standing in for a subprocess.Popen result."""
    proc = MagicMock()
    proc.stdout = iter(stdout_lines)
    proc.stderr = iter(stderr_lines)
    proc.stdin = None
    proc.wait.return_value = returncode
    proc.returncode = returncode
    return proc


def _prepare_codex_agent(tmp_path, monkeypatch, agent="codex-agent"):
    """Shared setup for the _run_agent_subprocess lifecycle-event tests below:
    an isolated cwd, a codex-runner session, and locking/blocker bypasses so
    the call reaches _do_run_agent_subprocess."""
    from agentweave.session import Session

    monkeypatch.chdir(tmp_path)
    session = Session.create(name="Test", agents=[agent])
    session.set_runner_config(agent, "codex", {})
    session.save()
    monkeypatch.setattr("agentweave.locking.acquire_lock", lambda *_a, **_k: True)
    monkeypatch.setattr("agentweave.locking.release_lock", lambda *_a, **_k: None)
    monkeypatch.setattr("agentweave.diagnostics.launch_blockers", lambda *_a, **_k: [])
    return agent


class TestLifecycleEventsCompletionAndRunError:
    """task 4.3: the end-of-run summary is now backed by a canonical
    status_event("completed", ...) on success or error_event(...) on a
    non-zero exit, delivered through the existing text channel."""

    def test_successful_run_posts_unchanged_done_summary(self, tmp_path, monkeypatch):
        from agentweave import watchdog as wd

        agent = _prepare_codex_agent(tmp_path, monkeypatch)
        proc = _fake_proc([], [], 0)
        monkeypatch.setattr(wd.subprocess, "Popen", MagicMock(return_value=proc))
        transport = MagicMock()

        _run_agent_subprocess(agent, ["codex", "exec"], "subject", transport, True)

        posted = [c.args[1] for c in transport.post_agent_output.call_args_list]
        assert any("done" in p and "✅" in p for p in posted)
        assert not any("exited with code" in p for p in posted)

    def test_nonzero_exit_posts_new_run_error_message(self, tmp_path, monkeypatch):
        """Before task 4.3, a non-zero exit silently still said '✅ done' to the
        user; this is the behavior this task fixes."""
        from agentweave import watchdog as wd

        agent = _prepare_codex_agent(tmp_path, monkeypatch)
        proc = _fake_proc([], [], 1)
        monkeypatch.setattr(wd.subprocess, "Popen", MagicMock(return_value=proc))
        transport = MagicMock()

        _run_agent_subprocess(agent, ["codex", "exec"], "subject", transport, True)

        posted = [c.args[1] for c in transport.post_agent_output.call_args_list]
        assert any("exited with code 1" in p and "❌" in p for p in posted)
        assert not any("✅" in p and "done" in p for p in posted)

    def test_copilot_auth_failure_posts_unchanged_actionable_message(self, tmp_path, monkeypatch):
        from agentweave import watchdog as wd
        from agentweave.session import Session

        agent = "copilot-agent"
        monkeypatch.chdir(tmp_path)
        session = Session.create(name="Test", agents=[agent])
        session.set_runner_config(agent, "copilot", {})
        session.save()
        monkeypatch.setattr("agentweave.locking.acquire_lock", lambda *_a, **_k: True)
        monkeypatch.setattr("agentweave.locking.release_lock", lambda *_a, **_k: None)
        monkeypatch.setattr("agentweave.diagnostics.launch_blockers", lambda *_a, **_k: [])
        proc = _fake_proc([], ["No authentication information found"], 1)
        monkeypatch.setattr(wd.subprocess, "Popen", MagicMock(return_value=proc))
        transport = MagicMock()

        _run_agent_subprocess(agent, ["copilot"], "subject", transport, True)

        posted = [c.args[1] for c in transport.post_agent_output.call_args_list]
        assert any("authentication error" in p for p in posted)
        assert not any("exited with code" in p for p in posted)


class TestLifecycleEventsSkipped:
    """task 4.3: the two already-user-visible skip points (launch blockers,
    copilot cross-agent lock timeout) now deliver a canonical
    status_event("skipped", ...), with unchanged visible text."""

    def test_launch_blocker_skip_posts_skipped_event(self, tmp_path, monkeypatch):
        from agentweave.diagnostics import DiagnosticResult

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr("agentweave.locking.acquire_lock", lambda *_a, **_k: True)
        monkeypatch.setattr("agentweave.locking.release_lock", lambda *_a, **_k: None)
        blocker = DiagnosticResult(
            id="proxy_api_key_missing",
            target="some-agent",
            status="blocked",
            severity="error",
            message="API key missing",
            hint="set it",
        )
        monkeypatch.setattr("agentweave.diagnostics.launch_blockers", lambda *_a, **_k: [blocker])
        transport = MagicMock()

        _run_agent_subprocess("some-agent", ["cmd"], "subject", transport, True)

        posted = [c.args[1] for c in transport.post_agent_output.call_args_list]
        assert any("Launch skipped for some-agent" in p for p in posted)

    def test_copilot_lock_timeout_skip_posts_skipped_event(self, tmp_path, monkeypatch):
        from agentweave.session import Session

        agent = "copilot-agent"
        monkeypatch.chdir(tmp_path)
        session = Session.create(name="Test", agents=[agent])
        session.set_runner_config(agent, "copilot", {})
        session.save()

        def _acquire_lock(name, timeout=None):
            return not name.startswith("spawn_runner_")

        monkeypatch.setattr("agentweave.locking.acquire_lock", _acquire_lock)
        monkeypatch.setattr("agentweave.locking.release_lock", lambda *_a, **_k: None)
        transport = MagicMock()

        _run_agent_subprocess(agent, ["copilot"], "subject", transport, True)

        posted = [c.args[1] for c in transport.post_agent_output.call_args_list]
        assert any("queued too long" in p for p in posted)


class TestLifecycleEventRetrying:
    """task 4.1/4.3: a Codex stale-session retry now posts a canonical
    "retrying" status event (previously silent to the user), and the retried
    invocation gets its own fresh run_id, not a reused one."""

    def test_retry_posts_retrying_message_with_fresh_run_id(self, tmp_path, monkeypatch):
        from agentweave import watchdog as wd

        agent = _prepare_codex_agent(tmp_path, monkeypatch)
        stale_line = json.dumps(
            {"type": "error", "message": "Session not found for thread_id abc-123"}
        )
        fresh_line = json.dumps({"type": "session.info"})
        proc1 = _fake_proc([stale_line], [], 0)
        proc2 = _fake_proc([fresh_line], [], 0)
        monkeypatch.setattr(wd.subprocess, "Popen", MagicMock(side_effect=[proc1, proc2]))
        monkeypatch.setattr(wd, "_clear_agent_session", lambda *_a, **_k: None)

        recorded_run_ids = []
        real_parse = wd._parse_codex_stdout_line

        def _recording_parse(line, runner_type, session_id_ref, *, run_id=None):
            recorded_run_ids.append(run_id)
            return real_parse(line, runner_type, session_id_ref, run_id=run_id)

        monkeypatch.setattr(wd, "_parse_codex_stdout_line", _recording_parse)
        transport = MagicMock()

        _run_agent_subprocess(
            agent,
            ["codex", "exec"],
            "subject",
            transport,
            True,
            prompt="continue",
            known_session_id="abc-123",
        )

        posted = [c.args[1] for c in transport.post_agent_output.call_args_list]
        assert any("retrying" in p.lower() for p in posted)
        assert len(recorded_run_ids) == 2
        assert recorded_run_ids[0] is not None
        assert recorded_run_ids[1] is not None
        assert recorded_run_ids[0] != recorded_run_ids[1]


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
