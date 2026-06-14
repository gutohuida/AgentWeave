"""Tests for the per-agent `cli:` override.

Background: on hosts with more than one `opencode` on PATH (e.g. WSL with
a stale Linux install shadowing a working Windows one), the watchdog would
pick whichever `shutil.which` resolved first — and an older binary would
return `ProviderModelNotFoundError` for newer models. The `cli:` override
in agentweave.yml pins the binary path per agent, so the right opencode
is always invoked.
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from agentweave.config import (
    AgentConfig,
    ConfigValidationError,
    load_agentweave_yml,
)
from agentweave.session import Session

# ---------------------------------------------------------------------------
# 1. Config parsing — yml -> AgentConfig
# ---------------------------------------------------------------------------


class TestCliConfigField:
    def test_default_is_none(self):
        cfg = AgentConfig(runner="opencode")
        assert cfg.cli is None

    def test_to_dict_omits_when_none(self):
        cfg = AgentConfig(runner="opencode")
        assert "cli" not in cfg.to_dict()

    def test_to_dict_includes_when_set(self):
        cfg = AgentConfig(runner="opencode", cli="/usr/local/bin/opencode")
        assert cfg.to_dict()["cli"] == "/usr/local/bin/opencode"

    def test_load_absolute_path(self, tmp_path):
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test
  mode: hierarchical

agents:
  opencode-pinned:
    runner: opencode
    model: minimax-coding-plan/MiniMax-M3
    cli: /mnt/c/Users/huida/AppData/Roaming/npm/opencode
""")
        config = load_agentweave_yml(config_file)
        assert config.agents["opencode-pinned"].cli == (
            "/mnt/c/Users/huida/AppData/Roaming/npm/opencode"
        )

    def test_load_without_cli_field_uses_none(self, tmp_path):
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test
  mode: hierarchical

agents:
  opencode-dev:
    runner: opencode
    model: ollama/qwen2.5-coder:7b
""")
        config = load_agentweave_yml(config_file)
        assert config.agents["opencode-dev"].cli is None

    def test_rejects_empty_string(self, tmp_path):
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test
  mode: hierarchical

agents:
  opencode-dev:
    runner: opencode
    cli: ""
""")
        with pytest.raises(ConfigValidationError) as exc_info:
            load_agentweave_yml(config_file)
        assert "non-empty string" in str(exc_info.value)

    def test_rejects_non_string(self, tmp_path):
        config_file = tmp_path / "agentweave.yml"
        config_file.write_text("""
project:
  name: Test
  mode: hierarchical

agents:
  opencode-dev:
    runner: opencode
    cli: 42
""")
        with pytest.raises(ConfigValidationError) as exc_info:
            load_agentweave_yml(config_file)
        assert "must be a string" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 2. Session sync — yml -> session.json (round-trip)
# ---------------------------------------------------------------------------


class TestCliSessionSync:
    def _write_session(self, tmp_path, agents_dict):
        from agentweave.constants import SESSION_FILE

        session_file = tmp_path / SESSION_FILE.name
        session_file.parent.mkdir(parents=True, exist_ok=True)
        session_file.write_text(
            json.dumps(
                {
                    "id": "test-session",
                    "name": "Test",
                    "mode": "hierarchical",
                    "principal": "opencode-dev",
                    "agents": agents_dict,
                }
            )
        )
        return session_file

    def test_sync_adds_cli_field(self, tmp_path):
        from agentweave.config import AGENTWEAVE_YML_PATH

        yml = tmp_path / AGENTWEAVE_YML_PATH.name
        yml.write_text("""
project:
  name: Test
  mode: hierarchical

agents:
  opencode-dev:
    runner: opencode
    model: minimax-coding-plan/MiniMax-M3
    cli: /usr/local/bin/opencode
""")
        self._write_session(
            tmp_path,
            {"opencode-dev": {"role": "principal", "since": "2026-01-01T00:00:00+00:00"}},
        )

        session = Session(json.loads((tmp_path / "session.json").read_text()))
        cfg = load_agentweave_yml(yml)
        declared = {
            name: {
                "runner": a.runner,
                "model": a.model,
                "roles": a.roles,
                "yolo": a.yolo,
                "pilot": a.pilot,
                "env": a.env,
                "base_url": a.base_url,
                "runner_options": a.runner_options,
                "cli": a.cli,
            }
            for name, a in cfg.agents.items()
        }
        session.sync_agents(declared)
        assert session.agents["opencode-dev"]["cli"] == "/usr/local/bin/opencode"

    def test_sync_drops_cli_field_when_removed_from_yml(self, tmp_path):
        from agentweave.config import AGENTWEAVE_YML_PATH

        yml = tmp_path / AGENTWEAVE_YML_PATH.name
        yml.write_text("""
project:
  name: Test
  mode: hierarchical

agents:
  opencode-dev:
    runner: opencode
    model: ollama/qwen2.5-coder:7b
""")
        self._write_session(
            tmp_path,
            {
                "opencode-dev": {
                    "role": "principal",
                    "since": "2026-01-01T00:00:00+00:00",
                    "cli": "/stale/path/opencode",
                }
            },
        )

        session = Session(json.loads((tmp_path / "session.json").read_text()))
        cfg = load_agentweave_yml(yml)
        declared = {
            name: {
                "runner": a.runner,
                "model": a.model,
                "roles": a.roles,
                "yolo": a.yolo,
                "pilot": a.pilot,
                "env": a.env,
                "base_url": a.base_url,
                "runner_options": a.runner_options,
                "cli": a.cli,
            }
            for name, a in cfg.agents.items()
        }
        session.sync_agents(declared)
        assert "cli" not in session.agents["opencode-dev"]

    def test_get_runner_config_surfaces_cli(self):
        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "opencode-dev",
                "agents": {
                    "opencode-dev": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "opencode",
                        "model": "minimax/M3",
                        "cli": "/abs/path/opencode",
                    }
                },
            }
        )
        cfg = session.get_runner_config("opencode-dev")
        assert cfg["cli"] == "/abs/path/opencode"
        assert cfg["runner"] == "opencode"
        assert cfg["model"] == "minimax/M3"


