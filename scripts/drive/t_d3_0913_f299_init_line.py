"""F299 R2 (day 2026-09-13, d3-r2) -- does the Hub's own read loop see the harness's `init` line?

    py -3.11 scripts/drive/t_d3_0913_f299_init_line.py

Any mechanism keyed on the harness's `system/init` line is only real if `_execute_run`'s read loop
(agent_trigger.py:2220-2229 -> `_flush_line`) turns that line into a parsed JSON object. R1's
harness script needed a wider escape regex than the Hub's (`pty_runner._ANSI_ESCAPE_RE` has no
`ESC =` / `ESC >` branch), so this replays the Hub's exact handling -- split on "\\n", rstrip "\\r",
`strip_ansi_escapes`, `parse_claude_line` -- over a raw PTY capture.

The condition is A_hub from t_d2_0913_f299_harness.py: today's argv with the policy blocking the
Hub's server. On 2.1.269 it exits 1 before any model call, so it spends nothing.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import t_d2_0913_f299_harness as r1  # noqa: E402

from hub.pty_runner import PtySession, strip_ansi_escapes  # noqa: E402
from hub.runner_parsing import parse_claude_line  # noqa: E402


def main() -> None:
    cli = shutil.which("claude")
    assert cli
    base = r1.BASE.parent / "d3_0913_f299_init"
    ws = base / "ws"
    if base.exists():
        shutil.rmtree(base)
    ws.mkdir(parents=True)
    tiny = base / "tiny_mcp.py"
    tiny.write_text(r1.TINY, encoding="utf-8")
    argv = r1.conditions(cli, [sys.executable, str(tiny)])["A_hub"]
    pty = PtySession.spawn(argv, cwd=str(ws), env=r1.environment("plain"), dimensions=(24, 32000))
    chunks, t0 = [], time.time()
    while time.time() < t0 + 120:
        chunk = pty.read()
        if not chunk:
            break
        chunks.append(chunk)
    rc = pty.wait()
    raw = "".join(chunks)
    (base / "raw.txt").write_text(raw, encoding="utf-8")
    # _execute_run's loop, verbatim in shape.
    lines, buffer = [], raw
    while "\n" in buffer:
        raw_line, buffer = buffer.split("\n", 1)
        lines.append(raw_line)
    if buffer.strip():
        lines.append(buffer)
    report = {"rc": rc, "lines": []}
    for raw_line in lines:
        line = strip_ansi_escapes(raw_line.rstrip("\r"))
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            kind = f"json:{obj.get('type')}/{obj.get('subtype')}"
        except ValueError:
            kind = "NOT-JSON"
        parsed = parse_claude_line(line)
        report["lines"].append(
            {
                "kind": kind,
                "head_repr": repr(line[:60]),
                "parsed_session_id": parsed.session_id,
                "parsed_events": [e.kind for e in parsed.events],
            }
        )
    print(json.dumps(report, indent=1))
    (base / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
