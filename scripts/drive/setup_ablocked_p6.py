"""Build the a-blocked-agent-workspace-holds-its-input phase-6 fixture.

    AW_HUB=http://127.0.0.1:8011 py -3.11 scripts/drive/setup_ablocked_p6.py <fixture-dir>

One scratch git repository outside this repo, one runner on `claude-haiku-4-5-20251001`, one
agent bound to it. The agent must be a *writing* agent and the project must be a git repository,
or `takes_task_workspace`/`resolve_agent_workspace` never reach `ensure_worktree` at all and the
whole drive would assert over a code path it never entered.

Prints AW_PROJECT / AW_AGENT / AW_ROOT on the last lines.
"""

import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

root = pathlib.Path(sys.argv[1]).resolve()
TAG = os.environ.get("AW_RUN_TAG") or time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"

root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text(f"a-blocked phase 6 fixture {TAG}\n", encoding="utf-8")
(root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "ablocked@example.invalid"],
    ["git", "config", "user.name", "ablocked"],
    ["git", "add", "README.md", "calc.py"],
    ["git", "commit", "-m", "a-blocked p6 fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"ablocked-p6-{TAG}"})
show("POST /projects/open", code, proj, limit=400)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"

code, runner = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
show("POST /runners", code, runner, limit=260)

AGENT = f"blocked{TAG}"
code, agent = api("POST", f"{A}/agents", {"name": AGENT, "runner_id": runner["id"]})
show("POST /agents", code, agent, limit=400)

print()
print(f"AW_PROJECT={PID}")
print(f"AW_AGENT={AGENT}")
print(f"AW_ROOT={root}")
print(f"AW_RUN_TAG={TAG}")
