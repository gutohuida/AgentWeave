"""Access-axes tests (task 1.6): `resolve_access_axes` against design D4's five rows, and
`ClaudeAdapter.posture_at_rest`'s three postures.

No golden capture, like 1.5: design D4's table (the "Today's values, reproduced" rows and the
R3 trigger trace) is the oracle, not a captured fixture. FAILS today on
`ModuleNotFoundError: hub.runner_adapters`, the same as every other `test_runner_adapters_*` file
until group 2 lands the module (tasks.md's own "no function" is the failure once the module
exists but `resolve_access_axes` does not -- not yet reachable on today's tree).
"""

from __future__ import annotations

import pytest

from hub.codex_appserver import APP_SERVER_OPT_IN_FLAG, APP_SERVER_OPT_OUT_FLAG
from hub.runner_adapters import AccessAxes, get_adapter, resolve_access_axes

CLAUDE = get_adapter("claude")
CODEX = get_adapter("codex")


# --- D4's five rows, reproduced -----------------------------------------------------------------


@pytest.mark.parametrize("hub_client", [None, "mcp", "auto"])
def test_claude_mcp_row(hub_client):
    axes = resolve_access_axes(CLAUDE, hub_client=hub_client, flags=None)
    assert axes == AccessAxes(tool_surface="mcp", approvals="mcp_permission_tool", plane="mcp")


def test_claude_cli_row():
    axes = resolve_access_axes(CLAUDE, hub_client="cli", flags=None)
    assert axes == AccessAxes(tool_surface="none", approvals="none", plane="cli")


@pytest.mark.parametrize("hub_client", [None, "mcp", "auto"])
def test_codex_app_server_mcp_row(hub_client):
    axes = resolve_access_axes(CODEX, hub_client=hub_client, flags=None)
    assert axes == AccessAxes(tool_surface="mcp", approvals="rpc", plane="mcp")


def test_codex_app_server_cli_row():
    # The fourth row: axis 2 does not follow axis 1 here (the Hub still answers RPC requests
    # with no server materialised).
    axes = resolve_access_axes(CODEX, hub_client="cli", flags=None)
    assert axes == AccessAxes(tool_surface="none", approvals="rpc", plane="cli")


@pytest.mark.parametrize(
    "hub_client, tool_surface, plane",
    [(None, "mcp", "mcp"), ("mcp", "mcp", "mcp"), ("auto", "mcp", "mcp"), ("cli", "none", "cli")],
)
def test_codex_exec_row(hub_client, tool_surface, plane):
    # The fifth row: `exec` has no live approvals regardless of tool surface.
    axes = resolve_access_axes(CODEX, hub_client=hub_client, flags=[APP_SERVER_OPT_OUT_FLAG])
    assert axes == AccessAxes(tool_surface=tool_surface, approvals="none", plane=plane)


# --- R3: the opt-out sentinel wins when both are present, same as `uses_app_server` -------------


def test_codex_both_sentinels_resolves_to_exec():
    axes = resolve_access_axes(
        CODEX, hub_client=None, flags=[APP_SERVER_OPT_IN_FLAG, APP_SERVER_OPT_OUT_FLAG]
    )
    assert axes.approvals == "none"  # exec's row, not app-server's "rpc"


# --- Review 3: `flags=None` behaves as no flags on both runners ---------------------------------


def test_codex_none_flags_gives_the_app_server_row():
    axes = resolve_access_axes(CODEX, hub_client=None, flags=None)
    assert axes == AccessAxes(tool_surface="mcp", approvals="rpc", plane="mcp")


def test_claude_none_flags_gives_row_one():
    axes = resolve_access_axes(CLAUDE, hub_client=None, flags=None)
    assert axes == AccessAxes(tool_surface="mcp", approvals="mcp_permission_tool", plane="mcp")


# --- `ClaudeAdapter.posture_at_rest`'s three postures --------------------------------------------


def test_claude_posture_at_rest_workspace_when_approvals_exist():
    axes = AccessAxes(tool_surface="mcp", approvals="mcp_permission_tool", plane="mcp")
    assert CLAUDE.posture_at_rest(axes, yolo=False) == "workspace"


def test_claude_posture_at_rest_accept_edits_when_no_approvals():
    axes = AccessAxes(tool_surface="none", approvals="none", plane="cli")
    assert CLAUDE.posture_at_rest(axes, yolo=False) == "acceptEdits"


def test_claude_posture_at_rest_bypass_permissions_under_yolo():
    # yolo wins even over an mcp row: `posture_at_rest` reads yolo first (design D4).
    axes = AccessAxes(tool_surface="mcp", approvals="mcp_permission_tool", plane="mcp")
    assert CLAUDE.posture_at_rest(axes, yolo=True) == "bypassPermissions"
