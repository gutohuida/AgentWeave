"""Tests for runner_commands.build_command and runner_parsing.parse_*_line.

The JSONL fixtures below are trimmed real output captured from live headless spawns
against this repo's actual installed CLIs (Claude Code 2.1.220, codex-cli 0.146.0) during
task 3.5's implementation — not hand-guessed shapes.
"""

import pytest

from hub.runner_commands import UnsupportedRunnerError, build_command
from hub.runner_parsing import parse_claude_line, parse_codex_line


class TestBuildCommandClaude:
    def test_new_session_minimal(self):
        cmd = build_command(runner="claude", cli="claude", prompt="hello")
        assert cmd == ["claude", "--output-format", "stream-json", "--verbose", "-p", "hello"]

    def test_resume_appends_flag(self):
        cmd = build_command(runner="claude", cli="claude", prompt="hi", session_id="sess-123")
        assert "--resume" in cmd
        assert cmd[cmd.index("--resume") + 1] == "sess-123"

    def test_model_flag(self):
        cmd = build_command(runner="claude", cli="claude", prompt="hi", model="claude-opus-4")
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "claude-opus-4"

    def test_yolo_adds_dangerously_skip_permissions(self):
        cmd = build_command(runner="claude", cli="claude", prompt="hi", yolo=True)
        assert "--dangerously-skip-permissions" in cmd

    def test_no_yolo_omits_permission_flag(self):
        cmd = build_command(runner="claude", cli="claude", prompt="hi", yolo=False)
        assert "--dangerously-skip-permissions" not in cmd

    def test_context_file_injected_only_if_it_exists(self, tmp_path):
        missing = tmp_path / "nope.md"
        cmd = build_command(runner="claude", cli="claude", prompt="hi", context_file=missing)
        assert "--append-system-prompt-file" not in cmd

        present = tmp_path / "context.md"
        present.write_text("system prompt")
        cmd = build_command(runner="claude", cli="claude", prompt="hi", context_file=present)
        assert "--append-system-prompt-file" in cmd
        assert cmd[cmd.index("--append-system-prompt-file") + 1] == str(present)

    def test_claude_proxy_and_native_use_the_same_construction(self):
        for runner in ("claude_proxy", "native"):
            cmd = build_command(runner=runner, cli="claude", prompt="hi")
            assert cmd == ["claude", "--output-format", "stream-json", "--verbose", "-p", "hi"]

    def test_prompt_is_always_the_final_argument(self):
        cmd = build_command(
            runner="claude", cli="claude", prompt="hi", model="x", session_id="s", yolo=True
        )
        assert cmd[-4:] == ["--resume", "s", "-p", "hi"]


class TestBuildCommandCodex:
    def test_new_session_minimal(self):
        cmd = build_command(runner="codex", cli="codex", prompt="hello")
        assert cmd[:2] == ["codex", "exec"]
        assert "--json" in cmd
        assert "--skip-git-repo-check" in cmd
        assert "--sandbox" in cmd  # no yolo -> workspace-write sandbox
        assert cmd[-1] == "hello"

    def test_resume_uses_positional_subcommand(self):
        cmd = build_command(runner="codex", cli="codex", prompt="hi", session_id="thread-abc")
        assert cmd[:4] == ["codex", "exec", "resume", "thread-abc"]

    def test_yolo_bypasses_sandbox(self):
        cmd = build_command(runner="codex", cli="codex", prompt="hi", yolo=True)
        assert "--dangerously-bypass-approvals-and-sandbox" in cmd
        assert "--sandbox" not in cmd

    def test_context_file_uses_dash_c_model_instructions(self, tmp_path):
        ctx = tmp_path / "codex-context.md"
        ctx.write_text("instructions")
        cmd = build_command(runner="codex", cli="codex", prompt="hi", context_file=ctx)
        assert "-c" in cmd
        idx = cmd.index("-c")
        assert cmd[idx + 1] == f"model_instructions_file={ctx}"

    def test_model_flag(self):
        cmd = build_command(runner="codex", cli="codex", prompt="hi", model="gpt-5.5")
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "gpt-5.5"


