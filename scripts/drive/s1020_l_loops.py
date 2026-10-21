"""2026-10-20 loops sweep (scratch Hub :8160): a documentless loop that fires, claims, drains, stops.

    AW_P=proj-... py -3.11 scripts/drive/s1020_l_loops.py <step> [args]
"""

import json
import sys
import time

from s1020_l_lib import P, q, req, show

B = f"/projects/{P}"
FAR = "0 0 1 1 *"


def wait_runs(since_ids, timeout=420):
    end = time.time() + timeout
    while time.time() < end:
        rows = q("select id, agent, status, task_id from runs where project_id=? order by started_at", P)
        new = [r for r in rows if r["id"] not in since_ids]
        if new and all(r["status"] not in ("running", "starting", "queued") for r in new):
            return new
        time.sleep(5)
    return [r for r in q("select id, agent, status, task_id from runs where project_id=?", P) if r["id"] not in since_ids]


def run_ids():
    return {r["id"] for r in q("select id from runs where project_id=?", P)}


def loop_view(lid):
    st, lp = req("GET", f"{B}/loops/{lid}")
    keep = ("state", "queue", "stop_reason", "stopped_at", "ending_state", "stall_reason", "control", "fired_count", "run_count")
    print("LOOP", st, json.dumps({k: lp.get(k) for k in keep if k in lp}, ensure_ascii=False)[:1500])
    return lp


def tasks():
    st, res = req("GET", f"{B}/tasks?limit=50")
    for t in res["tasks"]:
        print("  TASK", t["id"], t["title"][:40], t["status"], t.get("assignee"))
    return res["tasks"]


def a1():
    body = {
        "name": "loop A", "agent": "alpha", "cron": FAR, "enabled": True,
        "message": "Work the next task on your loop's queue, then complete it.",
        "purpose": "two tiny files", "stop_when_queue_empties": True,
        "initial_tasks": [
            {"title": "Write ONE.txt", "description": "Create ONE.txt containing the single word ONE, commit it, then move this task to completed."},
            {"title": "Write TWO.txt", "description": "Create TWO.txt containing the single word TWO, commit it, then move this task to completed."},
        ],
    }
    st, j = show("POST", f"{B}/jobs", body, limit=2500)
    jid, lid = j["id"], j["loop"]["id"]
    print(json.dumps({"job": jid, "loop": lid}))
    before = run_ids()
    show("POST", f"{B}/jobs/{jid}/run")
    time.sleep(2)
    show("POST", f"{B}/jobs/{jid}/run")  # second press while the first is in flight
    new = wait_runs(before)
    print("NEW RUNS", new)
    tasks()
    loop_view(lid)


def fire(jid, lid):
    before = run_ids()
    st, res = show("POST", f"{B}/jobs/{jid}/run")
    if st < 300:
        print("NEW RUNS", wait_runs(before))
    tasks()
    loop_view(lid)


def approve(tid):
    show("PATCH", f"{B}/tasks/{tid}", {"status": "under_review"}, limit=400)
    show("PATCH", f"{B}/tasks/{tid}", {"status": "approved"}, limit=800)



def mk(name, agent, tasks_, **kw):
    body = {"name": name, "agent": agent, "cron": FAR, "enabled": True,
            "message": "Work the next task on your loop's queue, then complete it.",
            "purpose": name, "stop_when_queue_empties": True,
            "initial_tasks": [{"title": t, "description": f"Create {t.split()[-1]} containing OK, commit it, then complete this task."} for t in tasks_]}
    body.update(kw)
    st, j = req("POST", f"{B}/jobs", body)
    print("CREATE", name, st, j.get("id") if st < 300 else j)
    return j


def stopat():
    """Second ending: a stop time that passes, reached by the scheduler's own tick."""
    from datetime import datetime, timedelta, timezone
    when = (datetime.now(timezone.utc) + timedelta(seconds=8)).isoformat()
    j = mk("loop B stop_at", "beta", ["Write B.txt"], cron="* * * * *", stop_at=when, stop_when_queue_empties=False)
    lid = j["loop"]["id"]
    before = run_ids()
    for _ in range(16):
        time.sleep(5)
        lp = req("GET", f"{B}/loops/{lid}")[1]
        if lp.get("ending_state"):
            break
    loop_view(lid)
    print("NEW RUNS (want none)", [r for r in q("select id, agent, status from runs where project_id=?", P) if r["id"] not in before])
    show("GET", f"{B}/jobs/{j['id']}/history", limit=1200)
    show("POST", f"{B}/jobs/{j['id']}/run", limit=600)
    show("PATCH", f"{B}/jobs/{j['id']}", {"enabled": True}, limit=600)


def runnerless():
    show("PATCH", f"{B}/agents/gamma", {"runner_id": None}, limit=300)
    j = mk("loop C runnerless", "gamma", ["Write C.txt"])
    st, res = show("POST", f"{B}/jobs/{j['id']}/run", limit=1200)
    show("GET", f"{B}/queue/gamma/status", limit=1200)
    show("GET", f"{B}/jobs/{j['id']}/history", limit=1200)
    loop_view(j["loop"]["id"])
    print(json.dumps({"jobC": j["id"], "loopC": j["loop"]["id"]}))


def rebind(jid, lid, rid):
    before = run_ids()
    show("PATCH", f"{B}/agents/gamma", {"runner_id": rid}, limit=300)
    print("NEW RUNS", wait_runs(before, 300))
    show("GET", f"{B}/jobs/{jid}/history", limit=1500)
    loop_view(lid)



def budget():
    """A loop firing on a spent token budget."""
    show("PATCH", f"{B}/accounting/budget", {"token_budget": 1000}, limit=500)
    j = mk("loop D budget", "alpha", ["Write D.txt"])
    before = run_ids()
    show("POST", f"{B}/jobs/{j['id']}/run", limit=1200)
    time.sleep(8)
    print("NEW RUNS (want none)", [r for r in q("select id, status from runs where project_id=?", P) if r["id"] not in before])
    show("GET", f"{B}/queue/alpha/status", limit=800)
    show("GET", f"{B}/jobs/{j['id']}/history", limit=900)
    show("POST", f"{B}/jobs/{j['id']}/run", limit=1200)  # second press while held
    loop_view(j["loop"]["id"])
    print(json.dumps({"jobD": j["id"], "loopD": j["loop"]["id"]}))


def unbudget(jid, lid):
    before = run_ids()
    show("PATCH", f"{B}/accounting/budget", {"token_budget": None}, limit=300)
    print("NEW RUNS", wait_runs(before, 300))
    show("GET", f"{B}/jobs/{jid}/history", limit=900)
    loop_view(lid)


def codex():
    """Failure injection: a firing whose agent's CLI cannot start (Codex is undrivable here)."""
    st, r = req("POST", f"{B}/runners", {"name": "codex", "cli": "codex"})
    print("codex runner", st, r.get("id") if st < 300 else r)
    show("POST", f"{B}/agents", {"name": "delta", "runner_id": r["id"]}, limit=200)
    j = mk("loop E codex", "delta", ["Write E.txt"])
    before = run_ids()
    show("POST", f"{B}/jobs/{j['id']}/run", limit=1200)
    print("NEW RUNS", wait_runs(before, 200))
    show("GET", f"{B}/jobs/{j['id']}/history", limit=1200)
    loop_view(j["loop"]["id"])
    tasks()
    show("GET", f"{B}/queue/delta/status", limit=800)
    print(json.dumps({"jobE": j["id"], "loopE": j["loop"]["id"]}))


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
