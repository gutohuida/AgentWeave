"""6.3 drive setup: git-backed project, haiku runner, author + holder + unreach agents."""
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"unstaffed-drive-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text(f"unstaffed drive fixture {TAG}\n", encoding="utf-8")
(root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "unstaffed@example.invalid"],
    ["git", "config", "user.name", "unstaffed"],
    ["git", "add", "README.md", "calc.py"],
    ["git", "commit", "-m", "unstaffed drive fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"unstaffed-{TAG}"})
show("POST /projects/open", code, proj, limit=300)
PID = proj["id"]
A = f"/projects/{PID}"

code, runner = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
show("POST /runners", code, runner, limit=200)
RID = runner["id"]

for n in ("author", "holder1", "holder2", "unreach"):
    c, agent = api("POST", f"{A}/agents", {"name": n, "runner_id": RID})
    show(f"POST /agents {n}", c, agent, limit=200)
    api("PATCH", f"{A}/agents/{n}", {"default_permission_mode": "bypassPermissions"})

print()
print(f"AW_PROJECT={PID}")
print(f"AW_ROOT={root}")
print(f"AW_RUNNER={RID}")
print(f"AW_TAG={TAG}")
