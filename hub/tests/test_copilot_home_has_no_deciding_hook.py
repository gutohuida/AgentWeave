"""Slice 5 task 1.6: a Copilot agent's home holds no deciding hook and trusts no folder.

`a-copilot-agent-uses-hooks-and-its-own-agents` design D2 (the Hub installs no hook, operator
decision 2026-09-28) and D3 (what no Hub hook may do, and no trusted folder). A `permissionRequest`
hook's `allow` short-circuits `session/request_permission`, so a decision there would bypass the
judge, the operator's cards and the decision record; a `preToolUse` command hook fails open on a
timeout; an `agentStop` block is the backstop CLAUDE.md forbids. A trusted cwd loads this
repository's `.claude/settings.json` hooks and `.mcp.json` servers into a Copilot run.

**This is a guard.** It fails today only if a writer that does not exist yet appears: slice 2
writes the agent file and `agentweave-mcp.json` only. The half on `COPILOT_ALLOW_ALL` is ungrouped
(task 2.8) and holds whichever groups are kept: slice 2's `copilot_guard_env` strips it from the
inherited environment and from `env_vars`, under every posture, for the turn and both one-shots.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.launchability import resolve_agent_env
from hub.runner_adapters import get_adapter

from .test_copilot_home_routes import _create, _runner_id

_DECIDING_EVENTS = (
    "permissionRequest",
    "PermissionRequest",
    "preToolUse",
    "PreToolUse",
    "agentStop",
    "Stop",
    "subagentStop",
    "SubagentStop",
)
_POSTURES = ("manual", "acceptEdits", "workspace", "bypassPermissions")


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        "hub.api.v1.agents.probe_agent",
        lambda name, config: {
            "runner": config["runner"],
            "present": True,
            "authorized": True,
            "runnable": True,
            "reason": None,
        },
    )
    return tmp_path


def _copilot_home(home: Path, agent: str) -> Path:
    return home / ".agentweave" / "hub" / "copilot-home" / "projects" / "proj-test" / agent


@pytest.mark.asyncio
async def test_a_created_copilot_agents_home_has_no_deciding_hook_and_no_trusted_folder(
    app, auth_headers, _home
):
    response = await _create(
        app, auth_headers, "cop-hooks", await _runner_id(app, auth_headers, "copilot")
    )
    assert response.status_code == 201, response.text
    home = _copilot_home(_home, "cop-hooks")
    assert (home / "agents" / "cop-hooks.agent.md").is_file(), "the writer ran"

    hook_files = sorted((home / "hooks").rglob("*.json")) if (home / "hooks").is_dir() else []
    for path in hook_files:
        text = path.read_text(encoding="utf-8")
        assert not [event for event in _DECIDING_EVENTS if event in text], path
    settings = home / "settings.json"
    if settings.is_file():
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks") or {}
        assert not [event for event in _DECIDING_EVENTS if event in json.dumps(hooks)]
    config = home / "config.json"
    if config.is_file():
        data = json.loads(config.read_text(encoding="utf-8"))
        assert "trustedFolders" not in data and "trusted_folders" not in data


@pytest.mark.parametrize("posture", _POSTURES)
def test_no_copilot_turn_environment_carries_allow_all_whatever_the_posture(posture, monkeypatch):
    """Ambient and in `env_vars`, under every posture including full access (`allow_all` does
    not trust the folder; design D3, R2, VERIFIED in `app.js`)."""
    monkeypatch.setenv("COPILOT_ALLOW_ALL", "true")
    env = resolve_agent_env(
        "copilot",
        {"permission_mode": posture, "env_vars": {"COPILOT_ALLOW_ALL": "true"}},
    )
    assert env is not None
    assert "COPILOT_ALLOW_ALL" not in {key.upper() for key in env}


@pytest.mark.parametrize("purpose", ["worker", "title"])
def test_no_copilot_one_shot_environment_carries_allow_all(purpose, monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("COPILOT_ALLOW_ALL", "true")
    env = get_adapter("copilot").one_shot_env(purpose, {"env_vars": {"COPILOT_ALLOW_ALL": "true"}})
    assert env is not None
    assert "COPILOT_ALLOW_ALL" not in {key.upper() for key in env}
