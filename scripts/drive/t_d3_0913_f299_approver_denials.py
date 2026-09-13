"""F299 R2 (day 2026-09-13, d3-r2) -- does a refusal the APPROVER decides also appear in the
harness's own `permission_denials`?

    py -3.11 scripts/drive/t_d3_0913_f299_approver_denials.py

R1's design D6 records the result line's `permission_denials` only for Claude runs whose command
names no approver, "so a refusal `_decide` or the operator already recorded is not recorded twice".
That argument presumes the harness lists the approver's refusals there too. If it does not, the
keying on argv buys nothing and costs the approver-named runs every refusal the harness decides by
itself. This measures it on the installed build.

A stand-in server named `agentweave` exposes `approve_tool_call`, which refuses everything with
the JSON shape `mcp_server.approve_tool_call` returns. argv is `build_command`'s own, no policy, so
the approver is named and served. Spawned through `PtySession`, `plain` environment, Haiku.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import t_d2_0913_f299_harness as r1  # noqa: E402

DENYING = '''import json, sys
from pathlib import Path
from typing import Any, Dict
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agentweave")


@mcp.tool()
def approve_tool_call(tool_name: str, input: Dict[str, Any], tool_use_id: str = ""):
    """Runtime approval endpoint."""
    with open(sys.argv[1], "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"tool_name": tool_name, "tool_use_id": tool_use_id}) + "\\n")
    return json.dumps({"behavior": "deny", "message": "Denied: r2 stand-in refuses everything."})


if __name__ == "__main__":
    mcp.run()
'''


def main() -> None:
    cli = shutil.which("claude")
    assert cli
    base = r1.BASE.parent / "d3_0913_f299_denials"
    base.mkdir(parents=True, exist_ok=True)
    server = base / "denying_mcp.py"
    server.write_text(DENYING, encoding="utf-8")
    received = base / "approver_received.jsonl"
    received.unlink(missing_ok=True)
    argv = r1.hub_argv(cli, [sys.executable, str(server), str(received)])
    assert r1.CLAUDE_PERMISSION_PROMPT_TOOL in argv
    out = r1.run("D_approver_denies", argv, "plain")
    transcript = (r1.BASE / "D_approver_denies__plain" / "transcript.txt").read_text(
        encoding="utf-8"
    )
    tool_uses = []
    for line in transcript.split("\n"):
        try:
            obj = json.loads(line.strip())
        except ValueError:
            continue
        if obj.get("type") == "assistant":
            for block in obj.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    tool_uses.append((block.get("name"), block.get("id")))
        if obj.get("type") == "result":
            out["permission_denials_full"] = obj.get("permission_denials")
    out["tool_uses"] = tool_uses
    # What the approver itself was handed: the join D6 needs is on this `tool_use_id`.
    out["approver_received"] = (
        [json.loads(x) for x in received.read_text(encoding="utf-8").splitlines() if x.strip()]
        if received.exists()
        else []
    )
    print(json.dumps(out, indent=1))
    (base / "result.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
