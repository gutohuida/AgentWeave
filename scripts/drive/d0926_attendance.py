"""Drive a-task-is-attended-only-by-a-turn-that-will-reach-it against a live Hub (F368, F370).

Everything the operator can do goes through the API (project, runner, agents, flow, task, Run
presses, withdraw). Three things no operator can do are written straight into the drive profile's
SQLite file, and are labelled so: a provider hold (a TurnUsage row), and queue entries in the
states a real refusal leaves (a peer's entry sorted first; an entry with delivery_attempts=1 and
a waiting_reason). Needs AW_HUB, AW_KEY, AW_DB.
"""
import json, os, pathlib, sqlite3, subprocess, sys, time, uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

DB = os.environ["AW_DB"]
TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"attend-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("attendance drive\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "a@example.invalid"],
            ["git", "config", "user.name", "a"], ["git", "add", "README.md"], ["git", "commit", "-m", "x"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"attend-{TAG}"})
PID = proj["id"]; A = f"/projects/{PID}"
c, runner = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
for n in ("dev", "dev2", "aaa-peer"):
    api("POST", f"{A}/agents", {"name": n, "runner_id": runner["id"]})


def flow(label, agent):
    c, job = api("POST", f"{A}/jobs", {"name": label, "agent": agent, "message": "work the queue",
                                        "cron": "0 3 * * *", "session_mode": "new", "purpose": label})
    if c != 201:
        show("job", c, job); sys.exit(1)
    lid = job["loop"]["id"] if job.get("loop") else None
    c, t = api("POST", f"{A}/tasks", {"title": f"work {label}", "loop_id": lid, "assignee": agent})
    if c not in (200, 201):
        show("task", c, t); sys.exit(1)
    return job["id"], lid, t["id"]


def NOW():
    return datetime.now(timezone.utc).isoformat(sep=" ")


def sql(q, args=()):
    con = sqlite3.connect(DB, timeout=30); con.execute("PRAGMA foreign_keys=ON")
    con.execute(q, args); con.commit(); con.close()


def count(agent):
    con = sqlite3.connect(DB); n = con.execute(
        "select count(*) from inbound_queue_entries where project_id=? and agent=? and origin_type='job' and state='queued'",
        (PID, agent)).fetchone()[0]; con.close(); return n


def conv(agent):
    cid = f"conv-{uuid.uuid4().hex[:8]}"
    sql("insert into conversations (id, project_id, agent, lifecycle, title_set_by_operator, origin, created_at, updated_at) values (?,?,?,'open',0,'operator',?,?)", (cid, PID, agent, NOW(), NOW()))
    return cid


def entry(agent, task_id, origin="job", attempts=0, reason=None):
    sql("insert into inbound_queue_entries (id, project_id, agent, origin_type, origin_agent, content, hop_depth, state,"
        " conversation_id, task_id, delivery_attempts, waiting_reason, arrived_at) values (?,?,?,?,?,?,0,'queued',?,?,?,?,?)",
        (f"iq-{uuid.uuid4().hex[:10]}", PID, agent, origin, "aaa-peer" if origin == "agent" else None, "work",
         conv(agent), task_id, attempts, reason, datetime.now(timezone.utc).isoformat(sep=" ")))


def press(job, n=3):
    for i in range(n):
        c, b = api("POST", f"{A}/jobs/{job}/run")
        print(f"   press {i+1}: {c} {json.dumps(b)[:330]}")
        time.sleep(1.5)


print("=== A. F370: held assignee, peer entry queued first, then dev's own briefing")
job, lid, task = flow("f370", "dev")
epoch = (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
allowance = {"status": "rejected", "resetsAt": epoch, "rateLimitType": "five_hour", "overageStatus": "rejected",
             "overageDisabledReason": "out_of_credits", "isUsingOverage": False,
             "unifiedWindows": {"five_hour": {"utilization": 1.02, "resetsAt": epoch}}}
rid = f"run-{uuid.uuid4().hex[:10]}"
sql("insert into runs (id, project_id, agent, status, started_at) values (?,?,?,'failed',?)", (rid, PID, "dev", datetime.now(timezone.utc).isoformat(sep=" ")))
sql("insert into turn_usage (id, run_id, project_id, agent, status, allowance, observed_at) values (?,?,?,?,'unavailable',?,?)",
    (f"u-{uuid.uuid4().hex[:8]}", rid, PID, "dev", json.dumps(allowance),
     (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(sep=" ")))
c, t = api("PATCH", f"{A}/tasks/{task}", {"status": "assigned"}); print("   task ->", c, (t.get("status") if isinstance(t, dict) else t))
entry("aaa-peer", task, origin="agent")
entry("dev", task)
print("   dev job entries before:", count("dev"))
press(job)
print("   dev job entries after:", count("dev"), " (F370 before the change: 4)")

print("=== B. F368-refused: idle dev, its briefing refused at delivery")
job2, lid2, task2 = flow("f368", "dev2")
c, t = api("PATCH", f"{A}/tasks/{task2}", {"status": "assigned"})
print("   note: dev is also held from A; drops the hold to isolate B")
sql("delete from turn_usage where project_id=?", (PID,))
reason = f"Could not prepare the checkout for task {task2}: drive-made refusal"
entry("dev2", task2, attempts=1, reason=reason)
print("   dev job entries before:", count("dev2"))
press(job2)
print("   dev job entries after:", count("dev2"))
c, hist = api("GET", f"{A}/jobs/{job2}/history"); show("history", c, hist, 900)
c, st = api("GET", f"{A}/queue/dev2/status"); show("queue status dev2", c, st, 700)
c, jb = api("GET", f"{A}/jobs/{job2}"); show("job", c, jb, 900)
print("=== C. withdraw the refused entry, press once")
con = sqlite3.connect(DB); eid = con.execute("select id from inbound_queue_entries where agent='dev2' and project_id=?", (PID,)).fetchone()[0]; con.close()
print("   DELETE", api("DELETE", f"{A}/queue/entries/{eid}")[0])
press(job2, 1)
print("   dev2 job entries after withdraw+press:", count("dev2"), "(expected 1, the new briefing)")
print(f"AW_PROJECT={PID} JOB2={job2} TASK2={task2}")

print("=== cleanup: no job left enabled")
c, projs = api("GET", "/projects")
for p in projs:
    c, jobs = api("GET", f"/projects/{p['id']}/jobs")
    for j in jobs if isinstance(jobs, list) else []:
        if j.get("enabled"):
            print("   disable", j["id"], api("PATCH", f"/projects/{p['id']}/jobs/{j['id']}", {"enabled": False})[0])
