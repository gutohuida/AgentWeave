"""Drive a-task-is-attended-only-by-a-turn-that-will-reach-it against a live Hub (F368, F370).

Everything the operator can do goes through the API (project, runner, agents, flow, task, Run
presses, withdraw). Three things no operator can do are written straight into the drive profile's
SQLite file, and are labelled so: a provider hold (a TurnUsage row), and queue entries in the
states a real refusal leaves (a peer's entry sorted first; an entry with delivery_attempts=1 and
a waiting_reason). Needs AW_HUB, AW_KEY, AW_DB.
"""
import json, os, pathlib, sqlite3, subprocess, sys, time, uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, show  # noqa: E402

DB = os.environ["AW_DB"]
TAG = time.strftime("%H%M%S")
root = pathlib.Path(r"C:\Users\huida\Documents\projects\AgentWeave\testbed\scratch") / f"qtruth2-{TAG}"
root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text("attendance drive\n", encoding="utf-8")
for cmd in (["git", "init", "-b", "main"], ["git", "config", "user.email", "a@example.invalid"],
            ["git", "config", "user.name", "a"], ["git", "add", "README.md"], ["git", "commit", "-m", "x"]):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

c, proj = api("POST", "/projects/open", {"path": str(root), "name": f"qtruth2-{TAG}"})
PID = proj["id"]; A = f"/projects/{PID}"
c, runner = api("POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": "claude-haiku-4-5-20251001"})
for n in ("holder", "chall"):
    api("POST", f"{A}/agents", {"name": n, "runner_id": runner["id"]})


def flow(label, agent):
    c, job = api("POST", f"{A}/jobs", {"name": label, "agent": agent, "message": "Run the shell command: sleep 45, using your Bash tool, before anything else. Then say done.",
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



job, lid, task = flow("hold", "holder")
c, t = api("PATCH", f"{A}/tasks/{task}", {"status": "assigned"}); print("task ->", c)
sentence = f"holder is already running a turn on task {task}; a task's checkout takes one writing turn at a time."
entry("chall", task, attempts=1, reason=sentence)
c, r = api("POST", f"{A}/jobs/{job}/run"); print("press holder:", c, str(r)[:200])
for i in range(12):
    time.sleep(5)
    c, st = api("GET", f"{A}/queue/chall/status")
    c2, ag = api("GET", f"{A}/agents")
    stat = {a["name"]: a.get("status") for a in ag}
    print(f"  t+{5*(i+1)}s holder={stat.get('holder')} reason={st.get('waiting_reason') if isinstance(st, dict) else st}")
    if i >= 3 and stat.get("holder") != "running":
        break
for i in range(20):
    if api("GET", f"{A}/agents")[1] and all(a.get("status") != "running" for a in api("GET", f"{A}/agents")[1]): break
    time.sleep(5)
c, st = api("GET", f"{A}/queue/chall/status"); print("AFTER holder ended:", c, json.dumps(st)[:500])
print(f"AW_PROJECT={PID}")
c, jobs = api("GET", f"{A}/jobs")
for j in jobs:
    if j.get("enabled"): print("disable", j["id"], api("PATCH", f"{A}/jobs/{j['id']}", {"enabled": False})[0])
