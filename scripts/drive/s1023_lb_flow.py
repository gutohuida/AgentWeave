"""2026-10-23 Flows & review drive (scratch Hub :8112): fire the flow, watch both build tasks run in
parallel, the tester's review turns, the waiting-review withdrawal on a verdict.

    AW_P=proj-... py -3.11 scripts/drive/s1023_lb_flow.py status|fire|watch [secs]|queue <agent>|story <task>|events [types]
"""

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from s1023_lb_lib import B, P, q, req, show  # noqa: E402

JOB = "job-ac7715fe2b79"
AGENTS = ("alpha", "beta", "tester")


def status():
    for r in q("select id, agent, status, task_id, conversation_id, substr(started_at,12,8) s, substr(ended_at,12,8) e from runs where project_id=? order by started_at", P):
        print("  RUN", r)
    for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        print("  TASK", t["id"], t["title"][:34], t["status"], t.get("assignee"), t.get("loop_id"))
    for a in AGENTS:
        es = req("GET", f"{B}/queue/{a}")[1]
        for e in es if isinstance(es, list) else []:
            if e["state"] in ("queued", "withdrawn", "abandoned"):
                print("  QUEUE", a, e["id"], e["state"], e["origin_type"], e.get("review_task_id"),
                      e.get("waiting_reason"), e.get("abandoned_reason"))
    st, jobs = req("GET", f"{B}/jobs?include_archived=true")
    for j in jobs:
        lp = j.get("loop") or {}
        print("  JOB", j["id"], j["enabled"], j.get("archived"), lp.get("id"), lp.get("stop_reason"),
              lp.get("ending_state"), lp.get("stall_reason"))


def fire():
    show("POST", f"{B}/jobs/{JOB}/run", limit=2500)
    time.sleep(8)
    status()


def watch(secs="420"):
    end = time.time() + int(secs)
    while time.time() < end:
        live = q("select count(*) n from runs where project_id=? and status in ('running','starting','queued')", P)[0]["n"]
        if not live:
            break
        time.sleep(10)
    status()


def queue(agent):
    show("GET", f"{B}/queue/{agent}", limit=8000)


def story(tid):
    show("GET", f"{B}/tasks/{tid}/story", limit=12000)


def events(types=""):
    want = [t for t in types.split(",") if t]
    for e in q("select event_type, agent, substr(timestamp,12,8) t, data from event_logs where project_id=? order by timestamp", P):
        if not want or e["event_type"] in want:
            print(" ", e["t"], e["event_type"], e["agent"], (e["data"] or "")[:600])


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
