"""Build the a-turn-says-how-it-ended phase-6 fixture: a fresh project outside this repo with
two agents — one that runs Haiku turns, one whose runner cannot spawn.

    AW_HUB=http://127.0.0.1:8011 py -3.11 scripts/drive/setup_aturn_p6.py <fixture-dir>

Both runners bind `claude-haiku-4-5-20251001` — the failing one fails on an unknown *flag*, not on
an unknown model, so the standing "every real agent turn binds Haiku" directive holds for the one
turn that reaches a model at all.

Prints AW_PROJECT on the last lines.
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
(root / "README.md").write_text(f"a-turn phase 6 fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "p6@example.invalid"],
    ["git", "config", "user.name", "p6"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "a-turn p6 fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"aturn-p6-{TAG}"})
show("POST /projects/open", code, proj, limit=400)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"

code, good = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
show("POST /runners (haiku)", code, good, limit=260)

code, bad = api(
    "POST",
    f"{A}/runners",
    {
        "name": f"haiku-badflag-{TAG}",
        "cli": "claude",
        "model": HAIKU,
        # An unknown flag, appended verbatim by `runner_commands.py:266`. The CLI rejects it and
        # exits non-zero before any model is contacted, which is how this drive gets a *failed*
        # run without inventing a fake model.
        "flags": ["--aw-p6-no-such-flag"],
    },
)
show("POST /runners (bad flag)", code, bad, limit=260)

for name, rid in ((f"p6driver{TAG}", good["id"]), (f"p6fail{TAG}", bad["id"])):
    code, _ = api("POST", f"{A}/agents", {"name": name, "runner_id": rid})
    print(f"agent {name}: [{code}]")

print()
print(f"AW_PROJECT={PID}")
print(f"AW_RUN_TAG={TAG}")
print(f"AW_AGENT_OK=p6driver{TAG}")
print(f"AW_AGENT_FAIL=p6fail{TAG}")
