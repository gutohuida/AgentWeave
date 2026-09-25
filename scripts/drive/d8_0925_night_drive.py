"""0925 night drive: pressing Run on a loop -> flow-move origin, job_run_id, Run reasons. Haiku only."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
from aw import api, P
if ":8000" in os.environ.get("AW_HUB", "") or ":8010" in os.environ.get("AW_HUB", ""):
    sys.exit("refusing")
A = f"/projects/{P}"
c, job = api("POST", f"{A}/jobs", {"name": "drive loop", "agent": "author", "message": "Reply with the single word ok and stop. Do not use tools.",
    "cron": "0 0 1 1 *", "enabled": True, "purpose": "drive", "stop_when_queue_empties": True,
    "initial_tasks": [{"title": "drive task one", "description": "say ok"}]})
print("create job", c, str(job)[:300])
jid = job["id"]
c, r = api("POST", f"{A}/jobs/{jid}/run"); print("run#1", c, str(r)[:400])
c, r2 = api("POST", f"{A}/jobs/{jid}/run"); print("run#2 immediately", c, str(r2)[:400])
for _ in range(40):
    time.sleep(3)
    c, h = api("GET", f"{A}/jobs/{jid}/history")
    print("history", [(x.get("status"), x.get("id")) for x in h][:3]) if c == 200 else print(c, h)
    if h and h[0].get("status") not in ("running", "pending", None): break
c, tasks = api("GET", f"{A}/tasks")
for t in (tasks if isinstance(tasks, list) else tasks.get("tasks", [])):
    c, tr = api("GET", f"{A}/tasks/{t['id']}/transitions")
    print(t["id"], t["status"])
    for x in tr: print("  ", x["from_status"], "->", x["to_status"], x["actor_kind"], x.get("origin"), x.get("job_id"), x.get("job_name"), x.get("job_kind"))
