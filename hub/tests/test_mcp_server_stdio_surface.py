"""The tools the MCP server serves when **spawned as a script**, which is how the Hub spawns it.

Every other test of this server imports the module. An import executes the whole file; running it
as a script stops at `mcp.run()`, which never returns. `submit_spec_document` was defined *after*
the `if __name__ == "__main__"` guard, so it registered for every test and for no agent — the tool
the entire `2026-08-12-hub-owns-the-spec-document` change is built around, invisible in production
and perfectly visible in CI.

What it cost: an agent interviewed an operator across three turns, settled the whole scope, and
finished with *"I could not submit the specification because the required `submit_spec_document`
tool is not available in this session"*. Two earlier sessions recorded the same tool as merely
"never observed in use" and treated that as verification pending.

This is the only test that spawns the file the way the Hub does and asks it over the wire, so it is
the only one that can see a tool defined below the guard, an import that fails only outside the
package, or a registration that depends on the working directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "hub" / "mcp_server.py"


def _tools_over_stdio() -> list:
    """Speak enough MCP to `tools/list`, against the real process."""
    env = dict(
        os.environ,
        AW_RUN_TOKEN="aw_run_stdio-probe",
        HUB_URL="http://127.0.0.1:1",
        AW_AGENT_IDENTITY="probe",
        AW_RUN_ID="run-probe",
        AW_TURN_DEPTH="0",
    )
    # Spawned from a directory that is not the package root, because that is the Hub's situation:
    # an agent's worktree. An import that only resolves relative to the repo would pass otherwise.
    process = subprocess.Popen(
        [sys.executable, str(SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
        cwd=str(Path(env.get("TEMP", "/tmp"))),
    )
    try:

        def send(message):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()

        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "stdio-probe", "version": "1"},
                },
            }
        )
        if not process.stdout.readline():
            pytest.fail(f"server produced no initialize response; stderr:\n{process.stderr.read()}")
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        line = process.stdout.readline()
    finally:
        process.kill()
    if not line:
        pytest.fail("server returned no tools/list response")
    return json.loads(line)["result"]["tools"]


def test_the_spawned_server_serves_the_spec_tool():
    """The specific regression. Named on its own rather than folded into the count, because a
    count is satisfied by any sixteen tools."""
    names = {tool["name"] for tool in _tools_over_stdio()}
    assert "submit_spec_document" in names, (
        "the spawned server does not serve submit_spec_document — check for a definition below "
        f"the `if __name__ == '__main__'` guard. Served: {sorted(names)}"
    )


def test_the_spawned_server_serves_what_the_imported_module_does():
    """Import and spawn must agree. They diverged silently for the whole life of the spec change,
    and the divergence was invisible to every test because every test imported."""
    import asyncio

    from hub.mcp_server import mcp

    imported = {tool.name for tool in asyncio.run(mcp.list_tools())}
    spawned = {tool["name"] for tool in _tools_over_stdio()}
    assert spawned == imported, (
        "importing the module and spawning it disagree about the tool surface. "
        f"import-only: {sorted(imported - spawned)}; spawn-only: {sorted(spawned - imported)}"
    )


def test_the_spawned_server_advertises_the_spec_tools_arguments():
    """Serving the name is not enough — a tool whose schema lost its arguments is as unusable as
    one that is absent, and would pass the test above."""
    tool = next(t for t in _tools_over_stdio() if t["name"] == "submit_spec_document")
    properties = tool["inputSchema"]["properties"]
    for required in ("path", "title", "kind", "requirements", "acceptance_criteria", "tasks"):
        assert required in properties, f"{required} missing from the served schema"


def test_the_rename_tool_is_served_too():
    """Added after the guard was moved to the end of the file. If a later edit
    ever puts a definition back below it, this is what says so."""
    names = {tool["name"] for tool in _tools_over_stdio()}
    assert "rename_spec_document" in names
