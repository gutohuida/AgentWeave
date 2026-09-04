"""Build the a-write-outside-the-workspace-is-recorded phase-9 drive fixture.

    AW_HUB=http://127.0.0.1:8011 py -3.11 scripts/drive/setup_awrite_p9.py <fixture-dir>

One scratch git repository *outside* this repo (the project root), one sibling directory outside
that root entirely, one runner on `claude-haiku-4-5-20251001`, one agent bound to it under the
**full-access** posture. The posture matters: `workspace` would put the write to the approver,
which would refuse it, and a refused write is not a write -- there would be nothing to record.

The project must be a git repository and the agent must be a writing agent, or the agent never
gets a worktree of its own and every path it writes is trivially `inside`.

Prints AW_PROJECT / AW_AGENT / AW_ROOT / AW_ELSEWHERE on the last lines.
"""

import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

base = pathlib.Path(sys.argv[1]).resolve()
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"

root = base / "proj"
elsewhere = base / "elsewhere"
root.mkdir(parents=True, exist_ok=True)
elsewhere.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text(f"a-write phase 9 fixture {TAG}\n", encoding="utf-8")
(root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "awrite@example.invalid"],
    ["git", "config", "user.name", "awrite"],
    ["git", "add", "README.md", "calc.py"],
    ["git", "commit", "-m", "a-write p9 fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"awrite-p9-{TAG}"})
show("POST /projects/open", code, proj, limit=400)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"

code, runner = api(
    "POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU}
)
show("POST /runners", code, runner, limit=260)

AGENT = f"writer{TAG}"
code, agent = api("POST", f"{A}/agents", {"name": AGENT, "runner_id": runner["id"]})
show("POST /agents", code, agent, limit=400)

code, patched = api(
    "PATCH", f"{A}/agents/{AGENT}", {"default_permission_mode": "bypassPermissions"}
)
show("PATCH /agents (full access)", code, patched, limit=400)

print()
print(f"AW_PROJECT={PID}")
print(f"AW_AGENT={AGENT}")
print(f"AW_ROOT={root}")
print(f"AW_ELSEWHERE={elsewhere}")
print(f"AW_RUN_TAG={TAG}")
