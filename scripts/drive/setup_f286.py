"""Build the F286 phase-0 fixture: a fresh project outside this repo with one Haiku agent."""
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, r"C:\Users\huida\Documents\projects\AgentWeave\scripts\drive")
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

root = pathlib.Path(sys.argv[1]).resolve()
TAG = time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text(f"F286 phase 0 fixture {TAG}\n", encoding="utf-8")
for cmd in (["git","init","-b","main"],["git","config","user.email","f286@example.invalid"],
            ["git","config","user.name","f286"],["git","add","README.md"],
            ["git","commit","-m","f286 fixture"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"f286-{TAG}"})
show("POST /projects/open", code, proj, limit=400)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"
code, r = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
show("POST /runners", code, r, limit=260)
code, _ = api("POST", f"{A}/agents", {"name": f"f286a{TAG}", "runner_id": r["id"]})
print(f"agent f286a{TAG}: [{code}]")
print()
print(f"AW_PROJECT={PID}")
print(f"AW_AGENT=f286a{TAG}")
