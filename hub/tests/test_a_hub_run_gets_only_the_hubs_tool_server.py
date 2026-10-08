"""A Hub Claude run loads the MCP servers its own command line names, and no other (F531).

`spec/changes/a-hub-claude-run-gets-only-the-hubs-tool-server`, criteria `argv` and the argv half of
`runner-flag`. Without `--strict-mcp-config` Claude Code merges in the operator's claude.ai account connectors
and user/project servers; driven on `:8010`, a fresh agent listed eight `mcp__claude_ai_Claude_Docs__*` tools.
"""

import json

import pytest

from hub.runner_adapters import build_command

SERVER = ["<PY>", "<SERVER>"]


def _claude(**kwargs):
    return build_command(runner="claude", cli="claude", prompt="hello", **kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"mcp_command": SERVER}, id="hub-server"),
        pytest.param({}, id="no-server"),
        pytest.param({"mcp_command": SERVER, "yolo": True}, id="yolo"),
        pytest.param({"mcp_command": SERVER, "session_id": "sess-1"}, id="resume"),
        pytest.param({"mcp_command": SERVER, "restrict_spec_writes": True}, id="spec-turn"),
    ],
)
def test_every_claude_turn_loads_only_the_servers_its_command_line_names(kwargs):
    command = _claude(**kwargs)
    assert command.count("--strict-mcp-config") == 1


def test_the_hubs_own_server_config_is_unchanged():
    command = _claude(mcp_command=SERVER)
    config = json.loads(command[command.index("--mcp-config") + 1])
    assert config == {
        "mcpServers": {"agentweave": {"type": "stdio", "command": "<PY>", "args": ["<SERVER>"]}}
    }


def test_a_runners_own_mcp_config_flag_still_reaches_the_run():
    extra = json.dumps({"mcpServers": {"extra": {"type": "stdio", "command": "x"}}})
    command = _claude(mcp_command=SERVER, extra_flags=["--mcp-config", extra])
    assert command.count("--strict-mcp-config") == 1
    configs = [command[i + 1] for i, word in enumerate(command[:-1]) if word == "--mcp-config"]
    assert len(configs) == 2 and extra in configs


def test_a_runner_that_already_says_strict_is_not_told_twice():
    command = _claude(mcp_command=SERVER, extra_flags=["--strict-mcp-config"])
    assert command.count("--strict-mcp-config") == 1


def test_codex_argv_is_not_given_a_claude_flag():
    command = build_command(runner="codex", cli="codex", prompt="hello", mcp_command=SERVER)
    assert "--strict-mcp-config" not in command
