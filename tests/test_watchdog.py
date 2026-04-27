"""Tests for watchdog dispatch logic."""

import json
from unittest.mock import patch

import pytest

from agentweave.watchdog import (
    _agent_ping_cmd,
    _extract_jsonl_session_id,
    _parse_codex_stream_line,
    _write_codex_context_usage,
)


class TestAgentPingCmdKimi:
    """Tests for _agent_ping_cmd with kimi runner."""

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

        with patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir), patch(
            "agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir
        ), patch("agentweave.session.Session.load", return_value=self.session):
            yield

    def test_kimi_with_model(self):
        """Model flag is appended when agent config has a model."""
        cmd = _agent_ping_cmd("kimi-dev", "do the task")
        assert cmd == ["kimi", "--wire", "--model", "kimi-k2"]

    def test_kimi_without_model(self):
        """No --model flag when model is not configured."""
        cmd = _agent_ping_cmd("kimi-qa", "do the task")
        assert cmd == ["kimi", "--wire"]

    def test_kimi_resume_with_model(self):
        """Resume keeps the configured model flag."""
        cmd = _agent_ping_cmd("kimi-dev", "do the task", session_id="sess-123")
        assert cmd == ["kimi", "--wire", "--model", "kimi-k2", "--session", "sess-123"]


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
        """Basic dispatch without session or model."""
        cmd = _agent_ping_cmd("opencode-qa", "do the task")
        assert cmd[0] == "opencode"
        assert cmd[1] == "run"
        assert cmd[2] == "--session"
        assert cmd[3] == "agentweave-opencode-qa"
        assert cmd[4] == "--format"
        assert cmd[5] == "json"
        assert cmd[6] == "do the task"

    def test_opencode_with_model(self):
        """Dispatch with model flag when agent config has a model."""
        cmd = _agent_ping_cmd("opencode-dev", "do the task")
        assert "--model" in cmd
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "ollama/qwen2.5-coder:7b"

    def test_opencode_with_context_file(self):
        """Role file injected when present."""
        context_file = self.context_dir / "opencode-dev.md"
        context_file.write_text("# Context")
        cmd = _agent_ping_cmd("opencode-dev", "do the task")
        assert "--file" in cmd
        idx = cmd.index("--file")
        assert cmd[idx + 1] == str(context_file)

    def test_opencode_without_context_file(self):
        """No --file flag when context file does not exist."""
        cmd = _agent_ping_cmd("opencode-qa", "do the task")
        assert "--file" not in cmd

    def test_opencode_preserves_provided_session_id(self):
        """When a session_id is provided, it is used instead of computing stable id."""
        cmd = _agent_ping_cmd("opencode-dev", "do the task", session_id="custom-session-123")
        assert "--session" in cmd
        idx = cmd.index("--session")
        assert cmd[idx + 1] == "custom-session-123"

    def test_opencode_saves_stable_session_id(self):
        """Stable session ID is saved to agent session file."""
        session_file = self.agents_dir / "opencode-qa-session.json"
        assert not session_file.exists()
        _agent_ping_cmd("opencode-qa", "do the task")
        assert session_file.exists()
        data = json.loads(session_file.read_text())
        assert data["session_id"] == "agentweave-opencode-qa"


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
    """Tests for _parse_codex_stream_line."""

    def test_parses_turn_completed_usage(self):
        """Extracts token counts from turn.completed event."""
        line = json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1000,
                    "cached_input_tokens": 200,
                    "output_tokens": 500,
                },
            }
        )
        display, usage = _parse_codex_stream_line(line)
        assert display == []
        assert usage["input_tokens"] == 1000
        assert usage["cached_input_tokens"] == 200
        assert usage["output_tokens"] == 500

    def test_parses_agent_message(self):
        """Renders agent_message from item.completed."""
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "Hello world"},
            }
        )
        display, usage = _parse_codex_stream_line(line)
        assert display == ["Hello world"]
        assert usage is None

    def test_parses_mcp_tool_call_started(self):
        """Renders MCP tool call from item.started."""
        line = json.dumps(
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
        display, usage = _parse_codex_stream_line(line)
        assert len(display) == 1
        assert "get_inbox" in display[0]
        assert usage is None

    def test_parses_mcp_tool_call_error(self):
        """Renders MCP tool call error from item.completed."""
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
        display, usage = _parse_codex_stream_line(line)
        assert len(display) == 1
        assert "user cancelled" in display[0]
        assert usage is None

    def test_parses_command_execution(self):
        """Renders command execution from item.completed."""
        line = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "command_execution",
                    "command": "ls -la",
                    "exit_code": 0,
                    "aggregated_output": "file1\nfile2",
                },
            }
        )
        display, usage = _parse_codex_stream_line(line)
        assert len(display) == 3
        assert "ls -la" in display[0]
        assert "file1" in display[1]
        assert usage is None

    def test_ignores_thread_and_turn_events(self):
        """Returns empty for internal lifecycle events."""
        for evt in ["thread.started", "turn.started"]:
            line = json.dumps({"type": evt})
            display, usage = _parse_codex_stream_line(line)
            assert display == []
            assert usage is None

    def test_ignores_unknown_event_types(self):
        """Returns empty for unknown events."""
        line = json.dumps({"type": "unknown.event", "data": "something"})
        display, usage = _parse_codex_stream_line(line)
        assert display == []
        assert usage is None

    def test_passes_through_non_json(self):
        """Returns non-empty non-JSON lines as display."""
        display, usage = _parse_codex_stream_line("some plain text")
        assert display == ["some plain text"]
        assert usage is None


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
