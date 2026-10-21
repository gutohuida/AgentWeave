"""F767 acceptance drive (scratch Hub :8154, profile f767): a flow that names `rev` as its reviewer
and has two independent ready tasks, builder and rev both free, starts ONE build, on builder.

    AW_E2E_STATE=~/.agentweave/e2e-f767.json py -3.11 scripts/drive/s1021_f767_drive.py <project-id>
"""

import os
import pathlib
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f767.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

P = sys.argv[1]
BASE = f"/projects/{P}/project"
doc = f"spec/changes/f767-{time.strftime('%H%M%S')}/spec.json"
reqs = [{"key": k, "statement": f"It MUST do {k}.", "modal": "MUST"} for k in ("alpha", "beta")]
e2e.request("POST", f"{BASE}/documents", {"path": doc, "title": "F767"})
st, out = e2e.request("PUT", f"{BASE}/documents/{doc}/content", {"document": {
    "schema_version": 1, "kind": "change-spec", "title": "F767",
    "scope": {"in_scope": ["notes/"], "non_goals": ["sync"]}, "requirements": reqs,
    "acceptance_criteria": [{"key": f"c-{q['key']}", "requirement": q["key"], "given": "g", "when": "w",
                             "then": "t"} for q in reqs],
    "tasks": [{"key": f"t-{q['key']}", "title": f"Write notes/{q['key']}.txt",
               "description": f"Create notes/{q['key']}.txt holding one line, then commit.",
               "requirements": [q["key"]], "files": [f"notes/{q['key']}.txt"]} for q in reqs],
    "delivery": {"mode": "flow", "agent": "builder", "reviewer": "rev", "tester": False,
                 "stop_when_queue_empties": True, "cron": "0 0 1 1 *"}}})
print("write", st)
q = doc.replace("/", "%2F")
for step in ("close-exploration", "propose"):
    print(step, e2e.request("POST", f"{BASE}/documents/{step}?path={q}")[0])
print("approve", e2e.request("POST", f"{BASE}/documents/phase?path={q}&to=approved",
                             {"reason": "f767", "approve_anyway": True})[0])
time.sleep(4)
st, jobs = e2e.request("GET", f"/projects/{P}/jobs")
job = jobs[0]["id"]
print("fire", e2e.request("POST", f"/projects/{P}/jobs/{job}/run")[0])
time.sleep(10)
rows = e2e.ro().execute(
    "select t.spec_task_key, t.assignee, r.agent as run_agent from tasks t "
    "left join runs r on r.task_id = t.id where t.project_id=?", (P,)).fetchall()
agents = sorted({r["run_agent"] or r["assignee"] for r in rows if (r["run_agent"] or r["assignee"])})
for r in rows:
    print(" ", dict(r))
ok = agents == ["builder"]
print(("HELD " if ok else "ODD  ") + "one build, on builder; rev not handed fresh work:", agents)
sys.exit(0 if ok else 1)
