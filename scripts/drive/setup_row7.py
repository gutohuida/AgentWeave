"""Build row 7's fixture: a git repository outside this repo, opened as a Hub project,
with a Haiku runner and the three agents the inbound-queue sweep needs.

    AW_HUB=http://127.0.0.1:8011 AW_KEY=... py -3.11 scripts/drive/setup_row7.py <fixture-dir>

Differs from `setup_row5.py` in one measured way: that script asks `POST /agents` for an agent
with no `runner_id` and is answered **422** (iteration 8), so its third agent never exists. An
unbound agent is row 7's contrast case for F114 — the refusal that must *not* burn a delivery
attempt — so this one creates it bound and then unbinds it with
`PATCH /agents/{name} {"runner_id": null}`, which is the route the Hub UI's own binding control
uses.

Prints `AW_PROJECT=` on one of its last lines. Git-initialised and committed first, because a
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
(root / "README.md").write_text(f"row7 fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "row7@example.invalid"],
    ["git", "config", "user.name", "row7"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "row7 fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"row7-{TAG}"})
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

AGENTS = (f"r7a{TAG}", f"r7b{TAG}", f"r7unbound{TAG}")
for name in AGENTS:
    code, _ = api("POST", f"{A}/agents", {"name": name, "runner_id": RUNNER})
    print(f"agent {name}: [{code}]")

code, body = api("PATCH", f"{A}/agents/{AGENTS[2]}", {"runner_id": None})
print(f"unbind {AGENTS[2]}: [{code}] runner_id={body.get('runner_id')!r}")

print()
print(f"AW_PROJECT={PID}")
print(f"AW_RUN_TAG={TAG}")
print(f"AW_RUNNER={RUNNER}")
print(f"AGENT_A={AGENTS[0]}")
print(f"AGENT_B={AGENTS[1]}")
print(f"AGENT_UNBOUND={AGENTS[2]}")