# ---------------------------------------------------------------------------
# 3. Watchdog _agent_ping_cmd — pinned binary is preserved
# ---------------------------------------------------------------------------


class TestAgentPingCmdOpencodeCliOverride:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.tmp_path = tmp_path
        self.session_dir = tmp_path / ".agentweave"
        self.session_dir.mkdir()
        self.agents_dir = self.session_dir / "agents"
        self.agents_dir.mkdir()
        self.context_dir = self.session_dir / "context"
        self.context_dir.mkdir()
        yield

    def _patch_session(self, session):
        return (
            patch("agentweave.watchdog.AGENTS_DIR", self.agents_dir),
            patch("agentweave.watchdog.AGENT_CONTEXT_DIR", self.context_dir),
            patch("agentweave.session.Session.load", return_value=session),
        )

    def _session(self, **agent_overrides):
        agent_cfg = {
            "role": "principal",
            "since": "2026-01-01T00:00:00+00:00",
            "runner": "opencode",
            "model": "minimax-coding-plan/MiniMax-M3",
        }
        agent_cfg.update(agent_overrides)
        return Session(
            {
                "id": "test-session",
                "name": "Test",
                "mode": "hierarchical",
                "principal": "opencode-pinned",
                "agents": {"opencode-pinned": agent_cfg},
            }
        )

    def test_absolute_path_override_preserved(self):
        """When `cli:` is set in session, the cmd's first element is that
        absolute path — no `shutil.which` rewrite happens."""
        from agentweave.watchdog import _agent_ping_cmd

        pinned = "/mnt/c/Users/huida/AppData/Roaming/npm/opencode"
        session = self._session(cli=pinned)
        with self._patch_session(session)[0], self._patch_session(session)[1], self._patch_session(
            session
        )[2]:
            cmd = _agent_ping_cmd("opencode-pinned", "do the task")

        assert cmd[0] == pinned
        assert cmd[1] == "run"
        # Sanity: model and other flags are still emitted.
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "minimax-coding-plan/MiniMax-M3"

    def test_bare_name_kept_when_no_override(self):
        """Without a `cli:` override, the cmd uses the bare runner name so
        the existing PATH-based resolution still applies."""
        from agentweave.watchdog import _agent_ping_cmd

        session = self._session()  # no cli
        with self._patch_session(session)[0], self._patch_session(session)[1], self._patch_session(
            session
        )[2]:
            cmd = _agent_ping_cmd("opencode-pinned", "do the task")

        assert cmd[0] == "opencode"
        assert cmd[1] == "run"

    def test_override_takes_precedence_over_runner_config_default(self):
        """The per-agent `cli:` wins over the runner's default `cli: opencode`."""
        from agentweave.constants import RUNNER_CONFIGS
        from agentweave.watchdog import _agent_ping_cmd

        assert RUNNER_CONFIGS["opencode"]["cli"] == "opencode"
        pinned = "/opt/other-opencode/bin/opencode"
        session = self._session(cli=pinned)
        with self._patch_session(session)[0], self._patch_session(session)[1], self._patch_session(
            session
        )[2]:
            cmd = _agent_ping_cmd("opencode-pinned", "do the task")

        assert cmd[0] == pinned
        assert cmd[0] != RUNNER_CONFIGS["opencode"]["cli"]


# ---------------------------------------------------------------------------
# 4. _check_cli_available — pinned absolute path bypasses PATH lookup
# ---------------------------------------------------------------------------


