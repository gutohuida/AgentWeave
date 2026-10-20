"""2026-10-20 resilience sweep (scratch Hub :8160): kill the Hub with a run in flight, restart,
read what was reconciled; concurrent triggers (F349); unknown routes.

    AW_P=proj-... py -3.11 scripts/drive/s1020_l_resil.py <step>
"""

import json
import sys
import threading
import time

from s1020_l_lib import P, q, req, show

B = f"/projects/{P}"
SLEEP = 'py -3.11 -c "import time\nfor i in range(150): time.sleep(1)"'


def hold():
    st, r = req("POST", f"{B}/agent/trigger", {"agent": "alpha", "message": f"Run exactly this shell command and wait for it to finish, then reply DONE: {SLEEP}", "overrides": {"permission_mode": "workspace"}})
    print("trigger", st, r.get("run_id"), r.get("conversation_id"))
    run = r["run_id"]
    for _ in range(30):
        time.sleep(3)
        outs = q("select kind, substr(content,1,80) c from agent_outputs where run_id=? order by sequence", run)
        if any("sleep" in (o["c"] or "") or "PowerShell" in (o["c"] or "") or "Bash" in (o["c"] or "") for o in outs):
            break
    print("outputs", outs[-3:])
    st, r2 = req("POST", f"{B}/agent/trigger", {"agent": "alpha", "message": "After that, reply with the word QUEUED-OK.", "conversation_id": r.get("conversation_id")})
    print("second", st, {k: r2.get(k) for k in ("status", "run_id", "queued", "message", "entry_id")})
    print(q("select id, status from runs where id=?", run))
    print("QUEUE", [(e["id"], e["state"]) for e in req("GET", f"{B}/queue/alpha")[1] if e["state"] in ("queued", "delivered")][-3:])
    print(json.dumps({"run": run}))


def after(run):
    print("RUN", q("select id, status, exit_code, error, ended_at from runs where id=?", run))
    print("RUNS since", q("select id, status, substr(started_at,12,8) t, error from runs where agent='alpha' and project_id=? order by started_at desc limit 3", P))
    for e in req("GET", f"{B}/queue/alpha")[1][-4:]:
        print("ENTRY", e["id"], e["state"], e["origin_type"], e.get("delivered_in_run_id"), e.get("abandoned_reason"), e["content"][:50])
    st, ev = req("GET", f"{B}/events/history?limit=60")
    for e in ev:
        t = e.get("event_type")
        if t and any(w in t for w in ("reconcil", "orphan", "interrupt", "restart", "run_ended", "run_failed", "returned")):
            print("EVENT", t, json.dumps(e.get("data"), ensure_ascii=False)[:400])


def concurrent():
    out = []

    def fire(i, agent):
        st, r = req("POST", f"{B}/agent/trigger", {"agent": agent, "message": f"Concurrent {i}: reply ok only, no tools.", "overrides": {"permission_mode": "workspace"}})
        out.append((i, agent, st, {k: r.get(k) for k in ("success", "run_id", "waiting_reason", "message", "detail")} if isinstance(r, dict) else r))

    ts = [threading.Thread(target=fire, args=(i, "beta")) for i in range(5)] + [threading.Thread(target=fire, args=(9, "gamma"))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    for r in sorted(out):
        print("TRIGGER", r)


def routes():
    for meth, path, body in (
        ("GET", "/no/such/route", None), ("POST", "/no/such/route", {}), ("GET", f"{B}/no-such", None),
        ("DELETE", f"{B}/loops", None), ("PUT", f"{B}/jobs/job-000000000000/run", None),
        ("POST", f"{B}/jobs/job-000000000000/run", {}), ("GET", f"{B}/loops/loop-000000000000", None),
        ("POST", f"{B}/loops/loop-000000000000/control", {"control": "creator"}),
        ("POST", "/projects/proj-000000000000/jobs", {"name": "x", "agent": "alpha", "message": "m", "cron": "* * * * *"}),
        ("POST", f"{B}/jobs", {"name": "x", "agent": "alpha", "message": "m", "cron": "not a cron"}),
        ("POST", f"{B}/jobs", {"name": "x", "agent": "nobody", "message": "m", "cron": "0 0 1 1 *", "enabled": False}),
        ("POST", f"{B}/jobs", {"name": "x", "agent": "alpha", "message": "m", "cron": "0 0 1 1 *", "enabled": False, "spec_document_id": "spdoc-000000000000"}),
        ("POST", f"{B}/jobs", {"name": "x", "agent": "alpha", "message": "m", "cron": "0 0 1 1 *", "enabled": False, "stop_at": "2001-01-01T00:00:00Z"}),
        ("POST", f"{B}/loops/loop-0cfd531a5286/control", {"control": "bogus"}),
    ):
        st, r = req(meth, path, body)
        print(f"{meth} {path[len(B):] if path.startswith(B) else path} -> {st} {json.dumps(r, ensure_ascii=False)[:300]}")



def nogit():
    """Failure injection: the project's .git is gone (moved aside) while the Hub runs."""
    import pathlib
    d = pathlib.Path.home() / "Documents" / "aw-l-1020"
    (d / ".git").rename(d / ".git_aside")
    try:
        st, j = req("POST", f"{B}/jobs", {"name": "loop F nogit", "agent": "gamma", "cron": "0 0 1 1 *", "enabled": True,
                                          "message": "Work the next task.", "purpose": "nogit", "stop_when_queue_empties": True,
                                          "initial_tasks": [{"title": "Write F.txt", "description": "Create F.txt containing OK and complete this task."}]})
        print("create", st, j.get("id") if st < 300 else j)
        for meth, path, body in (
            ("POST", f"{B}/jobs/{j.get('id')}/run", {}),
            ("POST", f"{B}/tasks/task-8d36435b40ca/land", {}),
            ("GET", f"{B}/tasks/task-8d36435b40ca/story", None),
            ("GET", f"{B}/worktrees", None),
            ("GET", f"{B}/workspace/paths", None),
            ("GET", f"{B}/project/settings", None),
            ("GET", f"{B}/settings", None),
            ("POST", f"{B}/agent/trigger", {"agent": "beta", "message": "Reply ok, no tools."}),
        ):
            st, r = req(meth, path, body)
            print(f"{meth} {path[len(B):]} -> {st} {json.dumps(r, ensure_ascii=False)[:420]}")
        time.sleep(30)
        print("RUNS", q("select id, agent, status, substr(error,1,200) e from runs where project_id=? order by started_at desc limit 3", P))
        print("JOBRUN", q("select id, status, error_summary from job_runs where job_id=?", j.get("id")))
        print(json.dumps({"jobF": j.get("id")}))
    finally:
        (d / ".git_aside").rename(d / ".git")
        print("restored .git")


if __name__ == "__main__":
    globals()[sys.argv[1]](*sys.argv[2:])
