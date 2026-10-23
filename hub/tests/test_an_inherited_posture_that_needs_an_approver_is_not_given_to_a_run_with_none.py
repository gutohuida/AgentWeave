"""F933: a project or agent default of "Ask me" / "Workspace only" on an agent with no tool server.

`hub_client: "cli"` gives a Claude run no MCP server and so no approver. A default that routes
calls through an approver then reached it as `--permission-mode manual` with nobody to answer: every
write was refused, with no card and no Activity line. An *inherited* default the run cannot honour
falls back to the runner's own at-rest posture, and the roster says what the run will get.
"""

from __future__ import annotations

import pytest

from tests.test_an_operator_sets_how_far_an_agent_reaches import (
    PROJECT,
    _agents,
    _claude_run,
    _patch,
    _settings,
)


async def _cli_agent(app, auth_headers, bind_runner, name: str) -> None:
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {name: {"runner": "claude", "hub_client": "cli"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner(name, cli="claude")


async def _row(app, auth_headers, name: str) -> dict:
    roster = (await app.get(f"/api/v1/projects/{PROJECT}/agents", headers=auth_headers)).json()
    return next(a for a in roster if a["name"] == name)


@pytest.mark.asyncio
@pytest.mark.parametrize("posture", ["manual", "workspace"])
async def test_a_project_default_needing_an_approver_falls_back_on_a_run_with_none(
    app, auth_headers, bind_runner, posture
):
    name = f"f933-proj-{posture}"
    await _cli_agent(app, auth_headers, bind_runner, name)
    await _settings(app, auth_headers, default_permission_mode=posture)

    command, _env = await _claude_run(app, auth_headers, name)

    assert command[command.index("--permission-mode") + 1] == "acceptEdits"
    assert "--permission-prompt-tool" not in command
    assert (await _row(app, auth_headers, name))["permission_mode_at_rest"] == "acceptEdits"


@pytest.mark.asyncio
async def test_an_agents_own_default_needing_an_approver_falls_back_too(
    app, auth_headers, bind_runner
):
    await _cli_agent(app, auth_headers, bind_runner, "f933-own")
    await _patch(app, auth_headers, "f933-own", default_permission_mode="manual")

    command, _env = await _claude_run(app, auth_headers, "f933-own")

    assert command[command.index("--permission-mode") + 1] == "acceptEdits"


@pytest.mark.asyncio
async def test_a_default_that_needs_no_approver_still_reaches_a_run_with_none(
    app, auth_headers, bind_runner
):
    await _cli_agent(app, auth_headers, bind_runner, "f933-yolo")
    await _settings(app, auth_headers, default_permission_mode="bypassPermissions")

    command, _env = await _claude_run(app, auth_headers, "f933-yolo")

    assert command[command.index("--permission-mode") + 1] == "bypassPermissions"
    assert (await _row(app, auth_headers, "f933-yolo"))["permission_mode_at_rest"] == (
        "bypassPermissions"
    )


@pytest.mark.asyncio
async def test_an_agent_with_a_tool_server_keeps_the_default(app, auth_headers, bind_runner):
    await _agents(app, auth_headers, bind_runner, **{"f933-mcp": "claude"})
    await _settings(app, auth_headers, default_permission_mode="manual")

    command, _env = await _claude_run(app, auth_headers, "f933-mcp")

    assert command[command.index("--permission-mode") + 1] == "manual"
    assert "--permission-prompt-tool" in command
    assert (await _row(app, auth_headers, "f933-mcp"))["permission_mode_at_rest"] == "manual"
