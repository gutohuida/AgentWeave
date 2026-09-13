"""F299 R2 (day 2026-09-13, d3-r2) -- does a PERMITTED harness start its MCP server before an
unrelated early exit?

    py -3.11 scripts/drive/t_d3_0913_f299_early_exit.py [COND ...]

R1's design D3 counts an earlier run as a *test of the harness* when the Hub injected its server,
the run has an `exit_code`, it ended `completed` or `failed`, and `mcp_adapter_online_at` is NULL.
The adapter's announce (`mcp_server.py` `_announce_adapter_online`) is made when the adapter process
starts. So D3 is only sound if every harness exit that leaves `exit_code` set happens *after* the
harness has started its servers. This script asks that question of the installed build, with no
policy in force: every condition below is a machine on which the approver would work.

The server here writes a marker file the moment it is started, standing in for the announce (which
is the adapter's first act). A missing marker means the harness exited without starting the server,
which D3 would read as the server having been refused.

Conditions (argv from `runner_commands.build_command`, spawned through `PtySession`, the `plain`
environment, which R1 found indistinguishable from `inherit`):
  E_ok        control: a turn that succeeds.
  E_badflag   the runner's flags carry an option the harness does not know (an operator typo).
  E_badmodel  a model name the API does not serve.
  E_resume    `--resume` with a session id the harness has never seen.
  E_badkey    ANTHROPIC_API_KEY set to a key that is not valid.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import t_d2_0913_f299_harness as r1  # noqa: E402

BASE = r1.BASE.parent / "d3_0913_f299_early"
PROMPT = "Reply with just the word ok."
MARKER_SERVER = '''import sys, time
from pathlib import Path
Path(sys.argv[1]).write_text(str(time.time()), encoding="utf-8")
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tiny")


@mcp.tool()
def ping() -> str:
    """Return pong."""
    return "pong"


if __name__ == "__main__":
    mcp.run()
'''


def argv(cli: str, marker: Path, **kw) -> list[str]:
    server = BASE / "marker_mcp.py"
    return r1.build_command(
        runner="claude",
        cli=cli,
        prompt=PROMPT,
        model=kw.pop("model", r1.MODEL),
        mcp_command=[sys.executable, str(server), str(marker)],
        **kw,
    )


def main() -> None:
    cli = shutil.which("claude")
    assert cli, "claude is not on PATH"
    import subprocess

    version = subprocess.run([cli, "--version"], capture_output=True, text=True).stdout.strip()
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "marker_mcp.py").write_text(MARKER_SERVER, encoding="utf-8")
    conds = {
        "E_ok": ({}, None),
        "E_badflag": ({"extra_flags": ["--no-such-flag-0913"]}, None),
        "E_badmodel": ({"model": "claude-no-such-model-0913"}, None),
        "E_resume": ({"session_id": str(uuid.uuid4())}, None),
        "E_badkey": ({}, {"ANTHROPIC_API_KEY": "sk-ant-api03-not-a-real-key-0913"}),
    }
    wanted = sys.argv[1:] or list(conds)
    results = {"claude_version": version, "runs": []}
    for name in wanted:
        kw, extra_env = conds[name]
        marker = BASE / f"{name}.marker"
        marker.unlink(missing_ok=True)
        cmd = argv(cli, marker, **kw)
        if extra_env:
            base_env = r1.environment

            def patched(kind: str, _extra=extra_env, _base=base_env) -> dict:
                return {**_base(kind), **_extra}

            r1.environment = patched
        t_end = None
        try:
            out = r1.run(name, cmd, "plain")
        finally:
            if extra_env:
                r1.environment = base_env
        t_end = time.time()
        out["server_started"] = marker.exists()
        if marker.exists():
            out["server_started_secs_before_end"] = round(
                t_end - float(marker.read_text(encoding="utf-8")), 1
            )
        out.pop("file_written", None)
        print(json.dumps(out, indent=1), flush=True)
        results["runs"].append(out)
    (BASE / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("claude", version, "->", BASE / "results.json")


if __name__ == "__main__":
    main()
