"""D-1 (day 2026-09-21): independent replication of group 7 of a-first-turn-is-not-told-it-has-nothing.
Three brand-new Haiku agents, hub_client unset, same instruction; classify each first turn from the
run's agent_outputs. Never :8000/:8010.  AW_HUB=http://127.0.0.1:8097 AW_KEY=... AW_DB=<sqlite path>"""
import os, pathlib, sqlite3, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api
HUB = os.environ.get("AW_HUB", "")
assert HUB and not HUB.endswith((":8000", ":8010"))
HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
root = pathlib.Path.home() / "Documents" / f"drive-0921-g7-{TAG}"
root.mkdir(parents=True); (root / "README.md").write_text("x\n")
for c in (["git","init","-b","main"],["git","config","user.email","d@e.invalid"],["git","config","user.name","d"],["git","add","."],["git","commit","-m","i"]):
    subprocess.run(c, cwd=root, check=True, capture_output=True)
_, proj = api("POST", "/projects/open", {"path": str(root), "name": "g7-%s" % TAG})
A = "/projects/%s" % proj["id"]; print("project", proj["id"])
_, rn = api("POST", A + "/runners", {"name": "haiku", "cli": "claude", "model": HAIKU})
runs = {}
for n in ("g7a", "g7b", "g7c"):
    c, b = api("POST", A + "/agents", {"name": n, "runner_id": rn["id"]}); assert c == 201, b
    api("PATCH", "%s/agents/%s" % (A, n), {"default_permission_mode": "bypassPermissions"})
for n in runs or ("g7a", "g7b", "g7c"):
    c, t = api("POST", A + "/agent/trigger", {"agent": n, "session_mode": "new",
        "message": 'Create a task titled "F302 probe task" with description "measurement probe" in this project, then stop.',
        "overrides": {"permission_mode": "bypassPermissions"}})
    print(n, c, t.get("run_id") if isinstance(t, dict) else t); runs[n] = t.get("run_id")
    time.sleep(1)
db = sqlite3.connect("file:%s?mode=ro" % os.environ["AW_DB"], uri=True)
deadline = time.time() + 240
while time.time() < deadline:
    st = [db.execute("select status from runs where id=?", (r,)).fetchone() for r in runs.values()]
    if all(s and s[0] not in ("running", "queued", "pending") for s in st): break
    time.sleep(5)
cols = [r[1] for r in db.execute("pragma table_info(agent_outputs)")]
print("agent_outputs cols:", cols)
for n, r in runs.items():
    print("\n==", n, r, db.execute("select status,exit_code from runs where id=?", (r,)).fetchone())
    rows = db.execute("select * from agent_outputs where run_id=? order by sequence", (r,)).fetchall()
    blob = "\n".join(str(x) for x in rows)
    mcp = "mcp__agentweave__" in blob; http = any(k in blob for k in ("curl ", "Invoke-WebRequest", "python -c", "agent-actions"))
    print("  rows:", len(rows), " MCP:", mcp, " HTTP-ish:", http)
    for x in rows[:8]: print("   ", str(x)[:230])
_, tk = api("GET", A + "/tasks"); print("\ntasks:", [(t["title"]) for t in (tk if isinstance(tk, list) else tk.get("tasks", []))])
