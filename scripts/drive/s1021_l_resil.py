"""2026-10-21 resilience sweep (scratch Hub :8159): Land while .git is unreadable (F820 live), a
route battery with the project folder gone, and the Hub killed during a loop firing (F123/F147).

    AW_P=proj-... py -3.11 scripts/drive/s1021_l_resil.py <step> [args]
"""

import json
import pathlib
import subprocess
import sys
import time

from s1021_l_lib import P, e2e, q, req, show

B = f"/projects/{P}"
DIR = pathlib.Path.home() / "Documents" / "aw-l-1021"
SLEEP = 'py -3.11 -c "import time\nfor i in range(150): time.sleep(1)"'


def integrations(tid):
    st, rows = req("GET", f"{B}/tasks/{tid}/integrations")
    for r in rows if isinstance(rows, list) else rows.get("integrations", [rows]):
        print("  INTEGRATION", json.dumps(r, ensure_ascii=False)[:420])


def accept(tid):
    st, ev = req("GET", f"{B}/project/spec/evidence")
    items = ev if isinstance(ev, list) else ev.get("evidence") or ev.get("items") or []
    for e in items:
        if e.get("task_id") == tid and e.get("decision", e.get("status")) in (None, "awaiting"):
            show("POST", f"{B}/project/spec/evidence/{e['id']}/decision", {"decision": "accepted"}, limit=300)


def land_nogit(tid):
    accept(tid)
    show("GET", f"{B}/tasks/{tid}/integration-preview", limit=800)
    (DIR / ".git").rename(DIR / ".git_aside")
    try:
        show("POST", f"{B}/tasks/{tid}/land", {}, limit=1500)
    finally:
        (DIR / ".git_aside").rename(DIR / ".git")
        print("restored .git")
    show("GET", f"{B}/tasks/{tid}", limit=300)
    integrations(tid)


def nodir(tid, jid):
    """The whole project folder gone (moved aside) while the Hub runs: what each route returns."""
    aside = DIR.with_name(DIR.name + "_aside")
    DIR.rename(aside)
    try:
        for meth, path, body in (
            ("GET", f"{B}/loops", None),
            ("GET", f"{B}/jobs", None),
            ("POST", f"{B}/jobs/{jid}/run", {}),
            ("GET", f"{B}/tasks/{tid}/story", None),
            ("GET", f"{B}/tasks/{tid}/integration-preview", None),
            ("POST", f"{B}/tasks/{tid}/integrations/retry", {}),
            ("POST", f"{B}/tasks/{tid}/checks/run", {}),
            ("GET", f"{B}/project/documents", None),
            ("POST", f"{B}/agent/trigger", {"agent": "beta", "message": "Reply ok, no tools."}),
        ):
            st, r = req(meth, path, body)
            print(f"{meth} {path[len(B):]} -> {st} {json.dumps(r, ensure_ascii=False)[:500]}")
        time.sleep(20)
        print("RUNS", q("select id, agent, status, substr(error,1,300) e from runs where project_id=? order by started_at desc limit 2", P))
    finally:
        aside.rename(DIR)
        print("restored dir")


def hold():
    """A documentless loop for beta whose one task holds a 150 s tool call; fire it."""
    body = {"name": "loop K kill", "agent": "beta", "cron": "0 0 1 1 *", "enabled": True,
            "message": "Work the next task on your loop's queue.", "purpose": "kill drive",
            "stop_when_queue_empties": True,
            "initial_tasks": [{"title": "Wait out the clock", "description": f"Run exactly this shell command and wait for it to finish: {SLEEP} . Then write K.txt holding OK, commit it, and complete this task."}]}
    st, j = show("POST", f"{B}/jobs", body, limit=200)
    st, r = show("POST", f"{B}/jobs/{j['id']}/run", limit=600)
    run = None
    for _ in range(40):
        time.sleep(3)
        rows = q("select id, status from runs where project_id=? and agent='beta' order by started_at desc limit 1", P)
        if rows and rows[0]["status"] == "running":
            run = rows[0]["id"]
            outs = q("select substr(content,1,120) c from agent_outputs where run_id=? order by sequence", run)
            if any("time.sleep" in (o["c"] or "") or "PowerShell" in (o["c"] or "") or "Bash" in (o["c"] or "") for o in outs):
                break
    print("RUN", run, q("select id, status from job_runs where job_id=?", j["id"]))
    print(json.dumps({"job": j["id"], "loop": j["loop"]["id"], "run": run}))


def kill():
    st = json.loads(pathlib.Path(e2e.STATE).read_text())
    print(subprocess.run(["taskkill", "/PID", str(st["pid"]), "/F"], capture_output=True, text=True).stdout)


def after(jid, lid, run):
    print("RUN", q("select id, status, exit_code, substr(error,1,300) e, ended_at from runs where id=?", run))
    print("JOBRUNS", q("select * from job_runs where job_id=?", jid))
    print("LOOP", json.dumps({k: v for k, v in req("GET", f"{B}/loops/{lid}")[1].items() if k in ("queue", "stall_reason", "ending_state", "firing_active")}, ensure_ascii=False))
    for t in req("GET", f"{B}/tasks?limit=50")[1]["tasks"]:
        if t.get("loop_id") == lid:
            print("TASK", t["id"], t["status"], t.get("assignee"))
    for e in req("GET", f"{B}/queue/beta")[1][-3:]:
        print("ENTRY", e["id"], e["state"], e["origin_type"], e.get("delivered_in_run_id"), e.get("abandoned_reason"), e["content"][:60])
    show("GET", f"{B}/jobs/{jid}/history", limit=1500)


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
