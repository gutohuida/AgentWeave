"""night-recheck: F767 (reviewer is not the job's agent; two ready tasks, alpha + beta free, beta
named reviewer -> only alpha builds) and F773 (the completed flow task's checks run before its
review).  AW_P=<project> py -3.11 scripts/drive/s1021_r_flow.py  (scratch Hub :8160)"""
import os, pathlib, sys, time, json
os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-r1021.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402
P = os.environ["AW_P"]; BASE = f"/projects/{P}/project"
st, cur = e2e.request("GET", f"{BASE}/settings")
cur["checks"] = [{"name": "ok", "command": "py -3.11 -c \"print('checks ran')\"", "timeout_seconds": 60}]
print("settings", e2e.request("PUT", f"{BASE}/settings", cur)[0])
doc = f"spec/changes/r1021-{time.strftime('%H%M%S')}/spec.json"
reqs = [{"key": k, "statement": f"It MUST do {k}.", "modal": "MUST"} for k in ("one", "two")]
e2e.request("POST", f"{BASE}/documents", {"path": doc, "title": "R1021"})
st, out = e2e.request("PUT", f"{BASE}/documents/{doc}/content", {"document": {
    "schema_version": 1, "kind": "change-spec", "title": "R1021",
    "scope": {"in_scope": ["notes/"], "non_goals": ["sync"]}, "requirements": reqs,
    "acceptance_criteria": [{"key": f"c-{q['key']}", "requirement": q["key"], "given": "g", "when": "w", "then": "t"} for q in reqs],
    "tasks": [{"key": f"t-{q['key']}", "title": f"Write notes/{q['key']}.txt",
               "description": f"Create notes/{q['key']}.txt holding one line, then commit it, then mark the task completed.",
               "requirements": [q["key"]], "files": [f"notes/{q['key']}.txt"]} for q in reqs],
    "delivery": {"mode": "flow", "agent": "alpha", "reviewer": "beta", "tester": False,
                 "stop_when_queue_empties": True, "cron": "0 0 1 1 *"}}})
print("write", st)
q = doc.replace("/", "%2F")
for step in ("close-exploration", "propose"):
    print(step, e2e.request("POST", f"{BASE}/documents/{step}?path={q}")[0])
print("approve", e2e.request("POST", f"{BASE}/documents/phase?path={q}&to=approved", {"reason": "r", "approve_anyway": True})[0])
time.sleep(4)
st, jobs = e2e.request("GET", f"/projects/{P}/jobs")
job = [j for j in jobs if not j.get("archived")][0]["id"] if isinstance(jobs, list) else None
print("job", job, "fire", e2e.request("POST", f"/projects/{P}/jobs/{job}/run")[0])
time.sleep(12)
c = e2e.ro()
rows = c.execute("select r.id, r.agent, r.status, t.spec_task_key from runs r left join tasks t on t.id=r.task_id where r.project_id=? and t.spec_task_key is not null order by r.started_at", (P,)).fetchall()
for r in rows: print(" ", dict(r))
agents = sorted({r["agent"] for r in rows})
print("F767", "CONFIRMED" if agents == ["alpha"] and len(rows) == 1 else "ODD", agents)
print("DOC", doc, "JOB", job)
