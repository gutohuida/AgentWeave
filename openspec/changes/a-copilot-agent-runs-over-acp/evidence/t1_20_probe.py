"""Task 1.20 probe (no model call): which `agentweave` MCP server loads, with what source and
transport, when the repository also claims one.

Under a scratch `COPILOT_HOME`, in a scratch git repository holding `.mcp.json` and
`.github/agents/<agent>.agent.md` whose `mcp-servers` both name a stand-in server `agentweave`,
spawn `copilot.exe --acp` with the Hub's `--additional-mcp-config` (dead `HUB_URL`) and
`COPILOT_ALLOW_ALL` unset. Run `initialize` (subscribing `session.mcp_servers_loaded`),
`session/new`, select then deselect the agent, and `session/close`. Record every server report.

Run from the repository root: `py -3.11 openspec/changes/a-copilot-agent-runs-over-acp/evidence/t1_20_probe.py`.
Writes `t1_20_probe.log` beside this file, with scratch paths replaced by `<HOME>`/`<WS>`.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "hub"))

from hub.copilot_acp import ACPProcess  # noqa: E402
from hub.copilot_probe import resolve_copilot_executable  # noqa: E402
from hub.launchability import copilot_guard_env  # noqa: E402

AGENT = "probe-builder"
STAND_IN = "import sys\nfor line in sys.stdin:\n    pass\n"
OUT = Path(__file__).with_name("t1_20_probe.log")


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ghcp-t120-") as scratch:
        root = Path(scratch)
        home, ws = root / "home", root / "ws"
        home.mkdir()
        ws.mkdir()
        subprocess.run(["git", "init", "-q", str(ws)], check=True)
        stand_in = ws / "stand_in.py"
        stand_in.write_text(STAND_IN, encoding="utf-8")
        repo_server = {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(stand_in)],
            "tools": ["*"],
        }
        (ws / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"agentweave": repo_server}}), encoding="utf-8"
        )
        (ws / ".github" / "agents").mkdir(parents=True)
        (ws / ".github" / "agents" / f"{AGENT}.agent.md").write_text(
            "---\n"
            f"name: {AGENT}\n"
            'description: "a repository agent claiming the Hub name"\n'
            "mcp-servers:\n"
            "  agentweave:\n"
            "    type: stdio\n"
            f"    command: {json.dumps(sys.executable)}\n"
            f"    args: [{json.dumps(str(stand_in))}]\n"
            '    tools: ["*"]\n'
            "---\n\nRepository agent body.\n",
            encoding="utf-8",
        )
        hub_config = home / "agentweave-mcp.json"
        hub_config.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "agentweave": {
                            "type": "stdio",
                            "command": sys.executable,
                            "args": [str(REPO / "hub" / "hub" / "mcp_server.py")],
                            "tools": ["*"],
                            "timeout": 660000,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        env, _ = copilot_guard_env(dict(os.environ), {})
        env.update({"COPILOT_HOME": str(home), "HUB_URL": "http://127.0.0.1:9"})
        exe = resolve_copilot_executable(None)
        argv = [
            str(exe),
            "--acp",
            "--stdio",
            "--no-auto-update",
            "--disable-builtin-mcps",
            "--additional-mcp-config",
            f"@{hub_config}",
        ]
        log = []

        def note(kind, payload):
            text = json.dumps(payload)
            text = text.replace(json.dumps(str(home))[1:-1], "<HOME>")
            text = text.replace(json.dumps(str(ws))[1:-1], "<WS>")
            log.append(f"{kind} {text}")

        async def on_notification(method, params):
            if method == "github.com/copilot/sessionEvent":
                note("RAW", {"type": params.get("type"), "data": params.get("data")})

        async def on_server_request(method, params):
            note("REQUEST", {"method": method})
            return {"outcome": {"outcome": "cancelled"}}

        session = await ACPProcess.spawn(
            argv,
            cwd=str(ws),
            env=env,
            on_notification=on_notification,
            on_server_request=on_server_request,
        )
        try:
            init = await session.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "_meta": {
                            "github.com/copilot": {
                                "events": [
                                    "session.mcp_servers_loaded",
                                    "session.mcp_server_status_changed",
                                ]
                            }
                        }
                    },
                },
            )
            note("INIT", {"version": (init.get("agentInfo") or {}).get("version")})
            new = await session.request(
                "session/new", {"cwd": str(ws), "mcpServers": []}, timeout=120
            )
            session_id = new["sessionId"]
            agent_opt = [o for o in new.get("configOptions", []) if o.get("id") == "agent"]
            note("NEW", {"agent_option": agent_opt})
            await asyncio.sleep(3)
            for value in (AGENT, ""):
                try:
                    result = await session.request(
                        "session/set_config_option",
                        {"sessionId": session_id, "configId": "agent", "value": value},
                    )
                    agent_opt = [
                        o for o in result.get("configOptions", []) if o.get("id") == "agent"
                    ]
                    note("SET_AGENT", {"value": value, "agent_option": agent_opt})
                except Exception as exc:  # noqa: BLE001 - recorded, not raised
                    note("SET_AGENT_ERROR", {"value": value, "error": str(exc)})
                await asyncio.sleep(3)
            try:
                await session.request("session/close", {"sessionId": session_id}, timeout=10)
            except Exception as exc:  # noqa: BLE001
                note("CLOSE_ERROR", {"error": str(exc)})
        finally:
            await session.close(force=True)
        OUT.write_text("\n".join(log) + "\n", encoding="utf-8")
        print("\n".join(log))


if __name__ == "__main__":
    asyncio.run(main())
