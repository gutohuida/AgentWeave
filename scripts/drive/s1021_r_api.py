"""night-recheck API drive (scratch Hub :8160, profile r1021): F810, F832, F798.

    AW_E2E_STATE=~/.agentweave/e2e-r1021.json AW_P=<project> py -3.11 scripts/drive/s1021_r_api.py
"""
import json, os, pathlib, subprocess, sys
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-r1021.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
P = os.environ["AW_P"]; B = f"/projects/{P}"
def r(m, p, b=None):
    s, x = e2e.request(m, B + p, b); print(m, p, "->", s, json.dumps(x, ensure_ascii=False)[:500]); return s, x

print("--- F810")
_, rs = r("GET", "/runners"); rid = rs[0]["id"]; r("POST", "/agents", {"name": "gamma", "runner_id": rid}); r("PATCH", "/agents/gamma", {"runner_id": None})
s, x = r("POST", "/agent/trigger", {"agent": "gamma", "message": "hello gamma"})
r("GET", "/queue/gamma/status")
s, x = r("POST", "/session/sync", {"data": {"agents": {"alpha": {}, "beta": {}}}})
print("F810", "CONFIRMED" if s == 409 and "agent_removal_under_held_work" in json.dumps(x) else "REOPENED")
_, ag = r("GET", "/agents")
print("gamma still on roster:", "gamma" in json.dumps(ag))

print("--- F832")
s, t = r("POST", "/tasks", {"title": "f832 task", "assignee": "alpha"})
tid = t["id"]
r("PATCH", f"/tasks/{tid}", {"status": "in_progress"})
r("PATCH", f"/tasks/{tid}", {"status": "completed"})
s, x = r("PATCH", f"/tasks/{tid}", {"status": "revision_needed"})
print("F832", "CONFIRMED" if s == 200 and x.get("status") == "revision_needed" else "REOPENED")
s, al = r("GET", f"/tasks/transitions/allowed?status=completed")

print("--- F798")
base = pathlib.Path("C:/Users/huida/Documents/aw-r-1021-vault"); (base / "locked").mkdir(parents=True, exist_ok=True)
(base / "ok.md").write_text("# ok\nsome text about widgets\n"); (base / "locked" / "x.md").write_text("# x\n")
subprocess.run(["icacls", str(base / "locked"), "/deny", "Everyone:(RD)"], capture_output=True)
s, x = r("POST", "/vault/paths", {"paths": [str(base)], "distil": False})
subprocess.run(["icacls", str(base / "locked"), "/remove:d", "Everyone"], capture_output=True)
print("F798", "CONFIRMED" if s == 200 and "Access is denied" in json.dumps(x) else "REOPENED?")
