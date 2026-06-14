"""Tests for CLI helpers."""

import argparse
import json
import platform
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from agentweave.cli import (
    _build_codex_launch_command,
    _build_opencode_launch_command,
    _write_opencode_config_from_yml,
    _write_opencode_mcp_config,
    cmd_agent_set_model,
)


class TestWriteOpencodeMcpConfig:
    """Tests for _write_opencode_mcp_config helper.

    The helper now writes to BOTH the project-root opencode.json AND
    the user-global opencode.jsonc at ~/.config/opencode/opencode.jsonc.
    This ensures the MCP server is registered even when opencode's --dir
    is a UNC path the CLI cannot chdir into (the session is then created
    in the global "Windows" project, and only the global config loads).
    """

    def test_creates_new_files_when_both_missing(self, tmp_path, monkeypatch):
        """When both project and global opencode configs are missing,
        create them with the mcp.agentweave block."""
        # Redirect HOME to a controlled dir so the global write goes there
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.chdir(tmp_path)

        ok, paths, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is True
        # The project-root file should exist
        project = Path(paths[0])
        assert project.exists()
        data = json.loads(project.read_text())
        assert data["mcp"]["agentweave"]["type"] == "local"
        assert data["mcp"]["agentweave"]["command"] == ["agentweave-mcp"]
        # The global file should also exist
        global_path = fake_home / ".config" / "opencode" / "opencode.jsonc"
        assert global_path.exists()
        gdata = json.loads(global_path.read_text())
        assert gdata["mcp"]["agentweave"]["command"] == ["agentweave-mcp"]

    def test_merges_into_existing_project_file(self, tmp_path, monkeypatch):
        """When project opencode.json exists with other keys, preserve them."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.chdir(tmp_path)
        existing = {"theme": "dark", "editor": {"fontSize": 14}}
        Path("opencode.json").write_text(json.dumps(existing))

        ok, paths, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is True
        data = json.loads(Path(paths[0]).read_text())
        assert data["theme"] == "dark"
        assert data["editor"]["fontSize"] == 14
        assert data["mcp"]["agentweave"]["type"] == "local"

    def test_overwrites_existing_agentweave_entry(self, tmp_path, monkeypatch):
        """Overwrite existing mcp.agentweave entry while preserving other keys."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.chdir(tmp_path)
        existing = {
            "mcp": {
                "agentweave": {"type": "old", "command": ["old-cmd"]},
                "other": {"type": "local", "command": ["other-cmd"]},
            }
        }
        Path("opencode.json").write_text(json.dumps(existing))

        ok, paths, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is True
        data = json.loads(Path(paths[0]).read_text())
        assert data["mcp"]["agentweave"]["command"] == ["agentweave-mcp"]
        assert data["mcp"]["other"]["command"] == ["other-cmd"]

    def test_preserves_global_config_customizations(self, tmp_path, monkeypatch):
        """Global config customizations (theme, keybinds) survive the merge."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.chdir(tmp_path)

        global_dir = fake_home / ".config" / "opencode"
        global_dir.mkdir(parents=True)
        global_path = global_dir / "opencode.jsonc"
        global_path.write_text(
            json.dumps({"$schema": "https://opencode.ai/config.json", "theme": "tokyonight"})
        )

        ok, paths, msg = _write_opencode_mcp_config("agentweave-mcp")
        assert ok is True
        gdata = json.loads(global_path.read_text())
        assert gdata["theme"] == "tokyonight"  # preserved
        assert gdata["mcp"]["agentweave"]["command"] == ["agentweave-mcp"]

    def test_handles_malformed_project_json(self, tmp_path, monkeypatch, capsys):
        """Malformed project opencode.json: print error, still write global."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.chdir(tmp_path)
        Path("opencode.json").write_text("{not valid json")

        ok, paths, msg = _write_opencode_mcp_config("agentweave-mcp")
        # Project write failed, but global write should still succeed
        assert ok is True
        # The malformed project file should NOT be overwritten
        assert "not valid json" in Path("opencode.json").read_text()
        captured = capsys.readouterr()
        assert "Malformed opencode.json" in captured.out
        # Global should have the entry
        global_path = fake_home / ".config" / "opencode" / "opencode.jsonc"
        assert global_path.exists()

    def test_handles_non_object_project_json(self, tmp_path, monkeypatch, capsys):
        """Project JSON that is not an object is treated as failure for that file."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.chdir(tmp_path)
        Path("opencode.json").write_text("[1, 2, 3]")

        ok, paths, msg = _write_opencode_mcp_config("agentweave-mcp")
        # Project write failed; global write still succeeded
        assert ok is True
        captured = capsys.readouterr()
        assert "not a JSON object" in captured.out


class TestAgentSetModel:
    """Tests for agent model configuration."""

    def test_set_model_updates_native_runner(self, tmp_path, monkeypatch):
        """set-model is not limited to claude_proxy agents."""
        import argparse

        from agentweave.session import Session

        monkeypatch.chdir(tmp_path)
        session = Session.create(name="Test", agents=["claude", "kimi", "codex"])
        session.agents["claude"]["runner"] = "claude"
        session.agents["kimi"]["runner"] = "kimi"
        session.agents["codex"]["runner"] = "codex"
        session.save()

        result = cmd_agent_set_model(argparse.Namespace(agent_name="kimi", model="kimi-k2"))

        assert result == 0
        loaded = Session.load()
        assert loaded is not None
        assert loaded.get_runner_config("kimi")["model"] == "kimi-k2"
        assert loaded.get_runner_config("kimi")["runner"] == "kimi"

    def test_set_model_rejects_manual_runner(self, tmp_path, monkeypatch):
        """Manual agents do not have a CLI model flag to apply."""
        import argparse

        from agentweave.session import Session

        monkeypatch.chdir(tmp_path)
        session = Session.create(name="Test", agents=["manual-agent"])
        session.agents["manual-agent"]["runner"] = "manual"
        session.save()

        result = cmd_agent_set_model(
            argparse.Namespace(agent_name="manual-agent", model="anything")
        )

        assert result == 1
        loaded = Session.load()
        assert loaded is not None
        assert loaded.get_runner_config("manual-agent")["model"] is None


class TestPilotLaunchCommands:
    """Tests for generated pilot launch commands."""

    def test_codex_launch_command_includes_model_context_and_yolo(self, tmp_path, monkeypatch):
        """Codex pilot command should include the same context/model flags as watchdog runs."""
        monkeypatch.chdir(tmp_path)
        context_dir = tmp_path / ".agentweave" / "context"
        context_dir.mkdir(parents=True)
        (context_dir / "codex.md").write_text("# Codex context")

        cmd = _build_codex_launch_command("codex", model="gpt-5.4-mini", yolo=True)

        assert cmd == (
            "codex exec --json --skip-git-repo-check --model gpt-5.4-mini "
            "-c model_instructions_file=.agentweave/context/codex.md "
            '--dangerously-bypass-approvals-and-sandbox "<prompt>"'
        )

    def test_codex_launch_command_can_resume(self, tmp_path, monkeypatch):
        """Codex session registration command should use the resume subcommand."""
        monkeypatch.chdir(tmp_path)
        context_dir = tmp_path / ".agentweave" / "context"
        context_dir.mkdir(parents=True)
        (context_dir / "codex.md").write_text("# Codex context")

        cmd = _build_codex_launch_command(
            "codex",
            model="gpt-5.4-mini",
            session_id="thread-123",
        )

        assert cmd == (
            "codex exec resume thread-123 --json --skip-git-repo-check "
            "--model gpt-5.4-mini -c model_instructions_file=.agentweave/context/codex.md "
            '"<prompt>"'
        )

    def test_opencode_launch_command_can_start_new_session(self, tmp_path, monkeypatch):
        """OpenCode helper can omit --session for a fresh manual start."""
        monkeypatch.chdir(tmp_path)
        context_dir = tmp_path / ".agentweave" / "context"
        context_dir.mkdir(parents=True)
        (context_dir / "opencode-dev.md").write_text("# OpenCode context")

        cmd = _build_opencode_launch_command(
            "opencode-dev",
            model="ollama/qwen2.5-coder:7b",
            session_id="",
        )

        assert cmd == (
            "opencode run --model ollama/qwen2.5-coder:7b "
            "--file .agentweave/context/opencode-dev.md --format json '<prompt>'"
        )


class TestWriteOpencodeConfigFromYml:
    """Tests for _write_opencode_config_from_yml helper.

    Auto-generates opencode.json from the yml's top-level opencode: block.
    Add-or-replace semantics: declared keys overwrite or add, others preserved.
    """

    def test_creates_file_when_missing(self, tmp_path, monkeypatch):
        """When opencode.json does not exist, create from scratch with the yml block."""
        monkeypatch.chdir(tmp_path)
        yml_block = {
            "provider": {
                "minimax": {
                    "npm": "@ai-sdk/anthropic",
                    "options": {"baseURL": "https://api.minimax.io/anthropic"},
                }
            }
        }
        ok, path, msg = _write_opencode_config_from_yml(yml_block)
        assert ok is True
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["provider"]["minimax"]["npm"] == "@ai-sdk/anthropic"
        assert data["provider"]["minimax"]["options"]["baseURL"] == (
            "https://api.minimax.io/anthropic"
        )

    def test_merges_into_existing_file(self, tmp_path, monkeypatch):
        """When opencode.json exists with other top-level keys, preserve them."""
        monkeypatch.chdir(tmp_path)
        existing = {"theme": "dark", "editor": {"fontSize": 14}}
        Path("opencode.json").write_text(json.dumps(existing))
        yml_block = {"provider": {"minimax": {"npm": "@ai-sdk/anthropic"}}}
        ok, path, msg = _write_opencode_config_from_yml(yml_block)
        assert ok is True
        data = json.loads(Path(path).read_text())
        # Declared key overwritten
        assert data["provider"]["minimax"]["npm"] == "@ai-sdk/anthropic"
        # Other keys preserved
        assert data["theme"] == "dark"
        assert data["editor"]["fontSize"] == 14

    def test_overwrites_declared_keys(self, tmp_path, monkeypatch):
        """When a yml-declared key already exists, the yml value wins."""
        monkeypatch.chdir(tmp_path)
        existing = {
            "provider": {"minimax": {"npm": "old-npm", "options": {"timeout": 5000}}},
            "model": "old/model",
        }
        Path("opencode.json").write_text(json.dumps(existing))
        yml_block = {
            "provider": {"minimax": {"npm": "@ai-sdk/anthropic"}},
            "model": "minimax/M3",
        }
        ok, path, msg = _write_opencode_config_from_yml(yml_block)
        assert ok is True
        data = json.loads(Path(path).read_text())
        # provider.minimax replaced wholesale (top-level key add-or-replace)
        assert data["provider"]["minimax"]["npm"] == "@ai-sdk/anthropic"
        assert "options" not in data["provider"]["minimax"]
        # model replaced
        assert data["model"] == "minimax/M3"

    def test_handles_malformed_json(self, tmp_path, monkeypatch, capsys):
        """Malformed opencode.json: returns False, prints error."""
        monkeypatch.chdir(tmp_path)
        Path("opencode.json").write_text("{ this is not valid json")
        ok, path, msg = _write_opencode_config_from_yml({"provider": {}})
        assert ok is False
        assert "malformed" in msg.lower()
        # Original file should be untouched
        assert Path(path).read_text() == "{ this is not valid json"

    def test_handles_non_object_json(self, tmp_path, monkeypatch, capsys):
        """opencode.json with non-object root: returns False, prints error."""
        monkeypatch.chdir(tmp_path)
        Path("opencode.json").write_text(json.dumps([1, 2, 3]))
        ok, path, msg = _write_opencode_config_from_yml({"provider": {}})
        assert ok is False
        assert "not a JSON object" in msg

    def test_preserves_mcp_block_written_by_mcp_setup(self, tmp_path, monkeypatch):
        """Round-trip: mcp setup writes mcp block, then yml write preserves it."""
        monkeypatch.chdir(tmp_path)
        # Simulate mcp setup first
        _write_opencode_mcp_config("agentweave-mcp")
        # Then yml-driven config write
        yml_block = {"provider": {"minimax": {"npm": "@ai-sdk/anthropic"}}}
        _write_opencode_config_from_yml(yml_block)
        data = json.loads(Path("opencode.json").read_text())
        # Both blocks coexist
        assert data["provider"]["minimax"]["npm"] == "@ai-sdk/anthropic"
        assert data["mcp"]["agentweave"]["type"] == "local"
        assert data["mcp"]["agentweave"]["command"] == ["agentweave-mcp"]


class TestActivateOpencodeConfig:
    """Tests for the _activate_opencode_config step in cmd_activate."""

    def test_activate_generates_opencode_json_from_yml(self, tmp_path, monkeypatch, capsys):
        """cmd_activate writes opencode.json when yml has an opencode: block."""
        from agentweave.cli import _activate_opencode_config
        from agentweave.config import AgentWeaveConfig, ProjectConfig

        monkeypatch.chdir(tmp_path)
        config = AgentWeaveConfig(
            project=ProjectConfig(name="Test", mode="hierarchical"),
            opencode={
                "provider": {
                    "minimax": {
                        "npm": "@ai-sdk/anthropic",
                        "options": {
                            "baseURL": "https://api.minimax.io/anthropic",
                            "apiKey": "{env:MINIMAX_API_KEY}",
                        },
                    }
                }
            },
        )
        result = _activate_opencode_config(config)
        assert result == 0
        assert Path("opencode.json").exists()
        data = json.loads(Path("opencode.json").read_text())
        assert data["provider"]["minimax"]["options"]["apiKey"] == "{env:MINIMAX_API_KEY}"

    def test_activate_skips_when_block_absent(self, tmp_path, monkeypatch, capsys):
        """cmd_activate leaves opencode.json alone when yml has no opencode: block."""
        from agentweave.cli import _activate_opencode_config
        from agentweave.config import AgentWeaveConfig, ProjectConfig

        monkeypatch.chdir(tmp_path)
        # Pre-existing opencode.json that must be preserved
        existing = {"theme": "dark"}
        Path("opencode.json").write_text(json.dumps(existing))
        config = AgentWeaveConfig(
            project=ProjectConfig(name="Test", mode="hierarchical"),
            opencode=None,
        )
        result = _activate_opencode_config(config)
        assert result == 0
        # File untouched
        data = json.loads(Path("opencode.json").read_text())
        assert data == {"theme": "dark"}


class TestMcpSetupCodex:
    """Tests for cmd_mcp_setup with codex runner."""

    def test_mcp_setup_produces_codex_command(self, tmp_path, monkeypatch):
        """cmd_mcp_setup builds correct 'codex mcp add' for codex agent."""
        import argparse
        import json

        from agentweave.cli import cmd_mcp_setup

        monkeypatch.chdir(tmp_path)
        session_dir = tmp_path / ".agentweave"
        session_dir.mkdir()
        session_data = {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "principal": "claude",
            "agents": {
                "codex-dev": {"runner": "codex"},
            },
        }
        (session_dir / "session.json").write_text(json.dumps(session_data))

        # Mock subprocess to avoid actually running codex CLI
        import subprocess

        original_run = subprocess.run

        def mock_run(cmd, **kwargs):
            class Result:
                returncode = 0
                stdout = ""
                stderr = ""

            # Simulate --version check
            if "--version" in cmd:
                r = Result()
                r.returncode = 0
                return r
            # Capture the actual mcp add command
            if "mcp" in cmd and "add" in cmd:
                self.captured_cmd = cmd
                r = Result()
                r.returncode = 0
                return r
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run)

        args = argparse.Namespace()
        result = cmd_mcp_setup(args)
        assert result == 0
        assert hasattr(self, "captured_cmd")
        assert self.captured_cmd == ["codex", "mcp", "add", "agentweave", "--", "agentweave-mcp"]


class TestDatetimeIsTzAware:
    """M3 — datetime.utcnow() is deprecated in Python 3.12+ and returns a
    naive datetime that mixes badly with aware datetimes. The audit asks
    us to standardize on datetime.now(timezone.utc) across the CLI.

    This is a source-level regression guard: the buggy substring
    `datetime.utcnow()` must not appear anywhere in cli.py. (The test
    is portable, fast, and tells future contributors exactly which
    pattern to avoid.)
    """

    def test_cli_does_not_use_datetime_utcnow(self):
        from pathlib import Path

        src = Path("src/agentweave/cli.py").read_text(encoding="utf-8")
        assert "datetime.utcnow()" not in src, (
            "M3 regression: datetime.utcnow() is deprecated (Python 3.12+). "
            "Use datetime.now(timezone.utc) instead."
        )

    def test_cli_uses_timezone_aware_now(self):
        from pathlib import Path

        src = Path("src/agentweave/cli.py").read_text(encoding="utf-8")
        assert "datetime.now(timezone.utc)" in src, (
            "Expected datetime.now(timezone.utc) somewhere in cli.py"
        )


class TestTransportJsonAtomicWrite:
    """S8 — transport.json must be written via write_json_atomic so the
    0600 chmod and os.replace atomicity from PR 3 are inherited.

    The two call sites (cmd_transport_setup for git, cmd_transport_setup
    for http, and a third in the http cluster update path) all funnel
    through utils.save_json. PR 3 turned save_json into a thin wrapper
    around write_json_atomic, so the call sites are already correct.
    This test is the regression guard: if anyone ever calls
    Path.write_text() directly to write transport.json, it fails.
    """

    def test_transport_setup_git_writes_transport_json(self, tmp_path, monkeypatch):
        """Run the git branch of cmd_transport_setup and verify
        transport.json exists with the expected keys, and is chmod 0600
        on POSIX (the write_json_atomic contract)."""
        import platform

        import agentweave.cli as cli_mod
        from agentweave.cli import cmd_transport_setup

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(cli_mod, "AGENTWEAVE_DIR", tmp_path / ".agentweave")

        # Stub out the git plumbing (it would need a real repo).
        # Patch subprocess.run at the module level — cmd_transport_setup
        # binds it via `import subprocess as _sp` inside the function, so
        # patching the subprocess module itself is the correct target.
        def fake_run(cmd, *args, **kwargs):
            class R:
                returncode = 0
                stdout = ""
                stderr = ""

            r = R()
            if "ls-remote" in cmd:
                # Pretend the branch already exists
                r.stdout = "deadbeef\trefs/heads/agentweave/collab\n"
            return r

        monkeypatch.setattr(subprocess, "run", fake_run)

        ns = argparse.Namespace(
            type="git",
            remote="origin",
            branch="agentweave/collab",
            cluster="test-cluster",
            api_key="",
            url="",
            project_id="",
        )
        result = cmd_transport_setup(ns)
        assert result == 0

        transport = tmp_path / ".agentweave" / "transport.json"
        assert transport.exists()
        data = json.loads(transport.read_text(encoding="utf-8"))
        assert data["type"] == "git"
        assert data["remote"] == "origin"
        assert data["cluster"] == "test-cluster"

        if platform.system() != "Windows":
            mode = transport.stat().st_mode & 0o777
            assert mode == 0o600, f"transport.json should be 0600, got {oct(mode)}"

    def test_save_json_is_thin_wrapper_around_write_json_atomic(self):
        """Regression guard: utils.save_json must remain a thin wrapper
        around write_json_atomic so the 0600 + atomic semantics are
        inherited by every call site (S8)."""
        from agentweave import utils

        # Inspect the source of save_json
        import inspect

        src = inspect.getsource(utils.save_json)
        assert "write_json_atomic" in src, (
            f"utils.save_json no longer delegates to write_json_atomic: {src!r}"
        )


class TestSubprocessRunHasTimeout:
    """M12 — every subprocess.run call in cli.py must pass timeout= so a
    hung child (e.g. git push, docker compose up, claude proxy) cannot
    freeze the user's terminal.

    This is a source-level regression guard. The PR 2 fix added
    timeouts to the GitTransport git calls but not to the higher-level
    CLI plumbing. After PR 4, no subprocess.run in cli.py may be
    called without a timeout.
    """

    def _find_undefined_subprocess_runs(self):
        import re
        from pathlib import Path

        src = Path("src/agentweave/cli.py").read_text(encoding="utf-8")
        # Match all subprocess.run( ... ) calls. We can't perfectly
        # parse Python, but we can find lines that have
        # `subprocess.run(` or `._sp.run(` (the aliased form) but
        # don't have `timeout=` on a reasonable near-by continuation.
        # A simpler heuristic: any line that starts a
        # subprocess.run call should have `timeout=` in the visible
        # portion of that call (within 200 chars).
        issues = []
        for i, line in enumerate(src.splitlines(), 1):
            stripped = line.lstrip()
            if "subprocess.run(" in stripped or "._sp.run(" in stripped:
                # Look ahead 200 chars (allow wrapped calls)
                look_ahead = "\n".join(src.splitlines()[i - 1 : i + 8])
                if "timeout=" not in look_ahead:
                    issues.append((i, line.rstrip()))
        return issues

    def test_no_subprocess_run_without_timeout(self):
        issues = self._find_undefined_subprocess_runs()
        assert not issues, (
            "M12 regression: subprocess.run calls in cli.py without timeout=:\n"
            + "\n".join(f"  cli.py:{ln}: {l}" for ln, l in issues)
        )


class TestDownloadWithSha256:
    """S9 — verify SHA256 of downloaded Hub docker-compose.yml and .env
    via a new _download_with_sha256 helper.

    The helper downloads the file, optionally fetches a sidecar
    `<url>.sha256` and compares. If the sidecar is missing, it logs a
    WARN and continues (the file is still saved). If the sidecar is
    present but the checksum does not match, the file is deleted and
    an error is returned.
    """

    def test_downloads_file_when_no_sha256_url(self, tmp_path, monkeypatch):
        """No sha256 URL configured -> download proceeds, no verification."""
        import urllib.request

        from agentweave.cli import _download_with_sha256

        dest = tmp_path / "out.txt"
        # The helper will be called with a fake URL; we patch urlretrieve
        # at the urllib.request module level (the helper imports urllib.request
        # as _req inside the function, so the module attribute is the right
        # target).
        def fake_urlretrieve(url, path):
            Path(path).write_text("hello world", encoding="utf-8")

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        result = _download_with_sha256(
            url="https://example.com/file.txt",
            dest=dest,
            sha256_url=None,
        )
        assert result is True
        assert dest.exists()
        assert dest.read_text(encoding="utf-8") == "hello world"

    def test_verifies_sha256_when_provided_and_matches(self, tmp_path, monkeypatch):
        """sha256 URL configured and checksum matches -> success."""
        import urllib.request

        from agentweave.cli import _download_with_sha256

        dest = tmp_path / "out.txt"
        # SHA256 of "hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

        def fake_urlretrieve(url, path):
            Path(path).write_text("hello world", encoding="utf-8")

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        result = _download_with_sha256(
            url="https://example.com/file.txt",
            dest=dest,
            sha256_url="https://example.com/file.txt.sha256",
            expected_sha256=expected,
        )
        assert result is True
        assert dest.exists()

    def test_fails_loud_on_sha256_mismatch(self, tmp_path, monkeypatch, capsys):
        """sha256 URL configured and checksum does NOT match -> error,
        destination file is removed (no partial download left behind)."""
        import urllib.request

        from agentweave.cli import _download_with_sha256

        dest = tmp_path / "out.txt"
        # Wrong checksum
        wrong = "0000000000000000000000000000000000000000000000000000000000000000"

        def fake_urlretrieve(url, path):
            Path(path).write_text("hello world", encoding="utf-8")

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)

        result = _download_with_sha256(
            url="https://example.com/file.txt",
            dest=dest,
            sha256_url="https://example.com/file.txt.sha256",
            expected_sha256=wrong,
        )
        assert result is False
        # Destination should not exist — the corrupted file must be cleaned up
        assert not dest.exists()

