"""night-recheck F759 (scratch Hub :8160): overturn accepted evidence that has an open drift
candidate -> coverage reads rejected (not drifting), approval gate 409 gate_unsatisfied.
AW_P=<project> AW_DIR=<project dir> py -3.11 scripts/drive/s1021_r_f759.py"""
import json, os, pathlib, subprocess, sys, time
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-r1021.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
P = os.environ["AW_P"]; D = pathlib.Path(os.environ["AW_DIR"]); BASE = f"/projects/{P}/project"
def r(m, p, b=None):
    s, x = e2e.request(m, p, b); print(m, p.split("?")[0][-50:], "->", s, json.dumps(x)[:260]); return s, x
def git(*a): return subprocess.run(["git", "-C", str(D), "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True).stdout.strip()
(D / "todo").mkdir(exist_ok=True); (D / "todo/other.py").write_text("X = 1\n"); git("add", "todo"); git("commit", "-qm", "other")
sha = git("rev-parse", "HEAD")
DOC = f"spec/changes/r759-{time.strftime('%H%M%S')}/spec.json"
r("POST", f"{BASE}/documents", {"path": DOC, "title": "R759"})
s, out = r("PUT", f"{BASE}/documents/{DOC}/content", {"document": {
    "schema_version": 1, "kind": "change-spec", "title": "R759", "scope": {"in_scope": ["x"], "non_goals": ["y"]},
    "requirements": [{"key": "gamma", "statement": "It MUST hold X.", "modal": "MUST"}],
    "acceptance_criteria": [{"key": "c-g", "requirement": "gamma", "given": "g", "when": "w", "then": "t"}],
    "delivery": {"mode": "none"},
    "tasks": [{"key": "t-g", "title": "Build gamma", "description": "Do.", "requirements": ["gamma"]}]}})
ident = (out.get("identifiers") or {}).get("gamma", "FR-1")
s, ev = r("POST", f"{BASE}/spec/evidence", {"identifier": ident, "document": DOC, "summary": "holds X", "locator": "todo/other.py", "commit": sha, "covers": "full"})
(D / "todo/other.py").write_text("X = 2\n"); git("add", "todo"); git("commit", "-qm", "change")
s, det = r("POST", f"{BASE}/spec/drift/detect")
s, cov = r("GET", f"{BASE}/spec/coverage?document={DOC}"); print("before overturn:", [e["state"] for e in cov["requirements"]])
s, ov = r("POST", f"{BASE}/spec/evidence/{ev['id']}/overturn", {"reason": "it does not hold X"})
s, cov = r("GET", f"{BASE}/spec/coverage?document={DOC}"); states = [e["state"] for e in cov["requirements"]]; print("after overturn:", states)
s, dr = e2e.request("GET", f"{BASE}/spec/drift?document={DOC}"); print("drift rows:", [(d.get("status")) for d in (dr if isinstance(dr, list) else dr.get("drift", dr.get("items", [])))])
for step in ("close-exploration", "propose"): e2e.request("POST", f"{BASE}/documents/{step}?path={DOC.replace('/', '%2F')}")
e2e.request("POST", f"{BASE}/documents/phase?path={DOC.replace('/', '%2F')}&to=approved", {"reason": "r", "approve_anyway": True})
s, tasks = e2e.request("GET", f"/projects/{P}/tasks"); t = [x for x in tasks["tasks"] if x["title"] == "Build gamma"][0]
for st_ in ("in_progress", "completed", "under_review"): e2e.request("PATCH", f"/projects/{P}/tasks/{t['id']}", {"status": st_})
s, ap = r("PATCH", f"/projects/{P}/tasks/{t['id']}", {"status": "approved"})
print("F759", "CONFIRMED" if states == ["rejected"] and s == 409 and "gate_unsatisfied" in json.dumps(ap) else "REOPENED", states, s)
