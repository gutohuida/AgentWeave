"""Tests for runner_commands.build_command and runner_parsing.parse_*_line.

The JSONL fixtures below are trimmed real output captured from live headless spawns
against this repo's actual installed CLIs (Claude Code 2.1.220, codex-cli 0.146.0) during
task 3.5's implementation — not hand-guessed shapes.
"""

import pytest

from hub.runner_commands import UnsupportedRunnerError, build_command
from hub.runner_parsing import (
    parse_claude_line,
    parse_codex_line,
    parse_opencode_line,
    read_codex_rollout_accounting,
)


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

    def test_runner_record_flags_are_inserted_before_prompt(self):
        cmd = build_command(
            runner="claude",
            cli="claude",
            prompt="hi",
            extra_flags=["--effort", "high"],
        )
        assert cmd[-4:] == ["--effort", "high", "-p", "hi"]


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
        resume_index = cmd.index("resume")
        assert cmd[resume_index : resume_index + 2] == ["resume", "thread-abc"]

    def test_resume_keeps_exec_only_sandbox_before_subcommand(self):
        cmd = build_command(runner="codex", cli="codex", prompt="hi", session_id="thread-abc")
        assert cmd.index("--sandbox") < cmd.index("resume")

    def test_resume_keeps_yolo_bypass_before_subcommand(self):
        cmd = build_command(
            runner="codex", cli="codex", prompt="hi", session_id="thread-abc", yolo=True
        )
        assert cmd.index("--dangerously-bypass-approvals-and-sandbox") < cmd.index("resume")

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

    def test_runner_record_flags_are_inserted_before_prompt(self):
        cmd = build_command(
            runner="codex",
            cli="codex",
            prompt="hello",
            extra_flags=["--profile", "review"],
        )
        assert cmd[-3:] == ["--profile", "review", "hello"]


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
CLAUDE_ACCOUNTING_RESULT_LINE = (
    '{"type":"result","subtype":"success","is_error":false,"session_id":"sess-usage",'
    '"total_cost_usd":0.0125,"usage":{"input_tokens":100,"output_tokens":20,'
    '"cache_read_input_tokens":30,"cache_creation_input_tokens":10},'
    '"modelUsage":{"claude-sonnet-5":{"inputTokens":999,"outputTokens":999,'
    '"contextWindow":1000000}}}'
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

    def test_final_result_usage_is_the_accounting_outcome(self):
        partial = parse_claude_line(CLAUDE_ASSISTANT_LINE)
        final = parse_claude_line(CLAUDE_ACCOUNTING_RESULT_LINE)

        assert partial.accounting is None
        assert final.accounting is not None
        assert final.accounting.input_tokens == 140
        assert final.accounting.output_tokens == 20
        assert final.accounting.total_tokens == 160
        assert final.accounting.cache_read_tokens == 30
        assert final.accounting.api_equivalent_usd_micros == 12_500

    def test_model_usage_is_a_fallback_when_result_usage_is_absent(self):
        line = (
            '{"type":"result","subtype":"success","modelUsage":{'
            '"primary":{"inputTokens":10,"outputTokens":2,"cacheReadInputTokens":3},'
            '"helper":{"inputTokens":4,"outputTokens":1}}}'
        )
        accounting = parse_claude_line(line).accounting
        assert accounting is not None
        assert accounting.input_tokens == 17
        assert accounting.output_tokens == 3
        assert accounting.total_tokens == 20

    def test_rate_limit_allowance_merges_with_final_usage(self):
        allowance = parse_claude_line(
            '{"type":"rate_limit_event","rate_limit_info":'
            '{"five_hour":{"remaining_percent":64}}}'
        ).accounting
        final = parse_claude_line(CLAUDE_ACCOUNTING_RESULT_LINE).accounting
        assert allowance is not None and final is not None
        merged = allowance.merged(final)
        assert merged.total_tokens == 160
        assert merged.allowance == {"five_hour": {"remaining_percent": 64}}

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

    def test_turn_completed_yields_usage_from_the_catalogs_context_window(self):
        # 2026-08-04-hub-model-control-and-provisioning: the limit comes from
        # model_catalog.model_context_window, not a local fallback table.
        parsed = parse_codex_line(CODEX_TURN_COMPLETED_LINE, model="gpt-5.5")
        assert parsed.usage is not None
        assert parsed.usage.status == "estimated"
        assert parsed.usage.context_tokens == 13690 + 5
        assert parsed.usage.limit_tokens == 272000
        assert parsed.accounting is not None
        assert parsed.accounting.total_tokens == 13695
        assert parsed.accounting.cache_read_tokens == 11008
        assert parsed.accounting.reasoning_tokens == 0

    def test_turn_completed_unrecognised_model_reports_usage_as_unknown(self):
        # The live symptom this replaces: an unrecognised model used to silently borrow
        # a 128000-token default and could report over 100% of a window that was never
        # actually its own. It now reports unknown usage as unknown instead.
        parsed = parse_codex_line(CODEX_TURN_COMPLETED_LINE, model="some-future-model")
        assert parsed.usage is not None
        assert parsed.usage.status == "unavailable"
        assert parsed.usage.limit_tokens is None
        assert parsed.usage.percent is None

    def test_turn_completed_usage_is_attributed_to_the_model_that_ran_the_turn(self):
        # A conversation whose model changed between turns must not have one turn's
        # usage silently attributed to a different model's window.
        sol = parse_codex_line(CODEX_TURN_COMPLETED_LINE, model="gpt-5.6-sol")
        mini = parse_codex_line(CODEX_TURN_COMPLETED_LINE, model="gpt-5.4-mini")
        assert sol.usage.model == "gpt-5.6-sol"
        assert mini.usage.model == "gpt-5.4-mini"

    def test_turn_completed_usage_never_exceeds_its_own_catalog_window(self):
        parsed = parse_codex_line(CODEX_TURN_COMPLETED_LINE, model="gpt-5.5")
        assert parsed.usage is not None
        assert parsed.usage.percent is not None
        assert parsed.usage.percent <= 100.0

    def test_turn_failed_yields_error_event(self):
        parsed = parse_codex_line(CODEX_TURN_FAILED_LINE)
        assert len(parsed.events) == 1
        assert parsed.events[0].kind == "error"
        assert "model overloaded" in parsed.events[0].content

    def test_rollout_token_count_uses_latest_request_delta_not_cumulative_total(self):
        line = (
            '{"type":"event_msg","payload":{"type":"token_count","info":{'
            '"last_token_usage":{"input_tokens":40,"cached_input_tokens":30,'
            '"output_tokens":5,"reasoning_output_tokens":2,"total_tokens":45},'
            '"total_token_usage":{"total_tokens":999}}}}'
        )
        accounting = parse_codex_line(line).accounting
        assert accounting is not None
        assert accounting.total_tokens == 45
        assert accounting.input_tokens == 40
        assert accounting.reasoning_tokens == 2

    def test_malformed_json_falls_back_to_text_event(self):
        parsed = parse_codex_line("also not json")
        assert parsed.events[0].kind == "text"


class TestParseOpenCodeLine:
    def test_step_finish_normalizes_tokens_cache_reasoning_and_cost(self):
        line = (
            '{"type":"step_finish","part":{"tokens":{"total":12537,"input":217,'
            '"output":10,"reasoning":22,"cache":{"read":12000,"write":288}},'
            '"cost":0.0042}}'
        )
        parsed = parse_opencode_line(line, model="opencode/big-pickle")
        assert parsed.accounting is not None
        assert parsed.accounting.total_tokens == 12537
        assert parsed.accounting.input_tokens == 217
        assert parsed.accounting.cache_read_tokens == 12000
        assert parsed.accounting.cache_write_tokens == 288
        assert parsed.accounting.reasoning_tokens == 22
        assert parsed.accounting.api_equivalent_usd_micros == 4200
        assert parsed.usage is not None
        assert parsed.usage.context_tokens == 12515

    @pytest.mark.parametrize(
        "line",
        [
            "not json",
            '{"type":"step_finish","part":{}}',
            '{"type":"step_finish","part":{"tokens":{"input":"unknown"}}}',
        ],
    )
    def test_malformed_or_missing_telemetry_yields_no_accounting_sample(self, line):
        assert parse_opencode_line(line).accounting is None


def test_codex_rollout_accounting_uses_latest_request_delta(tmp_path):
    rollout_dir = tmp_path / "sessions" / "2026" / "08" / "03"
    rollout_dir.mkdir(parents=True)
    rollout = rollout_dir / "rollout-2026-08-03T01-00-00-thread-abc.jsonl"
    rollout.write_text(
        "\n".join(
            [
                '{"type":"event_msg","payload":{"type":"token_count","info":{'
                '"last_token_usage":{"input_tokens":10,"output_tokens":2,'
                '"total_tokens":12}}}}',
                '{"type":"event_msg","payload":{"type":"token_count","info":{'
                '"last_token_usage":{"input_tokens":20,"cached_input_tokens":15,'
                '"output_tokens":3,"reasoning_output_tokens":1,"total_tokens":23},'
                '"total_token_usage":{"total_tokens":999}}}}',
                "{partial",
            ]
        ),
        encoding="utf-8",
    )

    accounting = read_codex_rollout_accounting(
        "thread-abc", codex_home=tmp_path, model="gpt-5.5"
    )
    assert accounting is not None
    assert accounting.source == "codex_token_count"
    assert accounting.total_tokens == 23
    assert accounting.cache_read_tokens == 15
    assert accounting.reasoning_tokens == 1


def test_codex_rollout_accounting_returns_none_when_session_is_missing(tmp_path):
    assert read_codex_rollout_accounting("missing", codex_home=tmp_path) is None
