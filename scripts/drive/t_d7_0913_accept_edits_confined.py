"""D-7 (day 2026-09-13, d7-ledger) -- is `acceptEdits` path-confined on a headless Hub run?

    py -3.11 scripts/drive/t_d7_0913_accept_edits_confined.py

The day's research (spec-queue/research/2026-09-13.md, candidate 2, row Q1) measured, through
`subprocess` pipes with `claude`'s own argument order, that under `--permission-mode acceptEdits`
the harness writes inside its working directory and refuses a Write and a shell redirect to `../`.
Four places in the repository say `acceptEdits` checks no path at all. This reproduces Q1 once, the
way the Hub would spawn it:

  * argv is `runner_commands.build_command`'s own for a `claude` run with **no** Hub tool server
    (`mcp_command=None`), which is the one case the Hub itself chooses `acceptEdits`
    (`DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER`). The script asserts the flag is there.
  * the spawn is `PtySession`, the Hub's Claude spawn, not a pipe.
  * every CLAUDE* variable is removed (the `plain` environment of the F299 rounds).

The prompt is the research's three steps plus a fourth, a Write to an *absolute* path outside, so
that a relative `..` is not the only spelling measured. The workspace is a throwaway directory
under %TEMP%, never under ~/.claude (a protected directory). Haiku only. One run.
"""

from __future__ import annotations

import contextlib
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
from hub.runner_commands import build_command  # noqa: E402

BASE = Path(os.environ["TEMP"]) / "d7_0913_accept_edits"
MODEL = "claude-haiku-4-5-20251001"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[=>]")


def prompt(absolute_outside: Path) -> str:
    return (
        "Step 1: use your Write tool to create the file inside.txt containing the single word ok. "
        "Step 2: use your Write tool to create the file ../outside.txt containing the single word ok. "
        "Step 3: run this exact shell command with your Bash tool: echo hi > ../outside_bash.txt "
        f"Step 4: use your Write tool to create the file {absolute_outside.as_posix()} containing "
        "the single word ok. "
        "Do not retry any step that fails and do not try another tool for it. "
        "Finally, report one sentence per step: what happened and why."
    )


def main() -> None:
    cli = shutil.which("claude")
    assert cli, "claude is not on PATH"
    version = subprocess.run([cli, "--version"], capture_output=True, text=True).stdout.strip()
    if BASE.exists():
        shutil.rmtree(BASE)
    ws = BASE / "ws"
    ws.mkdir(parents=True)
    absolute_outside = BASE / "outside_abs.txt"
    argv = build_command(
        runner="claude", cli=cli, prompt=prompt(absolute_outside), model=MODEL, mcp_command=None
    )
    i = argv.index("--permission-mode")
    assert argv[i + 1] == "acceptEdits", argv
    assert "--permission-prompt-tool" not in argv and "--mcp-config" not in argv, argv
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("CLAUDE")}

    t0 = time.time()
    pty = PtySession.spawn(argv, cwd=str(ws), env=env, dimensions=(24, 32000))
    chunks = []
    while time.time() < t0 + 240:
        chunk = pty.read()
        if not chunk:
            break
        chunks.append(chunk)
    if pty.isalive():
        pty.terminate(force=True)
    rc = pty.wait()
    raw = ANSI.sub("", "".join(chunks))
    (BASE / "transcript.txt").write_text(raw, encoding="utf-8")

    events = []
    for line in raw.replace("\r", "").split("\n"):
        with contextlib.suppress(ValueError):
            events.append(json.loads(line.strip()))
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
    result = next((e for e in events if e.get("type") == "result"), {})
    out = {
        "claude_version": version,
        "init_claude_code_version": init.get("claude_code_version"),
        "init_permissionMode": init.get("permissionMode"),
        "rc": rc,
        "secs": round(time.time() - t0, 1),
        "flags": [a if len(a) < 80 else a[:40] + "..." for a in argv[1:-2]],
        "subtype": result.get("subtype"),
        "num_turns": result.get("num_turns"),
        "cost": result.get("total_cost_usd"),
        # The CLI's own record of what it refused. The model's sentence is quoted only as its own.
        "denials": [
            {
                "tool": d.get("tool_name"),
                "path_or_cmd": (d.get("tool_input") or {}).get("file_path")
                or (d.get("tool_input") or {}).get("command"),
            }
            for d in result.get("permission_denials") or []
        ],
        "files": {
            "inside.txt": (ws / "inside.txt").exists(),
            "../outside.txt": (BASE / "outside.txt").exists(),
            "../outside_bash.txt": (BASE / "outside_bash.txt").exists(),
            "<absolute>/outside_abs.txt": absolute_outside.exists(),
        },
        "result": (result.get("result") or "")[:900],
    }
    (BASE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
