"""F526: an MCP server started with no `HUB_URL` used to fall back to `http://127.0.0.1:8000`.

`:8000` is the operator's real instance. A client configured with no environment (this repo's own
Claude Code config is one) would have sent its first tool call there, under no run credential. The
server now refuses to start, and a request made without an address never leaves the process.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from hub import mcp_server
from hub.tool_server import pinned_server_path


def _spawn_without(*dropped: str, **given: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in dropped}
    env.update(given)
    return subprocess.run(
        [sys.executable, str(pinned_server_path())],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_a_server_started_without_a_hub_address_exits_naming_the_variable():
    done = _spawn_without("HUB_URL", AW_RUN_TOKEN="aw_run_probe")
    assert done.returncode != 0
    assert "HUB_URL" in done.stderr
    assert "8000" not in done.stderr


def test_a_request_without_a_hub_address_never_opens_a_connection(monkeypatch):
    monkeypatch.delenv("HUB_URL", raising=False)
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_probe")

    def refuse(*_args, **_kwargs):
        pytest.fail("a request was sent with no HUB_URL set")

    monkeypatch.setattr(mcp_server.urllib.request, "urlopen", refuse)
    with pytest.raises(mcp_server.UnboundIdentityError, match="HUB_URL"):
        mcp_server._hub_request("GET", "/anything")


def test_a_blank_hub_address_is_no_address(monkeypatch):
    monkeypatch.setenv("HUB_URL", "   ")
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_probe")
    with pytest.raises(mcp_server.UnboundIdentityError, match="HUB_URL"):
        mcp_server._hub_request("GET", "/anything")
