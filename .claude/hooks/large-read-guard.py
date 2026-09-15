"""PreToolUse guard: refuse whole-file Reads of large files in autonomous runs.

Every token a Read brings into context is re-read on every later call of the session; measured on
2026-09-14, tool results were ~34% of the windows' cache reads, led by whole reads of a 78 KB
STATE-day.json (16 times) and 100 KB spec-queue files. Active only when the autonomous driver set
AW_AUTONOMOUS=1 -- interactive sessions are never touched. Any failure here allows the Read: a
guard that breaks the session it is guarding costs more than the read.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LIMIT_BYTES = 60 * 1024
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb"}


def main() -> int:
    if os.environ.get("AW_AUTONOMOUS") != "1":
        return 0
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if event.get("tool_name") != "Read":
            return 0
        tool_input = event.get("tool_input") or {}
        if tool_input.get("limit"):
            return 0
        path = Path(tool_input.get("file_path") or "")
        if path.suffix.lower() in SKIP_SUFFIXES or not path.is_file():
            return 0
        size = path.stat().st_size
    except Exception:  # noqa: BLE001 - never break the session over the guard
        return 0
    if size <= LIMIT_BYTES:
        return 0
    sys.stderr.write(
        f"large-read-guard: {path.name} is {size // 1024} KB. In an autonomous run, read it by "
        "section: Grep for the heading or symbol you need, then Read with offset/limit (a few "
        "hundred lines). A whole read is paid again on every later call of this session.\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