class TestBuildCommandUnsupported:
    @pytest.mark.parametrize("runner", ["kimi", "opencode", "copilot", "codex_mcp", "manual"])
    def test_unsupported_runner_raises_with_clear_message(self, runner):
        with pytest.raises(UnsupportedRunnerError, match=runner):
            build_command(runner=runner, cli="whatever", prompt="hi")


# Trimmed real output from a live `claude --output-format stream-json --verbose
# --dangerously-skip-permissions -p "Reply with exactly the single word: OK"` invocation.
CLAUDE_INIT_LINE = (
    '{"type":"system","subtype":"init","cwd":"C:\\\\tmp","session_id":'
    '"39ad524c-b7f7-4ae6-a480-2c57ee1180e2","tools":["Bash","Read"],"model":"claude-sonnet-5"}'
)
CLAUDE_ASSISTANT_LINE = (
    '{"type":"assistant","message":{"model":"claude-sonnet-5","content":'
    '[{"type":"text","text":"OK"}],"usage":{"input_tokens":2,'
    '"cache_creation_input_tokens":8615,"cache_read_input_tokens":21375,"output_tokens":1}},'
    '"session_id":"39ad524c-b7f7-4ae6-a480-2c57ee1180e2"}'
)
CLAUDE_TOOL_USE_LINE = (
    '{"type":"assistant","message":{"content":[{"type":"tool_use","id":"call_1",'
    '"name":"Bash","input":{"command":"echo hi"}}]},"session_id":"sess-1"}'
)
CLAUDE_TOOL_RESULT_LINE = (
    '{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"call_1",'
    '"is_error":false,"content":"hi"}]},"session_id":"sess-1"}'
)
CLAUDE_RESULT_LINE = (
    '{"is_error":false,"session_id":"39ad524c-b7f7-4ae6-a480-2c57ee1180e2",'
    '"total_cost_usd":0.0587525,"result":"OK","type":"result","subtype":"success",'
    '"modelUsage":{"claude-haiku-4-5-20251001":{"contextWindow":200000},'
    '"claude-sonnet-5":{"contextWindow":1000000}}}'
)
CLAUDE_ERROR_RESULT_LINE = (
    '{"is_error":true,"session_id":"sess-1","type":"result","subtype":"error_max_turns",'
    '"result":"Max turns reached"}'
)


class TestParseClaudeLine:
    def test_init_line_yields_session_id_no_events(self):
        parsed = parse_claude_line(CLAUDE_INIT_LINE)
        assert parsed.session_id == "39ad524c-b7f7-4ae6-a480-2c57ee1180e2"
        assert parsed.events == []

    def test_assistant_text_event_and_usage(self):
        parsed = parse_claude_line(CLAUDE_ASSISTANT_LINE)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "OK"
        assert parsed.usage is not None
        assert parsed.usage.status == "measured"
        assert parsed.usage.context_tokens == 2 + 21375 + 8615
        assert parsed.session_id == "39ad524c-b7f7-4ae6-a480-2c57ee1180e2"

    def test_tool_use_event(self):
        parsed = parse_claude_line(CLAUDE_TOOL_USE_LINE)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_use"
        assert event.payload["tool"] == "Bash"
        assert event.payload["call_id"] == "call_1"

    def test_tool_result_event(self):
        parsed = parse_claude_line(CLAUDE_TOOL_RESULT_LINE)
        assert len(parsed.events) == 1
        event = parsed.events[0]
        assert event.kind == "tool_result"
        assert event.payload["is_error"] is False
        assert event.payload["call_id"] == "call_1"

    def test_result_line_picks_largest_context_window(self):
        parsed = parse_claude_line(CLAUDE_RESULT_LINE)
        assert parsed.usage is not None
        assert parsed.usage.limit_tokens == 1000000
        assert parsed.usage.model == "claude-sonnet-5"
        assert parsed.events[0].kind == "status"

    def test_error_result_line_yields_error_event(self):
        parsed = parse_claude_line(CLAUDE_ERROR_RESULT_LINE)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "error"
        assert "Max turns reached" in parsed.events[0].content

    def test_malformed_json_falls_back_to_text_event(self):
        parsed = parse_claude_line("not json at all")
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "not json at all"

    def test_blank_line_yields_nothing(self):
        parsed = parse_claude_line("   ")
        assert parsed.events == []
        assert parsed.session_id is None


