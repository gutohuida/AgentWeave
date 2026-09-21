"""D-2 (2026-09-21) fixture: one project, one Haiku runner, agents alpha/beta. Never :8000/:8010."""
import os, pathlib, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aw import api
assert not os.environ["AW_HUB"].endswith((":8000", ":8010"))
root = pathlib.Path.home() / "Documents" / f"drive-0921b-{time.strftime('%H%M%S')}"
root.mkdir(parents=True); (root / "README.md").write_text("x\n")
for c in (["git","init","-b","main"],["git","config","user.email","d@e.invalid"],["git","config","user.name","d"],["git","add","."],["git","commit","-m","i"]):
    subprocess.run(c, cwd=root, check=True, capture_output=True)
_, p = api("POST", "/projects/open", {"path": str(root), "name": "d2"})
A = "/projects/%s" % p["id"]
_, rn = api("POST", A + "/runners", {"name": "haiku", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
for n in ("alpha", "beta"):
    c, b = api("POST", A + "/agents", {"name": n, "runner_id": rn["id"]}); assert c == 201, b
    api("PATCH", "%s/agents/%s" % (A, n), {"default_permission_mode": "bypassPermissions"})
print(p["id"], rn["id"], root)
