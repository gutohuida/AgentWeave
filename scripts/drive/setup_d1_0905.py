"""Build the 2026-09-05 D-1 fixture: a fresh project outside this repo with two Haiku agents.

Independent of the night window's `setup_f286.py` fixture: its own directory, its own project,
its own agents, and both agents on full access so a turn can actually run a shell command.
"""
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
(root / "README.md").write_text(f"D-1 2026-09-05 fixture {TAG}\n", encoding="utf-8")
(root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"],
            ["git", "config", "user.email", "d1@example.invalid"],
            ["git", "config", "user.name", "d1"],
            ["git", "add", "README.md", "calc.py"],
            ["git", "commit", "-m", "d1 fixture"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"d1-{TAG}"})
show("POST /projects/open", code, proj, limit=400)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"
code, r = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU})
show("POST /runners", code, r, limit=260)
names = []
for suffix in ("a", "b"):
    name = f"d1{suffix}{TAG}"
    code, _ = api("POST", f"{A}/agents", {"name": name, "runner_id": r["id"]})
    print(f"POST /agents {name}: [{code}]")
    code, body = api("PATCH", f"{A}/agents/{name}", {"default_permission_mode": "bypassPermissions"})
    print(f"PATCH  {name} permission: [{code}] {str(body)[:120]}")
    names.append(name)
print()
print(f"AW_PROJECT={PID}")
print(f"AW_AGENTS={','.join(names)}")