# Trimmed real output from a live `codex exec --json --skip-git-repo-check
# --dangerously-bypass-approvals-and-sandbox "Reply with exactly the single word: OK"`.
CODEX_THREAD_STARTED_LINE = (
    '{"type":"thread.started","thread_id":"019fbcb2-f137-7d01-9258-703716d57a3b"}'
)
CODEX_TURN_STARTED_LINE = '{"type":"turn.started"}'
CODEX_AGENT_MESSAGE_LINE = (
    '{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"OK"}}'
)
CODEX_COMMAND_STARTED_LINE = (
    '{"type":"item.started","item":{"id":"item_1","type":"command_execution",'
    '"command":"echo hi"}}'
)
CODEX_COMMAND_COMPLETED_LINE = (
    '{"type":"item.completed","item":{"id":"item_1","type":"command_execution",'
    '"exit_code":0,"aggregated_output":"hi\\n"}}'
)
CODEX_TURN_COMPLETED_LINE = (
    '{"type":"turn.completed","usage":{"input_tokens":13690,"cached_input_tokens":11008,'
    '"cache_write_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0}}'
)
CODEX_TURN_FAILED_LINE = '{"type":"turn.failed","error":{"message":"model overloaded"}}'


class TestParseCodexLine:
    def test_thread_started_yields_session_id(self):
        parsed = parse_codex_line(CODEX_THREAD_STARTED_LINE)
        assert parsed.session_id == "019fbcb2-f137-7d01-9258-703716d57a3b"
        assert parsed.events == []

    def test_turn_started_yields_nothing(self):
        parsed = parse_codex_line(CODEX_TURN_STARTED_LINE)
        assert parsed.events == []
        assert parsed.session_id is None

    def test_agent_message_yields_text_event(self):
        parsed = parse_codex_line(CODEX_AGENT_MESSAGE_LINE)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "text"
        assert parsed.events[0].content == "OK"

    def test_command_execution_start_and_end(self):
        started = parse_codex_line(CODEX_COMMAND_STARTED_LINE)
        assert started.events[0].kind == "tool_use"
        assert started.events[0].payload["tool"] == "shell"

        completed = parse_codex_line(CODEX_COMMAND_COMPLETED_LINE)
        assert completed.events[0].kind == "tool_result"
        assert completed.events[0].payload["is_error"] is False

    def test_turn_completed_yields_usage_with_fallback_limit(self):
        parsed = parse_codex_line(CODEX_TURN_COMPLETED_LINE, model="gpt-5.5")
        assert parsed.usage is not None
        assert parsed.usage.status == "estimated"
        assert parsed.usage.context_tokens == 13690 + 5
        assert parsed.usage.limit_tokens == 272000

    def test_turn_completed_unknown_model_uses_default_limit(self):
        parsed = parse_codex_line(CODEX_TURN_COMPLETED_LINE, model="some-future-model")
        assert parsed.usage.limit_tokens == 128000

    def test_turn_failed_yields_error_event(self):
        parsed = parse_codex_line(CODEX_TURN_FAILED_LINE)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "error"
        assert "model overloaded" in parsed.events[0].content

    def test_malformed_json_falls_back_to_text_event(self):
        parsed = parse_codex_line("also not json")
        assert parsed.events[0].kind == "text"
