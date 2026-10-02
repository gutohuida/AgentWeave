"""The Hub-owned Copilot home (`a-copilot-agent-runs-over-acp` task 1.10, design D4)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from hub import copilot_home
from hub.copilot_home import (
    COPILOT_MCP_TIMEOUT_MS,
    OWNED_RECORD,
    PRECEDENCE_STATEMENT,
    agent_marker,
    copilot_home_path,
    copilot_worker_home,
    ensure_copilot_home,
)

MCP_COMMAND = ["C:/Python311/python.exe", "C:/pin/mcp_server.py"]


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


def _root(tmp_path: Path) -> Path:
    return tmp_path / ".agentweave" / "hub" / "copilot-home"


def _ensure(**overrides):
    kwargs = {
        "stable_context": "## Charter\nBuild things carefully.",
        "model": "claude-haiku-4.5",
        "effort": "high",
        "mcp_command": MCP_COMMAND,
    }
    kwargs.update(overrides)
    return ensure_copilot_home("proj-abc123", "cop-1", **kwargs)


def _frontmatter(text: str) -> dict:
    head = text.split("---\n")[1]
    fields = {}
    for line in head.strip().splitlines():
        key, _, value = line.partition(": ")
        fields[key] = json.loads(value)
    return fields


class TestPaths:
    def test_agent_home_is_under_projects(self, tmp_path):
        assert copilot_home_path("proj-abc123", "cop-1") == (
            _root(tmp_path) / "projects" / "proj-abc123" / "cop-1"
        )

    def test_worker_home_is_a_sibling_of_projects(self, tmp_path):
        assert copilot_worker_home() == _root(tmp_path) / "worker"

    @pytest.mark.parametrize("project_id", ["..", ".", "a/b", "a\\b", "..\\..\\x", "", "a b"])
    def test_an_unsafe_project_id_is_refused(self, project_id):
        with pytest.raises(ValueError):
            copilot_home_path(project_id, "cop-1")

    @pytest.mark.parametrize("agent", ["..", "x/y", "x\\y"])
    def test_an_unsafe_agent_name_is_refused(self, agent):
        with pytest.raises(ValueError):
            copilot_home_path("proj-abc123", agent)

    def test_a_project_id_resolving_outside_the_root_is_refused(self, tmp_path, monkeypatch):
        # A component that passes the character check can still resolve elsewhere through a
        # link; the resolved-path check is what refuses it.
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        projects = _root(tmp_path) / "projects"
        projects.mkdir(parents=True)
        link = projects / "linked"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("this machine cannot create a directory symlink")
        with pytest.raises(ValueError):
            copilot_home_path("linked", "cop-1")


class TestFiles:
    def test_agent_file_carries_frontmatter_precedence_and_stable_context(self):
        home = _ensure().path
        text = (home / "agents" / "cop-1.agent.md").read_text(encoding="utf-8")
        fields = _frontmatter(text)
        assert fields == {
            "name": "cop-1",
            "description": agent_marker("cop-1"),
            "tools": ["*"],
            "model": "claude-haiku-4.5",
            "reasoningEffort": "high",
        }
        body = text.split("---\n", 2)[2].strip()
        assert body.startswith(PRECEDENCE_STATEMENT)
        assert "Build things carefully." in body

    def test_model_is_omitted_for_auto_and_effort_when_unset(self):
        home = _ensure(model="auto", effort=None).path
        fields = _frontmatter((home / "agents" / "cop-1.agent.md").read_text(encoding="utf-8"))
        assert "model" not in fields
        assert "reasoningEffort" not in fields

    def test_mcp_config_has_no_env_and_outlasts_the_longest_wait(self):
        from hub.api.v1 import agents

        home = _ensure().path
        config = json.loads((home / "agentweave-mcp.json").read_text(encoding="utf-8"))
        server = config["mcpServers"]["agentweave"]
        assert server == {
            "type": "stdio",
            "command": MCP_COMMAND[0],
            "args": MCP_COMMAND[1:],
            "tools": ["*"],
            "timeout": COPILOT_MCP_TIMEOUT_MS,
        }
        assert COPILOT_MCP_TIMEOUT_MS == (agents.MAX_WAITING_SECONDS + 60) * 1000

    def test_no_mcp_config_when_the_run_is_not_given_mcp(self):
        home = _ensure(mcp_command=None).path
        assert not (home / "agentweave-mcp.json").exists()

    def test_a_second_identical_call_rewrites_nothing(self):
        home = _ensure().path
        agent_file = home / "agents" / "cop-1.agent.md"
        mcp_file = home / "agentweave-mcp.json"
        past = time.time() - 3600
        os.utime(agent_file, (past, past))
        os.utime(mcp_file, (past, past))
        before = (agent_file.stat().st_mtime, mcp_file.stat().st_mtime)
        _ensure()
        assert (agent_file.stat().st_mtime, mcp_file.stat().st_mtime) == before

    def test_a_changed_charter_is_rewritten(self):
        home = _ensure().path
        _ensure(stable_context="## Charter\nA new charter.")
        text = (home / "agents" / "cop-1.agent.md").read_text(encoding="utf-8")
        assert "A new charter." in text and "Build things carefully." not in text

    def test_no_file_carries_a_run_token(self, monkeypatch):
        monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_secretvalue")
        home = _ensure().path
        for path in home.rglob("*"):
            if path.is_file():
                assert "aw_run_" not in path.read_text(encoding="utf-8")


class TestSweep:
    def _plant(self, home: Path) -> None:
        (home / "hooks").mkdir(parents=True, exist_ok=True)
        (home / "hooks" / "allow.json").write_text("{}", encoding="utf-8")
        (home / "settings.json").write_text("{}", encoding="utf-8")
        (home / "mcp-config.json").write_text("{}", encoding="utf-8")
        (home / "installed-plugins" / "p").mkdir(parents=True)
        (home / "installed-plugins" / "p" / "x.js").write_text("", encoding="utf-8")
        (home / "agents").mkdir(parents=True, exist_ok=True)
        (home / "agents" / "other.agent.md").write_text("---\n---\n", encoding="utf-8")
        (home / "config.json").write_text(
            json.dumps({"trustedFolders": ["C:/"], "firstLaunchAt": "2026-09-01"}),
            encoding="utf-8",
        )
        (home / "session-state").mkdir()
        (home / "session-state" / "s.json").write_text("{}", encoding="utf-8")

    def test_what_the_hub_did_not_write_is_removed_and_reported(self):
        home = copilot_home_path("proj-abc123", "cop-1")
        home.mkdir(parents=True)
        self._plant(home)

        result = _ensure()

        for gone in (
            "hooks/allow.json",
            "settings.json",
            "mcp-config.json",
            "installed-plugins",
            "agents/other.agent.md",
        ):
            assert not (home / gone).exists(), gone
            assert gone in result.removed
        config = json.loads((home / "config.json").read_text(encoding="utf-8"))
        assert config == {"firstLaunchAt": "2026-09-01"}
        assert "config.json (trustedFolders)" in result.removed
        assert (home / "session-state" / "s.json").exists()
        assert (home / "agents" / "cop-1.agent.md").exists()

    def test_a_recorded_hook_survives_and_a_changed_one_is_removed(self):
        home = _ensure().path
        copilot_home.record_owned_file(home, "hooks/kept.json", '{"hooks": []}')
        (home / "hooks" / "tampered.json").write_text("original", encoding="utf-8")
        owned = json.loads((home / OWNED_RECORD).read_text(encoding="utf-8"))
        owned["hooks/tampered.json"] = hashlib.sha256(b"original").hexdigest()
        (home / OWNED_RECORD).write_text(json.dumps(owned), encoding="utf-8")
        (home / "hooks" / "tampered.json").write_text("changed", encoding="utf-8")

        result = _ensure()

        assert (home / "hooks" / "kept.json").exists()
        assert not (home / "hooks" / "tampered.json").exists()
        assert result.removed == ("hooks/tampered.json",)

    def test_a_config_json_that_does_not_parse_is_removed(self):
        home = copilot_home_path("proj-abc123", "cop-1")
        home.mkdir(parents=True)
        (home / "config.json").write_text("{not json", encoding="utf-8")
        result = _ensure()
        assert not (home / "config.json").exists()
        assert "config.json" in result.removed

    def test_what_copilot_writes_on_its_first_launch_is_left_alone(self):
        """Measured on 1.0.88 (group 11 drive): Copilot's first launch writes a JSONC
        `config.json` holding `firstLaunchAt` and an empty `installed-plugins/`. Neither can decide
        a permission, and sweeping them made every later turn report a repair."""
        home = copilot_home_path("proj-abc123", "cop-1")
        home.mkdir(parents=True)
        (home / "installed-plugins").mkdir()
        (home / "config.json").write_text(
            "// User settings belong in settings.json.\n"
            "// This file is managed automatically.\n"
            '{\n  "firstLaunchAt": "2026-09-30T11:20:36.081Z"\n}\n',
            encoding="utf-8",
        )
        assert _ensure().removed == ()
        assert (home / "installed-plugins").is_dir()
        assert "firstLaunchAt" in (home / "config.json").read_text(encoding="utf-8")

    def test_a_jsonc_config_with_a_trust_key_loses_only_that_key(self):
        home = copilot_home_path("proj-abc123", "cop-1")
        home.mkdir(parents=True)
        (home / "config.json").write_text(
            '// managed\n{"trustedFolders": ["C:/"], "firstLaunchAt": "x"}\n', encoding="utf-8"
        )
        assert _ensure().removed == ("config.json (trustedFolders)",)
        assert json.loads((home / "config.json").read_text(encoding="utf-8")) == {
            "firstLaunchAt": "x"
        }

    def test_a_clean_home_reports_nothing(self):
        _ensure()
        assert _ensure().removed == ()


class TestAccountPointer:
    """F483: `copilot login` names the account only in the operator's own home; a Hub-owned home
    without that pointer answers `session/new` with "Authentication required" unless the GitHub
    CLI holds a token. Measured on the work PC and at home with the probe's own handshake."""

    POINTER = {
        "lastLoggedInUser": {"host": "https://github.com", "login": "octo"},
        "loggedInUsers": [{"host": "https://github.com", "login": "octo"}],
    }

    @pytest.fixture(autouse=True)
    def _operator_home(self, tmp_path, monkeypatch):
        monkeypatch.delenv("COPILOT_HOME", raising=False)
        operator = tmp_path / ".copilot"
        operator.mkdir()
        # Copilot's own JSONC shape: a `//` header, then the object.
        (operator / "config.json").write_text(
            "// User settings belong in settings.json.\n// This file is managed automatically.\n"
            + json.dumps(
                {"firstLaunchAt": "2026-10-02T10:00:00Z", "theme": "dark", **self.POINTER}
            ),
            encoding="utf-8",
        )
        return operator

    def _config(self, home: Path) -> dict:
        return json.loads((home / "config.json").read_text(encoding="utf-8"))

    def test_a_new_agent_home_gets_the_pointer_and_nothing_else(self):
        home = _ensure().path
        assert self._config(home) == self.POINTER

    def test_the_agent_home_keeps_copilots_own_keys(self):
        home = copilot_home_path("proj-abc123", "cop-1")
        home.mkdir(parents=True)
        (home / "config.json").write_text(
            "// managed\n" + json.dumps({"firstLaunchAt": "x", "trustedFolders": ["C:/"]}),
            encoding="utf-8",
        )
        _ensure()
        # The sweep still drops the permission key; the pointer joins what Copilot wrote.
        assert self._config(home) == {"firstLaunchAt": "x", **self.POINTER}

    def test_a_changed_sign_in_is_copied_on_the_next_ensure(self, _operator_home):
        home = _ensure().path
        changed = {
            "lastLoggedInUser": {"host": "https://github.com", "login": "other"},
            "loggedInUsers": [{"host": "https://github.com", "login": "other"}],
        }
        (_operator_home / "config.json").write_text(json.dumps(changed), encoding="utf-8")
        _ensure()
        assert self._config(home) == changed

    def test_an_unchanged_pointer_is_not_rewritten(self):
        home = _ensure().path
        assert copilot_home.sync_account_pointer(home) is False

    def test_no_sign_in_leaves_the_home_alone(self, _operator_home):
        (_operator_home / "config.json").write_text('{"theme": "dark"}', encoding="utf-8")
        home = _ensure().path
        assert not (home / "config.json").exists()

    def test_a_missing_operator_home_leaves_the_home_alone(self, _operator_home):
        (_operator_home / "config.json").unlink()
        home = _ensure().path
        assert not (home / "config.json").exists()

    def test_copilot_home_names_the_operators_home(self, tmp_path, monkeypatch):
        elsewhere = tmp_path / "custom-copilot"
        elsewhere.mkdir()
        (elsewhere / "config.json").write_text(
            json.dumps({"lastLoggedInUser": {"login": "custom"}}), encoding="utf-8"
        )
        monkeypatch.setenv("COPILOT_HOME", str(elsewhere))
        home = _ensure().path
        assert self._config(home) == {"lastLoggedInUser": {"login": "custom"}}

    def test_the_worker_home_gets_the_pointer(self, tmp_path):
        home = copilot_home.ensure_copilot_worker_home()
        assert home == _root(tmp_path) / "worker"
        assert self._config(home) == self.POINTER

    def test_the_operators_own_home_is_never_written(self, _operator_home):
        before = (_operator_home / "config.json").read_bytes()
        assert copilot_home.sync_account_pointer(_operator_home) is False
        assert (_operator_home / "config.json").read_bytes() == before


class TestNotSignedInReason:
    def test_the_reason_names_the_file_the_account_is_read_from(self, tmp_path, monkeypatch):
        from hub.copilot_probe import not_signed_in_reason

        monkeypatch.delenv("COPILOT_HOME", raising=False)
        reason = not_signed_in_reason()
        assert reason.startswith("Copilot CLI is not signed in. Run `copilot login`")
        assert str(tmp_path / ".copilot" / "config.json") in reason
