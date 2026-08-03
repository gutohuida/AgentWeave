"""Run-token forwarding into dynamically configured runner tool servers."""

from hub.runner_commands import build_command


def test_codex_mcp_server_whitelists_run_identity_environment():
    command = build_command(
        runner="codex",
        cli="codex",
        prompt="verify",
        mcp_command=["python", "mcp_server.py"],
    )

    config_values = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "-c"]
    env_config = next(
        value for value in config_values if value.startswith("mcp_servers.agentweave.env_vars=")
    )

    assert "AW_RUN_TOKEN" in env_config
    assert "AW_AGENT_IDENTITY" in env_config
    assert "AW_RUN_ID" in env_config
    assert "HUB_URL" in env_config
    assert "aw_run_" not in env_config