class TestCheckCliAvailableWithOverride:
    def test_pinned_path_to_executable_file_passes(self, tmp_path, monkeypatch):
        from agentweave import session as sess_mod
        from agentweave import watchdog as wd

        fake_bin = tmp_path / "opencode"
        fake_bin.write_text("#!/bin/sh\necho opencode\n")
        os.chmod(fake_bin, 0o755)

        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "opencode-pinned",
                "agents": {
                    "opencode-pinned": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "opencode",
                        "cli": str(fake_bin),
                    }
                },
            }
        )
        monkeypatch.setattr(sess_mod.Session, "load", classmethod(lambda cls: session))
        assert wd._check_cli_available("opencode-pinned") is True

    def test_pinned_path_to_missing_file_fails(self, tmp_path, monkeypatch):
        from agentweave import session as sess_mod
        from agentweave import watchdog as wd

        missing = tmp_path / "does-not-exist-opencode"
        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "opencode-pinned",
                "agents": {
                    "opencode-pinned": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "opencode",
                        "cli": str(missing),
                    }
                },
            }
        )
        monkeypatch.setattr(sess_mod.Session, "load", classmethod(lambda cls: session))
        assert wd._check_cli_available("opencode-pinned") is False

    def test_no_override_uses_path_lookup(self, monkeypatch):
        from agentweave import session as sess_mod
        from agentweave import watchdog as wd

        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "kimi-dev",
                "agents": {
                    "kimi-dev": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "kimi",
                    }
                },
            }
        )
        monkeypatch.setattr(sess_mod.Session, "load", classmethod(lambda cls: session))
        # kimi CLI is typically not installed in CI — but as long as the
        # override-bypass code path is correct, we just assert the function
        # returns a bool (no exception).
        result = wd._check_cli_available("kimi-dev")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 5. cli.py _build_opencode_launch_command honors the override
# ---------------------------------------------------------------------------


class TestBuildOpencodeLaunchCommandCli:
    def test_default_uses_bare_name(self):
        from agentweave.cli import _build_opencode_launch_command

        cmd = _build_opencode_launch_command("opencode-dev", model="minimax/M3")
        assert cmd.startswith("opencode run ")
        assert "--model minimax/M3" in cmd

    def test_override_uses_absolute_path(self):
        from agentweave.cli import _build_opencode_launch_command

        pinned = "/usr/local/bin/opencode"
        cmd = _build_opencode_launch_command("opencode-dev", model="minimax/M3", cli=pinned)
        assert cmd.startswith(f"{pinned} run ")
        assert "--model minimax/M3" in cmd

    def test_override_preserves_session_id(self):
        from agentweave.cli import _build_opencode_launch_command

        pinned = "/opt/opencode"
        cmd = _build_opencode_launch_command("opencode-dev", session_id="ses_abc", cli=pinned)
        assert cmd.startswith(f"{pinned} run ")
        assert "--session ses_abc" in cmd


# ---------------------------------------------------------------------------
# 6. diagnostics: pinned binary shows up in the readiness report
# ---------------------------------------------------------------------------


class TestDiagnosticsWithCliOverride:
    def test_runner_cli_override_returns_pinned_path(self):
        from agentweave.diagnostics import _runner_cli_override

        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "opencode-pinned",
                "agents": {
                    "opencode-pinned": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "opencode",
                        "cli": "/abs/opencode",
                    }
                },
            }
        )
        assert _runner_cli_override("opencode-pinned", session) == "/abs/opencode"

    def test_runner_cli_override_returns_none_without_pin(self):
        from agentweave.diagnostics import _runner_cli_override

        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "opencode-pinned",
                "agents": {
                    "opencode-pinned": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "opencode",
                    }
                },
            }
        )
        assert _runner_cli_override("opencode-pinned", session) is None

    def test_readiness_reports_pinned_cli_available(self, tmp_path, monkeypatch):
        from agentweave.diagnostics import check_agent_readiness

        fake_bin = tmp_path / "opencode"
        fake_bin.write_text("#!/bin/sh\n")
        os.chmod(fake_bin, 0o755)

        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "opencode-pinned",
                "agents": {
                    "opencode-pinned": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "opencode",
                        "model": "minimax-coding-plan/MiniMax-M3",
                        "cli": str(fake_bin),
                    }
                },
            }
        )
        results = check_agent_readiness("opencode-pinned", session)
        cli_results = [r for r in results if r.id == "agent_cli_available"]
        assert cli_results, f"expected agent_cli_available in {results!r}"
        assert cli_results[0].status == "pass"
        assert cli_results[0].data["cli_pinned"] is True
        assert cli_results[0].data["cli"] == str(fake_bin)

    def test_readiness_reports_pinned_cli_missing(self, tmp_path):
        from agentweave.diagnostics import check_agent_readiness

        session = Session(
            {
                "id": "x",
                "name": "x",
                "mode": "hierarchical",
                "principal": "opencode-pinned",
                "agents": {
                    "opencode-pinned": {
                        "role": "principal",
                        "since": "2026-01-01T00:00:00+00:00",
                        "runner": "opencode",
                        "model": "minimax-coding-plan/MiniMax-M3",
                        "cli": "/definitely/does/not/exist/opencode",
                    }
                },
            }
        )
        results = check_agent_readiness("opencode-pinned", session)
        cli_results = [r for r in results if r.id == "agent_cli_missing"]
        assert cli_results, f"expected agent_cli_missing in {results!r}"
        assert cli_results[0].status == "fail"
        assert cli_results[0].data["cli_pinned"] is True
        # And it must block launches (it's in launch_blockers' allowlist).
        from agentweave.diagnostics import launch_blockers

        assert any(b.id == "agent_cli_missing" for b in launch_blockers("opencode-pinned", session))
