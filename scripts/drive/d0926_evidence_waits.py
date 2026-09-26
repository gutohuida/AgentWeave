"""Drive evidence-is-decided-after-the-run-that-recorded-it (F358, F426) against a live Hub.

3.1: a Haiku builder records evidence then keeps its turn open (sleep); the operator decides
mid-turn -> 409 recording_run_live (body verbatim); after the run ends, decide -> 200.
3.2 (D7): a second Haiku agent granted acceptance is told to decide a second row while the
builder still runs -> refused 409; after the run ends it is woken with the `evidence` note.
Needs AW_HUB, AW_KEY. Everything goes through operator routes and real agent turns.
"""
import os, pathlib, sqlite3, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"evwait-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("evidence wait drive\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "a@example.invalid"],
            ["git", "config", "user.name", "a"], ["git", "add", "README.md"], ["git", "commit", "-m", "x"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"evwait-{TAG}"})
PID = proj["id"]; A = f"/projects/{PID}"; S = f"{A}/project"
print("project", PID)
c, runner = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
for n in ("builder", "tester"):
    api("POST", f"{A}/agents", {"name": n, "runner_id": runner["id"]})
show("grant", *api("PATCH", f"{A}/agents/tester", {"can_accept_evidence": True}))

c, doc = api("POST", f"{S}/documents", {"title": "evidence wait"}); path = doc["path"]
payload = {
    "schema_version": 1, "kind": doc["kind"], "title": "evidence wait",
    "summary": "Two requirements so each drive leg has its own evidence row.",
    "problem": "Drive fixture for the evidence-waits-for-its-run change.",
    "scope": {"in_scope": ["README"], "non_goals": ["Anything else"]},
    "requirements": [{"key": f"r{i}", "statement": f"The README MUST mention item {i}.", "modal": "MUST"} for i in (1, 2)],
    "acceptance_criteria": [{"key": f"c{i}", "requirement": f"r{i}", "given": "the README", "when": "read", "then": f"it mentions item {i}"} for i in (1, 2)],
    "tasks": [{"key": f"t{i}", "title": f"Check item {i}", "description": f"Record evidence for item {i}.", "requirements": [f"r{i}"]} for i in (1, 2)],
    "algorithms": [], "design": "", "evidence": {"checked": [], "limits": []}, "lifecycle": "one-off", "open_questions": [],
}
show("write", *api("PUT", f"{S}/documents/{path}/content", {"document": payload}))
api("POST", f"{S}/documents/close-exploration?path={path}")
api("POST", f"{S}/documents/propose?path={path}")
c, res = api("POST", f"{S}/documents/phase?path={path}&to=approved", {"reason": "drive"})
show("approve", c, res)
tasks = res["tasks_created"]
for t in tasks:
    api("PATCH", f"{A}/tasks/{t}", {"assignee": "builder", "status": "in_progress"})


def evidence():
    c, b = api("GET", f"{S}/spec/evidence")
    return b if isinstance(b, list) else b.get("evidence") or b.get("items") or []


def wait_for(pred, secs, what):
    end = time.time() + secs
    while time.time() < end:
        r = pred()
        if r:
            return r
        time.sleep(3)
    print("TIMEOUT waiting for", what); return None


def leg(i, idx):
    ident = f"FR-{i}"
    msg = (f"Use the record_evidence tool once with identifier {ident}, task_id {tasks[idx]}, summary 'README checked', "
           "kind manual_observation. Then run the shell command: for i in 1 2 3 4 5 6 7 8 9 10 11 12; do sleep 10; done, as ONE Bash call with timeout 150000 ms. Do not shorten it. Then say done.")
    show(f"trigger builder ({ident})", *api("POST", f"{A}/agent/trigger", {"agent": "builder", "message": msg}, timeout=90))
    row = wait_for(lambda: next((e for e in evidence() if e.get("task_id") == tasks[idx]), None), 120, f"{ident} evidence")
    return row


DB = "file:" + os.environ["AW_DB"].replace("\\", "/") + "?mode=ro"


def runs():
    con = sqlite3.connect(DB, uri=True); r = con.execute("select id, agent, status, started_at, ended_at from runs where project_id=? order by started_at", (PID,)).fetchall(); con.close(); return r


def ended():
    return all(st not in ("running", "starting", "queued") for _, ag, st, _, _ in runs() if ag == "builder")


# ---- 3.2
row2 = leg(1, 0)
if not row2:
    sys.exit(1)
print("row2", row2["id"])
msg = f"Decide evidence {row2['id']}: use list_evidence then decide_evidence accepted with a reason. Report exactly what the tool returned."
show("trigger tester", *api("POST", f"{A}/agent/trigger", {"agent": "tester", "message": msg}, timeout=90))
time.sleep(20)
print("runs", runs())
wait_for(ended, 200, "builder run end 2")
time.sleep(60)
print("runs after", runs())
for e in evidence():
    print("evidence", e.get("identifier"), e.get("review_state"), e.get("decided_by") or "")
print("PID", PID)
con = sqlite3.connect(DB, uri=True)
for r in con.execute("select agent,origin_type,state,conversation_id,content,arrived_at from inbound_queue_entries where project_id=? order by arrived_at", (PID,)):
    print("QUEUE", r)
for r in con.execute("select decision,actor,created_at from evidence_reviews"):
    print("REVIEW", r)
