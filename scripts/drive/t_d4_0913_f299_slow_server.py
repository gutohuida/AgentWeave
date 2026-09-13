"""F299 R3 (day 2026-09-13, d4-r3) -- does the harness wait for a SLOW server before `init`?

    py -3.11 scripts/drive/t_d4_0913_f299_slow_server.py [COND ...]

R2's design D3 counts an earlier run as a *test of the harness* only once the harness wrote its
`system/init` line, on the argument that "the harness writes `init` after it has dealt with its MCP
servers", so a server `init` reports `connected` has already made the adapter's announce (the
adapter's first act, `mcp_server.py` `main()`, before it serves). R2 measured four failure modes,
all with a stand-in that starts at once. It did not measure a server that is slow to become ready,
which is what the real adapter is when its announce waits on the Hub (`_hub_request`, up to 10 s)
or its imports are cold.

If the harness writes `init` with the server still `pending`, or gives up on it and writes
`failed`, then a turn can end -- `completed`, `exit_code` 0, `init` seen -- before the adapter
announces, on a machine where the approver works. D3 would count that as a refutation.

The stand-in writes `<marker>.start` when launched, sleeps DELAY seconds (standing in for a slow
announce), writes `<marker>.serving`, then serves. Each output chunk is timestamped so the `init`
line's arrival can be placed against both markers. No policy is in force: every condition is a
permitted harness.

Conditions (argv from `runner_commands.build_command`, spawned through `PtySession`, `plain` env):
  S_0    control: the server serves at once.
  S_8    serves after 8 s (inside the adapter's own 10 s announce timeout).
  S_45   serves after 45 s (beyond it, and beyond a 30 s connect timeout if the harness has one).
  S_8_nb S_8 with MCP_CONNECTION_NONBLOCKING=true in the spawn environment. The Hub hands its
         children its own os.environ (launchability.resolve_agent_env), so an operator shell that
         sets it reaches every run. Asks whether `init` can then precede the server with `pending`.
  S_crash the server exits 1 at start, standing in for an adapter whose import fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import t_d2_0913_f299_harness as r1  # noqa: E402

BASE = r1.BASE.parent / "d4_0913_f299_slow"
PROMPT = "Reply with just the word ok."
SLOW_SERVER = '''import sys, time
from pathlib import Path
marker, delay = sys.argv[1], float(sys.argv[2])
Path(marker + ".start").write_text(str(time.time()), encoding="utf-8")
if delay < 0:
    sys.exit(1)
time.sleep(delay)
Path(marker + ".serving").write_text(str(time.time()), encoding="utf-8")
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tiny")


@mcp.tool()
def ping() -> str:
    """Return pong."""
    return "pong"


if __name__ == "__main__":
    mcp.run()
'''


def run(name: str, delay: float, cli: str, extra_env: dict[str, str] | None = None) -> dict:
    root = BASE / name
    if root.exists():
        shutil.rmtree(root)
    ws = root / "ws"
    ws.mkdir(parents=True)
    marker = root / "m"
    cmd = r1.build_command(
        runner="claude",
        cli=cli,
        prompt=PROMPT,
        model=r1.MODEL,
        mcp_command=[sys.executable, str(BASE / "slow_mcp.py"), str(marker), str(delay)],
    )
    t0 = time.time()
    env = {**r1.environment("plain"), **(extra_env or {})}
    pty = r1.PtySession.spawn(cmd, cwd=str(ws), env=env, dimensions=(24, 32000))
    stamped: list[tuple[float, str]] = []
    buf = ""
    deadline = t0 + 240
    while time.time() < deadline:
        chunk = pty.read()
        if not chunk:
            break
        now = time.time()
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            stamped.append((now, r1.ANSI.sub("", line).strip()))
    if buf.strip():
        stamped.append((time.time(), r1.ANSI.sub("", buf).strip()))
    if pty.isalive():
        pty.terminate(force=True)
    rc = pty.wait()
    t_end = time.time()

    def rel(p: Path) -> float | None:
        return round(float(p.read_text(encoding="utf-8")) - t0, 1) if p.exists() else None

    out: dict = {
        "cond": name,
        "delay": delay,
        "rc": rc,
        "secs": round(t_end - t0, 1),
        "server_start_at": rel(Path(str(marker) + ".start")),
        "server_serving_at": rel(Path(str(marker) + ".serving")),
    }
    for ts, line in stamped:
        try:
            ev = json.loads(line)
        except ValueError:
            if line:
                out.setdefault("text_lines", []).append([round(ts - t0, 1), line[:160]])
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            out["init_at"] = round(ts - t0, 1)
            servers = ev.get("mcp_servers") or []
            out["init_agentweave"] = next(
                (s for s in servers if s.get("name") == "agentweave"), "ABSENT"
            )
        elif ev.get("type") == "result":
            out["result_at"] = round(ts - t0, 1)
            out["subtype"] = ev.get("subtype")
            out["num_turns"] = ev.get("num_turns")
            out["cost"] = ev.get("total_cost_usd")
            out["result"] = (ev.get("result") or "")[:200]
    (root / "stamped.json").write_text(
        json.dumps([[round(t - t0, 2), s] for t, s in stamped], indent=0), encoding="utf-8"
    )
    return out


def main() -> None:
    cli = shutil.which("claude")
    assert cli, "claude is not on PATH"
    version = subprocess.run([cli, "--version"], capture_output=True, text=True).stdout.strip()
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "slow_mcp.py").write_text(SLOW_SERVER, encoding="utf-8")
    conds = {
        "S_0": (0.0, None),
        "S_8": (8.0, None),
        "S_45": (45.0, None),
        "S_8_nb": (8.0, {"MCP_CONNECTION_NONBLOCKING": "true"}),
        "S_crash": (-1.0, None),
    }
    wanted = sys.argv[1:] or list(conds)
    results = {"claude_version": version, "runs": []}
    for name in wanted:
        delay, extra_env = conds[name]
        out = run(name, delay, cli, extra_env)
        print(json.dumps(out, indent=1), flush=True)
        results["runs"].append(out)
    (BASE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("claude", version, "->", BASE / "results.json")


if __name__ == "__main__":
    main()
