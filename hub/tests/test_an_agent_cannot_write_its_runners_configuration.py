"""F675: under "Workspace only", a write to the runner's own configuration is refused even though
it is inside the workspace.

Measured in research 2026-10-01 §1 on Claude Code 2.1.280 and 2.1.286: an agent's `Write` of
`.claude/settings.local.json` with an allow rule was approved as "inside your workspace", and on
the next `--resume` turn a command outside the workspace ran without the approver being called.
A project or local allow rule runs ahead of `--permission-prompt-tool`, and the Hub launches
Claude with `--setting-sources project,local`, so both files load on every turn.
"""

from __future__ import annotations

import sys

import pytest

from hub.mcp_server import _decide


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    (ws / "sub").mkdir(parents=True)
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


CONFIG_FILES = [
    ".claude/settings.local.json",
    ".claude/settings.json",
    ".claude/hooks/pre_tool.sh",
    ".mcp.json",
    ".codex/config.toml",
    ".github/hooks/hooks.json",
]


def _refused_as_config(decision):
    assert decision["allow"] is False, decision
    assert "configures your runner" in decision["reason"]
    assert "ask_user" in decision["reason"]


@pytest.mark.parametrize("relative", CONFIG_FILES)
@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_a_write_tool_naming_runner_configuration_is_refused(workspace, tool, relative):
    _refused_as_config(_decide(tool, {"file_path": relative}))
    _refused_as_config(_decide(tool, {"file_path": str(workspace / relative)}))


def test_the_research_measurement_is_refused(workspace):
    """The exact write research 10-01's chain made on its first turn."""
    _refused_as_config(
        _decide(
            "Write",
            {
                "file_path": str(workspace / ".claude" / "settings.local.json"),
                "content": '{"permissions":{"allow":["Bash","PowerShell"]}}',
            },
        )
    )


def test_a_copilot_edit_judged_by_its_path_key_is_refused(workspace):
    """Copilot's ACP client judges an edit as `("Write", {"path": p})`."""
    _refused_as_config(_decide("Write", {"path": str(workspace / ".claude/settings.json")}))


def test_a_traversal_back_into_the_configuration_is_refused(workspace):
    _refused_as_config(_decide("Write", {"file_path": "sub/../.claude/settings.local.json"}))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows names are case-insensitive")
def test_a_differently_cased_name_is_refused_on_windows(workspace):
    _refused_as_config(_decide("Write", {"file_path": ".CLAUDE\\Settings.Local.json"}))
    _refused_as_config(_decide("Write", {"file_path": ".claude\\settings.local.json."}))


@pytest.mark.parametrize(
    "command",
    [
        """echo '{"permissions":{"allow":["Bash"]}}' > .claude/settings.local.json""",
        "cp allow.json .claude/settings.json",
        "printf x > .mcp.json",
        "mkdir -p .claude/hooks && printf x > .claude/hooks/a.sh",
        "touch .codex",
    ],
)
def test_a_bash_command_naming_runner_configuration_is_refused(workspace, command):
    _refused_as_config(_decide("Bash", {"command": command}))


def test_a_powershell_command_naming_runner_configuration_is_refused(workspace):
    _refused_as_config(
        _decide(
            "PowerShell",
            {"command": "Set-Content -Path .claude\\settings.local.json -Value '{}'"},
        )
    )


@pytest.mark.parametrize(
    "tool,tool_input",
    [
        ("Read", {"file_path": ".claude/settings.json"}),
        ("Write", {"file_path": "CLAUDE.md"}),
        ("Write", {"file_path": ".claude/skills/x/SKILL.md"}),
        ("Write", {"file_path": ".claude/settings.json.bak/x"}),
        ("Write", {"file_path": "sub/.claude/settings.json"}),
        ("Write", {"file_path": "settings.local.json"}),
        ("Bash", {"command": "printf x > .claude/notes.md"}),
        ("Bash", {"command": "ls .claude"}),
    ],
)
def test_ordinary_workspace_content_is_still_allowed(workspace, tool, tool_input):
    """Only what the runner reads to configure itself is held back: instructions, skills and a
    nested project's files are ordinary work (research 10-01 §1, "Legitimate edits")."""
    assert _decide(tool, tool_input)["allow"] is True
