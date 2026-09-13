"""F299 R1 (day 2026-09-13, d2-r1) -- what does the INSTALLED harness do with each flag set?

    py -3.11 scripts/drive/t_d2_0913_f299_harness.py [COND ...] [--env inherit|plain|both]

DECISIONS.md 1b was decided against F299's 2026-09-09 drive, whose condition A *started*, read,
was refused every write, and blamed the operator's machine. The day's research (spec-queue/
research/2026-09-13.md, candidate 1) measured the same flags on 2.1.269 exiting 1 at spawn. It
measured through `subprocess` pipes, with every CLAUDE* variable stripped, and with `claude`'s
argument order rather than the Hub's. None of the three is what the Hub does:

  * Claude runs are spawned under a pseudo-terminal (`PtySession`, agent_trigger.py:2034), not a
    pipe. `PipeSession` (pty_runner.py:357, `stderr=STDOUT`) is Codex's. Under a PTY the harness
    sees a terminal on stdin, and its stderr and stdout share one stream by construction.
  * The Hub's spawn environment is its own `os.environ` (launchability.resolve_agent_env), so a
    Hub started inside a Claude Code session hands its children CLAUDECODE and friends, and a Hub
    started from a plain terminal does not. Both are measured, labelled `inherit` and `plain`.
  * argv comes from `runner_commands.build_command` itself, for the conditions it can produce.

The "policy" is `deniedMcpServers` passed through `--settings`, as the research did. It is not a
real managed-settings file. Every condition runs in a throwaway directory under %TEMP%, never under
~/.claude (a protected directory, which invalidated the research's first pass). Haiku only.

Conditions (all `--model claude-haiku-4-5-20251001`):
  A_hub     today's tree, F299's configuration: build_command's own argv for a `claude` run with
            the Hub's server injected, plus the policy blocking it.       (the research's Q4b)
  A_repro   F299's own reproduction flags: manual + approver, no --mcp-config.   (research P4)
  B_1b      1b as decided: A_hub's argv with only `--permission-prompt-tool X` removed. The server
            is still injected and still blocked. This is the shape 1b produces; the research's Q5
            dropped --mcp-config as well, which is not.
  B_q5      the research's Q5, for comparability: `--permission-mode manual` and nothing else.
  C_1b_none shape (a): B_1b plus `--permission-prompts none`.
  C_q3      the research's Q3: manual + `--permission-prompts none`, no --mcp-config.

The prompt is F299's own.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "hub"))

from hub.pty_runner import PtySession  # noqa: E402
from hub.runner_commands import CLAUDE_PERMISSION_PROMPT_TOOL, build_command  # noqa: E402

BASE = Path(os.environ["TEMP"]) / "d2_0913_f299"
MODEL = "claude-haiku-4-5-20251001"
PROMPT = "Create a file called written_A.txt containing the single word ok. Use your Write tool."
DENY = json.dumps({"deniedMcpServers": [{"serverName": "agentweave"}]})
TINY = '''from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tiny")


@mcp.tool()
def ping() -> str:
    """Return pong."""
    return "pong"


if __name__ == "__main__":
    mcp.run()
'''
# The PTY prefixes the stream with a window-title OSC terminated by ST (`ESC ]0;claude ESC \`), which
# glues itself to the first JSON line.
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[=>]")


def hub_argv(cli: str, mcp: list[str]) -> list[str]:
    return build_command(runner="claude", cli=cli, prompt=PROMPT, model=MODEL, mcp_command=mcp)


def with_policy(argv: list[str]) -> list[str]:
    """Insert the policy before `-p`, which build_command always places last."""
    i = argv.index("-p")
    return [*argv[:i], "--settings", DENY, *argv[i:]]


def without_approver(argv: list[str]) -> list[str]:
    i = argv.index("--permission-prompt-tool")
    assert argv[i + 1] == CLAUDE_PERMISSION_PROMPT_TOOL
    return argv[:i] + argv[i + 2 :]


def plus_prompts_none(argv: list[str]) -> list[str]:
    i = argv.index("-p")
    return [*argv[:i], "--permission-prompts", "none", *argv[i:]]


def bare(cli: str, *flags: str) -> list[str]:
    return [
        cli,
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        MODEL,
        *flags,
        "-p",
        PROMPT,
    ]


def conditions(cli: str, mcp: list[str]) -> dict[str, list[str]]:
    a_hub = with_policy(hub_argv(cli, mcp))
    b_1b = without_approver(a_hub)
    return {
        "A_hub": a_hub,
        "A_repro": bare(
            cli,
            "--permission-mode",
            "manual",
            "--permission-prompt-tool",
            CLAUDE_PERMISSION_PROMPT_TOOL,
        ),
        "B_1b": b_1b,
        "B_q5": bare(cli, "--permission-mode", "manual"),
        "C_1b_none": plus_prompts_none(b_1b),
        "C_q3": bare(cli, "--permission-mode", "manual", "--permission-prompts", "none"),
    }


def environment(kind: str) -> dict[str, str]:
    if kind == "inherit":
        return dict(os.environ)
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("CLAUDE")}


def run(name: str, argv: list[str], env_kind: str) -> dict:
    root = BASE / f"{name}__{env_kind}"
    if root.exists():
        shutil.rmtree(root)
    ws = root / "ws"
    ws.mkdir(parents=True)
    t0 = time.time()
    pty = PtySession.spawn(argv, cwd=str(ws), env=environment(env_kind), dimensions=(24, 32000))
    chunks = []
    deadline = t0 + 240
    while time.time() < deadline:
        chunk = pty.read()
        if not chunk:
            break
        chunks.append(chunk)
    if pty.isalive():
        pty.terminate(force=True)
    rc = pty.wait()
    raw = ANSI.sub("", "".join(chunks))
    (root / "transcript.txt").write_text(raw, encoding="utf-8")
    events, text_lines = [], []
    for line in raw.replace("\r", "").split("\n"):
        s = line.strip()
        if not s:
            continue
        try:
            events.append(json.loads(s))
        except ValueError:
            text_lines.append(s)
    init = next(
        (e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None
    )
    result = next((e for e in events if e.get("type") == "result"), None)
    out = {
        "cond": name,
        "env": env_kind,
        "rc": rc,
        "secs": round(time.time() - t0, 1),
        # The `init` line, not a model call: under the PTY it is printed even by a spawn that then
        # exits 1 at startup. A model call is the presence of `result` below. (R1's evidence file
        # predates this rename and calls it `started`.)
        "init_emitted": init is not None,
        "flags": [a if len(a) < 80 else a[:40] + "..." for a in argv[1:-2]],
        "non_json_lines": text_lines[:6],
        "file_written": (ws / "written_A.txt").exists(),
    }
    if init is not None:
        servers = init.get("mcp_servers") or []
        out["init_agentweave"] = next(
            (s for s in servers if s.get("name") == "agentweave"), "ABSENT"
        )
        out["init_mcp_server_errors"] = init.get("mcp_server_errors")
        out["init_permissionMode"] = init.get("permissionMode")
    if result is not None:
        out["subtype"] = result.get("subtype")
        out["num_turns"] = result.get("num_turns")
        out["cost"] = result.get("total_cost_usd")
        out["denials"] = [d.get("tool_name") for d in result.get("permission_denials") or []]
        out["result"] = (result.get("result") or "")[:600]
    return out


def main() -> None:
    args = sys.argv[1:]
    env_kinds = ["inherit", "plain"]
    if "--env" in args:
        i = args.index("--env")
        env_kinds = ["inherit", "plain"] if args[i + 1] == "both" else [args[i + 1]]
        args = args[:i] + args[i + 2 :]
    cli = shutil.which("claude")
    assert cli, "claude is not on PATH"
    version = subprocess.run([cli, "--version"], capture_output=True, text=True).stdout.strip()
    BASE.mkdir(parents=True, exist_ok=True)
    tiny = BASE / "tiny_mcp.py"
    tiny.write_text(TINY, encoding="utf-8")
    conds = conditions(cli, [sys.executable, str(tiny)])
    wanted = args or list(conds)
    results = {"claude_version": version, "runs": []}
    for kind in env_kinds:
        for name in wanted:
            r = run(name, conds[name], kind)
            print(json.dumps(r, indent=1), flush=True)
            results["runs"].append(r)
    (BASE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("claude", version, "->", BASE / "results.json")


if __name__ == "__main__":
    main()
