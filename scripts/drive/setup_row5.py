"""Build row 5's fixture: a git repository outside this repo, opened as a Hub project,
with a Haiku runner and the agents the runs sweep needs.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/setup_row5.py <fixture-dir>

Prints the project id on the last line. Git-initialised and committed first, because a
writing agent needs a repository to cut a worktree from.
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
(root / "README.md").write_text(f"row5 fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "row5@example.invalid"],
    ["git", "config", "user.name", "row5"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "row5 fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"row5-{TAG}"})
show("POST /projects/open", code, proj, limit=400)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"

code, runner = api(
    "POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU}
)
show("POST /runners", code, runner, limit=300)
RUNNER = runner["id"]

for name, rid in (
    (f"r5runner{TAG}", RUNNER),  # the agent that actually runs turns
    (f"r5norun{TAG}", None),  # no runner bound
    (f"r5arch{TAG}", RUNNER),  # archived below
):
    body = {"name": name}
    if rid:
        body["runner_id"] = rid
    code, made = api("POST", f"{A}/agents", body)
    print(f"agent {name}: [{code}]")

code, _ = api("POST", f"{A}/agents/r5arch{TAG}/archive")
print(f"archive r5arch{TAG}: [{code}]")

print()
print(f"AW_PROJECT={PID}")
print(f"AW_RUN_TAG={TAG}")
print(f"AW_RUNNER={RUNNER}")
